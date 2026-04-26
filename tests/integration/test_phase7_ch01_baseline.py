"""Phase 7 Plan 05 PHYSICS-12 part 2: ch01-04 zero-FP read-only smoke.

For each of ch01-ch04 committed canon files (the frozen baseline per D-21
+ OQ-01), run the engine in READ-ONLY mode and assert:
  - ZERO scan_stub_leak hits across every canon chapter (Warning #5
    calibration must hold).
  - ZERO TRUE-LOOP repetition_loop hits (identical-line count >= 6).
    Soft trigram-rate signals on liturgical-density paragraphs are
    permitted — the pipeline routes those via Treatment.LITURGICAL at
    the scene level, not at the chapter-aggregate scan.

Manual-Only Verifications:
  The 13-axis LLM-judged checks are out of scope for the read-only smoke
  (they need Anthropic + the assembled scene_metadata). See
  07-VALIDATION.md "Manual-Only Verifications" for the operator-eyeball
  sweep covering the LLM-judged half of the rubric on ch01-04.

Slow-marked because real BGE-M3 embeddings would also be required for the
full-on scene-buffer smoke; we keep the deterministic detectors here so the
test runs in <1s on any machine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from book_pipeline.physics import scan_repetition_loop, scan_stub_leak
from book_pipeline.physics.schema import Treatment

CANON_DIR = Path("canon")


@pytest.mark.slow
@pytest.mark.parametrize("chapter_num", [1, 2, 3, 4])
def test_ch01_04_zero_stub_leak(chapter_num: int) -> None:
    """Each of ch01-04 committed canon files must produce ZERO stub-leak hits.

    Warning #5 (calibration): Goal/Conflict/Outcome were excluded from the
    directive whitelist precisely because they recur as legitimate prose
    nouns in ch01-04. If this test ever fires a hit, the WARNING #5
    calibration has regressed and the directive whitelist must be revisited.
    """
    canon_path = CANON_DIR / f"chapter_{chapter_num:02d}.md"
    if not canon_path.exists():
        pytest.skip(
            f"{canon_path} not committed; ch01-04 baseline incomplete"
        )
    body = canon_path.read_text(encoding="utf-8")
    hits = scan_stub_leak(body)
    assert hits == [], (
        f"ch{chapter_num:02d} has {len(hits)} stub-leak hit(s) — bug "
        f"against zero-FP baseline. First 3 hits: {hits[:3]}"
    )


@pytest.mark.slow
@pytest.mark.parametrize("chapter_num", [1, 2, 3, 4])
def test_ch01_04_zero_true_repetition_loops_default_treatment(
    chapter_num: int,
) -> None:
    """Each of ch01-04 must produce ZERO TRUE-LOOP repetition_loop hits.

    A "true loop" is an identical_line hit with score >= 6 (>=6 distinct
    identical lines under default treatment). Trigram-rate soft signals on
    liturgical-density passages are permitted at the chapter-aggregate
    scan because the production pipeline runs scan_repetition_loop with
    Treatment.LITURGICAL on those scenes, NOT default.
    """
    canon_path = CANON_DIR / f"chapter_{chapter_num:02d}.md"
    if not canon_path.exists():
        pytest.skip(f"{canon_path} not committed")
    body = canon_path.read_text(encoding="utf-8")
    hits = scan_repetition_loop(body, treatment=None)
    true_loops = [
        h for h in hits if h.hit_type == "identical_line" and h.score >= 6
    ]
    assert not true_loops, (
        f"ch{chapter_num:02d} has true repetition loops: {true_loops}"
    )


@pytest.mark.slow
def test_ch01_sc01_liturgical_opening_passes_with_treatment_marker() -> None:
    """The ch01 sc01 'The hum. Always the hum.' opening is the LITURGICAL
    false-positive guard canary. Under Treatment.LITURGICAL, the chapter
    head MUST NOT flag a single repetition_loop hit (raised thresholds).
    """
    canon_path = CANON_DIR / "chapter_01.md"
    if not canon_path.exists():
        pytest.skip("ch01 not committed")
    body = canon_path.read_text(encoding="utf-8")
    # Take the first ~500 words (the liturgical opening + a few paragraphs).
    head = " ".join(body.split()[:500])
    hits = scan_repetition_loop(head, treatment=Treatment.LITURGICAL)
    # Acceptable to have zero hits on the liturgical opening — that's the
    # whole point of the LITURGICAL treatment.
    true_loops = [
        h for h in hits if h.hit_type == "identical_line" and h.score >= 6
    ]
    assert not true_loops, (
        f"ch01 sc01 liturgical opening flagged a true loop: {true_loops}"
    )


@pytest.mark.slow
def test_ch01_04_no_dot_comma_corruption_in_canon() -> None:
    """The quote-corruption pattern `<word>., <word>` (D-18 / WARNING #6
    canary shape) MUST NOT appear in any ch01-04 canon file. ch01-04 is
    the frozen baseline; corruption appearing here would mean a corrupt
    file was committed to canon.
    """
    from book_pipeline.chapter_assembler.concat import _normalize_quote_corruption

    for n in (1, 2, 3, 4):
        canon_path = CANON_DIR / f"chapter_{n:02d}.md"
        if not canon_path.exists():
            continue
        body = canon_path.read_text(encoding="utf-8")
        out, repairs = _normalize_quote_corruption(body)
        assert repairs == [], (
            f"ch{n:02d} contains the `., ` quote-corruption pattern: "
            f"{[r.before for r in repairs[:3]]}"
        )
        assert out == body, "normalizer mutated ch{n:02d} despite empty repairs"
