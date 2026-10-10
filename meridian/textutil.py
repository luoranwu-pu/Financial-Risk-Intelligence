"""Tokenisation and small text helpers shared by retrieval and review."""

from __future__ import annotations

import re

STOP = {
    "the", "a", "an", "of", "and", "or", "to", "for", "in", "on", "under", "with",
    "by", "is", "are", "was", "were", "be", "as", "at", "from", "that", "this",
    "these", "those", "it", "its", "into", "over", "than", "not", "what", "which",
    "who", "how", "does", "do", "our", "against", "between", "about", "please",
    "if", "when", "where", "can", "may", "should", "would", "could", "has", "have",
    "had", "their", "them", "they", "we", "you", "your", "any", "there", "been",
}

ACRONYMS = {
    "lcr": ["liquidity", "coverage", "ratio"],
    "nsfr": ["net", "stable", "funding"],
    "hqla": ["high", "quality", "liquid", "assets"],
    "ilaap": ["internal", "liquidity", "adequacy", "assessment", "process"],
    "cfp": ["contingency", "funding", "plan"],
    "srep": ["supervisory", "review", "evaluation"],
    "crr": ["regulation", "575"],
    "crd": ["directive", "2013"],
    "eba": ["eba"],
    "ecb": ["ecb"],
    "nco": ["net", "cash", "outflow"],
}


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("€", " eur ").replace("%", " percent ")
    return re.findall(r"[a-z0-9]+", text)


def content_tokens(text: str) -> list[str]:
    expanded = []
    for token in tokenize(text):
        expanded.append(token)
        expanded.extend(ACRONYMS.get(token, []))
    seen = []
    for token in expanded:
        if token in STOP or token in seen:
            continue
        seen.append(token)
    return seen


def expand_query(text: str) -> str:
    extra = []
    for token in tokenize(text):
        extra.extend(ACRONYMS.get(token, []))
    if not extra:
        return text
    return text + " " + " ".join(extra)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.])\s+", text.strip())
    return [part.strip() for part in parts if len(part.strip()) > 30]


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def squash(text: str) -> str:
    return " ".join(text.split())
