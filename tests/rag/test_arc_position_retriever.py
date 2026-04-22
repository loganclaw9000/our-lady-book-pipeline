"""Tests for book_pipeline.rag.retrievers.arc_position.ArcPositionRetriever.

Behavior under test (from 02-04-PLAN.md Task 2 <behavior>):
  Test 1: reindex() (no args) populates arc_position table with 12 rows whose
          chunk_ids match the beat_ids from parse_outline; chapter int column
          carries 1, 2, 3 per the mini fixture's 3 chapters.
  Test 2 (W-5): retrieve with SceneRequest(chapter=1) returns only chapter=1 hits
          — exact-equality filter, NOT LIKE-prefix.
  Test 3 (W-5): retrieve with SceneRequest(chapter=99) returns hits=[] on the
          same fixture (no chapter=99 rows). Proves no fragile string-matching bug.
  Test 4 (B-2): inspect.signature(r.reindex).parameters is empty (frozen signature).
  Test 5 (B-2): isinstance(r, Retriever) runtime_checkable Protocol success.
  Test 6: r.reindex() is idempotent — calling twice yields same beat_id set.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import numpy as np

_FIXTURE = Path(__file__).parent / "fixtures" / "mini_outline.md"


# --- Fakes ------------------------------------------------------------------


class _FakeEmbedder:
    revision_sha = "fake-ap-sha"

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


def _make_retriever(tmp_path: Path) -> Any:
    from book_pipeline.rag.retrievers import ArcPositionRetriever

    assert ArcPositionRetriever is not None, (
        "ArcPositionRetriever failed to import from book_pipeline.rag.retrievers; "
        "Plan 02-04 must land its source file so the B-1 import guard resolves."
    )
    return ArcPositionRetriever(
        db_path=tmp_path,
        outline_path=_FIXTURE,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
        ingestion_run_id="ing-ap-test-1",
    )


def _scene_request(chapter: int) -> Any:
    from book_pipeline.interfaces.types import SceneRequest

    return SceneRequest(
        chapter=chapter,
        scene_index=1,
        pov="Andrés",
        date_iso="1519-03-25",
        location="Potonchán",
        beat_function="inciting",
    )


# --- Tests ------------------------------------------------------------------


def test_arc_position_reindex_populates_12_rows_with_stable_beat_ids(
    tmp_path: Path,
) -> None:
    from book_pipeline.rag.lance_schema import open_or_create_table
    from book_pipeline.rag.outline_parser import parse_outline

    r = _make_retriever(tmp_path)
    r.reindex()  # no args (B-2)

    tbl = open_or_create_table(tmp_path, "arc_position")
    assert tbl.count_rows() == 12

    rows = tbl.to_arrow().to_pylist()
    actual_ids = {row["chunk_id"] for row in rows}
    expected_beats = parse_outline(_FIXTURE.read_text())
    expected_ids = {b.beat_id for b in expected_beats}
    assert actual_ids == expected_ids

    # chapter int column populated (W-5).
    chapters_seen = {row["chapter"] for row in rows}
    assert chapters_seen == {1, 2, 3}


def test_arc_position_retrieve_filters_by_chapter_exact_equality(
    tmp_path: Path,
) -> None:
    """W-5: retrieve with chapter=1 returns only chapter=1 hits."""
    r = _make_retriever(tmp_path)
    r.reindex()

    out = r.retrieve(_scene_request(chapter=1))
    assert out.retriever_name == "arc_position"
    assert len(out.hits) > 0
    for hit in out.hits:
        assert hit.metadata["chapter"] == 1


def test_arc_position_retrieve_chapter_99_returns_no_hits(tmp_path: Path) -> None:
    """W-5: exact-equality filter — no fragile prefix-matching leaks."""
    r = _make_retriever(tmp_path)
    r.reindex()

    out = r.retrieve(_scene_request(chapter=99))
    assert out.retriever_name == "arc_position"
    assert out.hits == []


def test_arc_position_reindex_has_no_extra_args(tmp_path: Path) -> None:
    """B-2: frozen Protocol signature — reindex takes only self."""
    r = _make_retriever(tmp_path)
    sig = inspect.signature(r.reindex)
    assert len(sig.parameters) == 0, (
        f"expected reindex to take only self; got {list(sig.parameters)}"
    )


def test_arc_position_satisfies_retriever_protocol(tmp_path: Path) -> None:
    """B-2: runtime_checkable isinstance with state-in-init pattern."""
    from book_pipeline.interfaces.retriever import Retriever

    r = _make_retriever(tmp_path)
    assert isinstance(r, Retriever)


def test_arc_position_reindex_is_idempotent(tmp_path: Path) -> None:
    """Calling reindex() twice on same outline yields the same beat_id set."""
    from book_pipeline.rag.lance_schema import open_or_create_table

    r = _make_retriever(tmp_path)
    r.reindex()
    tbl = open_or_create_table(tmp_path, "arc_position")
    first_ids = {row["chunk_id"] for row in tbl.to_arrow().to_pylist()}

    r.reindex()
    second_ids = {row["chunk_id"] for row in tbl.to_arrow().to_pylist()}

    assert first_ids == second_ids
    assert tbl.count_rows() == 12  # overwrite semantics: still exactly 12 rows.
