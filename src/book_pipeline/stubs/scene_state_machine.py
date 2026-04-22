"""Stub SceneStateMachine — uniform method wrapper around the pure-function `transition`.

SceneStateMachine is NOT an LLM-calling Protocol (see
book_pipeline.interfaces.scene_state_machine). The `transition` helper is pure
Python and ready today. This stub exists for uniformity with the other 12 Protocol
stubs (FOUND-04 SC-4 isinstance assertion parity) and exposes `transition()` as
a bound method.
"""

from __future__ import annotations

from book_pipeline.interfaces.scene_state_machine import (
    SceneState,
    SceneStateRecord,
    transition,
)


class StubSceneStateMachine:
    """Thin wrapper around the pure-function transition helper."""

    def transition(
        self, record: SceneStateRecord, to_state: SceneState, note: str
    ) -> SceneStateRecord:
        """Delegate to book_pipeline.interfaces.scene_state_machine.transition."""
        return transition(record, to_state, note)
