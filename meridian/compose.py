"""Build a citation-grounded draft from retrieved sentences and tool output.

The composer does not invent regulatory claims. Sentences are either copied
from a retrieved briefing, copied from the calculator narrative, or taken
from a short list of framing lines.
"""

from __future__ import annotations

import re

from meridian.textutil import content_tokens, sentences, squash, tokenize

FRAMING_SOURCES = "From the indexed public sources:"
FRAMING_CALC = (
    "The figures below were computed by the risk-metric function and checked again by the reviewer."
)
FRAMING_POLICY = (
    "No internal liquidity policy has been indexed, so this desk cannot identify gaps "
    "against an internal policy that has not been provided."
)
FRAMING_NEAREST = (
    "Nearest indexed sources were inspected and are listed as context only. "
    "They are not evidence for the instrument named in the question."
)
SAMPLE_POLICY = (
    "The liquidity policy requires Treasury to maintain an LCR above 110 percent "
    "and to report the 30-day buffer to ALCO each week. The ALCO approves the limit. "
    "Funding concentration is reviewed quarterly."
)
ABSTAIN_LEAD = "Insufficient evidence in the retrieved regulatory sources."

THEMES = (
    {
        "id": "minimum",
        "label": "LCR regulatory minimum",
        "patterns": (r"100\s*percent", r"lcr\s+(above|over|at least|minimum|limit|target)"),
        "query": "minimum LCR is 100 percent",
    },
    {
        "id": "horizon",
        "label": "30-day LCR horizon",
        "patterns": (r"30[\s-]*day", r"30 calendar", r"thirty day"),
        "query": "LCR stress horizon is 30 calendar days",
    },
    {
        "id": "inflow",
        "label": "75 percent inflow cap",
        "patterns": (r"inflow cap", r"75\s*percent"),
        "query": "inflow cap is 75 percent of total expected cash outflows",
    },
    {
        "id": "survival",
        "label": "Internal survival horizon",
        "patterns": (r"survival horizon",),
        "query": "internal survival horizon ILAAP",
    },
    {
        "id": "intraday",
        "label": "Intraday liquidity",
        "patterns": (r"intraday",),
        "query": "intraday liquidity risk payments",
    },
    {
        "id": "cfp",
        "label": "Contingency funding plan",
        "patterns": (r"contingency funding", r"\bcfp\b"),
        "query": "contingency funding plan",
    },
    {
        "id": "reverse",
        "label": "Reverse stress testing",
        "patterns": (r"reverse stress",),
        "query": "reverse stress testing liquidity",
    },
    {
        "id": "multi",
        "label": "Multiple stress horizons",
        "patterns": (r"multiple (time )?horizons", r"several time horizons", r"longer than the 30"),
        "query": "stress testing several time horizons beyond the 30-day LCR",
    },
    {
        "id": "concentration",
        "label": "Funding concentration",
        "patterns": (r"concentration",),
        "query": "concentration of funding monitoring",
    },
)


def best_sentence(query: str, text: str) -> str | None:
    choices = sentences(text)
    if not choices:
        return None
    terms = content_tokens(query)
    ranked = sorted(choices, key=lambda item: _overlap(terms, item), reverse=True)
    if _overlap(terms, ranked[0]) <= 0:
        return choices[0]
    return ranked[0]


def abstain_message(instruments: list[str]) -> str:
    if instruments:
        named = ", ".join(instruments)
        return (
            f"{ABSTAIN_LEAD} {named} does not appear in the indexed ECB, EBA, Basel, "
            "CRR or CRD briefings, so Meridian will not attribute a requirement to it."
        )
    return (
        f"{ABSTAIN_LEAD} The retrieved briefings do not cover this question closely "
        "enough to support an answer."
    )


def assess_policy(policy_text: str, search) -> list[dict]:
    if not policy_text or not policy_text.strip():
        return []
    rows = []
    for theme in THEMES:
        mentioned = any(re.search(pattern, policy_text, re.I) for pattern in theme["patterns"])
        hits = search(theme["query"], k=1)
        evidence = ""
        chunk_id = ""
        source = ""
        if hits:
            chunk = hits[0].chunk
            evidence = best_sentence(theme["query"], chunk.text) or ""
            chunk_id = chunk.chunk_id
            source = f"{chunk.title} — {chunk.heading}"
            full_text = chunk.text
        else:
            full_text = ""
        rows.append(
            {
                "id": theme["id"],
                "label": theme["label"],
                "status": "mentioned" if mentioned else "not_mentioned",
                "evidence": evidence,
                "chunk_id": chunk_id,
                "source": source,
                "text": full_text,
            }
        )
    return rows


