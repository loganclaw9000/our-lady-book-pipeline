"""Tests for post-ingest ArcPositionRetriever.reindex() wiring in cli/ingest.py.

After CorpusIngester.ingest() returns a non-skipped IngestionReport, the CLI
must:
  1. Construct ArcPositionRetriever with state-in-__init__ kwargs:
     db_path, outline_path, embedder, reranker, ingestion_run_id.
  2. Call `.reindex()` (no args, B-2 Protocol-conformant).

This test uses monkeypatching to intercept CorpusIngester and
ArcPositionRetriever so no real model load / no real LanceDB write occurs.
Validates the CLI composition layer's B-2 compliance.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def test_cli_ingest_calls_arc_reindex_with_correct_kwargs(
    monkeypatch: Any, tmp_path: Path, capsys: Any
) -> None:
    """Fake CorpusIngester + ArcPositionRetriever; assert B-2 wiring."""
    import book_pipeline.cli.ingest as ingest_mod

    recorded: dict[str, Any] = {}

    class _FakeIngestionReport:
        def __init__(self) -> None:
            self.skipped = False
            self.ingestion_run_id = "ing_20260422T080000000000Z_abcd1234"
            self.embed_model_revision = "fake-sha"
            self.db_version = "lancedb-0.30.2"
            self.wall_time_ms = 1234
            self.source_files: list[str] = []
            self.chunk_counts_per_axis: dict[str, int] = {
                "historical": 1,
                "metaphysics": 1,
                "entity_state": 1,
                "arc_position": 1,
                "negative_constraint": 1,
            }

        def model_dump_json(self, **_: Any) -> str:
            return "{}"

    class _FakeIngester:
        def __init__(self, **kwargs: Any) -> None:
            recorded["ingester_kwargs"] = kwargs

        def ingest(self, _indexes_dir: Path, *, force: bool = False) -> Any:
            recorded["ingest_force"] = force
            return _FakeIngestionReport()

    class _FakeEmbedder:
        def __init__(self, **kwargs: Any) -> None:
            recorded["embedder_kwargs"] = kwargs

        def embed_texts(self, texts: list[str]) -> Any:
            # Plan 07-02: cli/ingest.py invokes ingest_canonical_quantities
            # which calls embed_texts on the same shared embedder. Return a
            # numpy array shaped (len(texts), 1024) so the canonical
            # quantities ingest path completes without touching real BGE-M3.
            import numpy as np

            return np.zeros((len(texts), 1024), dtype=np.float32)

    class _FakeReranker:
        def __init__(self, **kwargs: Any) -> None:
            recorded["reranker_kwargs"] = kwargs

    class _FakeArcPositionRetriever:
        def __init__(self, **kwargs: Any) -> None:
            recorded["arc_init_kwargs"] = kwargs
            self.reindexed = False

        def reindex(self) -> None:  # B-2 no args
            recorded["arc_reindex_called"] = True
            self.reindexed = True

    monkeypatch.setattr(ingest_mod, "CorpusIngester", _FakeIngester)
    monkeypatch.setattr(ingest_mod, "BgeM3Embedder", _FakeEmbedder)
    # BgeReranker may or may not already be on the module; patch by import path.
    import book_pipeline.rag.reranker as reranker_mod

    monkeypatch.setattr(reranker_mod, "BgeReranker", _FakeReranker)
    import book_pipeline.rag.retrievers.arc_position as arc_mod

    monkeypatch.setattr(arc_mod, "ArcPositionRetriever", _FakeArcPositionRetriever)

    # JsonlEventLogger is constructed but never called; fake it.
    class _FakeEventLogger:
        def emit(self, _e: Any) -> None:
            return None

    import book_pipeline.observability as obs_mod

    monkeypatch.setattr(obs_mod, "JsonlEventLogger", _FakeEventLogger)

    args = argparse.Namespace(
        dry_run=False,
        force=False,
        indexes_dir=str(tmp_path / "indexes"),
        json=False,
    )
    rc = ingest_mod._run(args)
    assert rc == 0

    # B-2 assertions: arc reindex was called with no args.
    assert recorded.get("arc_reindex_called") is True, (
        "ArcPositionRetriever.reindex() was not called after ingest"
    )
    # __init__ kwargs must carry db_path, outline_path, embedder, reranker,
    # ingestion_run_id.
    arc_kwargs = recorded.get("arc_init_kwargs") or {}
    for key in ("db_path", "outline_path", "embedder", "reranker", "ingestion_run_id"):
        assert key in arc_kwargs, (
            f"ArcPositionRetriever init missing kwarg: {key}. Got: {list(arc_kwargs)}"
        )
    assert arc_kwargs["ingestion_run_id"] == "ing_20260422T080000000000Z_abcd1234"


def test_cli_ingest_skips_arc_reindex_when_skipped_report(
    monkeypatch: Any, tmp_path: Path, capsys: Any
) -> None:
    """If CorpusIngester.ingest() returns skipped=True, no arc reindex fires."""
    import book_pipeline.cli.ingest as ingest_mod

    called: dict[str, bool] = {"arc_reindex_called": False}

    class _FakeSkippedReport:
        def __init__(self) -> None:
            self.skipped = True
            self.ingestion_run_id = None
            self.embed_model_revision = None
            self.db_version = "lancedb-0.30.2"
            self.wall_time_ms = 0
            self.source_files: list[str] = []
            self.chunk_counts_per_axis: dict[str, int] = {}

        def model_dump_json(self, **_: Any) -> str:
            return "{}"

    class _FakeIngester:
        def __init__(self, **_: Any) -> None:
            pass

        def ingest(self, _i: Path, *, force: bool = False) -> Any:
            return _FakeSkippedReport()

    class _FakeArcPositionRetriever:
        def __init__(self, **_: Any) -> None:
            pass

        def reindex(self) -> None:
            called["arc_reindex_called"] = True

    monkeypatch.setattr(ingest_mod, "CorpusIngester", _FakeIngester)
    monkeypatch.setattr(ingest_mod, "BgeM3Embedder", lambda **kw: object())

    import book_pipeline.rag.reranker as reranker_mod

    monkeypatch.setattr(reranker_mod, "BgeReranker", lambda **kw: object())
    import book_pipeline.rag.retrievers.arc_position as arc_mod

    monkeypatch.setattr(arc_mod, "ArcPositionRetriever", _FakeArcPositionRetriever)

    class _FakeEventLogger:
        def emit(self, _e: Any) -> None:
            return None

    import book_pipeline.observability as obs_mod

    monkeypatch.setattr(obs_mod, "JsonlEventLogger", _FakeEventLogger)

    args = argparse.Namespace(
        dry_run=False,
        force=False,
        indexes_dir=str(tmp_path / "indexes"),
        json=False,
    )
    rc = ingest_mod._run(args)
    assert rc == 0
    assert called["arc_reindex_called"] is False
