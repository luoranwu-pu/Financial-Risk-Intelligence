"""Optional OpenAI-compatible drafting. The reviewer still has to clear it."""

from __future__ import annotations

import httpx

from meridian.settings import openai_api_key, openai_base_url, openai_model


def draft_with_model(question: str, chunks: list[dict], narrative: str) -> str | None:
    key = openai_api_key()
    if not key or not chunks:
        return None
    sources = []
    for index, chunk in enumerate(chunks[:6], start=1):
        sources.append(
            f"[{index}] {chunk['title']} — {chunk['heading']}\n{chunk['text']}"
        )
    tool = f"\n\nCalculator output:\n{narrative}" if narrative else ""
    prompt = (
        "Answer the question using only the numbered sources and the calculator output. "
        "Cite sources as [1] or [2]. Do not add regulatory facts from memory. "
        "If the sources do not support an answer, reply with exactly INSUFFICIENT.\n\n"
        f"Question: {question}\n\nSources:\n\n" + "\n\n".join(sources) + tool
    )
    try:
        response = httpx.post(
            f"{openai_base_url()}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": openai_model(),
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a second-line liquidity risk analyst. "
                            "You never invent article numbers, ratios, or supervisory expectations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=40.0,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
    if not text or "INSUFFICIENT" in text.upper():
        return None
    return text
