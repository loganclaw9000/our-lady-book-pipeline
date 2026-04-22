"""Stub Critic — NotImplementedError. Concrete impl lands in Phase 3 (CRITIC-01) / Phase 4 (CRITIC-02)."""

from __future__ import annotations

from book_pipeline.interfaces.critic import Critic
from book_pipeline.interfaces.types import CriticRequest, CriticResponse


class StubCritic:
    """Structurally satisfies Critic Protocol. NotImplementedError on every call."""

    level: str = "scene"

    def review(self, request: CriticRequest) -> CriticResponse:
        raise NotImplementedError(
            "StubCritic.review: concrete impl lands in Phase 3 (CRITIC-01 scene-level) "
            "and Phase 4 (CRITIC-02 chapter-level)."
        )


_: Critic = StubCritic()
