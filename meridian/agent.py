"""LangGraph desk: route, retrieve, calculate, draft, then an independent review."""

from __future__ import annotations

import logging
import re
import time
from typing import Annotated, Optional, TypedDict

import operator

from meridian.calculate import (
    DEMO_BOOK,
    TARGET_LABELS,
    liquidity_coverage_ratio,
    lcr_narrative,
    net_stable_funding_ratio,
    nsfr_narrative,
    one_decimal,
    scenario_narrative,
    scenario_on_book,
)
from meridian.compose import assess_policy, best_sentence, compose
from meridian.guard import mentions_internal_policy, unsupported_instruments
from meridian.index import get_index
from meridian.llm import draft_with_model
from meridian.review import review_draft

log = logging.getLogger("meridian")

_SCENARIO = re.compile(
    r"what happens|how would|increase|decrease|rise by|fall by|if .{0,80}\bby\b",
    re.I,
)
_COMPARE = re.compile(
    r"\bcompare\b|\bversus\b|\bvs\.?\b|\bagainst\b|\bgaps?\b|difference between",
    re.I,
)


class AgentState(TypedDict, total=False):
    question: str
    policy_text: str
    intent: str
    branch: str
    unsupported: list
    missing_policy: bool
    retrieval_query: str
    chunks: list
    tool_result: Optional[dict]
    draft: str
    citations: list
    coverage: list
    review: dict
    iteration: int
    abstain: bool
    confidence: float
    support: float
    prefer_extractive: bool
    force_abstain: bool
    scenario_override: Optional[dict]
    trace: Annotated[list, operator.add]


def run_desk(question: str, policy_text: str = "", scenario: dict | None = None) -> dict:
    graph = _compiled_graph()
    if graph is not None:
        try:
            final = graph.invoke(_initial(question, policy_text, scenario))
            return _present(final, "langgraph")
        except Exception as exc:  # pragma: no cover
            log.warning("LangGraph failed (%s); using the Python runner.", exc)
    final = run_linear(_initial(question, policy_text, scenario))
    return _present(final, "python")


def run_linear(state: dict) -> dict:
    state = _apply(state, route_node(state))
    branch = state["branch"]
    if branch == "calculate":
        state = _apply(state, calculate_node(state))
        state = _apply(state, retrieve_node(state))
    elif branch == "scenario":
        state = _apply(state, scenario_node(state))
        state = _apply(state, retrieve_node(state))
    elif branch == "compare":
        state = _apply(state, compare_node(state))
    else:
        state = _apply(state, retrieve_node(state))
    state = _apply(state, draft_node(state))
    state = _apply(state, review_node(state))
    if state.get("review", {}).get("verdict") == "returned" and state.get("iteration", 0) < 1:
        state = _apply(state, revise_node(state))
        state = _apply(state, retrieve_node(state))
        state = _apply(state, draft_node(state))
        state = _apply(state, review_node(state))
    return state


def route_node(state: dict) -> dict:
    started = time.perf_counter()
    question = state["question"]
    index = get_index()
    missing = unsupported_instruments(question, index)
    amounts = _parse_lcr_amounts(question)
    nsfr = _parse_nsfr(question)
    if missing:
        intent, branch = "adversarial", "search"
        detail = "Named instrument is not in the corpus. The desk will retrieve context and abstain."
    elif _SCENARIO.search(question):
        intent, branch = "scenario", "scenario"
        detail = "Scenario question. Outflows will be recomputed in Python, then read against the rulebook."
    elif (amounts[0] is not None and amounts[1] is not None) or nsfr:
        intent, branch = "calculation", "calculate"
        detail = "Balance-sheet inputs detected. The ratio will be calculated, not estimated."
    elif _COMPARE.search(question):
        intent, branch = "comparison", "compare"
        detail = "Comparison question. Each side is retrieved from its own supervisory sources."
    else:
        intent, branch = "regulation_search", "search"
        detail = "Regulatory search. The answer has to come from the indexed briefings."
    if mentions_internal_policy(question) and not (state.get("policy_text") or "").strip():
        detail += " No internal policy text was provided."
    return _traced(
        started,
        {
            "intent": intent,
            "branch": branch,
            "unsupported": missing,
            "missing_policy": mentions_internal_policy(question) and not (state.get("policy_text") or "").strip(),
            "retrieval_query": question,
        },
        "route",
        "Desk router",
        detail,
        "done",
    )


