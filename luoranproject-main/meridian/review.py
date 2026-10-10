"""Independent risk review of a researcher draft.

The reviewer recomputes every ratio and rejects claims that are not in the
retrieved briefings or the calculator narrative.
"""

from __future__ import annotations

import hashlib
import re

from meridian.calculate import (
    liquidity_coverage_ratio,
    net_stable_funding_ratio,
    scenario_on_book,
)
from meridian.compose import sentence_ok
from meridian.index import RegulatoryIndex

_LCR_CLAIM = re.compile(r"liquidity coverage ratio is (\d+(?:\.\d+)?) percent", re.I)
_NSFR_CLAIM = re.compile(r"net stable funding ratio is (\d+(?:\.\d+)?) percent", re.I)
_CITATION = re.compile(r"\[(\d+)\]")


def review_draft(state: dict, index: RegulatoryIndex) -> dict:
    draft = state.get("draft") or ""
    citations = list(state.get("citations") or [])
    chunks = _support_chunks(state)
    narrative = (state.get("tool_result") or {}).get("narrative") or ""
    instruments = state.get("unsupported") or []
    checks: list[dict] = []

    if state.get("abstain"):
        checks.append(
            _check(
                "Release discipline",
                True,
                "The researcher abstained. No regulatory requirement was attributed without a source.",
            )
        )
        invented = _attributes_requirement(draft, instruments)
        checks.append(
            _check(
                "Instrument authenticity",
                not invented,
                "The draft does not assign a rule to an instrument that is absent from the corpus."
                if not invented
                else "The draft attributes a requirement to an instrument that is not indexed.",
            )
        )
        passed = all(item["passed"] for item in checks)
        verdict = "abstained" if passed else "returned"
        return _packet(state, verdict, checks, draft, citations)

    support_failures = []
    for unit in _units(draft):
        if not sentence_ok(unit, chunks, narrative):
            support_failures.append(unit)
    checks.append(
        _check(
            "Claim support",
            not support_failures,
            "Every statement is in a cited briefing or in the calculator narrative."
            if not support_failures
            else "Unsupported statement: " + support_failures[0][:180],
        )
    )

    missing_markers = []
    for marker in _CITATION.findall(draft):
        number = int(marker)
        if not any(item["n"] == number for item in citations):
            missing_markers.append(number)
    unknown_chunks = [
        item["chunk_id"] for item in citations if item["chunk_id"] not in index.by_id
    ]
    citation_ok = not missing_markers and not unknown_chunks
    checks.append(
        _check(
            "Citation integrity",
            citation_ok,
            "Every citation marker resolves to an indexed briefing."
            if citation_ok
            else "A citation marker does not resolve to the indexed corpus.",
        )
    )

    calc_ok, calc_detail = _recalculate(state)
    checks.append(_check("Independent recalculation", calc_ok, calc_detail))

    invented = _attributes_requirement(draft, instruments)
    checks.append(
        _check(
            "Instrument authenticity",
            not invented,
            "Named instruments in the answer are present in the indexed briefings."
            if not invented
            else "The draft relies on an instrument that is not in the corpus.",
        )
    )

    passed = all(item["passed"] for item in checks)
    if passed:
        verdict = "cleared"
    elif state.get("iteration", 0) >= 1:
        verdict = "abstained"
    else:
        verdict = "returned"
    return _packet(state, verdict, checks, draft, citations)


def _packet(state: dict, verdict: str, checks: list[dict], draft: str, citations: list[dict]) -> dict:
    record = "MR-" + hashlib.sha1(state.get("question", "").encode()).hexdigest()[:4].upper()
    summary = {
        "cleared": "Released. The reviewer found source support and matching arithmetic.",
        "abstained": "Not released as a regulatory answer. Evidence or review checks were insufficient.",
        "returned": "Returned to the researcher for another retrieval pass.",
    }[verdict]
    update = {
        "review": {
            "verdict": verdict,
            "record_id": record,
            "checks": checks,
            "summary": summary,
        }
    }
    if verdict == "abstained" and not state.get("abstain"):
        from meridian.compose import abstain_message

        update["draft"] = abstain_message(state.get("unsupported") or [])
        update["citations"] = []
        update["abstain"] = True
        update["review"]["summary"] = (
            "Not released. A second pass still contained a statement the reviewer could not support."
        )
    return update


