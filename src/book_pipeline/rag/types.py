"""Axis-local Pydantic types for the rag kernel.

`Chunk` represents a persisted LanceDB row (what lives in the table). It is
intentionally NOT in book_pipeline.interfaces.types (which hosts Protocol
contracts that flow between components). When a retriever queries a LanceDB
table and returns results to the bundler, each Chunk is mapped to a
`RetrievalHit` (see book_pipeline.interfaces.types.RetrievalHit) — that is the
cross-protocol boundary.

Schema must stay in lockstep with book_pipeline.rag.lance_schema.CHUNK_SCHEMA.
When adding a column, update BOTH this model AND CHUNK_SCHEMA in the same
change (plus a test in test_lance_schema.py). `chapter` was added per W-5
revision so arc_position retriever (Plan 04) can filter on chapter equality
rather than a fragile `heading_path LIKE 'Chapter N %'` clause.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Chunk(BaseModel):
    """One persisted RAG chunk row.

    Fields map 1:1 to CHUNK_SCHEMA in lance_schema.py (minus `embedding`, which
    is populated at ingest time from a BgeM3Embedder and written directly to the
    LanceDB row — it is not kept on the Chunk model itself because the embedding
    vector is derived, not authored content).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    text: str
    source_file: str
    heading_path: str
    rule_type: str = "rule"
    ingestion_run_id: str
    chapter: int | None = None


__all__ = ["Chunk"]
