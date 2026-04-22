"""BgeReranker — cross-encoder reranking wrapper for RAG retrievers.

Model: BAAI/bge-reranker-v2-m3 (STACK.md pick). Top-k=8 per axis per
02-CONTEXT.md. The reranker runs AFTER dense vector search returns the top-50
candidates; it re-scores each (query, candidate_text) pair with a cross-encoder
and returns the best `top_k` ordered by score descending.

Lazy loading mirrors BgeM3Embedder: construction does NOT touch disk / GPU; the
`_ensure_loaded` helper materializes the model on first `rerank()` call with
non-empty candidates. Unit tests monkeypatch `sentence_transformers.CrossEncoder`
so no real inference runs in CI.

Mutation contract: `rerank()` does NOT mutate its `candidates` argument. Each
input tuple is passed through as-is (with the rerank score appended in a
brand-new outer tuple).
"""

from __future__ import annotations

from typing import Any


class BgeReranker:
    """Thin wrapper around sentence_transformers.CrossEncoder for BGE reranker-v2-m3.

    Shared across all 5 retrievers (one instance per process; reranker weights
    are large and inference is pure).
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cuda:0",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model: Any | None = None  # lazy-load sentinel

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        # Lazy import so `import book_pipeline.rag.reranker` does not pull in
        # sentence_transformers unless / until inference actually happens.
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self.model_name, device=self.device)

    def rerank(
        self,
        query: str,
        candidates: list[tuple[str, Any]],
        top_k: int = 8,
    ) -> list[tuple[str, Any, float]]:
        """Re-score `candidates` against `query` and return top_k sorted by score desc.

        Args:
          query: the query string the cross-encoder compares each candidate against.
          candidates: list of (text, payload) tuples. `payload` is opaque — we
            carry it through verbatim so the caller (LanceDBRetrieverBase) can
            look up the original LanceDB row by identity.
          top_k: how many (text, payload, score) triples to return.

        Returns:
          A list of (text, payload, float_score) triples of length
          `min(top_k, len(candidates))`, sorted by score descending.

        Degenerate: empty `candidates` returns [] WITHOUT loading the model.
        """
        if not candidates:
            return []
        self._ensure_loaded()
        assert self._model is not None
        pairs = [(query, text) for (text, _) in candidates]
        scores = self._model.predict(pairs)
        ranked = sorted(
            (
                (text, payload, float(score))
                for (text, payload), score in zip(candidates, scores, strict=True)
            ),
            key=lambda t: t[2],
            reverse=True,
        )
        return ranked[:top_k]


__all__ = ["BgeReranker"]
