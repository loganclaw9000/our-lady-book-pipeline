"""Tests for W-1 build_retrievers_from_config factory.

The factory lives in src/book_pipeline/rag/__init__.py and is the single
construction point for the 5 typed retrievers shared between cli/ingest.py
and cli/draft.py (Plan 03-07).

Covers:
  Test 1 — No outline_path → 4-retriever dict (historical/metaphysics/
           entity_state/negative_constraint). arc_position NOT in dict.
  Test 2 — With outline_path → 5-retriever dict including arc_position.
  Test 3 — Each retriever receives matching db_path + embedder + reranker +
           ingestion_run_id via spy-check on a monkeypatched ArcPositionRetriever.
  Test 5 — Wrong-type cfg arg → TypeError/ValueError (no silent duck-typing).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def test_factory_without_outline_path_returns_4_retrievers(tmp_path: Path) -> None:
    """Test 1: no outline_path → 4 retrievers, arc_position excluded."""
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig
    from book_pipeline.rag import build_retrievers_from_config

    cfg = RagRetrieversConfig()  # type: ignore[call-arg]
    indexes_dir = tmp_path / "indexes"
    indexes_dir.mkdir()

    class _FakeEmbedder:
        pass

    class _FakeReranker:
        pass

    retrievers = build_retrievers_from_config(
        cfg=cfg,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
        indexes_dir=indexes_dir,
        ingestion_run_id="ing_test_001",
    )

    assert isinstance(retrievers, dict)
    assert set(retrievers.keys()) == {
        "historical",
        "metaphysics",
        "entity_state",
        "negative_constraint",
    }
    assert "arc_position" not in retrievers


def test_factory_with_outline_path_returns_5_retrievers(tmp_path: Path) -> None:
    """Test 2: with outline_path → all 5 retrievers including arc_position."""
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig
    from book_pipeline.rag import build_retrievers_from_config

    cfg = RagRetrieversConfig()  # type: ignore[call-arg]
    indexes_dir = tmp_path / "indexes"
    indexes_dir.mkdir()
    outline_path = tmp_path / "outline.md"
    outline_path.write_text("# outline stub for test\n")

    class _FakeEmbedder:
        pass

    class _FakeReranker:
        pass

    retrievers = build_retrievers_from_config(
        cfg=cfg,
        embedder=_FakeEmbedder(),
        reranker=_FakeReranker(),
        indexes_dir=indexes_dir,
        ingestion_run_id="ing_test_002",
        outline_path=outline_path,
    )

    assert set(retrievers.keys()) == {
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
    }


def test_factory_passes_shared_deps_to_each_retriever(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Test 3: each retriever receives matching db_path / embedder / reranker /
    ingestion_run_id. Spy on ArcPositionRetriever constructor to verify the
    factory does NOT accidentally pass different deps per-retriever.
    """
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig
    from book_pipeline.rag import build_retrievers_from_config

    recorded: list[dict[str, Any]] = []

    class _SpyRetriever:
        """Sentinel-class spy; records its __init__ kwargs for later inspection."""

        def __init__(self, **kwargs: Any) -> None:
            recorded.append(kwargs)
            self.name = kwargs.get("name") or "spy"

        def reindex(self) -> None:
            return None

    # Patch the 5 retriever symbols the factory imports at call time.
    import book_pipeline.rag.retrievers.arc_position as arc_mod
    import book_pipeline.rag.retrievers.entity_state as ent_mod
    import book_pipeline.rag.retrievers.historical as hist_mod
    import book_pipeline.rag.retrievers.metaphysics as meta_mod
    import book_pipeline.rag.retrievers.negative_constraint as neg_mod

    monkeypatch.setattr(hist_mod, "HistoricalRetriever", _SpyRetriever)
    monkeypatch.setattr(meta_mod, "MetaphysicsRetriever", _SpyRetriever)
    monkeypatch.setattr(ent_mod, "EntityStateRetriever", _SpyRetriever)
    monkeypatch.setattr(neg_mod, "NegativeConstraintRetriever", _SpyRetriever)
    monkeypatch.setattr(arc_mod, "ArcPositionRetriever", _SpyRetriever)

    cfg = RagRetrieversConfig()  # type: ignore[call-arg]
    indexes_dir = tmp_path / "indexes"
    indexes_dir.mkdir()
    outline_path = tmp_path / "outline.md"
    outline_path.write_text("# outline stub\n")

    shared_embedder = object()
    shared_reranker = object()

    retrievers = build_retrievers_from_config(
        cfg=cfg,
        embedder=shared_embedder,
        reranker=shared_reranker,
        indexes_dir=indexes_dir,
        ingestion_run_id="ing_spy",
        outline_path=outline_path,
    )

    assert len(retrievers) == 5
    # All 5 retrievers constructed via spy.
    assert len(recorded) == 5
    # Each constructor received the SAME db_path + embedder + reranker +
    # ingestion_run_id — no per-retriever drift.
    for rec in recorded:
        assert rec["db_path"] == indexes_dir
        assert rec["embedder"] is shared_embedder
        assert rec["reranker"] is shared_reranker
        assert rec["ingestion_run_id"] == "ing_spy"
    # ArcPositionRetriever additionally receives outline_path.
    arc_recs = [r for r in recorded if "outline_path" in r]
    assert len(arc_recs) == 1
    assert arc_recs[0]["outline_path"] == outline_path


def test_factory_wrong_type_cfg_raises_typeerror(tmp_path: Path) -> None:
    """Test 5: passing a non-RagRetrieversConfig object doesn't silently work.

    The factory does not heavy-validate the cfg (it's a thin construction
    helper), but it DOES reach into cfg attributes; a bare dict/int/None
    surfaces an AttributeError. We accept any of AttributeError / TypeError
    (defense-in-depth, not strict-contract).
    """
    from book_pipeline.rag import build_retrievers_from_config

    indexes_dir = tmp_path / "indexes"
    indexes_dir.mkdir()

    class _FakeEmbedder:
        pass

    class _FakeReranker:
        pass

    # Wrong-type cfg: an int where RagRetrieversConfig is expected.
    import pytest

    with pytest.raises((AttributeError, TypeError)):
        build_retrievers_from_config(
            cfg=42,  # type: ignore[arg-type]
            embedder=_FakeEmbedder(),
            reranker=_FakeReranker(),
            indexes_dir=indexes_dir,
            ingestion_run_id="ing_test",
        )


def test_factory_exposed_from_rag_package() -> None:
    """build_retrievers_from_config must be importable from the rag package root
    and listed in __all__ (public surface for W-1)."""
    import book_pipeline.rag as rag_mod

    assert hasattr(rag_mod, "build_retrievers_from_config")
    assert "build_retrievers_from_config" in rag_mod.__all__
