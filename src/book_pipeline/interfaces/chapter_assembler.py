"""ChapterAssembler Protocol — joins committed scene drafts into one chapter.

Pre-conditions:
  - scene_drafts contains only COMMITTED scenes (state machine gate).
  - scene_drafts are in outline order for chapter_num.

Post-conditions:
  - Returned str is the concatenated chapter text ready for chapter-level critic
    (CRITIC-02) and for canon commit.
  - No LLM call; this is a deterministic join + transition-smoothing step.
  - No Event emitted (non-LLM operation).

Swap points: naive concat (Phase 3 default), transition-smoothing assembler
(Phase 4 if scene seams are rough).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import DraftResponse


@runtime_checkable
class ChapterAssembler(Protocol):
    """Join committed scene drafts into a chapter. Concrete impl in Phase 3 (LOOP-01)."""

    def assemble(self, scene_drafts: list[DraftResponse], chapter_num: int) -> str:
        """Return assembled chapter text."""
        ...
