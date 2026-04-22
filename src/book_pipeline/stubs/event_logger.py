"""Stub EventLogger — NotImplementedError. Concrete impl lands in Phase 1 plan 05 (OBS-01)."""

from __future__ import annotations

from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.types import Event


class StubEventLogger:
    """Structurally satisfies EventLogger Protocol. NotImplementedError on every call."""

    def emit(self, event: Event) -> None:
        raise NotImplementedError(
            "StubEventLogger.emit: concrete impl lands in plan 05 (OBS-01 EventLogger)."
        )


_: EventLogger = StubEventLogger()
