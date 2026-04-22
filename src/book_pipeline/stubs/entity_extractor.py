"""Stub EntityExtractor — NotImplementedError. Concrete impl lands in Phase 2 (CORPUS-02)."""

from __future__ import annotations

from book_pipeline.interfaces.entity_extractor import EntityExtractor
from book_pipeline.interfaces.types import EntityCard


class StubEntityExtractor:
    """Structurally satisfies EntityExtractor Protocol. NotImplementedError on every call."""

    def extract(
        self,
        chapter_text: str,
        chapter_num: int,
        chapter_sha: str,
        prior_cards: list[EntityCard],
    ) -> list[EntityCard]:
        raise NotImplementedError(
            "StubEntityExtractor.extract: concrete impl lands in Phase 2 (CORPUS-02)."
        )


_: EntityExtractor = StubEntityExtractor()
