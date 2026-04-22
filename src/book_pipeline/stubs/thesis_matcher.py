"""Stub ThesisMatcher — NotImplementedError. Concrete impl lands in Phase 4 (THESIS-01)."""

from __future__ import annotations

from book_pipeline.interfaces.thesis_matcher import ThesisMatcher
from book_pipeline.interfaces.types import Retrospective, ThesisEvidence


class StubThesisMatcher:
    """Structurally satisfies ThesisMatcher Protocol. NotImplementedError on every call."""

    def match(
        self, retrospective: Retrospective, open_theses: list[dict[str, object]]
    ) -> list[ThesisEvidence]:
        raise NotImplementedError(
            "StubThesisMatcher.match: concrete impl lands in Phase 4 (THESIS-01)."
        )


_: ThesisMatcher = StubThesisMatcher()
