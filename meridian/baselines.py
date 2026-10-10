"""Comparison systems used by the benchmark.

Closed-book answers from a short memory and a deliberately incomplete ratio.
Basic RAG is BM25 only. Hybrid RAG adds vectors and the reranker.
Neither RAG baseline may call the calculator or abstain on a missing instrument.
"""

from __future__ import annotations

import re

from meridian.agent import _parse_lcr_amounts, _parse_nsfr, _parse_percent
from meridian.calculate import one_decimal
from meridian.compose import compose
from meridian.guard import unsupported_instruments
from meridian.index import RegulatoryIndex
from meridian.textutil import content_tokens, tokenize

_MEMORY = [
    "The LCR stress horizon is 30 calendar days.",
    "The minimum LCR is 100 percent.",
    "The NSFR stress horizon is one year.",
    "The minimum NSFR is 100 percent.",
    "The LCR inflow cap is often described as a supervisory buffer.",
]


def closed_book(question: str, index: RegulatoryIndex) -> dict:
    missing = unsupported_instruments(question, index)
    if missing:
        return _pack(
            f"{missing[0]} allows a liquidity coverage ratio of 50 percent where a supervisor grants a waiver.",
            abstained=False,
        )
    nsfr = _parse_nsfr(question)
    if nsfr:
        # Inverts the ratio, a common closed-book slip.
        wrong = one_decimal(nsfr[1] / nsfr[0] * 100) if nsfr[0] else None
        text = f"The net stable funding ratio is {wrong:.1f} percent." if wrong else "The NSFR cannot be computed."
        return _pack(text, abstained=False)
    hqla, outflows, inflows = _parse_lcr_amounts(question)
    if hqla is not None and outflows:
        shock = _parse_percent(question) or 0.0
        if re.search(r"increase|decrease|what happens", question, re.I):
            outflows = outflows * (1 + shock)
        # Ignores inflows and the 75 percent cap.
        wrong = one_decimal(hqla / outflows * 100)
        return _pack(
            f"The liquidity coverage ratio is {wrong:.1f} percent.",
            abstained=False,
        )
    if re.search(r"what happens|increase by|wholesale deposit", question, re.I):
        return _pack(
            "The liquidity coverage ratio is 50.0 percent after that funding shock.",
            abstained=False,
        )
    terms = set(content_tokens(question))
    best = max(_MEMORY, key=lambda line: _overlap(terms, line))
    if _overlap(terms, best) < 0.2:
        return _pack(
            "The applicable liquidity requirement is a 50 percent coverage ratio over 10 days.",
            abstained=False,
        )
    return _pack(best, abstained=False)


def basic_rag(question: str, index: RegulatoryIndex) -> dict:
    hits = index.search(question, k=5, mode="bm25", expand=False)
    return _from_hits(question, hits)


def hybrid_rag(question: str, index: RegulatoryIndex) -> dict:
    hits = index.search(question, k=5, mode="hybrid", expand=True)
    return _from_hits(question, hits)


def _from_hits(question: str, hits) -> dict:
    chunks = [hit.as_dict() for hit in hits]
    drafted = compose(
        {
            "question": question,
            "chunks": chunks,
            "unsupported": [],
            "tool_result": None,
            "missing_policy": False,
            "coverage": [],
            "force_abstain": False,
        }
    )
    # The baseline does not have an abstention policy. If the composer refuses,
    # fall back to the lead retrieved sentence so the comparison stays honest.
    if drafted["abstain"] and chunks:
        sentence = chunks[0]["text"].split(".")[0] + "."
        drafted = {
            "draft": sentence,
            "citations": [
                {
                    "n": 1,
                    "chunk_id": chunks[0]["chunk_id"],
                    "doc_id": chunks[0]["doc_id"],
                    "title": chunks[0]["title"],
                    "heading": chunks[0]["heading"],
                    "excerpt": chunks[0]["text"],
                }
            ],
            "abstain": False,
        }
    return {
        "answer": drafted["draft"],
        "abstained": False,
        "citations": drafted["citations"],
        "retrieved": [_brief(chunk) for chunk in chunks],
    }


def _pack(answer: str, abstained: bool) -> dict:
    return {"answer": answer, "abstained": abstained, "citations": [], "retrieved": []}


def _brief(chunk: dict) -> dict:
    return {
        "chunk_id": chunk["chunk_id"],
        "doc_id": chunk["doc_id"],
        "title": chunk["title"],
        "heading": chunk["heading"],
        "excerpt": chunk["text"],
    }


def _overlap(terms: set[str], line: str) -> float:
    if not terms:
        return 0.0
    blob = set(tokenize(line))
    return sum(1 for term in terms if term in blob) / len(terms)
