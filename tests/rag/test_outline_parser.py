"""Tests for book_pipeline.rag.outline_parser.

Behavior under test (from 02-04-PLAN.md Task 1 <behavior>):
  Test 1: 3-chapter x 2-block x 2-beat synthetic outline -> 12 Beats with stable IDs.
  Test 2: Parse twice -> identical beat_id set and field-equal Beats.
  Test 3: Mutate only body text -> beat_ids and other fields stable, bodies differ.
  Test 4: Missing one # Chapter heading -> logs warning, returns partial Beats, no raise.
  Test 5: Duplicate chapter/block/beat numbers -> last-wins + warning logged.
  Test 6: Real OLoC outline -> parses to >0 Beats (canary for format changes).

Beat ID schema: `ch{chapter:02d}_b{block_lower}_beat{beat:02d}`
Stability rule: ID determined by NUMBERING only — body-text edits don't shift IDs.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

_FIXTURE = Path(__file__).parent / "fixtures" / "mini_outline.md"


def _load_fixture() -> str:
    return _FIXTURE.read_text()


# --- Test 1: synthetic outline round-trip -------------------------------------


def test_parse_outline_mini_produces_12_beats_with_stable_ids() -> None:
    from book_pipeline.rag.outline_parser import Beat, parse_outline

    beats = parse_outline(_load_fixture())
    assert len(beats) == 12, f"expected 12 beats, got {len(beats)}"

    beat_ids = {b.beat_id for b in beats}
    expected_ids = {
        "ch01_ba_beat01",
        "ch01_ba_beat02",
        "ch01_bb_beat01",
        "ch01_bb_beat02",
        "ch02_ba_beat01",
        "ch02_ba_beat02",
        "ch02_bb_beat01",
        "ch02_bb_beat02",
        "ch03_ba_beat01",
        "ch03_ba_beat02",
        "ch03_bb_beat01",
        "ch03_bb_beat02",
    }
    assert beat_ids == expected_ids

    # Every Beat has the expected field types.
    for b in beats:
        assert isinstance(b, Beat)
        assert isinstance(b.chapter, int) and 1 <= b.chapter <= 3
        assert b.block.lower() in {"a", "b"}
        assert b.beat in {1, 2}
        assert b.title  # non-empty
        assert b.heading_path  # non-empty
        assert b.body  # non-empty: fixture guarantees a body paragraph per beat


# --- Test 2: stability across re-parses --------------------------------------


def test_parse_outline_is_stable_across_reparses() -> None:
    from book_pipeline.rag.outline_parser import parse_outline

    text = _load_fixture()
    a = parse_outline(text)
    b = parse_outline(text)
    assert {x.beat_id for x in a} == {x.beat_id for x in b}

    # Field-by-field equality across the two runs.
    a_by_id = {beat.beat_id: beat for beat in a}
    b_by_id = {beat.beat_id: beat for beat in b}
    assert a_by_id == b_by_id


# --- Test 3: body-only mutation doesn't change beat_id -----------------------


def test_parse_outline_body_mutation_preserves_beat_ids() -> None:
    from book_pipeline.rag.outline_parser import parse_outline

    text = _load_fixture()
    original = parse_outline(text)

    # Add an extra paragraph into the Chapter 1 / Block A / Beat 1 body.
    mutated_text = text.replace(
        "Hook beat body. Establishes POV and stakes.",
        "Hook beat body. Establishes POV and stakes.\n\nEXTRA PARAGRAPH INJECTED.",
    )
    assert mutated_text != text, "sanity: fixture line must be present for this test"
    mutated = parse_outline(mutated_text)

    # Same number of beats + same IDs.
    assert len(mutated) == len(original)
    assert {x.beat_id for x in mutated} == {x.beat_id for x in original}

    # Other fields (chapter/block/beat/title/heading_path) equal per beat_id.
    orig_by_id = {beat.beat_id: beat for beat in original}
    mut_by_id = {beat.beat_id: beat for beat in mutated}
    for bid in orig_by_id:
        o = orig_by_id[bid]
        m = mut_by_id[bid]
        assert o.chapter == m.chapter
        assert o.block == m.block
        assert o.beat == m.beat
        assert o.title == m.title
        assert o.heading_path == m.heading_path

    # The Chapter 1 / Block A / Beat 1 body differs (the mutation target).
    assert orig_by_id["ch01_ba_beat01"].body != mut_by_id["ch01_ba_beat01"].body
    # Every other body is unchanged.
    for bid in orig_by_id:
        if bid != "ch01_ba_beat01":
            assert orig_by_id[bid].body == mut_by_id[bid].body, bid


# --- Test 4: lenient on malformed input --------------------------------------


def test_parse_outline_is_lenient_on_missing_chapter_heading(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from book_pipeline.rag.outline_parser import parse_outline

    # Remove the "# Chapter 2: Commitment" heading so the beats under it are
    # orphaned. Parser should log a warning and skip, not raise.
    text = _load_fixture().replace("# Chapter 2: Commitment\n", "")

    with caplog.at_level(logging.WARNING, logger="book_pipeline.rag.outline_parser"):
        beats = parse_outline(text)

    # We still expect beats from Chapter 1 + Chapter 3 (8 beats = 4 per chapter).
    # Chapter 2's 4 beats are orphaned under no chapter so may be dropped.
    # Minimum viable assertion: more than zero beats returned, and none
    # from chapter 2.
    assert len(beats) >= 8
    chapters_seen = {b.chapter for b in beats}
    assert 1 in chapters_seen
    assert 3 in chapters_seen
    assert 2 not in chapters_seen  # beats under removed chapter are dropped.

    # A warning was logged about the orphaned / missing section.
    assert any(
        rec.levelno >= logging.WARNING for rec in caplog.records
    ), "expected a warning log entry for the orphaned section"


# --- Test 5: duplicate beat IDs -> last-wins + warning ----------------------


def test_parse_outline_deduplicates_duplicate_beat_ids_last_wins(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from book_pipeline.rag.outline_parser import parse_outline

    # Construct a minimal outline with duplicate (chapter, block, beat) numbering.
    text = (
        "# Chapter 1: First\n\n"
        "## Block A: Opening\n\n"
        "### Beat 1: First Try\n\n"
        "Body of first try.\n\n"
        "## Block A: Opening Again\n\n"  # duplicate block A
        "### Beat 1: Second Try\n\n"
        "Body of second try.\n"
    )

    with caplog.at_level(logging.WARNING, logger="book_pipeline.rag.outline_parser"):
        beats = parse_outline(text)

    # Exactly one beat for (chapter=1, block=a, beat=1) — last-wins.
    matching = [b for b in beats if b.beat_id == "ch01_ba_beat01"]
    assert len(matching) == 1
    assert matching[0].title == "Second Try"
    assert "second try" in matching[0].body.lower()

    # Warning was logged about the dedupe.
    assert any(
        rec.levelno >= logging.WARNING for rec in caplog.records
    ), "expected a warning log entry for the duplicate beat_id"


# --- Test 6: real OLoC outline canary -----------------------------------------


def test_parse_outline_real_oloc_canary() -> None:
    """Canary for real-outline parse.

    The real OLoC outline uses `# ACT N —`, `## BLOCK N —`, `### Chapter N —`
    rather than the synthetic Chapter/Block/Beat headings. The parser has a
    lenient fallback that treats `### Chapter N` entries as single beats
    within their enclosing block. This test asserts the fallback produces
    >0 Beats; if the real outline format changes drastically and this test
    fails, the parser's fallback regex set needs to grow.

    Skipped if the real file is absent (CI on other machines).
    """
    from book_pipeline.rag.outline_parser import parse_outline

    real = Path("~/Source/our-lady-of-champion/our-lady-of-champion-outline.md").expanduser()
    if not real.exists():
        pytest.skip(f"real outline missing at {real}")

    beats = parse_outline(real.read_text())
    # The real outline has 27 chapters. Even in lenient-fallback mode we expect
    # at least 20 beats extracted. If this falls under 20, format may have
    # shifted drastically (act/block/chapter renamed).
    assert len(beats) >= 20, (
        f"real outline parsed to only {len(beats)} beats — format may have changed; "
        f"update outline_parser fallback regexes."
    )


# --- Empty-input handling ----------------------------------------------------


def test_parse_outline_empty_input_raises() -> None:
    from book_pipeline.rag.outline_parser import parse_outline

    with pytest.raises(ValueError, match="empty"):
        parse_outline("")

    with pytest.raises(ValueError, match="empty"):
        parse_outline("   \n\n   ")
