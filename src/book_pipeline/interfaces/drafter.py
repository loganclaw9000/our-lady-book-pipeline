"""Drafter Protocol — Mode A (voice FT) and Mode B (frontier) share this interface.

Pre-conditions:
  - request.context_pack.fingerprint is set (ContextPackBundler has run).
  - For Mode A: voice-pin SHA has been verified against loaded weights (Phase 3).

Post-conditions:
  - Returned DraftResponse.mode matches self.mode.
  - output_sha is xxhash of scene_text.
  - EventLogger.emit(Event(role='drafter', mode=self.mode, ...)) was called
    before return (checkpoint_sha populated for Mode A).

Swap points: vLLM local (Mode A), Anthropic Opus (Mode B), future DPO variants.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import DraftRequest, DraftResponse


@runtime_checkable
class Drafter(Protocol):
    """Scene drafter. Concrete impls: DRAFT-01 (Mode A, Phase 3),
    DRAFT-02 (Mode B, Phase 3)."""

    mode: str  # "A" | "B"

    def draft(self, request: DraftRequest) -> DraftResponse:
        """Generate a scene draft. Emits a drafter Event before returning."""
        ...
