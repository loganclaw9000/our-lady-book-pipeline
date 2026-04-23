"""book_pipeline.chapter_assembler — deterministic chapter assembly kernel.

Phase 4 Plan 04-02 lands ConcatAssembler (LOOP-02): joins COMMITTED scene
drafts into `canon/chapter_{NN}.md` in outline order with `\\n\\n---\\n\\n`
section-break markers. Re-running on identical inputs produces byte-identical
output (Phase 4 success criterion 1).

Kernel package — MUST NOT import from the book-domain layer. Import-linter
contract 1 (pyproject.toml) guards the boundary on every commit.
"""

from __future__ import annotations

from book_pipeline.chapter_assembler.concat import ConcatAssembler

__all__ = ["ConcatAssembler"]
