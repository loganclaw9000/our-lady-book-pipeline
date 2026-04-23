"""book_pipeline.entity_extractor — per-chapter EntityCard extraction kernel.

Phase 4 Plan 04-03 lands OpusEntityExtractor (CORPUS-02): Claude Code CLI
backed extractor producing `entity-state/chapter_{NN:02d}_entities.json`
with `source_chapter_sha` stamped for V-3 stale-card detection.

Plan 04-01 ships only this empty package anchor so pyproject.toml's
import-linter contracts 1 + 2 can reference the dotted name before the
concrete impl lands.
"""

from __future__ import annotations

__all__: list[str] = []
