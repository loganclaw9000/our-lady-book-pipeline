"""Tests for book_pipeline.rag.retrievers.historical.HistoricalRetriever.

Behavior under test (from 02-03-PLAN.md Task 2 <behavior>):
  - `name == "historical"`.
  - `retrieve(request)` returns RetrievalResult with retriever_name="historical",
    populated hits, each with non-empty source_path / chunk_id.
  - Protocol structural satisfaction (runtime_checkable Retriever).
  - B-2: `reindex` has no extra args beyond self.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import numpy as np


# --- Fakes (kept per-file for in-test isolation) ------------------------------


class _FakeEmbedder:
    revision_sha = "fake-hist-sha"

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


def _make_row(chunk_id: str, source_file: str) -> dict[str, Any]:
    rng = np.random.default_rng(seed=abs(hash(chunk_id)) % (2**32))
    emb = rng.standard_normal(1024).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    return {
        "chunk_id": chunk_id,
        "text": f"historical content for {chunk_id}",
        "source_file": source_file,
        "heading_path": "Historical Framework > Chapter 3",
        "rule_type": "rule",
        "ingestion_run_id": "ing-test-1",
        "chapter": 3,
        "embedding": emb.tolist(),
    }


def _populate(db_path: Path, axis: str, rows: list[dict[str, Any]]) -> None:
    from book_pipeline.rag.lance_schema import open_or_create_table

    tbl = open_or_create_table(db_path, axis)
    if rows:
        tbl.add(rows)


def _scene_request() -> Any:
    from book_pipeline.interfaces.types import SceneRequest

    return SceneRequest(
        chapter=3,
        scene_index=2,
        pov="Andrés",
        date_iso="1519-08-16",
        location="Cempoala",
        beat_function="arrival",
    )


# --- Tests --------------------------------------------------------------------


def test_historical_name_is_historical(tmp_path: Path) -> None:
    from book_pipeline.rag.retrievers import HistoricalRetriever

    r = HistoricalRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert r.name == "historical"


def test_historical_retrieve_populates_result(tmp_path: Path) -> None:
    from book_pipeline.rag.retrievers import HistoricalRetriever

    rows = [_make_row(f"h{i}", f"brief-{i % 2}.md") for i in range(5)]
    _populate(tmp_path, "historical", rows)

    r = HistoricalRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    out = r.retrieve(_scene_request())
    assert out.retriever_name == "historical"
    assert len(out.hits) == 5
    for hit in out.hits:
        assert hit.source_path != ""
        assert hit.chunk_id.startswith("h")


def test_historical_satisfies_retriever_protocol(tmp_path: Path) -> None:
    """B-2 runtime_checkable isinstance check."""
    from book_pipeline.interfaces.retriever import Retriever
    from book_pipeline.rag.retrievers import HistoricalRetriever

    r = HistoricalRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert isinstance(r, Retriever)


def test_historical_reindex_has_no_extra_args(tmp_path: Path) -> None:
    """B-2: inherited reindex signature is (self) -> None — no extra params."""
    from book_pipeline.rag.retrievers import HistoricalRetriever

    r = HistoricalRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    sig = inspect.signature(r.reindex)
    assert len(sig.parameters) == 0
