"""Tests for physics/repetition_loop.py — Plan 07-04 PHYSICS-09.

Test coverage (per Plan 07-04 Task 1 <behavior>):
  Test 8 — default treatment + ch10 sc02-style canary returns >=1 hit
  Test 9 — LITURGICAL treatment + liturgical-style baseline returns 0 hits
  Test 10 — threshold dict overrides honored (default vs liturgical)
  Test 11 — healthy 1000-word scene returns [] (false-positive guard)
  Test 12 — mode_thresholds.yaml load surfaces physics_repetition.default
"""
from __future__ import annotations

from pathlib import Path

import pytest

from book_pipeline.physics import scan_repetition_loop
from book_pipeline.physics.repetition_loop import RepetitionHit
from book_pipeline.physics.schema import Treatment


# ch10 sc02-style canary (D-19 — degenerate-loop manuscript evidence).
CH10_SC02_CANARY = (
    "He did not sleep.\n"
    "He did not sleep the next night.\n"
    "He did not sleep the next night either.\n"
    "He was tired.\n"
    "He was not tired.\n"
    "He was tired and not tired."
)

# Liturgical baseline — 5+ distinct lines opening with "The hum" (chant pattern,
# echoes ch01 sc01). Default treatment: trigram rate / identical lines should
# fire. LITURGICAL treatment: thresholds raised, hits expected to be 0.
LITURGICAL_BASELINE = (
    "The hum.\n"
    "Always the hum.\n"
    "The hum did not stop.\n"
    "The hum continued.\n"
    "The hum was eternal."
)


def test_8_default_treatment_canary_fires() -> None:
    """Test 8: default treatment + ch10 sc02-style canary returns >=1 hit."""
    hits = scan_repetition_loop(CH10_SC02_CANARY)
    assert len(hits) >= 1, "default thresholds should catch the ch10 sc02 canary"
    # Should detect either trigram rate OR identical-line repetition.
    assert any(h.hit_type in ("trigram_rate", "identical_line") for h in hits)


def test_9_liturgical_treatment_baseline_passes() -> None:
    """Test 9: LITURGICAL treatment + liturgical baseline returns 0 hits.

    Pitfall 10 mitigation: chant/prayer/ritual prose has high repetition by
    design. LITURGICAL thresholds (0.40 trigram rate, 5 identical-line max)
    raise the bar to allow the form.
    """
    hits = scan_repetition_loop(LITURGICAL_BASELINE, treatment=Treatment.LITURGICAL)
    assert hits == [], (
        f"liturgical baseline should pass under LITURGICAL treatment, got: {hits}"
    )


def test_10_threshold_dict_overrides_honored() -> None:
    """Test 10: passing user-thresholds dict (default+liturgical sections) honored.

    Default thresholds applied when treatment != LITURGICAL → canary fails.
    Liturgical thresholds applied when treatment=LITURGICAL → liturgical
    baseline passes; canary still fails (line repetition >5 not crossed but
    let's verify the structure).
    """
    user_thresholds = {
        "default": {
            "trigram_repetition_rate_max": 0.15,
            "identical_line_count_max": 2,
        },
        "liturgical_treatment": {
            "trigram_repetition_rate_max": 0.40,
            "identical_line_count_max": 5,
        },
    }
    # Default thresholds vs canary — fires.
    canary_hits_default = scan_repetition_loop(
        CH10_SC02_CANARY, thresholds=user_thresholds
    )
    assert len(canary_hits_default) >= 1

    # LITURGICAL thresholds vs liturgical baseline — passes.
    lit_hits = scan_repetition_loop(
        LITURGICAL_BASELINE,
        treatment=Treatment.LITURGICAL,
        thresholds=user_thresholds,
    )
    assert lit_hits == []


def test_11_healthy_scene_passes() -> None:
    """Test 11: healthy 1000-word scene returns [] (false-positive guard)."""
    sentences = [
        "Andrés knelt at the altar in the chapel of Havana.",
        "The hum rose around him, a vibration in the bones of the building.",
        "Two candles burned beside the painted Lady of Antigua.",
        "His mother had brought him to the reliquary when he was five.",
        "The priest stepped away after the host went into his mouth.",
        "Outside on the mole, La Niña stood in her cradle, fifty feet of plate.",
        "The fleet rode at anchor; the morning tide would carry them west.",
        "He had written his mother that afternoon; the dusk boat would take it.",
        "The men of the Santa Bárbara watched him pass and they did not speak.",
        "He stopped at the rail at the far end of the mole and looked west.",
    ]
    # Fifty distinct sentences mixed up — ~1000 words, healthy variety.
    base = " ".join(sentences * 5)
    hits = scan_repetition_loop(base)
    assert hits == [], f"healthy varied prose should pass, got: {hits}"


def test_12_mode_thresholds_yaml_surface() -> None:
    """Test 12: ModeThresholdsConfig load surfaces physics_repetition.default
    with the expected default values."""
    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig

    cfg = ModeThresholdsConfig()
    assert cfg.physics_repetition.default.trigram_repetition_rate_max == pytest.approx(0.15)
    assert cfg.physics_repetition.default.identical_line_count_max == 2
    assert cfg.physics_repetition.liturgical_treatment.trigram_repetition_rate_max == pytest.approx(0.40)
    assert cfg.physics_repetition.liturgical_treatment.identical_line_count_max == 5


def test_yaml_file_contains_physics_repetition_section() -> None:
    """Sanity: the on-disk config file actually carries the new section."""
    yaml_text = Path("config/mode_thresholds.yaml").read_text(encoding="utf-8")
    assert "physics_repetition:" in yaml_text
    assert "trigram_repetition_rate_max" in yaml_text
    assert "identical_line_count_max" in yaml_text


def test_repetition_hit_shape() -> None:
    """RepetitionHit Pydantic shape — frozen, score+threshold+hit_type+detail."""
    hit = RepetitionHit(
        hit_type="identical_line",
        score=4.0,
        threshold=2.0,
        detail="He did not sleep.",
    )
    assert hit.hit_type == "identical_line"
    assert hit.score == 4.0
    assert hit.threshold == 2.0


def test_empty_text_returns_empty() -> None:
    """Empty/whitespace input returns []."""
    assert scan_repetition_loop("") == []
    assert scan_repetition_loop("   \n  ") == []