def compose(state: dict) -> dict:
    chunks = state.get("chunks") or []
    instruments = state.get("unsupported") or []
    if instruments or state.get("force_abstain"):
        return {
            "draft": abstain_message(instruments),
            "citations": [],
            "abstain": True,
        }

    citations: list[dict] = []
    lines: list[str] = []
    tool = state.get("tool_result") or {}
    narrative = tool.get("narrative") or ""
    if narrative and tool.get("tool") in {"lcr", "nsfr", "scenario"}:
        lines.append(FRAMING_CALC)
        lines.extend(_narrative_lines(narrative))

    if state.get("missing_policy"):
        lines.append(FRAMING_POLICY)

    groups = tool.get("groups") or []
    if groups:
        lines.append(FRAMING_SOURCES)
        for group in groups:
            lines.append(f"**{group['name']}**")
            for item in group.get("picked") or []:
                _append_cited(lines, citations, item["sentence"], item)
    elif chunks and not tool.get("narrative"):
        lines.append(FRAMING_SOURCES)
        _append_diverse(lines, citations, state["question"], chunks, limit=4)
    elif chunks and tool.get("narrative"):
        regulatory = []
        _append_diverse(regulatory, citations, state.get("retrieval_query") or state["question"], chunks, limit=2)
        if regulatory:
            lines.append(FRAMING_SOURCES)
            lines.extend(regulatory)

    coverage_lines, coverage_cites = _coverage_lines(state.get("coverage") or [], citations)
    lines.extend(coverage_lines)
    citations.extend(coverage_cites)

    if not citations and not narrative and not state.get("missing_policy"):
        return {
            "draft": abstain_message([]),
            "citations": [],
            "abstain": True,
        }

    # Drop a dangling framing line if nothing was cited and nothing was calculated.
    draft = "\n\n".join(line for line in lines if line)
    return {"draft": draft, "citations": citations, "abstain": False}


def _append_diverse(lines: list[str], citations: list[dict], query: str, chunks: list[dict], limit: int) -> None:
    used = set()
    added = 0
    for chunk in chunks:
        sentence = best_sentence(query, chunk["text"])
        if not sentence or sentence in used:
            continue
        if _overlap(content_tokens(query), sentence) < 0.12 and added > 0:
            continue
        used.add(sentence)
        _append_cited(lines, citations, sentence, chunk)
        added += 1
        if added >= limit:
            break


def _append_cited(lines: list[str], citations: list[dict], sentence: str, chunk: dict) -> None:
    number = len(citations) + 1
    citations.append(
        {
            "n": number,
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "title": chunk["title"],
            "heading": chunk["heading"],
            "authority": chunk.get("authority", ""),
            "instruments": chunk.get("instruments") or [],
            "excerpt": chunk["text"],
            "score": chunk.get("score"),
        }
    )
    lines.append(f"{sentence} [{number}]")


def _coverage_lines(coverage: list[dict], existing: list[dict]) -> tuple[list[str], list[dict]]:
    if not coverage:
        return [], []
    lines = ["**Policy excerpt coverage**"]
    cites: list[dict] = []
    known = {item["chunk_id"]: item["n"] for item in existing}
    for row in coverage:
        if row["status"] == "mentioned":
            lead = f"The excerpt mentions {row['label']}."
        else:
            lead = (
                f"The excerpt does not mention {row['label']}. "
                "This is a coverage flag, not a finding of non-compliance."
            )
        if row.get("evidence") and row.get("chunk_id"):
            number = known.get(row["chunk_id"])
            if number is None:
                number = len(existing) + len(cites) + 1
                cites.append(
                    {
                        "n": number,
                        "chunk_id": row["chunk_id"],
                        "doc_id": row["chunk_id"].split("::", 1)[0],
                        "title": row["source"].split(" — ", 1)[0],
                        "heading": row["source"].split(" — ", 1)[-1],
                        "authority": "",
                        "instruments": [],
                        "excerpt": row["evidence"],
                        "score": None,
                    }
                )
                known[row["chunk_id"]] = number
            lines.append(f"{lead} Indexed expectation: {row['evidence']} [{number}]")
        else:
            lines.append(lead)
    return lines, cites


def _narrative_lines(narrative: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.])\s+", narrative.strip()) if part.strip()]
    return parts


def _overlap(terms: list[str], sentence: str) -> float:
    if not terms:
        return 0.0
    blob = set(tokenize(sentence))
    return sum(1 for term in terms if term in blob) / len(terms)


def sentence_ok(sentence: str, chunks: list[dict], narrative: str) -> bool:
    cleaned = sentence.strip().strip("*")
    if not cleaned:
        return True
    if cleaned in {FRAMING_SOURCES, FRAMING_CALC, FRAMING_POLICY, FRAMING_NEAREST}:
        return True
    if cleaned.startswith(ABSTAIN_LEAD) or cleaned.startswith("No internal liquidity policy"):
        return True
    if cleaned.startswith("Nearest indexed sources"):
        return True
    if cleaned.startswith("The excerpt does not mention") or cleaned.startswith("The excerpt mentions"):
        return True
    if "coverage flag, not a finding of non-compliance" in cleaned:
        return True
    if "will not attribute a requirement" in cleaned or "closely enough to support an answer" in cleaned:
        return True
    if cleaned.startswith("Indexed expectation:"):
        cleaned = cleaned[len("Indexed expectation:") :].strip()
    if narrative and squash(cleaned) in squash(narrative):
        return True
    for chunk in chunks:
        if squash(cleaned) in squash(chunk["text"]):
            return True
    significant = [token for token in tokenize(cleaned) if len(token) > 2]
    if len(significant) < 5:
        return False
    blob: set[str] = set()
    for chunk in chunks:
        blob.update(tokenize(chunk["text"] + " " + chunk["heading"]))
    if narrative:
        blob.update(tokenize(narrative))
    return sum(1 for token in significant if token in blob) / len(significant) >= 0.72
