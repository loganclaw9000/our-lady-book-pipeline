"""Tests for book_pipeline.book_specifics.corpus_paths.

Behavior under test (Plan 02-02 Task 1):
  - All 10 per-file constants (BRIEF, ENGINEERING, PANTHEON, SECONDARY_CHARACTERS,
    OUTLINE, KNOWN_LIBERTIES, RELICS, GLOSSARY, MAPS, HANDOFF) point at
    `our-lady-of-champion-<stem>.md` under CORPUS_ROOT.
  - CORPUS_FILES maps the 5 frozen axis names to ordered lists of Paths.
  - Every path in CORPUS_FILES.values() resolves to an on-disk file (skip if
    CORPUS_ROOT missing on this machine).
  - HANDOFF is defined but NOT in any axis list (meta-document).
"""

from __future__ import annotations

import pytest

AXIS_NAMES_FROZEN = {
    "historical",
    "metaphysics",
    "entity_state",
    "arc_position",
    "negative_constraint",
}


def test_corpus_root_points_at_our_lady_of_champion() -> None:
    from book_pipeline.book_specifics.corpus_paths import CORPUS_ROOT

    assert str(CORPUS_ROOT).endswith("our-lady-of-champion")


def test_per_file_constants_use_our_lady_prefix() -> None:
    """All per-file constants must reference `our-lady-of-champion-<stem>.md`."""
    from book_pipeline.book_specifics import corpus_paths as cp

    expected_stems = {
        "BRIEF": "brief",
        "ENGINEERING": "engineering",
        "PANTHEON": "pantheon",
        "SECONDARY_CHARACTERS": "secondary-characters",
        "OUTLINE": "outline",
        "KNOWN_LIBERTIES": "known-liberties",
        "RELICS": "relics",
        "GLOSSARY": "glossary",
        "MAPS": "maps",
        "HANDOFF": "handoff",
    }
    for const_name, stem in expected_stems.items():
        path = getattr(cp, const_name)
        assert path.name == f"our-lady-of-champion-{stem}.md", (
            f"{const_name} expected our-lady-of-champion-{stem}.md, got {path.name}"
        )


def test_corpus_files_mapping_axis_names() -> None:
    """CORPUS_FILES must map exactly the 5 FROZEN axis names."""
    from book_pipeline.book_specifics.corpus_paths import CORPUS_FILES

    assert set(CORPUS_FILES.keys()) == AXIS_NAMES_FROZEN, (
        f"CORPUS_FILES keys must equal {sorted(AXIS_NAMES_FROZEN)}, "
        f"got {sorted(CORPUS_FILES.keys())}"
    )


def test_handoff_not_in_any_axis() -> None:
    """HANDOFF is a meta-document and must NOT appear in any axis list."""
    from book_pipeline.book_specifics.corpus_paths import CORPUS_FILES, HANDOFF

    for axis, paths in CORPUS_FILES.items():
        assert HANDOFF not in paths, (
            f"HANDOFF should not be routed to any axis but appears in {axis!r}"
        )


def test_corpus_files_paths_exist_on_disk() -> None:
    """Every path in CORPUS_FILES.values() must resolve to an on-disk file.

    Skipped if CORPUS_ROOT is missing on this machine (e.g., fresh clone
    without the sibling corpus repo). The 10-file layout is frozen at
    ~/Source/our-lady-of-champion/ per PROJECT.md.
    """
    from book_pipeline.book_specifics.corpus_paths import CORPUS_FILES, CORPUS_ROOT

    if not CORPUS_ROOT.is_dir():
        pytest.skip(f"CORPUS_ROOT {CORPUS_ROOT} not present on this machine")

    missing: list[str] = []
    for axis, paths in CORPUS_FILES.items():
        for p in paths:
            if not p.is_file():
                missing.append(f"{axis}: {p}")
    assert not missing, "CORPUS_FILES references missing files:\n" + "\n".join(missing)


def test_brief_is_in_both_historical_and_metaphysics() -> None:
    """brief.md must appear in BOTH historical and metaphysics axes per routing table.

    Per-heading split is delegated to the injected heading_classifier at ingest
    time — the file-level router just reports both axes.
    """
    from book_pipeline.book_specifics.corpus_paths import BRIEF, CORPUS_FILES

    assert BRIEF in CORPUS_FILES["historical"], "brief.md missing from historical axis"
    assert BRIEF in CORPUS_FILES["metaphysics"], "brief.md missing from metaphysics axis"
