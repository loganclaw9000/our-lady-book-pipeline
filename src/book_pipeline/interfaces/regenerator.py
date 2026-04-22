"""Regenerator Protocol — scene-local regen driven by critic issues (REGEN-01).

Pre-conditions:
  - request.attempt_number >= 2 (attempt 1 is the original draft).
  - request.issues is the Critic's issue list from the previous attempt.

Post-conditions:
  - Returned DraftResponse.attempt_number == request.attempt_number.
  - Only the passages referenced by request.issues are rewritten (scene-local).
  - EventLogger.emit(Event(role='regenerator', ...)) was called before return.

Swap points: Mode-A regen (local), Mode-B regen after REGEN-02 escalation
(attempt_number > max_attempts).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import DraftResponse, RegenRequest


@runtime_checkable
class Regenerator(Protocol):
    """Scene-local regeneration. Concrete impl in Phase 3 (REGEN-01)."""

    def regenerate(self, request: RegenRequest) -> DraftResponse:
        """Rewrite affected passages based on critic issues."""
        ...
