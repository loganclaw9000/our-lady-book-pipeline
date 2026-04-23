"""Claude ``--json-schema`` contract for OpusEntityExtractor (CORPUS-02).

``claude --json-schema <EntityExtractionResponse.model_json_schema()>`` forces
the CLI boundary to validate the payload shape; we re-validate post-receive
via ``EntityExtractionResponse.model_validate`` for defense-in-depth.

Plan 04-03 Task 1 contract (per CONTEXT.md grey-area c):
  {
    entities: list[EntityCard],
    chapter_num: int,
    extraction_timestamp: str   # ISO-8601
  }

EntityCard is the frozen Phase 1 shape (source_chapter_sha mandatory per V-3).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from book_pipeline.interfaces.types import EntityCard


class EntityExtractionResponse(BaseModel):
    """Top-level response schema for OpusEntityExtractor.

    ``entities`` may be empty if the chapter introduces no new/updated
    entities relative to ``prior_cards`` (caller may still emit an Event).
    ``extraction_timestamp`` is the extractor-side ISO-8601 UTC timestamp
    stamped at call time (not the LLM clock).
    """

    entities: list[EntityCard] = Field(default_factory=list)
    chapter_num: int
    extraction_timestamp: str


__all__ = ["EntityExtractionResponse"]
