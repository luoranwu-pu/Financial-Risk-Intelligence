"""Second-line checks that run before an answer is released."""

from __future__ import annotations

import re

from meridian.index import RegulatoryIndex

_INSTRUMENT = re.compile(r"\b[A-Z]{2,}[-/][A-Z0-9][-A-Z0-9/]*\b")
_ARTICLE = re.compile(r"\bArticle\s+(\d+[a-z]?)\b", re.I)
_BCBS = re.compile(r"\bBCBS\s+(\d+)\b", re.I)
_XYZ = re.compile(r"\bXYZ\b")
_KNOWN_PARTS = {
    "EBA", "ECB", "CRR", "CRD", "CRR2", "BCBS", "EU", "LCR", "NSFR",
    "HQLA", "ILAAP", "SREP", "CFP", "BIS", "IMF", "GL",
}


def unsupported_instruments(question: str, index: RegulatoryIndex) -> list[str]:
    """Return named instruments in the question that are not in the corpus."""
    blob = index.blob
    missing: list[str] = []
    for token in _INSTRUMENT.findall(question):
        if token.lower() in blob.lower() or _known_authority_pair(token):
            continue
        missing.append(token)
    for article in _ARTICLE.findall(question):
        pattern = rf"Article\s+{re.escape(article)}\b"
        if not re.search(pattern, blob, re.I):
            missing.append(f"Article {article}")
    for number in _BCBS.findall(question):
        if f"BCBS {number}" not in blob and f"BCBS{number}" not in blob:
            missing.append(f"BCBS {number}")
    if _XYZ.search(question) and "xyz" not in blob.lower() and "XYZ" not in missing:
        missing.append("XYZ")
    # Preserve order while dropping duplicates.
    ordered: list[str] = []
    for item in missing:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _known_authority_pair(token: str) -> bool:
    parts = [part for part in re.split(r"[-/]", token) if part]
    return bool(parts) and all(part in _KNOWN_PARTS for part in parts)


def mentions_internal_policy(question: str) -> bool:
    return bool(
        re.search(
            r"\binternal (liquidity )?policy\b|\bour\b.{0,48}\bpolicy\b",
            question,
            re.I,
        )
    )
