"""ThesisMatcher Protocol — opens/updates/closes theses from retrospective evidence (THESIS-01).

Pre-conditions:
  - retrospective is a completed Retrospective for one chapter.
  - open_theses is the current state of the thesis registry (list of thesis dicts).

Post-conditions:
  - Returned list contains one ThesisEvidence per affected thesis.
  - Action values are 'open', 'update', or 'close'; registry is updated by the
    orchestrator based on this output.
  - EventLogger.emit(Event(role='thesis_matcher', ...)) was called before return.

Swap points: Anthropic Opus (primary), deterministic keyword matcher (future
ablation for reproducibility).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import Retrospective, ThesisEvidence


@runtime_checkable
class ThesisMatcher(Protocol):
    """Evidence-driven thesis updater. Concrete impl in Phase 4 (THESIS-01)."""

    def match(
        self, retrospective: Retrospective, open_theses: list[dict[str, object]]
    ) -> list[ThesisEvidence]:
        """Resolve retrospective evidence against the open thesis registry."""
        ...
