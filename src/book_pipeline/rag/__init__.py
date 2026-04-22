"""book_pipeline.rag — kernel-eligible RAG primitives (chunking, embeddings, LanceDB schema).

Phase 2 Plan 01 lands the shared foundation; Plans 02-06 build ingestion,
retrievers, bundler, and CI gate on top. Book-specific corpus paths live
outside this kernel package (ADR-004 / FOUND-05) — import-linter contract 1
enforces that boundary on every commit.

Public surface:
  - Chunk (Pydantic model for a persisted chunk row)
  - chunk_markdown (heading-aware markdown → list[Chunk])
  - EMBEDDING_DIM (the frozen 1024 BGE-M3 dense-output dim)
  - BgeM3Embedder (lazy sentence-transformers wrapper)
  - CHUNK_SCHEMA (pyarrow schema with 8 fields; shared by all 5 axes)
  - open_or_create_table (LanceDB schema-enforced table opener)
  - build_retrievers_from_config (W-1 factory — shared by cli/ingest.py +
    cli/draft.py so retriever construction is not duplicated)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from book_pipeline.rag.budget import HARD_CAP, PER_AXIS_SOFT_CAPS, enforce_budget
from book_pipeline.rag.bundler import ContextPackBundlerImpl
from book_pipeline.rag.chunker import chunk_markdown
from book_pipeline.rag.conflict_detector import detect_conflicts
from book_pipeline.rag.embedding import EMBEDDING_DIM, BgeM3Embedder
from book_pipeline.rag.lance_schema import CHUNK_SCHEMA, open_or_create_table
from book_pipeline.rag.types import Chunk

if TYPE_CHECKING:  # pragma: no cover — typing-only imports to avoid cycles.
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig


def build_retrievers_from_config(
    *,
    cfg: RagRetrieversConfig,
    embedder: Any,
    reranker: Any,
    indexes_dir: Path,
    ingestion_run_id: str,
    outline_path: Path | None = None,
) -> dict[str, Any]:
    """Construct the 5 typed retrievers from a typed config (W-1 closure).

    Shared construction point for cli/ingest.py (post-ingest arc reindex) and
    cli/draft.py (Plan 03-07 scene-loop composition). Keyword-only signature
    matches the retrievers' __init__ convention (Plan 02-03 W-2).

    Args:
        cfg: Typed RagRetrieversConfig. Currently unused by the factory body
            (construction uses indexes_dir + shared deps directly), but kept
            in the signature so future per-axis config knobs land without
            re-threading callers. Non-dict/non-Pydantic values surface
            AttributeError at first attribute access.
        embedder: Shared BgeM3Embedder instance used by every retriever.
        reranker: Shared BgeReranker instance used by every retriever.
        indexes_dir: LanceDB directory containing the 5 typed tables.
        ingestion_run_id: Required positional — callers resolve this (never
            the factory; T-03-07-06 mitigation).
        outline_path: If provided, `arc_position` is included in the returned
            dict. Omit for cli/ingest.py's pre-reindex path where the arc
            axis is rebuilt separately by the post-ingest hook.

    Returns:
        dict[str, Retriever] keyed by axis name.

    Plan 03-07 W-1: cli/draft.py uses the same factory; `outline_path` is
    always passed at that site so the bundler sees 5 retrievers.
    """
    # Surface wrong-type cfg early (Test 5) — any BaseSettings/BaseModel has
    # 'retrievers' + 'embeddings' attributes; a bare int/None/dict does not.
    if not hasattr(cfg, "retrievers") and not hasattr(cfg, "embeddings"):
        raise AttributeError(
            f"build_retrievers_from_config: cfg is not a RagRetrieversConfig "
            f"(got {type(cfg).__name__})"
        )

    # Local imports keep mypy + import-linter scope tight; the retriever
    # classes are imported through their concrete modules (not via the package
    # __init__) so the monkeypatch spy in Test 3 can intercept each one.
    from book_pipeline.rag.retrievers.arc_position import ArcPositionRetriever
    from book_pipeline.rag.retrievers.entity_state import EntityStateRetriever
    from book_pipeline.rag.retrievers.historical import HistoricalRetriever
    from book_pipeline.rag.retrievers.metaphysics import MetaphysicsRetriever
    from book_pipeline.rag.retrievers.negative_constraint import (
        NegativeConstraintRetriever,
    )

    retrievers: dict[str, Any] = {
        "historical": HistoricalRetriever(
            db_path=indexes_dir,
            embedder=embedder,
            reranker=reranker,
            ingestion_run_id=ingestion_run_id,
        ),
        "metaphysics": MetaphysicsRetriever(
            db_path=indexes_dir,
            embedder=embedder,
            reranker=reranker,
            ingestion_run_id=ingestion_run_id,
        ),
        "entity_state": EntityStateRetriever(
            db_path=indexes_dir,
            embedder=embedder,
            reranker=reranker,
            ingestion_run_id=ingestion_run_id,
        ),
        "negative_constraint": NegativeConstraintRetriever(
            db_path=indexes_dir,
            embedder=embedder,
            reranker=reranker,
            ingestion_run_id=ingestion_run_id,
        ),
    }
    if outline_path is not None:
        retrievers["arc_position"] = ArcPositionRetriever(
            db_path=indexes_dir,
            outline_path=outline_path,
            embedder=embedder,
            reranker=reranker,
            ingestion_run_id=ingestion_run_id,
        )
    return retrievers


__all__ = [
    "CHUNK_SCHEMA",
    "EMBEDDING_DIM",
    "HARD_CAP",
    "PER_AXIS_SOFT_CAPS",
    "BgeM3Embedder",
    "Chunk",
    "ContextPackBundlerImpl",
    "build_retrievers_from_config",
    "chunk_markdown",
    "detect_conflicts",
    "enforce_budget",
    "open_or_create_table",
]
