"""Tests for chapter_assembler quote-corruption normalizer (Plan 07-05 PHYSICS-11 / D-18).

Tests 6, 7, 7b (WARNING #6 NEGATIVE), 7c (WARNING #6 REAL FIXTURE) per plan.

The regex `(?<=["”\\w])\\s*\\.\\s*,\\s+` is anchored to fire ONLY after a
word-character or closing quote. Legitimate prose ("He paused, then
continued.") is left untouched; the real ch13 sc02 corruption shape
("Cortés stopped., I need her", "He ate., You are quiet") is repaired.
"""
from __future__ import annotations

from book_pipeline.chapter_assembler.concat import (
    QuoteRepair,
    _normalize_quote_corruption,
)

# ----------------------------------------------------------------- #
# Test 6 — no-op on clean prose                                     #
# ----------------------------------------------------------------- #


def test_6_no_op_on_clean_prose() -> None:
    """Body without the corruption pattern returns (input_unchanged, [])."""
    body = "normal dialogue.\nNext line."
    out, repairs = _normalize_quote_corruption(body)
    assert out == body
    assert repairs == []


# ----------------------------------------------------------------- #
# Test 7 — repair on canonical canary fixture                       #
# ----------------------------------------------------------------- #


def test_7_repairs_canonical_canary() -> None:
    """A canary `"Stop," he said., "we cannot."` returns a repaired body
    + non-empty repairs list."""
    canary = '"Stop," he said., "we cannot."'
    out, repairs = _normalize_quote_corruption(canary)
    assert len(repairs) >= 1
    assert ".," not in out, f"corruption not removed: {out!r}"
    assert isinstance(repairs[0], QuoteRepair)
    assert repairs[0].pattern_id == "dot_comma_corruption"


# ----------------------------------------------------------------- #
# Test 7b — WARNING #6 NEGATIVE: legitimate prose untouched          #
# ----------------------------------------------------------------- #


def test_normalize_quote_corruption_does_not_touch_legitimate_prose() -> None:
    """WARNING #6: tightened regex must NOT match `, ` in legitimate prose.

    These cases all contain `, ` after a word but with NO preceding `.,`
    sequence — the regex requires the literal `., ` separator which does
    not appear in well-formed English prose.
    """
    cases = [
        "He paused, then continued.",
        "After a moment, she replied.",
        "The night was cold, dark, and silent.",
        "She walked. He waited. Then, finally, she spoke.",
        "No comma here. Just two sentences.",
        "Cortés watched, but did not move.",
        "It was, in his judgment, a fair trade.",
    ]
    for text in cases:
        out, repairs = _normalize_quote_corruption(text)
        assert out == text, f"prose modified unexpectedly: {text!r} -> {out!r}"
        assert repairs == [], (
            f"unexpected repairs on legitimate prose {text!r}: {repairs}"
        )


# ----------------------------------------------------------------- #
# Test 7c — WARNING #6 REAL FIXTURE: ch13 corruption round-trip      #
# ----------------------------------------------------------------- #


def test_normalize_quote_corruption_round_trips_real_ch13_corruption() -> None:
    """WARNING #6: real ch13 corruption fixture round-trips with surrounding
    prose untouched. Only the `., ` sequences are repaired; the surrounding
    `paused, breathing` (legitimate `, `) MUST NOT be touched.
    """
    canary = '"Stop," he said., "we cannot." Then he paused, breathing hard.'
    out, repairs = _normalize_quote_corruption(canary)
    assert len(repairs) == 1, f"expected exactly 1 repair, got {len(repairs)}: {repairs}"
    # The `, ` AFTER 'paused' (no preceding `., `) MUST NOT be touched.
    assert "paused, breathing" in out, f"surrounding prose was modified: {out!r}"
    # The corruption itself MUST be repaired.
    assert "said., " not in out, f"corruption not repaired: {out!r}"
    assert 'said, "we cannot."' in out, f"unexpected repair shape: {out!r}"


# ----------------------------------------------------------------- #
# Real ch13 corruption shapes (multi-fixture round-trip)             #
# ----------------------------------------------------------------- #


def test_real_ch13_inter_word_corruption_repaired() -> None:
    """Real ch13 corruption: `<word>., <word>` (no closing quote anywhere)."""
    fixtures = [
        (
            "Cortés stopped., I need her with me, Captain.",
            "Cortés stopped, I need her with me, Captain.",
        ),
        (
            "He ate., You are quiet, Bernardo said., I am thinking., I know.",
            "He ate, You are quiet, Bernardo said, I am thinking, I know.",
        ),
    ]
    for src, expected in fixtures:
        out, repairs = _normalize_quote_corruption(src)
        assert out == expected, f"mismatch:\nsrc:  {src!r}\nout:  {out!r}\nwant: {expected!r}"
        assert len(repairs) >= 1


# ----------------------------------------------------------------- #
# QuoteRepair record carries before/after + line_number              #
# ----------------------------------------------------------------- #


def test_quote_repair_record_carries_audit_fields() -> None:
    body = "line one is clean.\nCortés stopped., I need her here.\nline three is clean."
    out, repairs = _normalize_quote_corruption(body)
    assert len(repairs) == 1
    r = repairs[0]
    assert r.line_number == 2
    assert "stopped." in r.before  # original line snippet
    assert "stopped," in r.after  # repaired line snippet
    # The unrelated lines are preserved.
    assert "line one is clean." in out
    assert "line three is clean." in out
