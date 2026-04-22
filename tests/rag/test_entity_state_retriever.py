"""Tests for book_pipeline.rag.retrievers.entity_state.EntityStateRetriever.

Behavior under test (from 02-04-PLAN.md Task 2 <behavior>):
  Test 1: Empty table -> RetrievalResult(hits=[], bytes_used=0, retriever_name="entity_state",
          valid query_fingerprint) — the zero-cards-tolerance Phase 4 guarantee.
  Test 2: Populated table -> hits populated with metadata.heading_path set.
  Test 3: isinstance(r, Retriever) structural Protocol check (B-2).
  Test 4: inspect.signature(r.reindex).parameters is empty (B-2 frozen signature).
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import numpy as np


# --- Fakes (per-file isolation) ---------------------------------------------


class _FakeEmbedder:
    revision_sha = "fake-es-sha"

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


def _make_row(chunk_id: str, source_file: str, heading_path: str) -> dict[str, Any]:
    rng = np.random.default_rng(seed=abs(hash(chunk_id)) % (2**32))
    emb = rng.standard_normal(1024).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    return {
        "chunk_id": chunk_id,
        "text": f"entity card body for {chunk_id}",
        "source_file": source_file,
        "heading_path": heading_path,
        "rule_type": "rule",
        "ingestion_run_id": "ing-es-1",
        "chapter": None,  # entity cards typically have no chapter
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
        chapter=7,
        scene_index=1,
        pov="Malintzin",
        date_iso="1519-10-20",
        location="Cholula",
        beat_function="translation",
    )


# --- Tests ------------------------------------------------------------------


def test_entity_state_empty_table_returns_empty_result(tmp_path: Path) -> None:
    """Zero-cards-tolerance: the load-bearing Phase 4 guarantee."""
    from book_pipeline.rag.retrievers import EntityStateRetriever

    assert EntityStateRetriever is not None, (
        "EntityStateRetriever failed to import from book_pipeline.rag.retrievers; "
        "Plan 02-04 must land its source file so the B-1 import guard resolves."
    )
    # Create the empty axis table explicitly so open_or_create_table doesn't
    # hit an unconfigured path; this matches Plan 02's ingester behavior when
    # entity-state/ is empty.
    _populate(tmp_path, "entity_state", [])

    r = EntityStateRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    out = r.retrieve(_scene_request())

    assert out.retriever_name == "entity_state"
    assert out.hits == []
    assert out.bytes_used == 0
    assert out.query_fingerprint  # non-empty: xxhash hex is always non-empty


def test_entity_state_populated_table_returns_hits_with_heading_path(
    tmp_path: Path,
) -> None:
    from book_pipeline.rag.retrievers import EntityStateRetriever

    rows = [
        _make_row(f"ec{i}", f"entity_card_{i}.md", f"Pantheon > Deity > Aspect {i}")
        for i in range(5)
    ]
    _populate(tmp_path, "entity_state", rows)

    r = EntityStateRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    out = r.retrieve(_scene_request())

    assert out.retriever_name == "entity_state"
    assert len(out.hits) == 5
    for hit in out.hits:
        assert isinstance(hit.metadata["heading_path"], str)
        assert hit.metadata["heading_path"].startswith("Pantheon > Deity > Aspect")


def test_entity_state_satisfies_retriever_protocol(tmp_path: Path) -> None:
    """B-2: runtime_checkable isinstance(r, Retriever) succeeds."""
    from book_pipeline.interfaces.retriever import Retriever
    from book_pipeline.rag.retrievers import EntityStateRetriever

    r = EntityStateRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert isinstance(r, Retriever)


def test_entity_state_reindex_has_no_extra_args(tmp_path: Path) -> None:
    """B-2: inherited reindex(self) -> None signature — zero args after self."""
    from book_pipeline.rag.retrievers import EntityStateRetriever

    r = EntityStateRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    sig = inspect.signature(r.reindex)
    assert len(sig.parameters) == 0
