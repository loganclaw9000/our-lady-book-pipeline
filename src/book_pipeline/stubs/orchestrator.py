"""Stub Orchestrator — NotImplementedError. Concrete impl lands in Phase 3 (LOOP-01)."""

from __future__ import annotations

from book_pipeline.interfaces.orchestrator import Orchestrator


class StubOrchestrator:
    """Structurally satisfies Orchestrator Protocol. NotImplementedError on every call."""

    def run_cycle(self, budget: dict[str, object]) -> None:
        raise NotImplementedError(
            "StubOrchestrator.run_cycle: concrete impl lands in Phase 3 (LOOP-01)."
        )


_: Orchestrator = StubOrchestrator()
