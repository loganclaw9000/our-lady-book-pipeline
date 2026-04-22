"""Stub Regenerator — NotImplementedError. Concrete impl lands in Phase 3 (REGEN-01)."""

from __future__ import annotations

from book_pipeline.interfaces.regenerator import Regenerator
from book_pipeline.interfaces.types import DraftResponse, RegenRequest


class StubRegenerator:
    """Structurally satisfies Regenerator Protocol. NotImplementedError on every call."""

    def regenerate(self, request: RegenRequest) -> DraftResponse:
        raise NotImplementedError(
            "StubRegenerator.regenerate: concrete impl lands in Phase 3 (REGEN-01)."
        )


_: Regenerator = StubRegenerator()
