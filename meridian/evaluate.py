"""Score closed-book, BM25 RAG, hybrid RAG, and the agentic desk on the same questions."""

from __future__ import annotations

import json
from pathlib import Path

from meridian.agent import run_desk
from meridian.baselines import basic_rag, closed_book, hybrid_rag
from meridian.calculate import DEMO_BOOK, liquidity_coverage_ratio, net_stable_funding_ratio, scenario_on_book
from meridian.index import RegulatoryIndex, get_index
from meridian.questions import all_questions
from meridian.settings import DATA_DIR

SYSTEMS = (
    ("closed_book", "Closed book"),
    ("basic_rag", "Basic RAG"),
    ("hybrid_rag", "Hybrid + reranker"),
    ("agentic", "Agentic RAG + reviewer"),
)


def run_evaluation(index: RegulatoryIndex | None = None, save: bool = True) -> dict:
    index = index or get_index()
    questions = all_questions()
    rows = []
    for question in questions:
        systems = {
            "closed_book": closed_book(question["question"], index),
            "basic_rag": basic_rag(question["question"], index),
            "hybrid_rag": hybrid_rag(question["question"], index),
            "agentic": _agentic(question["question"]),
        }
        expected = _expected_percents(question)
        scored = {}
        for name, result in systems.items():
            scored[name] = _score(question, result, expected)
        rows.append({"id": question["id"], "type": question["type"], "systems": scored})
    report = {
        "questions": len(questions),
        "systems": {key: _aggregate(rows, key) for key, _label in SYSTEMS},
        "by_type": _by_type(rows),
        "labels": {key: label for key, label in SYSTEMS},
        "rows": rows,
    }
    if save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "last_eval.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def load_saved(path: Path | None = None) -> dict | None:
    target = path or (DATA_DIR / "last_eval.json")
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def _agentic(question: str) -> dict:
    result = run_desk(question)
    return {
        "answer": result["answer"],
        "abstained": result["abstained"],
        "citations": result["citations"],
        "retrieved": result["retrieved"],
        "verdict": result.get("review", {}).get("verdict"),
    }


def _expected_percents(question: dict) -> list[float]:
    if "calc" in question:
        result = liquidity_coverage_ratio(**question["calc"])
        return [] if result["lcr_pct"] is None else [result["lcr_pct"]]
    if "nsfr" in question:
        result = net_stable_funding_ratio(**question["nsfr"])
        return [] if result["nsfr_pct"] is None else [result["nsfr_pct"]]
    if "simple_shock" in question:
        spec = question["simple_shock"]
        base = liquidity_coverage_ratio(spec["hqla"], spec["outflows"], spec["inflows"])
        shocked = liquidity_coverage_ratio(
            spec["hqla"], spec["outflows"] * (1 + spec["shock_pct"]), spec["inflows"]
        )
        return [value for value in (base["lcr_pct"], shocked["lcr_pct"]) if value is not None]
    if "book_shock" in question:
        spec = question["book_shock"]
        result = scenario_on_book(dict(DEMO_BOOK), spec["target"], spec["shock_pct"])
        return [value for value in (result["base"]["lcr_pct"], result["shocked"]["lcr_pct"]) if value is not None]
    return []


def _score(question: dict, result: dict, expected: list[float]) -> dict:
    retrieved_ids = [item["chunk_id"] for item in result.get("retrieved") or []]
    gold = question.get("gold_chunk_ids") or []
    facts = question.get("gold_facts") or []
    answer = result.get("answer") or ""
    abstained = bool(result.get("abstained"))
    expect_abstain = bool(question.get("expect_abstain"))
    calc_accuracy = None
    if expected:
        calc_accuracy = 1.0 if _contains_percents(answer, expected) else 0.0
    must = question.get("must_include") or []
    must_hit = None
    if must:
        must_hit = 1.0 if all(item.lower() in answer.lower() for item in must) else 0.0
    return {
        "recall_at_5": _recall(retrieved_ids, gold, 5) if gold else None,
        "mrr": _mrr(retrieved_ids, gold) if gold else None,
        "fact_coverage": _facts(answer, facts) if facts and not expect_abstain else None,
        "citation_correctness": _citations(result.get("citations") or [], gold, expect_abstain, abstained),
        "abstention_correct": 1.0 if abstained == expect_abstain else 0.0,
        "calculation_accuracy": calc_accuracy,
        "must_include": must_hit,
        "abstained": abstained,
        "verdict": result.get("verdict"),
    }


def _contains_percents(answer: str, expected: list[float]) -> bool:
    import re

    found = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", answer, re.I)]
    return all(any(abs(claim - target) < 0.15 for claim in found) for target in expected)


def _recall(retrieved: list[str], gold: list[str], k: int) -> float:
    if not gold:
        return 0.0
    return len(set(retrieved[:k]) & set(gold)) / len(gold)


def _mrr(retrieved: list[str], gold: list[str]) -> float:
    gold_set = set(gold)
    for index, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in gold_set:
            return 1.0 / index
    return 0.0


def _facts(answer: str, facts: list[str]) -> float:
    if not facts:
        return 0.0
    lowered = answer.lower()
    return sum(1 for fact in facts if fact.lower() in lowered) / len(facts)


def _citations(citations: list[dict], gold: list[str], expect_abstain: bool, abstained: bool) -> float | None:
    if expect_abstain:
        return 1.0 if abstained else 0.0
    if not gold:
        return None
    cited = {item["chunk_id"] for item in citations}
    if not cited:
        return 0.0
    return len(cited & set(gold)) / len(gold)


def _aggregate(rows: list[dict], system: str) -> dict:
    keys = [
        "recall_at_5",
        "mrr",
        "fact_coverage",
        "citation_correctness",
        "abstention_correct",
        "calculation_accuracy",
        "must_include",
    ]
    summary = {key: _mean([row["systems"][system][key] for row in rows]) for key in keys}
    summary["n"] = len(rows)
    return summary


def _by_type(rows: list[dict]) -> dict:
    kinds = sorted({row["type"] for row in rows})
    report = {}
    for kind in kinds:
        subset = [row for row in rows if row["type"] == kind]
        report[kind] = {key: _aggregate(subset, key) for key, _label in SYSTEMS}
    return report


def _mean(values: list[float | None]) -> float | None:
    kept = [value for value in values if value is not None]
    if not kept:
        return None
    return round(sum(kept) / len(kept), 4)
