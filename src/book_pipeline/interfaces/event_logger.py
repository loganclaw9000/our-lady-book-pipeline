"""EventLogger Protocol — structured-event emission for OBS-01.

Pre-conditions:
  - Caller has constructed a valid Event BaseModel (all required fields populated).

Post-conditions:
  - Event is serialized to JSON and appended to runs/events.jsonl atomically.
  - Append is crash-safe (line-level atomicity — no partial writes).
  - Method is idempotent per Event.event_id (caller is responsible for uniqueness
    via xxhash of ts + role + caller + prompt_sha).
  - No network I/O; this is a local-disk-only operation in the default impl.

Swap points: stdlib-logging JSON-lines impl (Phase 1 plan 05), future
Logfire/OTel additional handler (deferred per STACK.md).

Note: This Protocol is the contract that plan 05 implements. The shape here is
frozen at the end of Phase 1 so later phases can compose EventLogger without
rework.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import Event


@runtime_checkable
class EventLogger(Protocol):
    """Structured event emitter for OBS-01. Concrete impl in Phase 1 plan 05."""

    def emit(self, event: Event) -> None:
        """Append one Event to runs/events.jsonl (line-atomic, crash-safe)."""
        ...
