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
"""

from book_pipeline.rag.budget import HARD_CAP, PER_AXIS_SOFT_CAPS, enforce_budget
from book_pipeline.rag.bundler import ContextPackBundlerImpl
from book_pipeline.rag.chunker import chunk_markdown
from book_pipeline.rag.conflict_detector import detect_conflicts
from book_pipeline.rag.embedding import EMBEDDING_DIM, BgeM3Embedder
from book_pipeline.rag.lance_schema import CHUNK_SCHEMA, open_or_create_table
from book_pipeline.rag.types import Chunk

__all__ = [
    "CHUNK_SCHEMA",
    "EMBEDDING_DIM",
    "HARD_CAP",
    "PER_AXIS_SOFT_CAPS",
    "BgeM3Embedder",
    "Chunk",
    "ContextPackBundlerImpl",
    "chunk_markdown",
    "detect_conflicts",
    "enforce_budget",
    "open_or_create_table",
]