def retrieve_node(state: dict) -> dict:
    started = time.perf_counter()
    index = get_index()
    query = state.get("retrieval_query") or state["question"]
    hits = index.search(query, k=6, mode="hybrid")
    chunks = [hit.as_dict() for hit in hits]
    support = index.support(state["question"], hits)
    top = chunks[0]["heading"] if chunks else "no hit"
    return _traced(
        started,
        {"chunks": chunks, "support": support, "confidence": support},
        "retrieve",
        "Regulation search",
        f"Hybrid retrieval returned {len(chunks)} briefings. Lead section: {top}.",
        "done",
    )


def calculate_node(state: dict) -> dict:
    started = time.perf_counter()
    question = state["question"]
    nsfr = _parse_nsfr(question)
    if nsfr:
        result = net_stable_funding_ratio(*nsfr)
        narrative = " ".join(nsfr_narrative(result))
        tool = {
            "tool": "nsfr",
            "inputs": {"asf": nsfr[0], "rsf": nsfr[1]},
            "base": result,
            "narrative": narrative,
        }
        detail = narrative.split(".")[0] + "."
    else:
        hqla, outflows, inflows = _parse_lcr_amounts(question)
        result = liquidity_coverage_ratio(hqla, outflows, inflows or 0.0)
        narrative = " ".join(lcr_narrative(result))
        tool = {
            "tool": "lcr",
            "inputs": {"hqla": hqla, "outflows": outflows, "inflows": inflows or 0.0},
            "base": result,
            "narrative": narrative,
        }
        detail = lcr_narrative(result)[0]
    return _traced(
        started,
        {
            "tool_result": tool,
            "retrieval_query": "LCR minimum 100 percent inflow cap 75 percent net cash outflow 30 calendar days NSFR",
        },
        "calculate",
        "Risk metric calculator",
        detail,
        "done",
    )


def scenario_node(state: dict) -> dict:
    started = time.perf_counter()
    question = state["question"]
    override = state.get("scenario_override") or {}
    shock = float(override.get("shock_pct", _parse_percent(question) or 0.20))
    hqla, outflows, inflows = _parse_lcr_amounts(question)
    if override.get("hqla") is not None and override.get("retail_stable") is not None:
        book = dict(DEMO_BOOK)
        for key in DEMO_BOOK:
            if key in override and override[key] is not None:
                book[key] = float(override[key])
        target = override.get("shock_target", "wholesale")
        result = scenario_on_book(book, target, shock)
        tool = _book_tool(result, target)
    elif hqla is not None and outflows is not None:
        base = liquidity_coverage_ratio(hqla, outflows, inflows or 0.0)
        shocked = liquidity_coverage_ratio(hqla, outflows * (1 + shock), inflows or 0.0)
        delta = None if base["lcr_pct"] is None or shocked["lcr_pct"] is None else one_decimal(shocked["lcr_pct"] - base["lcr_pct"])
        packed = {"base": base, "shocked": shocked, "shock_pct": shock, "delta_lcr_pp": delta}
        tool = {
            "tool": "scenario",
            "mode": "simple",
            "inputs": {"hqla": hqla, "outflows": outflows, "inflows": inflows or 0.0, "shock_pct": shock},
            "target_label": "gross stressed outflow",
            "base": base,
            "shocked": shocked,
            "delta_lcr_pp": delta,
            "narrative": " ".join(scenario_narrative(packed, "gross stressed outflow")),
        }
    else:
        target = _shock_target(question)
        result = scenario_on_book(dict(DEMO_BOOK), target, shock)
        tool = _book_tool(result, target)
        tool["used_demo_book"] = True
        tool["narrative"] = (
            "No balance-sheet figures were supplied, so the desk used its illustrative book "
            "and held the Basel standard run-off weights unchanged. " + tool["narrative"]
        )
    detail = tool["narrative"].split(".")[0] + "."
    return _traced(
        started,
        {
            "tool_result": tool,
            "retrieval_query": "wholesale run-off rates 75 percent inflow cap LCR minimum 100 percent",
        },
        "scenario",
        "Scenario analysis",
        detail,
        "done",
    )


