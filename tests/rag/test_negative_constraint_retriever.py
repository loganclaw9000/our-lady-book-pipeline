"""Tests for book_pipeline.rag.retrievers.negative_constraint.NegativeConstraintRetriever.

Behavior under test (from 02-03-PLAN.md Task 2 <behavior>):
  - _where_clause(request) returns None for every SceneRequest (PITFALLS R-5).
  - retrieve returns up to final_k hits regardless of request content.
  - Same request run twice -> same query_fingerprint.
  - Protocol structural satisfaction (B-2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class _FakeEmbedder:
    revision_sha = "fake-neg-sha"

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)
        rng = np.random.default_rng(seed=abs(hash(tuple(texts))) % (2**32))
        arr = rng.standard_normal((len(texts), 1024)).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / norms


class _FakeReranker:
    def rerank(
        self, query: str, candidates: list[tuple[str, Any]], top_k: int = 8
    ) -> list[tuple[str, Any, float]]:
        scored = [
            (text, payload, 1.0 - (i * 0.05))
            for i, (text, payload) in enumerate(candidates)
        ]
        scored.sort(key=lambda t: t[2], reverse=True)
        return scored[:top_k]


def _make_row(chunk_id: str) -> dict[str, Any]:
    rng = np.random.default_rng(seed=abs(hash(chunk_id)) % (2**32))
    emb = rng.standard_normal(1024).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    return {
        "chunk_id": chunk_id,
        "text": f"don't do {chunk_id}",
        "source_file": "known-liberties.md",
        "heading_path": "Things to Avoid",
        "rule_type": "rule",
        "ingestion_run_id": "ing-neg-1",
        "chapter": None,
        "embedding": emb.tolist(),
    }


def _populate(db_path: Path, axis: str, rows: list[dict[str, Any]]) -> None:
    from book_pipeline.rag.lance_schema import open_or_create_table

    tbl = open_or_create_table(db_path, axis)
    if rows:
        tbl.add(rows)


def _scene_request_a() -> Any:
    from book_pipeline.interfaces.types import SceneRequest

    return SceneRequest(
        chapter=3,
        scene_index=2,
        pov="Andrés",
        date_iso="1519-08-16",
        location="Cempoala",
        beat_function="arrival",
    )


def _scene_request_b() -> Any:
    from book_pipeline.interfaces.types import SceneRequest

    return SceneRequest(
        chapter=14,
        scene_index=0,
        pov="Malintzin",
        date_iso="1520-03-01",
        location="Tenochtitlan",
        beat_function="reveal",
    )


# --- Tests --------------------------------------------------------------------


def test_negative_constraint_where_clause_is_none_for_every_request(
    tmp_path: Path,
) -> None:
    """PITFALLS R-5: _where_clause MUST return None; tag-based filtering lives in bundler."""
    from book_pipeline.rag.retrievers import NegativeConstraintRetriever

    r = NegativeConstraintRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert r._where_clause(_scene_request_a()) is None
    assert r._where_clause(_scene_request_b()) is None


def test_negative_constraint_returns_top_k_regardless_of_request(tmp_path: Path) -> None:
    from book_pipeline.rag.retrievers import NegativeConstraintRetriever

    rows = [_make_row(f"n{i}") for i in range(6)]
    _populate(tmp_path, "negative_constraint", rows)

    r = NegativeConstraintRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    # Both requests return full 6 (≤ final_k=8).
    out_a = r.retrieve(_scene_request_a())
    out_b = r.retrieve(_scene_request_b())
    assert len(out_a.hits) == 6
    assert len(out_b.hits) == 6


def test_negative_constraint_query_fingerprint_stable(tmp_path: Path) -> None:
    from book_pipeline.rag.retrievers import NegativeConstraintRetriever

    _populate(tmp_path, "negative_constraint", rows=[])
    r = NegativeConstraintRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    req = _scene_request_a()
    fp1 = r.retrieve(req).query_fingerprint
    fp2 = r.retrieve(req).query_fingerprint
    assert fp1 == fp2


def test_negative_constraint_satisfies_retriever_protocol(tmp_path: Path) -> None:
    """B-2 runtime_checkable protocol compliance."""
    from book_pipeline.interfaces.retriever import Retriever
    from book_pipeline.rag.retrievers import NegativeConstraintRetriever

    r = NegativeConstraintRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert isinstance(r, Retriever)
