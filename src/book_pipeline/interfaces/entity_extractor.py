"""EntityExtractor Protocol — post-commit extraction of per-chapter EntityCards (CORPUS-02).

Pre-conditions:
  - chapter_text is a COMMITTED canon chapter.
  - chapter_sha is the content hash of the committed chapter (for stale-card detection).
  - prior_cards are the entity cards from previous chapters (continuity context).

Post-conditions:
  - Returned list contains one EntityCard per entity present in the chapter.
  - Each EntityCard.source_chapter_sha equals chapter_sha (stale-card tombstone).
  - EventLogger.emit(Event(role='entity_extractor', ...)) was called before return.

Swap points: Anthropic Opus (primary), future domain-tuned extractor for Nahuatl
and secondary-character entities if Opus misses them.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import EntityCard


@runtime_checkable
class EntityExtractor(Protocol):
    """Per-chapter entity card generator. Concrete impl in Phase 2 (CORPUS-02)."""

    def extract(
        self,
        chapter_text: str,
        chapter_num: int,
        chapter_sha: str,
        prior_cards: list[EntityCard],
    ) -> list[EntityCard]:
        """Extract entity cards from a committed chapter."""
        ...
