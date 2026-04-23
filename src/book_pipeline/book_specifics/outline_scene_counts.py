"""Per-chapter expected scene count (Phase 4 gate-check source).

Populated from the real Our Lady of Champion outline structure. Falls back
to the nominal 3-scenes-per-chapter convention for chapters not explicitly
overridden. Chapter 99 is reserved for integration testing (see Plan
04-06 — 3-scene stub).

This table is book-specific; the kernel chapter_assembler/dag.py accepts
`expected_scene_count: int | None` via constructor injection, so the
kernel never imports this module. `book_pipeline.cli.chapter` is the
documented composition seam (Plan 04-05 ignore_imports exemption).
"""
from __future__ import annotations

# Derived from our-lady-of-champion-outline.md arc-position parser:
# 27 chapters nominal; most chapters are triptychs (3 scenes each) per
# outline convention. Some pre-flagged structurally-complex beats may
# have different counts — revisit during Phase 5 pre-flag work.
EXPECTED_SCENE_COUNTS: dict[int, int] = {
    **{n: 3 for n in range(1, 28)},  # chapters 1-27 default to 3 scenes each
    99: 3,  # reserved for Plan 04-06 integration test stub
}


def expected_scene_count(chapter_num: int) -> int:
    """Return the expected scene count for chapter_num, or 3 as a last resort."""
    return EXPECTED_SCENE_COUNTS.get(chapter_num, 3)


__all__ = ["EXPECTED_SCENE_COUNTS", "expected_scene_count"]
