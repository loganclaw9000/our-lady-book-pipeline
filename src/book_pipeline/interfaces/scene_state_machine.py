"""SceneStateMachine — persisted state record (not an LLM-calling Protocol).

Re-exports SceneState + SceneStateRecord from types.py and provides the pure-Python
`transition` helper that appends to the history list and atomically updates state.

Persisted as JSON to drafts/scene_buffer/<chapter>/<scene>.state.json (see
ARCHITECTURE.md §4.1). Phase 3 implements the orchestrator that calls transition().

This module is intentionally NOT a typing.Protocol — it's a Pydantic model + helper
function. It is kept under book_pipeline.interfaces/ for cohesion per ARCHITECTURE.md §2.7.
"""

from __future__ import annotations

from datetime import UTC, datetime

from book_pipeline.interfaces.types import SceneState, SceneStateRecord


def transition(record: SceneStateRecord, to_state: SceneState, note: str) -> SceneStateRecord:
    """Return a new SceneStateRecord with state advanced and a history entry appended.

    Pure function — caller is responsible for persisting the returned record.
    The input record is NOT mutated (model_copy produces a new instance).
    """
    updated = record.model_copy(
        update={
            "state": to_state,
            "history": [
                *record.history,
                {
                    "from": record.state.value,
                    "to": to_state.value,
                    "ts_iso": datetime.now(UTC).isoformat(),
                    "note": note,
                },
            ],
        }
    )
    return updated


__all__ = ["SceneState", "SceneStateRecord", "transition"]
