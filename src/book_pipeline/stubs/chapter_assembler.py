"""Stub ChapterAssembler — NotImplementedError. Concrete impl lands in Phase 3 (LOOP-01)."""

from __future__ import annotations

from book_pipeline.interfaces.chapter_assembler import ChapterAssembler
from book_pipeline.interfaces.types import DraftResponse


class StubChapterAssembler:
    """Structurally satisfies ChapterAssembler Protocol. NotImplementedError on every call."""

    def assemble(self, scene_drafts: list[DraftResponse], chapter_num: int) -> str:
        raise NotImplementedError(
            "StubChapterAssembler.assemble: concrete impl lands in Phase 3 (LOOP-01)."
        )


_: ChapterAssembler = StubChapterAssembler()
