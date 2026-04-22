"""Stub Drafter — NotImplementedError. Concrete impl lands in Phase 3 (DRAFT-01 / DRAFT-02)."""

from __future__ import annotations

from book_pipeline.interfaces.drafter import Drafter
from book_pipeline.interfaces.types import DraftRequest, DraftResponse


class StubDrafter:
    """Structurally satisfies Drafter Protocol. NotImplementedError on every call.

    Defaults to Mode A; Phase 3 will instantiate real Mode-A and Mode-B variants.
    """

    mode: str = "A"

    def draft(self, request: DraftRequest) -> DraftResponse:
        raise NotImplementedError(
            "StubDrafter.draft: concrete impl lands in Phase 3 (DRAFT-01 for Mode A, "
            "DRAFT-02 for Mode B)."
        )


_: Drafter = StubDrafter()
