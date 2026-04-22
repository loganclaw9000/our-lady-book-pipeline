"""Critic Protocol — rubric-driven scoring of a draft on 5 axes.

Pre-conditions:
  - request.rubric_version is set (config loader populated).
  - request.context_pack.fingerprint is set (for citation tracing).

Post-conditions:
  - CriticResponse.pass_per_axis has entries for all 5 axes.
  - overall_pass == all(pass_per_axis.values()) — enforced by implementation.
  - EventLogger.emit(Event(role='critic', rubric_version=..., ...)) was called
    before return.

Swap points: Anthropic Opus (scene-level, CRITIC-01), Anthropic Opus
(chapter-level, CRITIC-02), Sonnet fallback under cost pressure.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import CriticRequest, CriticResponse


@runtime_checkable
class Critic(Protocol):
    """Rubric-driven critic. Concrete impls: CRITIC-01 (scene, Phase 3),
    CRITIC-02 (chapter, Phase 4)."""

    level: str  # "scene" | "chapter"

    def review(self, request: CriticRequest) -> CriticResponse:
        """Score draft on 5 axes and emit structured issues."""
        ...
