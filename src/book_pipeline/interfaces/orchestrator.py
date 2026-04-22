"""Orchestrator Protocol — drives the end-to-end scene-to-commit loop (LOOP-01).

Pre-conditions:
  - budget dict specifies per-cycle limits (max_scenes, max_mode_b_escapes,
    max_anthropic_spend_usd).
  - All subcomponents (Retriever, Drafter, Critic, Regenerator, ChapterAssembler,
    EntityExtractor, EventLogger) are wired and ready.

Post-conditions:
  - Scenes that reach COMMITTED state are written to drafts/scene_buffer/<chapter>/.
  - On chapter completion: ChapterAssembler runs, canon/<chapter>.md is written,
    EntityExtractor and RetrospectiveWriter are fired, theses are updated.
  - EventLogger has received Events for every LLM call made within the cycle.
  - run_cycle returns None; structured state is persisted on disk.

Swap points: single-threaded orchestrator (Phase 3), future parallel-chapter
orchestrator if latency pressure demands it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Orchestrator(Protocol):
    """Top-level scene-to-commit loop driver. Concrete impl in Phase 3 (LOOP-01)."""

    def run_cycle(self, budget: dict[str, object]) -> None:
        """Run one orchestration cycle (one pass of outline-pending scenes)."""
        ...
