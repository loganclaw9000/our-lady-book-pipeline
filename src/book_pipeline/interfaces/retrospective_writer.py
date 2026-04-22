"""RetrospectiveWriter Protocol — per-chapter retrospective notes (RETRO-01).

Pre-conditions:
  - chapter_text has been committed to canon/.
  - chapter_events is the slice of events.jsonl for this chapter's drafting cycle.
  - prior_retros is the list of accepted retrospectives from earlier chapters.

Post-conditions:
  - Returned Retrospective.chapter_num matches the source chapter.
  - candidate_theses is a (possibly empty) list of thesis-candidate dicts —
    consumed downstream by ThesisMatcher.
  - EventLogger.emit(Event(role='retrospective_writer', ...)) was called before return.

Swap points: Anthropic Opus (primary), Sonnet fallback.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import Event, Retrospective


@runtime_checkable
class RetrospectiveWriter(Protocol):
    """Post-chapter retrospective generator. Concrete impl in Phase 4 (RETRO-01)."""

    def write(
        self,
        chapter_text: str,
        chapter_events: list[Event],
        prior_retros: list[Retrospective],
    ) -> Retrospective:
        """Produce a retrospective for one committed chapter."""
        ...