def compare_node(state: dict) -> dict:
    started = time.perf_counter()
    index = get_index()
    sides = _comparison_sides(state["question"])
    groups = []
    chunks = []
    seen = set()
    for name, query, doc_ids in sides:
        hits = index.search(query, k=3, mode="hybrid", doc_ids=doc_ids)
        picked = []
        used_sentences = set()
        for hit in hits:
            data = hit.as_dict()
            sentence = best_sentence(query, data["text"])
            if not sentence or sentence in used_sentences:
                continue
            used_sentences.add(sentence)
            data["sentence"] = sentence
            picked.append(data)
            if data["chunk_id"] not in seen:
                seen.add(data["chunk_id"])
                chunks.append(data)
            if len(picked) >= 2:
                break
        groups.append({"name": name, "picked": picked})
    policy = state.get("policy_text") or ""
    coverage = assess_policy(policy, index.search) if policy.strip() else []
    support = index.support(state["question"], index.search(state["question"], k=4))
    return _traced(
        started,
        {
            "chunks": chunks,
            "coverage": coverage,
            "support": support,
            "confidence": support,
            "tool_result": {"tool": "compare", "groups": groups, "narrative": ""},
        },
        "compare",
        "Regulatory comparison",
        "Retrieved " + " and ".join(side[0] for side in sides) + " as separate source groups.",
        "done",
    )


def draft_node(state: dict) -> dict:
    started = time.perf_counter()
    tool = state.get("tool_result") or {}
    chunks = state.get("chunks") or []
    top_coverage = chunks[0].get("coverage", 0) if chunks else 0
    low_support = state.get("support", 0) < 0.2 and top_coverage < 0.18
    force = bool(state.get("unsupported")) or (low_support and not tool)
    update = {"force_abstain": force}
    if force or state.get("prefer_extractive") or tool.get("tool") in {"lcr", "nsfr", "scenario", "compare"}:
        drafted = compose({**state, **update})
        channel = "extractive"
    else:
        model_text = draft_with_model(
            state["question"],
            chunks,
            tool.get("narrative") or "",
        )
        if model_text:
            drafted = {"draft": model_text, "citations": _citations_from_markers(model_text, chunks), "abstain": False}
            channel = "model"
        else:
            drafted = compose({**state, **update})
            channel = "extractive"
    status = "abstained" if drafted["abstain"] else "done"
    detail = "Draft withheld pending the abstention rule." if drafted["abstain"] else f"Draft written from {channel} evidence."
    update.update(drafted)
    return _traced(started, update, "draft", "Researcher", detail, status)


def review_node(state: dict) -> dict:
    started = time.perf_counter()
    packet = review_draft(state, get_index())
    verdict = packet["review"]["verdict"]
    detail = packet["review"]["summary"]
    return _traced(started, packet, "review", "Risk reviewer", detail, verdict)


def revise_node(state: dict) -> dict:
    started = time.perf_counter()
    return _traced(
        started,
        {
            "iteration": state.get("iteration", 0) + 1,
            "prefer_extractive": True,
            "retrieval_query": state["question"] + " liquidity coverage ratio NSFR ILAAP HQLA stress testing",
        },
        "revise",
        "Return for re-retrieval",
        "The reviewer returned the draft. The researcher retrieves again and may only quote the corpus.",
        "returned",
    )


