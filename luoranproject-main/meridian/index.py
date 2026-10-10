"""Hybrid index: BM25 plus a vector index (FAISS when the wheel is present)."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from meridian.corpus import Chunk, load_chunks
from meridian.settings import DATA_DIR, CORPUS_DIR, embedding_mode
from meridian.textutil import content_tokens, expand_query, tokenize

log = logging.getLogger("meridian")

try:
    import faiss
except ImportError:  # pragma: no cover
    faiss = None


@dataclass
class Hit:
    chunk: Chunk
    score: float
    bm25: float
    dense: float
    coverage: float

    def as_dict(self) -> dict:
        data = self.chunk.as_dict()
        data.update(
            {
                "score": round(float(self.score), 4),
                "bm25": round(float(self.bm25), 4),
                "dense": round(float(self.dense), 4),
                "coverage": round(float(self.coverage), 4),
            }
        )
        return data


class TfidfSpace:
    def __init__(self, texts: list[str]):
        docs = [tokenize(text) for text in texts]
        df: dict[str, int] = {}
        for doc in docs:
            for token in set(doc):
                df[token] = df.get(token, 0) + 1
        self.vocab = {token: i for i, token in enumerate(sorted(df))}
        n = len(docs)
        self.idf = np.zeros(len(self.vocab), dtype=np.float32)
        for token, index in self.vocab.items():
            self.idf[index] = math.log((1 + n) / (1 + df[token])) + 1.0
        matrix = np.vstack([self._vector(doc) for doc in docs])
        self.matrix = _normalise(matrix)

    def _vector(self, tokens: list[str]) -> np.ndarray:
        vec = np.zeros(len(self.vocab), dtype=np.float32)
        if not tokens:
            return vec
        counts: dict[str, int] = {}
        for token in tokens:
            if token in self.vocab:
                counts[token] = counts.get(token, 0) + 1
        length = len(tokens)
        for token, count in counts.items():
            vec[self.vocab[token]] = (count / length) * self.idf[self.vocab[token]]
        return vec

    def embed_documents(self) -> np.ndarray:
        return self.matrix

    def embed_query(self, text: str) -> np.ndarray:
        return _normalise(self._vector(tokenize(text)).reshape(1, -1))[0]


class RegulatoryIndex:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise RuntimeError("The regulatory corpus is empty.")
        self.chunks = chunks
        self.by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self.tokenized = [tokenize(self._document_text(chunk)) for chunk in chunks]
        self.bm25 = BM25Okapi(self.tokenized)
        self.embeddings, self.backend, self._embedder = _build_embeddings(
            [self._document_text(chunk) for chunk in chunks]
        )
        self.embeddings = _normalise(self.embeddings.astype(np.float32))
        self.vector_engine = "numpy"
        self._faiss = None
        if faiss is not None:
            index = faiss.IndexFlatIP(self.embeddings.shape[1])
            index.add(np.ascontiguousarray(self.embeddings))
            self._faiss = index
            self.vector_engine = "faiss"
        self.blob = "\n".join(
            " ".join(
                [
                    chunk.text,
                    chunk.heading,
                    chunk.title,
                    chunk.doc_id,
                    " ".join(chunk.instruments),
                ]
            )
            for chunk in chunks
        )

    @staticmethod
    def _document_text(chunk: Chunk) -> str:
        return "\n".join([chunk.title, chunk.heading, " ".join(chunk.instruments), chunk.text])

    def _embed_query(self, query: str) -> np.ndarray:
        if self.backend == "tfidf":
            return self._embedder.embed_query(query).astype(np.float32)
        vectors = list(self._embedder.embed([query]))
        return _normalise(np.array(vectors, dtype=np.float32))[0]

    def _dense_scores(self, query: str) -> np.ndarray:
        query_vector = self._embed_query(query)
        if self._faiss is not None:
            scores, ids = self._faiss.search(
                np.ascontiguousarray(query_vector.reshape(1, -1)),
                len(self.chunks),
            )
            out = np.zeros(len(self.chunks), dtype=np.float32)
            for score, index in zip(scores[0], ids[0]):
                if index >= 0:
                    out[index] = float(score)
            return out
        return self.embeddings @ query_vector

    def search(
        self,
        query: str,
        k: int = 6,
        mode: str = "hybrid",
        doc_ids: list[str] | None = None,
        expand: bool = True,
    ) -> list[Hit]:
        prepared = expand_query(query) if expand else query
        tokens = tokenize(prepared if expand else query)
        bm25_scores = self.bm25.get_scores(tokens)
        dense_scores = self._dense_scores(prepared if expand else query)
        candidates = [
            index
            for index, chunk in enumerate(self.chunks)
            if not doc_ids or chunk.doc_id in doc_ids
        ]
        if not candidates:
            return []
        bm25_norm = _minmax([float(bm25_scores[index]) for index in candidates])
        dense_norm = _minmax([float(dense_scores[index]) for index in candidates])
        query_terms = content_tokens(query)
        hits: list[Hit] = []
        for position, index in enumerate(candidates):
            chunk = self.chunks[index]
            coverage = _coverage(query_terms, chunk)
            if mode == "bm25":
                hybrid = bm25_norm[position]
                score = hybrid
            else:
                hybrid = 0.52 * bm25_norm[position] + 0.48 * dense_norm[position]
                heading_cov = _coverage(query_terms, chunk, heading_only=True)
                lexical = 0.78 * coverage + 0.22 * heading_cov
                score = 0.58 * hybrid + 0.42 * lexical
            hits.append(
                Hit(
                    chunk=chunk,
                    score=float(score),
                    bm25=float(bm25_scores[index]),
                    dense=float(dense_scores[index]),
                    coverage=coverage,
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:k]

    def support(self, query: str, hits: list[Hit]) -> float:
        if not hits:
            return 0.0
        terms = content_tokens(query)
        if not terms:
            return 0.0
        pooled: set[str] = set()
        for hit in hits[:3]:
            pooled.update(tokenize(hit.chunk.heading + " " + hit.chunk.text + " " + hit.chunk.title))
        covered = sum(1 for term in terms if term in pooled)
        return covered / len(terms)


_INDEX: RegulatoryIndex | None = None


def get_index() -> RegulatoryIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = RegulatoryIndex(load_chunks(CORPUS_DIR))
    return _INDEX


def reset_index() -> None:
    global _INDEX
    _INDEX = None


def _coverage(terms: list[str], chunk: Chunk, heading_only: bool = False) -> float:
    if not terms:
        return 0.0
    if heading_only:
        blob = set(tokenize(chunk.heading + " " + chunk.title))
    else:
        blob = set(tokenize(chunk.heading + " " + chunk.text + " " + chunk.title))
    return sum(1 for term in terms if term in blob) / len(terms)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if high - low < 1e-9:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _build_embeddings(texts: list[str]):
    mode = embedding_mode()
    if mode in {"auto", "fastembed"}:
        try:
            os.environ.setdefault("FASTEMBED_CACHE_PATH", str(DATA_DIR / "models"))
            from fastembed import TextEmbedding

            model = TextEmbedding("BAAI/bge-small-en-v1.5")
            vectors = np.array(list(model.embed(texts)), dtype=np.float32)
            return vectors, "bge-small-en-v1.5", model
        except Exception as exc:  # pragma: no cover
            if mode == "fastembed":
                raise
            log.warning("Falling back to TF-IDF embeddings: %s", exc)
    space = TfidfSpace(texts)
    return space.embed_documents(), "tfidf", space
