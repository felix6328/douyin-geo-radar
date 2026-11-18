"""BM25 retrieval over the Chinese corpus (jieba tokenization)."""

from __future__ import annotations

import jieba
from rank_bm25 import BM25Okapi

from geolab.corpus import Document


def tokenize(text: str) -> list[str]:
    return [t.strip().lower() for t in jieba.cut(text) if t.strip() and not t.isspace()]


class Retriever:
    def __init__(self, docs: list[Document]):
        self.docs = list(docs)
        self._tokens = [tokenize(d.text) for d in self.docs]
        self._bm25 = BM25Okapi(self._tokens)

    def search(self, query: str, top_k: int = 4) -> list[tuple[Document, float, int]]:
        """Return (doc, score, 1-based rank) sorted by score desc."""
        scores = list(self._bm25.get_scores(tokenize(query)))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        out = []
        for rank, i in enumerate(order[:top_k], start=1):
            out.append((self.docs[i], float(scores[i]), rank))
        return out

    def rank_of(self, query: str, doc_id: str) -> tuple[int | None, float]:
        scores = list(self._bm25.get_scores(tokenize(query)))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        for rank, i in enumerate(order, start=1):
            if self.docs[i].doc_id == doc_id:
                return rank, float(scores[i])
        return None, 0.0