def _compiled_graph():
    global _GRAPH
    if _GRAPH is not False and _GRAPH is not None:
        return _GRAPH
    if _GRAPH is False:
        return None
    try:
        from langgraph.graph import END, StateGraph

        builder = StateGraph(AgentState)
        for name, fn in (
            ("route", route_node),
            ("retrieve", retrieve_node),
            ("calculate", calculate_node),
            ("scenario", scenario_node),
            ("compare", compare_node),
            ("draft", draft_node),
            ("review", review_node),
            ("revise", revise_node),
        ):
            builder.add_node(name, fn)
        builder.set_entry_point("route")
        builder.add_conditional_edges(
            "route",
            lambda state: state["branch"],
            {
                "search": "retrieve",
                "calculate": "calculate",
                "scenario": "scenario",
                "compare": "compare",
            },
        )
        builder.add_edge("calculate", "retrieve")
        builder.add_edge("scenario", "retrieve")
        builder.add_edge("retrieve", "draft")
        builder.add_edge("compare", "draft")
        builder.add_edge("draft", "review")
        builder.add_conditional_edges(
            "review",
            lambda state: "revise" if state.get("review", {}).get("verdict") == "returned" and state.get("iteration", 0) < 1 else "end",
            {"revise": "revise", "end": END},
        )
        builder.add_edge("revise", "retrieve")
        _GRAPH = builder.compile()
        return _GRAPH
    except Exception as exc:  # pragma: no cover
        log.warning("LangGraph is not available (%s).", exc)
        _GRAPH = False
        return None


_GRAPH = None


def _initial(question: str, policy_text: str, scenario: dict | None) -> dict:
    return {
        "question": question.strip(),
        "policy_text": policy_text or "",
        "intent": "",
        "branch": "search",
        "unsupported": [],
        "missing_policy": False,
        "retrieval_query": question.strip(),
        "chunks": [],
        "tool_result": None,
        "draft": "",
        "citations": [],
        "coverage": [],
        "review": {},
        "iteration": 0,
        "abstain": False,
        "confidence": 0.0,
        "support": 0.0,
        "prefer_extractive": False,
        "force_abstain": False,
        "scenario_override": scenario,
        "trace": [],
    }


def _apply(state: dict, update: dict) -> dict:
    merged = dict(state)
    for key, value in update.items():
        if key == "trace":
            merged["trace"] = list(state.get("trace") or []) + list(value or [])
        else:
            merged[key] = value
    return merged


def _traced(started: float, update: dict, node: str, title: str, detail: str, status: str) -> dict:
    event = {
        "node": node,
        "title": title,
        "detail": detail,
        "status": status,
        "ms": max(1, int((time.perf_counter() - started) * 1000)),
    }
    trace = list(update.get("trace") or [])
    trace.append(event)
    update["trace"] = trace
    return update


def _present(state: dict, orchestrator: str) -> dict:
    tool = state.get("tool_result")
    if tool:
        tool = {key: value for key, value in tool.items() if key != "inputs" or True}
    retrieved = []
    for chunk in state.get("chunks") or []:
        retrieved.append(
            {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "title": chunk["title"],
                "heading": chunk["heading"],
                "authority": chunk.get("authority", ""),
                "score": chunk.get("score"),
                "excerpt": chunk["text"],
            }
        )
    review = state.get("review") or {}
    return {
        "question": state.get("question", ""),
        "intent": state.get("intent", ""),
        "abstained": bool(state.get("abstain")),
        "confidence": round(float(state.get("confidence") or 0), 3),
        "answer": state.get("draft") or "",
        "citations": state.get("citations") or [],
        "retrieved": retrieved,
        "tool_result": tool,
        "coverage": state.get("coverage") or [],
        "missing_policy": bool(state.get("missing_policy")),
        "unsupported": state.get("unsupported") or [],
        "review": review,
        "trace": state.get("trace") or [],
        "orchestrator": orchestrator,
    }


def _book_tool(result: dict, target: str) -> dict:
    label = TARGET_LABELS.get(target, target)
    components = []
    for base_row, shocked_row in zip(result["base"]["lines"], result["shocked"]["lines"]):
        components.append(
            {
                "label": base_row["label"],
                "base": round(base_row["outflow"], 4),
                "shocked": round(shocked_row["outflow"], 4),
            }
        )
    return {
        "tool": "scenario",
        "mode": "book",
        "inputs": {"book": result["book"], "target": target, "shock_pct": result["shock_pct"]},
        "target_label": label,
        "base": result["base"],
        "shocked": result["shocked"],
        "delta_lcr_pp": result["delta_lcr_pp"],
        "components": components,
        "narrative": " ".join(scenario_narrative(result, label)),
        "used_demo_book": False,
    }


