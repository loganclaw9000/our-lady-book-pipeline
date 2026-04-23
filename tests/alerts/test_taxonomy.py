"""Tests for book_pipeline.alerts.taxonomy (Plan 05-03 Task 1).

Behavior (D-12):
  - HARD_BLOCK_CONDITIONS is a frozenset with exactly 8 entries matching the
    CONTEXT.md D-12 taxonomy.
  - Every condition has a corresponding MESSAGE_TEMPLATES entry (no KeyError
    at alert time when a condition is raised with its canonical detail shape).
"""

from __future__ import annotations

_EXPECTED_CONDITIONS = {
    "spend_cap_exceeded",
    "regen_stuck_loop",
    "rubric_conflict",
    "voice_drift_over_threshold",
    "checkpoint_sha_mismatch",
    "vllm_health_failed",
    "stale_cron_detected",
    "mode_b_exhausted",
}


def test_hard_block_conditions_exact_8() -> None:
    from book_pipeline.alerts.taxonomy import HARD_BLOCK_CONDITIONS

    assert isinstance(HARD_BLOCK_CONDITIONS, frozenset), (
        "HARD_BLOCK_CONDITIONS must be a frozenset (immutable, per D-12 contract)"
    )
    assert len(HARD_BLOCK_CONDITIONS) == 8, (
        f"HARD_BLOCK_CONDITIONS must have exactly 8 entries; got {len(HARD_BLOCK_CONDITIONS)}"
    )
    assert set(HARD_BLOCK_CONDITIONS) == _EXPECTED_CONDITIONS


def test_message_template_available_per_condition() -> None:
    from book_pipeline.alerts.taxonomy import (
        HARD_BLOCK_CONDITIONS,
        MESSAGE_TEMPLATES,
    )

    assert set(MESSAGE_TEMPLATES.keys()) == set(HARD_BLOCK_CONDITIONS), (
        "Every HARD_BLOCK_CONDITIONS entry must have a MESSAGE_TEMPLATES key "
        "(no KeyError at alert time)"
    )
    # All templates are non-empty strings.
    for cond, tmpl in MESSAGE_TEMPLATES.items():
        assert isinstance(tmpl, str) and tmpl.strip(), f"empty template for {cond!r}"
