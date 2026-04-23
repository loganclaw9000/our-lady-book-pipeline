"""book_pipeline.entity_extractor — per-chapter EntityCard extraction kernel.

Phase 4 Plan 04-03 lands OpusEntityExtractor (CORPUS-02): Anthropic Opus 4.7
backed extractor producing per-chapter entity cards with source_chapter_sha
stamped for V-3 stale-card detection. Incremental-update semantics: prior
cards are fed to Opus as a compact summary, and extract() returns only NEW
or UPDATED cards (unchanged entities are filtered out for idempotency).

Kernel discipline: no book-domain imports. Import-linter contracts 1+2 in
pyproject.toml enforce the kernel/book-domain boundary on every commit.
"""

from __future__ import annotations

from book_pipeline.entity_extractor.opus import (
    EntityExtractorBlocked,
    OpusEntityExtractor,
)
from book_pipeline.entity_extractor.schema import EntityExtractionResponse

__all__ = [
    "EntityExtractionResponse",
    "EntityExtractorBlocked",
    "OpusEntityExtractor",
]
