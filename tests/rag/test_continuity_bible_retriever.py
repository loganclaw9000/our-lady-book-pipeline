"""Tests for book_pipeline.rag.retrievers.continuity_bible.ContinuityBibleRetriever.

Behavior under test (Plan 07-02 Task 1 <behavior>):
  - Test 1: ContinuityBibleRetriever instantiates with required ctor kwargs and
    exposes name="continuity_bible".
  - Test 2: _where_clause returns "rule_type = 'canonical_quantity'" verbatim.
  - Test 3 (slow, skipif indexes empty): retrieve(SceneRequest) for ch15 with
    location='Cempoala fortress' returns at least one row whose text contains
    a canonical-quantity value.
  - Test 4: Empty-table tolerance — calling retrieve() against an empty
    continuity_bible table returns a valid empty RetrievalResult (NOT raising).
  - Test 5: Protocol structural satisfaction (Retriever runtime_checkable).

Slow integration tests in this file are added in Task 3 once
`uv run book-pipeline ingest` writes 5 canonical-quantity rows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest


class _FakeEmbedder:
    revision_sha = "fake-cb-sha"

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


def _make_row(chunk_id: str, text: str) -> dict[str, Any]:
    rng = np.random.default_rng(seed=abs(hash(chunk_id)) % (2**32))
    emb = rng.standard_normal(1024).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": "config/canonical_quantities_seed.yaml",
        "heading_path": f"Canonical Quantity: {chunk_id}",
        "rule_type": "canonical_quantity",
        "ingestion_run_id": "ing-test-cb1",
        "chapter": None,
        "source_chapter_sha": None,
        "embedding": emb.tolist(),
    }


def _populate(db_path: Path, axis: str, rows: list[dict[str, Any]]) -> None:
    from book_pipeline.rag.lance_schema import open_or_create_table

    tbl = open_or_create_table(db_path, axis)
    if rows:
        tbl.add(rows)


def _scene_request_andres_cempoala() -> Any:
    from book_pipeline.interfaces.types import SceneRequest

    return SceneRequest(
        chapter=15,
        scene_index=2,
        pov="Andrés",
        date_iso="1519-08-30",
        location="Cempoala fortress",
        beat_function="warning",
    )


# --- Fast unit tests (Task 1) ----------------------------------------------


def test_continuity_bible_name_is_correct(tmp_path: Path) -> None:
    """ContinuityBibleRetriever.name == 'continuity_bible' (axis identity)."""
    from book_pipeline.rag.retrievers import ContinuityBibleRetriever

    r = ContinuityBibleRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert r.name == "continuity_bible"


def test_continuity_bible_where_clause_filters_canonical_quantity(
    tmp_path: Path,
) -> None:
    """_where_clause returns 'rule_type = \\'canonical_quantity\\'' verbatim
    (D-22 defense in depth — table holds only CB-01 rows but filter ensures
    cross-axis schema accidents are caught)."""
    from book_pipeline.rag.retrievers import ContinuityBibleRetriever

    r = ContinuityBibleRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    where = r._where_clause(_scene_request_andres_cempoala())
    assert where == "rule_type = 'canonical_quantity'"


def test_continuity_bible_empty_table_returns_empty_result(tmp_path: Path) -> None:
    """Empty-table tolerance — first invocation against a fresh db must NOT raise."""
    from book_pipeline.rag.retrievers import ContinuityBibleRetriever

    # Touch the axis table so it exists but is empty.
    _populate(tmp_path, "continuity_bible", rows=[])

    r = ContinuityBibleRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    out = r.retrieve(_scene_request_andres_cempoala())
    assert out.retriever_name == "continuity_bible"
    assert out.hits == []
    assert out.bytes_used == 0


def test_continuity_bible_returns_canonical_rows(tmp_path: Path) -> None:
    """With 5 canonical_quantity rows present, retrieve returns top-K hits
    that all carry rule_type='canonical_quantity' in their metadata."""
    from book_pipeline.rag.retrievers import ContinuityBibleRetriever

    rows = [
        _make_row(
            "canonical:andres_age",
            "Andrés Olivares: age 23 throughout the campaign window (ch01-ch14).",
        ),
        _make_row(
            "canonical:la_nina_height",
            "La Niña: 55-foot apex deck height above waterline.",
        ),
        _make_row(
            "canonical:santiago_del_paso_scale",
            "Santiago del Paso: 210-foot apex deterrent.",
        ),
        _make_row(
            "canonical:cholula_date",
            "Cholula stir: October 18, 1519 (canonical).",
        ),
        _make_row(
            "canonical:cempoala_arrival",
            "Cempoala arrival: June 2, 1519 (sole canonical arrival).",
        ),
    ]
    _populate(tmp_path, "continuity_bible", rows)

    r = ContinuityBibleRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    out = r.retrieve(_scene_request_andres_cempoala())
    assert len(out.hits) == 5
    for h in out.hits:
        assert h.metadata["rule_type"] == "canonical_quantity"


def test_continuity_bible_satisfies_retriever_protocol(tmp_path: Path) -> None:
    """B-2 runtime_checkable protocol compliance."""
    from book_pipeline.interfaces.retriever import Retriever
    from book_pipeline.rag.retrievers import ContinuityBibleRetriever

    r = ContinuityBibleRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert isinstance(r, Retriever)


# --- Slow integration tests (Task 3) ---------------------------------------
# Added by Task 3 after `uv run book-pipeline ingest` writes 5 canonical
# quantities to indexes/continuity_bible/.

INDEXES_DIR = Path(__file__).resolve().parents[2] / "indexes"

REQUIRED_AXES = (
    "historical",
    "metaphysics",
    "entity_state",
    "arc_position",
    "negative_constraint",
    "continuity_bible",
)


def _indexes_populated() -> bool:
    """True iff indexes/ contains the continuity_bible table directory.

    Mirrors the helper in tests/rag/test_golden_queries.py but checks for
    the new 6th axis specifically.
    """
    if not INDEXES_DIR.exists():
        return False
    cb_dir = INDEXES_DIR / "continuity_bible.lance"
    return cb_dir.is_dir()


def _build_real_retriever() -> Any:
    """Construct a real ContinuityBibleRetriever against indexes/."""
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig
    from book_pipeline.rag.embedding import BgeM3Embedder
    from book_pipeline.rag.reranker import BgeReranker
    from book_pipeline.rag.retrievers import ContinuityBibleRetriever

    cfg = RagRetrieversConfig()  # type: ignore[call-arg]
    embedder = BgeM3Embedder(
        model_name=cfg.embeddings.model, device=cfg.embeddings.device
    )
    reranker = BgeReranker(
        model_name=cfg.reranker.model, device=cfg.reranker.device
    )
    return ContinuityBibleRetriever(
        db_path=INDEXES_DIR, embedder=embedder, reranker=reranker
    )


@pytest.mark.slow
@pytest.mark.skipif(
    not _indexes_populated(),
    reason=(
        "indexes/continuity_bible.lance is empty; run "
        "`uv run book-pipeline ingest` first."
    ),
)
def test_canonical_value_for_cempoala() -> None:
    """Slow integration: query about Cempoala should surface the canonical
    arrival-date row (June 2, 1519)."""
    from book_pipeline.interfaces.types import SceneRequest

    retriever = _build_real_retriever()
    result = retriever.retrieve(
        SceneRequest(
            chapter=15,
            scene_index=2,
            pov="Andrés",
            date_iso="1519-08-30",
            location="Cempoala fortress",
            beat_function="warning",
        )
    )
    assert result.hits, "expected at least one hit for Cempoala query"
    blob = " ".join(h.text for h in result.hits)
    assert (
        "Cempoala" in blob or "1519-06-02" in blob or "June 2" in blob
    ), f"expected Cempoala canonical row in hits; got: {blob[:500]}"


@pytest.mark.slow
@pytest.mark.skipif(
    not _indexes_populated(),
    reason=(
        "indexes/continuity_bible.lance is empty; run "
        "`uv run book-pipeline ingest` first."
    ),
)
def test_canonical_value_for_cholula() -> None:
    """Slow integration: query about Cholula should surface the canonical
    October 18, 1519 date."""
    from book_pipeline.interfaces.types import SceneRequest

    retriever = _build_real_retriever()
    result = retriever.retrieve(
        SceneRequest(
            chapter=7,
            scene_index=1,
            pov="Andrés",
            date_iso="1519-10-18",
            location="Cholula",
            beat_function="reckoning",
        )
    )
    assert result.hits, "expected at least one hit for Cholula query"
    blob = " ".join(h.text for h in result.hits)
    assert (
        "Cholula" in blob
        or "Oct" in blob
        or "October" in blob
        or "1519-10-18" in blob
    ), f"expected Cholula canonical row in hits; got: {blob[:500]}"


@pytest.mark.slow
@pytest.mark.skipif(
    not _indexes_populated(),
    reason=(
        "indexes/continuity_bible.lance is empty; run "
        "`uv run book-pipeline ingest` first."
    ),
)
def test_canonical_value_for_andres() -> None:
    """Slow integration: query about Andrés should surface the canonical
    age=23 row."""
    from book_pipeline.interfaces.types import SceneRequest

    retriever = _build_real_retriever()
    result = retriever.retrieve(
        SceneRequest(
            chapter=15,
            scene_index=1,
            pov="Andrés",
            date_iso="1519-09-01",
            location="Cempoala",
            beat_function="reflection",
        )
    )
    assert result.hits, "expected at least one hit for Andrés query"
    blob = " ".join(h.text for h in result.hits)
    assert (
        "Andrés" in blob or "Andres" in blob or "23" in blob or "age" in blob
    ), f"expected Andrés canonical row in hits; got: {blob[:500]}"
