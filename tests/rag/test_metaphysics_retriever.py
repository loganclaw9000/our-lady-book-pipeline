"""Tests for book_pipeline.rag.retrievers.metaphysics.MetaphysicsRetriever.

Behavior under test (from 02-03-PLAN.md Task 2 <behavior>):
  - Default constructor -> hits only rule_type='rule' chunks (PITFALLS R-4).
  - include_rule_types=('rule','example') -> hits may include rule OR example
    but never hypothetical.
  - _where_clause(request) returns a SQL IN-clause string containing the
    rule_types.
  - Malformed rule_type (SQL injection attempt) -> ValueError.
  - Protocol structural satisfaction (B-2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest


class _FakeEmbedder:
    revision_sha = "fake-meta-sha"

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


def _make_row(chunk_id: str, rule_type: str) -> dict[str, Any]:
    rng = np.random.default_rng(seed=abs(hash(chunk_id)) % (2**32))
    emb = rng.standard_normal(1024).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    return {
        "chunk_id": chunk_id,
        "text": f"metaphysics {rule_type} for {chunk_id}",
        "source_file": "engineering.md",
        "heading_path": "Engines > Rule",
        "rule_type": rule_type,
        "ingestion_run_id": "ing-test-m1",
        "chapter": None,
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


def test_metaphysics_default_filter_is_rule_only(tmp_path: Path) -> None:
    """Default: include_rule_types=('rule',); hypothetical + example excluded."""
    from book_pipeline.rag.retrievers import MetaphysicsRetriever

    rows = (
        [_make_row(f"r{i}", "rule") for i in range(4)]
        + [_make_row(f"h{i}", "hypothetical") for i in range(2)]
        + [_make_row("e0", "example")]
    )
    _populate(tmp_path, "metaphysics", rows)

    r = MetaphysicsRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    out = r.retrieve(_scene_request())
    # 4 rule rows only; hypo + example filtered out.
    assert len(out.hits) == 4
    for hit in out.hits:
        assert hit.metadata["rule_type"] == "rule"


def test_metaphysics_include_rule_types_widens_filter(tmp_path: Path) -> None:
    """include_rule_types=('rule','example') -> rule OR example, never hypothetical."""
    from book_pipeline.rag.retrievers import MetaphysicsRetriever

    rows = (
        [_make_row(f"r{i}", "rule") for i in range(3)]
        + [_make_row(f"h{i}", "hypothetical") for i in range(3)]
        + [_make_row(f"e{i}", "example") for i in range(2)]
    )
    _populate(tmp_path, "metaphysics", rows)

    r = MetaphysicsRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
        include_rule_types=("rule", "example"),
    )
    out = r.retrieve(_scene_request())
    # 3 rule + 2 example = 5 hits.
    assert len(out.hits) == 5
    for hit in out.hits:
        assert hit.metadata["rule_type"] in ("rule", "example")


def test_metaphysics_where_clause_is_sql_in_clause(tmp_path: Path) -> None:
    from book_pipeline.rag.retrievers import MetaphysicsRetriever

    r = MetaphysicsRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
        include_rule_types=("rule", "cross_reference"),
    )
    clause = r._where_clause(_scene_request())
    assert clause is not None
    assert "rule_type IN" in clause
    assert "'rule'" in clause
    assert "'cross_reference'" in clause


def test_metaphysics_injection_guard_rejects_malicious_rule_type(tmp_path: Path) -> None:
    """SQL-injection attempt via include_rule_types -> ValueError."""
    from book_pipeline.rag.retrievers import MetaphysicsRetriever

    r = MetaphysicsRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
        include_rule_types=("rule'; DROP TABLE",),
    )
    with pytest.raises(ValueError, match="Invalid rule_type"):
        r._where_clause(_scene_request())


def test_metaphysics_satisfies_retriever_protocol(tmp_path: Path) -> None:
    """B-2 runtime_checkable protocol compliance."""
    from book_pipeline.interfaces.retriever import Retriever
    from book_pipeline.rag.retrievers import MetaphysicsRetriever

    r = MetaphysicsRetriever(
        db_path=tmp_path,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
    )
    assert isinstance(r, Retriever)
