"""DigestGenerator Protocol — weekly markdown digest (DIGEST-01).

Pre-conditions:
  - week_start_iso is an ISO-8601 date string (week boundary).
  - events, metrics, theses are pre-filtered to the week's scope.

Post-conditions:
  - Returned str is markdown ready to be written to digests/<week>.md and
    delivered to the Telegram channel.
  - EventLogger.emit(Event(role='digest_generator', ...)) was called before return.

Swap points: Anthropic Opus (primary), Sonnet fallback under cost pressure.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import Event


@runtime_checkable
class DigestGenerator(Protocol):
    """Weekly digest author. Concrete impl in Phase 5 (DIGEST-01)."""

    def generate(
        self,
        week_start_iso: str,
        events: list[Event],
        metrics: dict[str, object],
        theses: list[dict[str, object]],
    ) -> str:
        """Return a markdown digest summarizing the week."""
        ...
