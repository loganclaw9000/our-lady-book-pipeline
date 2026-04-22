"""Tests for book_pipeline.corpus_ingest.router.

Behavior under test (Plan 02-02 Task 2):
  - AXIS_NAMES is a frozen tuple of the 5 retriever names.
  - route_file_to_axis(path) is pure filename-stem-based primary routing:
      - our-lady-of-champion-brief.md           → ["historical", "metaphysics"]
      - our-lady-of-champion-engineering.md     → ["metaphysics"]
      - our-lady-of-champion-pantheon.md        → ["entity_state"]
      - our-lady-of-champion-secondary-characters.md → ["entity_state"]
      - our-lady-of-champion-outline.md         → ["arc_position"]
      - our-lady-of-champion-known-liberties.md → ["negative_constraint"]
      - our-lady-of-champion-relics.md          → ["metaphysics"]
      - our-lady-of-champion-glossary.md        → ["historical"]
      - our-lady-of-champion-maps.md            → ["historical"]
      - our-lady-of-champion-handoff.md         → []
  - Unknown stems raise ValueError.
  - Router is in the kernel — must not import book_specifics.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_axis_names_are_frozen_five() -> None:
    from book_pipeline.corpus_ingest.router import AXIS_NAMES

    assert isinstance(AXIS_NAMES, tuple)
    assert AXIS_NAMES == (
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
    )


def test_route_brief_returns_both_historical_and_metaphysics() -> None:
    """brief.md is the only multi-axis file. Heading-level split happens in the
    ingester via the injected heading_classifier (W-3)."""
    from book_pipeline.corpus_ingest.router import route_file_to_axis

    axes = route_file_to_axis(Path("our-lady-of-champion-brief.md"))
    assert set(axes) == {"historical", "metaphysics"}


def test_route_single_axis_files() -> None:
    from book_pipeline.corpus_ingest.router import route_file_to_axis

    cases = {
        "our-lady-of-champion-engineering.md": ["metaphysics"],
        "our-lady-of-champion-pantheon.md": ["entity_state"],
        "our-lady-of-champion-secondary-characters.md": ["entity_state"],
        "our-lady-of-champion-outline.md": ["arc_position"],
        "our-lady-of-champion-known-liberties.md": ["negative_constraint"],
        "our-lady-of-champion-relics.md": ["metaphysics"],
        "our-lady-of-champion-glossary.md": ["historical"],
        "our-lady-of-champion-maps.md": ["historical"],
    }
    for filename, expected in cases.items():
        assert route_file_to_axis(Path(filename)) == expected, (
            f"route_file_to_axis({filename!r}) expected {expected}"
        )


def test_route_handoff_returns_empty() -> None:
    """handoff.md is a meta-document; router returns [] so ingester skips it."""
    from book_pipeline.corpus_ingest.router import route_file_to_axis

    assert route_file_to_axis(Path("our-lady-of-champion-handoff.md")) == []


def test_route_unknown_raises_valueerror() -> None:
    from book_pipeline.corpus_ingest.router import route_file_to_axis

    with pytest.raises(ValueError, match="[Uu]nknown"):
        route_file_to_axis(Path("our-lady-of-champion-totally-fake.md"))


def test_route_accepts_full_path() -> None:
    """Router should route by filename stem regardless of parent directory."""
    from book_pipeline.corpus_ingest.router import route_file_to_axis

    axes = route_file_to_axis(Path("/some/other/dir/our-lady-of-champion-outline.md"))
    assert axes == ["arc_position"]


def test_router_module_does_not_import_book_specifics() -> None:
    """Kernel boundary: router.py is in the kernel (corpus_ingest) and MUST NOT
    import from book_specifics. Per-heading axis classification is DI'd by CLI."""
    import pathlib

    import book_pipeline.corpus_ingest.router as mod

    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "book_specifics" not in source, (
        "corpus_ingest.router must not reference book_specifics (ADR-004 / W-3)"
    )
