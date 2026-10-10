"""Load the regulatory briefing corpus and split it into citation-sized chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from meridian.textutil import slugify


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    authority: str
    topic: str
    instruments: list[str]
    heading: str
    text: str

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "authority": self.authority,
            "topic": self.topic,
            "instruments": list(self.instruments),
            "heading": self.heading,
            "text": self.text,
        }


@dataclass
class Document:
    doc_id: str
    title: str
    authority: str
    topic: str
    instruments: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)


def _parse_front_matter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    meta: dict = {}
    list_key = None
    for line in parts[1].splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and list_key:
            meta.setdefault(list_key, []).append(line.strip()[2:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value == "":
            list_key = key
            meta[key] = []
        else:
            list_key = None
            meta[key] = value
    return meta, parts[2]


def load_documents(corpus_dir: Path) -> list[Document]:
    documents: list[Document] = []
    for path in sorted(corpus_dir.glob("*.md")):
        meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))
        document = Document(
            doc_id=str(meta.get("doc_id") or path.stem),
            title=str(meta.get("title") or path.stem),
            authority=str(meta.get("authority") or ""),
            topic=str(meta.get("topic") or ""),
            instruments=list(meta.get("instruments") or []),
        )
        for section in body.split("\n## "):
            section = section.strip()
            if not section:
                continue
            if section.startswith("## "):
                section = section[3:]
            heading, _, remainder = section.partition("\n")
            heading = heading.strip()
            text = remainder.strip()
            if not heading or not text:
                continue
            document.chunks.append(
                Chunk(
                    chunk_id=f"{document.doc_id}::{slugify(heading)}",
                    doc_id=document.doc_id,
                    title=document.title,
                    authority=document.authority,
                    topic=document.topic,
                    instruments=document.instruments,
                    heading=heading,
                    text=text,
                )
            )
        documents.append(document)
    return documents


def load_chunks(corpus_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in load_documents(corpus_dir):
        chunks.extend(document.chunks)
    return chunks