def _recalculate(state: dict) -> tuple[bool, str]:
    tool = state.get("tool_result") or {}
    kind = tool.get("tool")
    if kind not in {"lcr", "nsfr", "scenario"}:
        return True, "No ratio was calculated on this question."
    draft = state.get("draft") or ""
    try:
        if kind == "lcr":
            fresh = liquidity_coverage_ratio(**tool["inputs"])
            return _match_lcr(draft, [fresh["lcr_pct"]], "Recalculated LCR")
        if kind == "nsfr":
            fresh = net_stable_funding_ratio(**tool["inputs"])
            claims = [float(value) for value in _NSFR_CLAIM.findall(draft)]
            if fresh["nsfr_pct"] is None:
                return False, "Required stable funding is zero, so the ratio is undefined."
            if any(abs(claim - fresh["nsfr_pct"]) < 0.15 for claim in claims):
                return True, f"Recalculated NSFR is {fresh['nsfr_pct']:.1f} percent and the draft matches."
            return False, f"Recalculated NSFR is {fresh['nsfr_pct']:.1f} percent and the draft does not match."
        fresh_base, fresh_shocked = _fresh_scenario(tool)
        return _match_lcr(
            draft,
            [fresh_base["lcr_pct"], fresh_shocked["lcr_pct"]],
            "Recalculated base and shocked LCR",
        )
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"The calculator inputs could not be recomputed ({exc})."


def _fresh_scenario(tool: dict) -> tuple[dict, dict]:
    if tool.get("mode") == "book":
        fresh = scenario_on_book(tool["inputs"]["book"], tool["inputs"]["target"], tool["inputs"]["shock_pct"])
        return fresh["base"], fresh["shocked"]
    inputs = tool["inputs"]
    base = liquidity_coverage_ratio(inputs["hqla"], inputs["outflows"], inputs["inflows"])
    shocked_out = inputs["outflows"] * (1 + inputs["shock_pct"])
    shocked = liquidity_coverage_ratio(inputs["hqla"], shocked_out, inputs["inflows"])
    return base, shocked


def _match_lcr(draft: str, expected: list[float | None], label: str) -> tuple[bool, str]:
    claims = [float(value) for value in _LCR_CLAIM.findall(draft)]
    wanted = [value for value in expected if value is not None]
    if not wanted:
        return False, "The ratio was undefined, so there is nothing to release."
    missing = [value for value in wanted if not any(abs(claim - value) < 0.15 for claim in claims)]
    unexpected = [claim for claim in claims if not any(abs(claim - value) < 0.15 for value in wanted)]
    if missing or unexpected:
        shown = ", ".join(f"{value:.1f} percent" for value in wanted)
        return False, f"{label} ({shown}) and the draft does not match the recomputed figures."
    shown = ", ".join(f"{value:.1f} percent" for value in wanted)
    return True, f"{label}: {shown}. The draft matches."


def _attributes_requirement(draft: str, instruments: list[str]) -> bool:
    for name in instruments:
        pattern = rf"{re.escape(name)}.{{0,60}}\b(allows|requires|permits|imposes|sets)\b"
        if re.search(pattern, draft, re.I):
            return True
    return False


def _support_chunks(state: dict) -> list[dict]:
    chunks = list(state.get("chunks") or [])
    for row in state.get("coverage") or []:
        if row.get("text"):
            chunks.append({"text": row["text"], "heading": row.get("label", ""), "chunk_id": row.get("chunk_id", "")})
    return chunks


def _units(draft: str) -> list[str]:
    units = []
    for block in re.split(r"\n+", draft):
        cleaned = re.sub(r"\s*\[\d+\]", "", block).strip()
        if not cleaned or (cleaned.startswith("**") and cleaned.endswith("**")):
            continue
        parts = [part.strip() for part in re.split(r"(?<=[.])\s+", cleaned) if part.strip()]
        units.extend(parts or [cleaned])
    return units


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": passed, "detail": detail}
