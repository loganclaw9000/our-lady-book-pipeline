"""Stub RetrospectiveWriter — NotImplementedError. Concrete impl lands in Phase 4 (RETRO-01)."""

from __future__ import annotations

from book_pipeline.interfaces.retrospective_writer import RetrospectiveWriter
from book_pipeline.interfaces.types import Event, Retrospective


class StubRetrospectiveWriter:
    """Structurally satisfies RetrospectiveWriter Protocol. NotImplementedError on every call."""

    def write(
        self,
        chapter_text: str,
        chapter_events: list[Event],
        prior_retros: list[Retrospective],
    ) -> Retrospective:
        raise NotImplementedError(
            "StubRetrospectiveWriter.write: concrete impl lands in Phase 4 (RETRO-01)."
        )


_: RetrospectiveWriter = StubRetrospectiveWriter()
