"""Tests for book_pipeline.book_specifics.heading_classifier.

Per W-3 revision (Plan 02-02): heading-level axis classification for multi-axis
files (currently brief.md) uses an explicit allowlist table, NOT regex. Any
heading not in the table returns None → ingester falls back to the file's
primary axis.

Invariants:
  - Every value in BRIEF_HEADING_AXIS_MAP is in {"metaphysics", "historical"}.
  - At least one entry exists per value axis (both metaphysics and historical
    must be populated — otherwise one axis is unreachable for brief.md chunks).
  - classify_brief_heading returns mapped value for known keys.
  - classify_brief_heading returns None for unknown keys.
  - heading_classifier.py contains no `re.` imports / usage (W-3: no regex).
"""

from __future__ import annotations


def test_all_values_in_allowed_axis_set() -> None:
    from book_pipeline.book_specifics.heading_classifier import BRIEF_HEADING_AXIS_MAP

    allowed = {"metaphysics", "historical"}
    bad = {k: v for k, v in BRIEF_HEADING_AXIS_MAP.items() if v not in allowed}
    assert not bad, (
        f"BRIEF_HEADING_AXIS_MAP values must be in {sorted(allowed)}, offending entries: {bad}"
    )


def test_at_least_one_entry_per_axis() -> None:
    """Both metaphysics and historical axes must be reachable from brief.md."""
    from book_pipeline.book_specifics.heading_classifier import BRIEF_HEADING_AXIS_MAP

    values = set(BRIEF_HEADING_AXIS_MAP.values())
    assert "metaphysics" in values, (
        "BRIEF_HEADING_AXIS_MAP has no 'metaphysics' entries; "
        "brief.md metaphysics-flavored sections would be unreachable."
    )
    assert "historical" in values, (
        "BRIEF_HEADING_AXIS_MAP has no 'historical' entries; "
        "brief.md historical-flavored sections would be unreachable."
    )


def test_classify_returns_mapped_axis_for_known_keys() -> None:
    from book_pipeline.book_specifics.heading_classifier import (
        BRIEF_HEADING_AXIS_MAP,
        classify_brief_heading,
    )

    for key, expected in BRIEF_HEADING_AXIS_MAP.items():
        assert classify_brief_heading(key) == expected, (
            f"classify_brief_heading({key!r}) expected {expected!r}"
        )


def test_classify_returns_none_for_unknown_heading() -> None:
    from book_pipeline.book_specifics.heading_classifier import classify_brief_heading

    assert classify_brief_heading("Some Completely Unknown Heading > Nowhere") is None
    assert classify_brief_heading("") is None


def test_heading_classifier_module_has_no_regex() -> None:
    """W-3 regression guard: no regex library usage, allowlist table only.

    Inspects the module source for `re.` usage or `import re`. The W-3 revision
    explicitly replaces an ambiguous regex with an explicit allowlist to stop
    drift.
    """
    import pathlib

    import book_pipeline.book_specifics.heading_classifier as mod

    source_path = pathlib.Path(mod.__file__)
    text = source_path.read_text(encoding="utf-8")
    assert "import re" not in text, (
        "heading_classifier.py must not import re (W-3: explicit allowlist only)"
    )
    # Also check that `re.search(`, `re.match(`, `re.compile(` don't appear.
    for token in ("re.search(", "re.match(", "re.compile(", "re.fullmatch("):
        assert token not in text, (
            f"heading_classifier.py contains forbidden regex usage {token!r} (W-3 violation)"
        )