def _comparison_sides(question: str) -> list[tuple[str, str, list[str]]]:
    text = question.lower()
    if "nsfr" in text and "lcr" in text:
        return [
            ("LCR", "LCR 30 calendar day minimum high-quality liquid assets inflow cap", ["lcr-framework", "net-cash-outflows"]),
            ("NSFR", "NSFR one year available stable funding required stable funding", ["nsfr", "eu-rulebook"]),
        ]
    if "level 2" in text or "2a" in text or "2b" in text:
        return [
            ("Level 2A", "Level 2A assets 15 percent haircut 40 percent cap", ["hqla"]),
            ("Level 2B", "Level 2B assets 15 percent composition cap haircut", ["hqla"]),
        ]
    if "crd" in text and "crr" in text:
        return [
            ("CRR", "CRR Article 412 Article 413 liquidity coverage stable funding", ["eu-rulebook"]),
            ("CRD", "Directive Article 86 intraday governance contingency", ["eu-rulebook", "intraday-cfp"]),
        ]
    if "monitoring" in text:
        return [
            ("LCR", "LCR 30 calendar day minimum ratio", ["lcr-framework"]),
            ("Monitoring tools", "five liquidity monitoring tools concentration significant currency", ["basel-monitoring"]),
        ]
    return [
        ("ECB ILAAP", "ECB ILAAP survival horizon internal stress testing risk appetite several time horizons", ["ecb-ilaap"]),
        ("EBA stress testing", "EBA/GL/2018/04 liquidity scenarios solvency contingency funding reverse stress", ["eba-stress"]),
    ]


def _citations_from_markers(text: str, chunks: list[dict]) -> list[dict]:
    numbers = [int(value) for value in re.findall(r"\[(\d+)\]", text)]
    citations = []
    seen = set()
    for number in numbers:
        if number in seen or number < 1 or number > len(chunks):
            continue
        seen.add(number)
        chunk = chunks[number - 1]
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
    return citations


def _parse_lcr_amounts(question: str) -> tuple[float | None, float | None, float | None]:
    compact = question.replace(",", "")
    hqla = _amount(r"hqla\s*(?:=|of|is|:)?\s*€?\s*(\d+(?:\.\d+)?)", compact)
    outflows = _amount(r"stressed\s+outflows?\s*(?:=|of|is|:)?\s*€?\s*(\d+(?:\.\d+)?)", compact)
    if outflows is None:
        outflows = _amount(r"\boutflows?\s*(?:=|of|is|:)\s*€?\s*(\d+(?:\.\d+)?)", compact)
    inflows = _amount(r"\binflows?\s*(?:=|of|is|:)?\s*€?\s*(\d+(?:\.\d+)?)", compact)
    return hqla, outflows, inflows


def _parse_nsfr(question: str) -> tuple[float, float] | None:
    compact = question.replace(",", "")
    asf = _amount(r"\basf\s*(?:=|of|is|:)?\s*€?\s*(\d+(?:\.\d+)?)", compact)
    rsf = _amount(r"\brsf\s*(?:=|of|is|:)?\s*€?\s*(\d+(?:\.\d+)?)", compact)
    if asf is None or rsf is None:
        return None
    return asf, rsf


def _parse_percent(question: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", question, re.I)
    if not match:
        return None
    return float(match.group(1)) / 100.0


def _shock_target(question: str) -> str:
    text = question.lower()
    if "non-operational" in text or "non operational" in text:
        return "wholesale_non_operational"
    if "operational" in text and "wholesale" in text:
        return "wholesale_operational"
    if "wholesale" in text:
        return "wholesale"
    if "retail" in text:
        return "retail"
    return "all"


def _amount(pattern: str, question: str) -> float | None:
    match = re.search(pattern, question, re.I)
    if not match:
        return None
    return float(match.group(1))
