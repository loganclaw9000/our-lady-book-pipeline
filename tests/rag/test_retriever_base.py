"""Tests for book_pipeline.rag.retrievers.base.LanceDBRetrieverBase.

Behavior under test (from 02-03-PLAN.md Task 1 <behavior>):
  - Empty table -> RetrievalResult with hits=[], bytes_used=0, retriever_name=self.name.
  - Populated table -> top-final_k hits after candidate_k vector search + rerank.
  - query_fingerprint is stable across calls for the same SceneRequest.
  - index_fingerprint distinguishes tables with different ingestion_run_id sets.
  - _where_clause hook filters candidates (rule_type='rule' example).
  - B-2: reindex(self) -> None has NO extra positional/keyword args (frozen Protocol).
  - B-2: runtime_checkable isinstance(r, Retriever) succeeds.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import numpy as np

# --- Fake embedder / reranker / row fixtures ---------------------------------


class _FakeEmbedder:
    """Stand-in for BgeM3Embedder: returns deterministic 1024-d vectors."""

    revision_sha = "fake-emb-sha"

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)
        rng = np.random.default_rng(seed=abs(hash(tuple(texts))) % (2**32))
        arr = rng.standard_normal((len(texts), 1024)).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / norms


class _FakeReranker:
    """Stand-in for BgeReranker: assigns scores 1.0, 0.9, 0.8 ... in input order."""

    def rerank(
        self,
        query: str,
        candidates: list[tuple[str, Any]],
        top_k: int = 8,
    ) -> list[tuple[str, Any, float]]:
        scored = [
            (text, payload, 1.0 - (i * 0.1))
            for i, (text, payload) in enumerate(candidates)
        ]
        scored.sort(key=lambda t: t[2], reverse=True)
        return scored[:top_k]


def _make_row(
    chunk_id: str,
    text: str,
    source_file: str,
    heading_path: str,
    rule_type: str,
    ingestion_run_id: str,
    chapter: int | None,
) -> dict[str, Any]:
    """Build a single CHUNK_SCHEMA row (random 1024-d unit-norm embedding)."""
    rng = np.random.default_rng(seed=abs(hash(chunk_id)) % (2**32))
    emb = rng.standard_normal(1024).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": source_file,
        "heading_path": heading_path,
        "rule_type": rule_type,
        "ingestion_run_id": ingestion_run_id,
        "chapter": chapter,
        "embedding": emb.tolist(),
    }


def _populate_table(db_path: Path, axis: str, rows: list[dict[str, Any]]) -> None:
    """Create axis table under db_path with CHUNK_SCHEMA and insert `rows`."""
    from book_pipeline.rag.lance_schema import open_or_create_table

    tbl = open_or_create_table(db_path, axis)
    if rows:
        tbl.add(rows)


def _sample_scene_request() -> Any:
    from book_pipeline.interfaces.types import SceneRequest

    return SceneRequest(
        chapter=3,
        scene_index=2,
        pov="Andrés",
        date_iso="1519-08-16",
        location="Cempoala",
        beat_function="arrival",
    )


# --- Tests -------------------------------------------------------------------


def test_empty_table_returns_empty_result(tmp_path: Path) -> None:
    """Empty table -> RetrievalResult(hits=[], bytes_used=0, retriever_name=..)."""
    from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

    class _Concrete(LanceDBRetrieverBase):
        def _build_query_text(self, request: Any) -> str:
            return "hello"

    # Create empty table by calling open_or_create_table without rows.
    _populate_table(tmp_path, "historical", rows=[])

    r = _Concrete(
        name="historical",
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    out = r.retrieve(_sample_scene_request())
    assert out.retriever_name == "historical"
    assert out.hits == []
    assert out.bytes_used == 0
    assert isinstance(out.query_fingerprint, str)
    assert len(out.query_fingerprint) > 0


def test_populated_table_returns_hits_with_metadata(tmp_path: Path) -> None:
    """Populated table -> at most final_k hits; metadata carries the schema columns."""
    from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

    rows = [
        _make_row(
            chunk_id=f"chunk-{i}",
            text=f"content text {i}",
            source_file=f"src_{i % 3}.md",
            heading_path=f"H1 > H2.{i}",
            rule_type="rule" if i % 2 == 0 else "hypothetical",
            ingestion_run_id="ing-test-1",
            chapter=(i % 5) if i % 2 == 0 else None,
        )
        for i in range(10)
    ]
    _populate_table(tmp_path, "historical", rows)

    class _Concrete(LanceDBRetrieverBase):
        def _build_query_text(self, request: Any) -> str:
            return "query text"

    r = _Concrete(
        name="historical",
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
        candidate_k=50,
        final_k=8,
    )
    out = r.retrieve(_sample_scene_request())
    assert out.retriever_name == "historical"
    # 10 rows total; final_k=8 so we expect 8 hits.
    assert len(out.hits) == 8
    for hit in out.hits:
        assert hit.text != ""
        assert hit.source_path.startswith("src_")
        assert hit.chunk_id.startswith("chunk-")
        assert isinstance(hit.score, float)
        # Metadata carries rule_type, heading_path, ingestion_run_id, chapter.
        assert "rule_type" in hit.metadata
        assert "heading_path" in hit.metadata
        assert hit.metadata["ingestion_run_id"] == "ing-test-1"
        assert "chapter" in hit.metadata
    # bytes_used = sum of encoded hit texts.
    expected_bytes = sum(len(h.text.encode("utf-8")) for h in out.hits)
    assert out.bytes_used == expected_bytes


def test_query_fingerprint_stable_across_calls(tmp_path: Path) -> None:
    from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

    _populate_table(tmp_path, "historical", rows=[])

    class _Concrete(LanceDBRetrieverBase):
        def _build_query_text(self, request: Any) -> str:
            return "q"

    r = _Concrete(
        name="historical",
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    req = _sample_scene_request()
    fp1 = r.retrieve(req).query_fingerprint
    fp2 = r.retrieve(req).query_fingerprint
    assert fp1 == fp2


def test_index_fingerprint_distinguishes_ingestion_runs(tmp_path: Path) -> None:
    """Two tables with different ingestion_run_id sets -> different fingerprints."""
    from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

    db_a = tmp_path / "a"
    db_b = tmp_path / "b"
    rows_a = [
        _make_row("a0", "t", "s.md", "H", "rule", "ing-a-1", 1),
        _make_row("a1", "t", "s.md", "H", "rule", "ing-a-2", 1),
    ]
    rows_b = [
        _make_row("b0", "t", "s.md", "H", "rule", "ing-b-99", 2),
    ]
    _populate_table(db_a, "historical", rows_a)
    _populate_table(db_b, "historical", rows_b)

    class _Concrete(LanceDBRetrieverBase):
        def _build_query_text(self, request: Any) -> str:
            return "q"

    r_a = _Concrete(
        name="historical",
        db_path=db_a,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    r_b = _Concrete(
        name="historical",
        db_path=db_b,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    fp_a = r_a.index_fingerprint()
    fp_b = r_b.index_fingerprint()
    assert fp_a != fp_b
    assert fp_a != "empty"
    assert fp_b != "empty"


def test_index_fingerprint_empty_table_returns_literal_empty(tmp_path: Path) -> None:
    from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

    _populate_table(tmp_path, "historical", rows=[])

    class _Concrete(LanceDBRetrieverBase):
        def _build_query_text(self, request: Any) -> str:
            return "q"

    r = _Concrete(
        name="historical",
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert r.index_fingerprint() == "empty"


def test_where_clause_hook_filters_candidates(tmp_path: Path) -> None:
    """Subclass overriding _where_clause to 'rule_type = rule' -> only rule hits."""
    from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

    rows = [
        _make_row(f"c{i}", f"text {i}", "s.md", "H", "rule", "ing-1", None)
        for i in range(4)
    ] + [
        _make_row(f"h{i}", f"hypo {i}", "s.md", "H", "hypothetical", "ing-1", None)
        for i in range(4)
    ]
    _populate_table(tmp_path, "metaphysics", rows)

    class _Concrete(LanceDBRetrieverBase):
        def _build_query_text(self, request: Any) -> str:
            return "q"

        def _where_clause(self, request: Any) -> str | None:
            return "rule_type = 'rule'"

    r = _Concrete(
        name="metaphysics",
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    out = r.retrieve(_sample_scene_request())
    assert len(out.hits) == 4  # only 4 rule rows
    for hit in out.hits:
        assert hit.metadata["rule_type"] == "rule"


def test_reindex_has_no_extra_args_and_does_not_raise(tmp_path: Path) -> None:
    """B-2: reindex(self) -> None — EXACT Protocol signature."""
    from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

    _populate_table(tmp_path, "historical", rows=[])

    class _Concrete(LanceDBRetrieverBase):
        def _build_query_text(self, request: Any) -> str:
            return "q"

    r = _Concrete(
        name="historical",
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    # No positional, no keyword args beyond self.
    sig = inspect.signature(r.reindex)
    assert len(sig.parameters) == 0, (
        f"reindex must have no extra params (B-2); got: {list(sig.parameters)}"
    )
    # Does not raise.
    out = r.reindex()
    assert out is None


def test_isinstance_retriever_protocol(tmp_path: Path) -> None:
    """B-2: runtime_checkable Retriever protocol MUST recognize the subclass."""
    from book_pipeline.interfaces.retriever import Retriever
    from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

    _populate_table(tmp_path, "historical", rows=[])

    class _Concrete(LanceDBRetrieverBase):
        def _build_query_text(self, request: Any) -> str:
            return "q"

    r = _Concrete(
        name="historical",
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert isinstance(r, Retriever)
