"""book_pipeline.chapter_assembler — deterministic chapter assembly kernel.

Phase 4 Plan 04-02 lands ConcatAssembler (LOOP-02): joins COMMITTED scene
drafts into `canon/chapter_{NN}.md` in outline order with `\\n\\n---\\n\\n`
section-break markers. Re-running on identical inputs produces byte-identical
output (Phase 4 success criterion 1).

Plan 04-01 ships only this empty package anchor so pyproject.toml's
import-linter contracts 1 + 2 can reference the dotted name before the
concrete impl lands.
"""

from __future__ import annotations

__all__: list[str] = []
