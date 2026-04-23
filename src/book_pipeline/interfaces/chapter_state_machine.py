"""ChapterStateMachine — persisted chapter state + pure transition() helper.

NEW in Phase 4 Plan 04-01, parallel to the frozen SceneStateMachine
(scene_state_machine.py). SceneStateMachine is NOT modified — Phase 4
introduces a separate ChapterStateMachine because chapter-grain states
(assembling, chapter_critiquing, post_commit_dag, dag_complete, ...) do not
map onto scene states.

Persisted as JSON to `drafts/chapter_buffer/ch{NN:02d}.state.json` via
atomic tmp+rename. Phase 4 Plan 04-04 implements the orchestrator that
calls `transition()` through the 4-step post-commit DAG
(canon → entity → rag → retro).

This module is intentionally NOT a typing.Protocol — it's a Pydantic model
(ChapterStateRecord in types.py) + Enum (ChapterState in types.py) + pure-
Python helper. It is kept under book_pipeline.interfaces/ for cohesion per
ARCHITECTURE.md §2.7, exactly mirroring scene_state_machine.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

from book_pipeline.interfaces.types import ChapterState, ChapterStateRecord


def transition(
    record: ChapterStateRecord, to_state: ChapterState, note: str
) -> ChapterStateRecord:
    """Return a new ChapterStateRecord with state advanced and a history entry appended.

    Pure function — caller is responsible for persisting the returned record.
    The input record is NOT mutated (model_copy produces a new instance).
    Exact parallel to `scene_state_machine.transition`.
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


__all__ = ["ChapterState", "ChapterStateRecord", "transition"]
