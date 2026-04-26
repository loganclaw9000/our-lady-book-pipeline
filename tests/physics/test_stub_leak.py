"""Tests for physics/stub_leak.py — Plan 07-04 PHYSICS-08.

Test coverage (per Plan 07-04 Task 1 <behavior>):
  Test 1 — empty / clean prose returns []
  Test 2 — ch11 sc03 line 119 canary "Establish: ..." returns 1 directive hit
  Test 3 — ALL 10 directive keywords in whitelist hit
  Test 3b — FALSE-POSITIVE GUARD per WARNING #5: 'goal'/'conflict'/'outcome'
            inline prose returns []
  Test 3c — CALIBRATION sweep: scan_stub_leak on canon/chapter_01..04.md
            returns [] (zero false-positives on frozen baseline)
  Test 4 — bracketed-label "[character intro]:" pattern detection
  Test 5 — case-insensitive directive matching ("ESTABLISH:" matches)
  Test 6 — DoS resistance: 100_000 spaces completes <100ms
  Test 7 — DoS resistance: 100_000 backslashes completes <100ms
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from book_pipeline.physics import STUB_LEAK_PATTERNS, scan_stub_leak
from book_pipeline.physics.stub_leak import _PATTERN_DIRECTIVE

# Canary fixture — literal stub leak from drafts/ch11/ch11_sc03.md line 119
# (D-17 + the failure-evidence anchor for PHYSICS-08).
CH11_SC03_CANARY = (
    "Establish: the friendship that will become Bernardo's death-witness in Ch 26."
)


def test_1_empty_returns_empty() -> None:
    """Test 1: empty + clean prose returns []."""
    assert scan_stub_leak("") == []
    assert scan_stub_leak("   ") == []
    assert scan_stub_leak(
        "Andrés knelt at the altar. The hum rose. He did not cross himself."
    ) == []


def test_2_ch11_canary_directive_hit() -> None:
    """Test 2: ch11 sc03 line 119 canary returns 1 directive hit on line 1."""
    hits = scan_stub_leak(CH11_SC03_CANARY)
    assert len(hits) == 1
    assert hits[0].pattern_id == "directive"
    assert hits[0].line_number == 1


@pytest.mark.parametrize(
    "keyword",
    [
        "Establish",
        "Resolve",
        "Set up",
        "Setup",
        "Beat",
        "Function",
        "Disaster",
        "Reaction",
        "Dilemma",
        "Decision",
    ],
)
def test_3_all_directive_keywords_match(keyword: str) -> None:
    """Test 3: all 10 directive keywords in whitelist trigger hits."""
    text = f"{keyword}: the inciting moment that opens the scene."
    hits = scan_stub_leak(text)
    assert len(hits) == 1, f"keyword={keyword!r} did not trigger"
    assert hits[0].pattern_id == "directive"


@pytest.mark.parametrize(
    "prose",
    [
        "His goal: to warn Xochitl.",
        "The conflict: father versus son.",
        "The outcome: she died.",
        # Capitalized variants too (case-insensitive whitelist must NOT include these).
        "His Goal: to warn Xochitl.",
        "The Conflict: father versus son.",
        "The Outcome: she died.",
    ],
)
def test_3b_false_positive_guard_goal_conflict_outcome(prose: str) -> None:
    """Test 3b (WARNING #5): 'goal'/'conflict'/'outcome' inline prose returns [].

    These three nouns are EXCLUDED from the directive whitelist because they
    have legitimate prose uses. Only stub-grammar verbs (Establish, Resolve,
    Set up, etc.) trigger the regex.
    """
    hits = scan_stub_leak(prose)
    assert hits == [], f"false-positive on {prose!r}: {hits}"


@pytest.mark.parametrize("chapter_num", [1, 2, 3, 4])
def test_3c_zero_false_positive_on_canon(chapter_num: int) -> None:
    """Test 3c (CALIBRATION): scan_stub_leak on ch01-04 canon returns [].

    The DIRECTIVE pattern's whitelist is the tightest set that catches the
    ch11 sc03 canary while producing ZERO matches on the four frozen-baseline
    chapters (PHYSICS-12 alignment).
    """
    canon_path = Path(f"canon/chapter_{chapter_num:02d}.md")
    if not canon_path.exists():
        pytest.skip(f"{canon_path} not committed")
    body = canon_path.read_text(encoding="utf-8")
    hits = scan_stub_leak(body)
    assert hits == [], (
        f"ch{chapter_num:02d}: scan_stub_leak produced "
        f"{len(hits)} false positives: {hits[:3]}"
    )


def test_4_bracketed_label_hit() -> None:
    """Test 4: '[character intro]: Bernardo enters' returns 1 bracketed_label hit."""
    hits = scan_stub_leak("[character intro]: Bernardo enters the courtyard.")
    assert len(hits) == 1
    assert hits[0].pattern_id == "bracketed_label"
    assert hits[0].line_number == 1


def test_5_case_insensitive_directive() -> None:
    """Test 5: directive whitelist is case-insensitive."""
    for variant in ("ESTABLISH:", "establish:", "Establish:", "EsTaBliSh:"):
        hits = scan_stub_leak(f"{variant} the opening beat.")
        assert len(hits) == 1, f"variant {variant!r} did not match"
        assert hits[0].pattern_id == "directive"


def test_6_dos_resistance_long_spaces() -> None:
    """Test 6 (T-07-04 mitigation): 100_000 spaces complete <100ms.

    Anchored line-start patterns + re.MULTILINE bound matching by line length.
    No nested quantifiers means no catastrophic backtracking.
    """
    pathological = " " * 100_000
    start = time.perf_counter()
    hits = scan_stub_leak(pathological)
    elapsed = time.perf_counter() - start
    assert hits == []
    assert elapsed < 0.1, f"100_000 spaces took {elapsed * 1000:.1f}ms (>100ms)"


def test_7_dos_resistance_long_backslashes() -> None:
    """Test 7 (T-07-04 mitigation): 100_000 backslashes complete <100ms."""
    pathological = "\\" * 100_000
    start = time.perf_counter()
    hits = scan_stub_leak(pathological)
    elapsed = time.perf_counter() - start
    assert hits == []
    assert elapsed < 0.1, f"100_000 backslashes took {elapsed * 1000:.1f}ms (>100ms)"


def test_pattern_module_exports() -> None:
    """STUB_LEAK_PATTERNS tuple exported and contains both patterns."""
    assert len(STUB_LEAK_PATTERNS) == 2


def test_directive_pattern_excludes_goal_conflict_outcome_at_re_level() -> None:
    """Defense-in-depth: the compiled regex literal must NOT contain Goal,
    Conflict, or Outcome (WARNING #5 — calibration test confirms; this
    asserts the whitelist directly so a future edit accidentally re-adding
    them surfaces in CI immediately).
    """
    pattern_text = _PATTERN_DIRECTIVE.pattern
    for forbidden in ("Goal", "Conflict", "Outcome"):
        assert forbidden not in pattern_text, (
            f"forbidden keyword {forbidden!r} found in DIRECTIVE pattern: "
            f"{pattern_text!r}"
        )
