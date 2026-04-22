"""Tests for book_pipeline.drafter.sampling_profiles (Plan 03-04 Task 1).

Covers DRAFT-02 per-scene-type sampling profile dispatch:
- SamplingProfile + SamplingProfiles Pydantic models.
- resolve_profile(profiles, scene_type) lookup.
- Unknown scene_type raises ValueError.
"""
from __future__ import annotations

import pytest

from book_pipeline.drafter.sampling_profiles import (
    VALID_SCENE_TYPES,
    SamplingProfile,
    SamplingProfiles,
    resolve_profile,
)


# --- Test 1: resolve_profile returns prose profile with expected defaults ----

def test_resolve_profile_prose_defaults() -> None:
    profiles = SamplingProfiles()
    profile = resolve_profile(profiles, "prose")
    assert isinstance(profile, SamplingProfile)
    assert profile.temperature == 0.85
    assert profile.top_p == 0.92
    assert profile.repetition_penalty == 1.05
    assert profile.max_tokens == 2048


def test_resolve_profile_dialogue_heavy_defaults() -> None:
    profiles = SamplingProfiles()
    profile = resolve_profile(profiles, "dialogue_heavy")
    assert profile.temperature == 0.7
    assert profile.top_p == 0.90


def test_resolve_profile_structural_complex_defaults() -> None:
    profiles = SamplingProfiles()
    profile = resolve_profile(profiles, "structural_complex")
    assert profile.temperature == 0.6
    assert profile.top_p == 0.88


# --- Test 2: resolve_profile raises ValueError on unknown scene_type ---------

def test_resolve_profile_unknown_scene_type_raises() -> None:
    profiles = SamplingProfiles()
    with pytest.raises(ValueError):
        resolve_profile(profiles, "unknown")


def test_valid_scene_types_are_exactly_three() -> None:
    assert VALID_SCENE_TYPES == frozenset({"prose", "dialogue_heavy", "structural_complex"})


def test_sampling_profile_temperature_bounds() -> None:
    """Pydantic validators clamp temperature to 0<=t<=2."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SamplingProfile(temperature=-0.1, top_p=0.9, repetition_penalty=1.05, max_tokens=256)
    with pytest.raises(ValidationError):
        SamplingProfile(temperature=2.5, top_p=0.9, repetition_penalty=1.05, max_tokens=256)


def test_sampling_profile_top_p_bounds() -> None:
    """Pydantic validators: 0<top_p<=1."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SamplingProfile(temperature=0.7, top_p=0.0, repetition_penalty=1.05, max_tokens=256)
    with pytest.raises(ValidationError):
        SamplingProfile(temperature=0.7, top_p=1.5, repetition_penalty=1.05, max_tokens=256)


# --- Test 3: ModeThresholdsConfig loads legacy yaml without sampling_profiles -

def test_mode_thresholds_config_loads_legacy_yaml_without_sampling_profiles(
    tmp_path, monkeypatch
) -> None:
    """Test 3: sampling_profiles field has default_factory so legacy mode_thresholds.yaml
    (without the block) still validates. Post-Plan-03-04, the canonical yaml HAS the
    sampling_profiles: block — this test writes a legacy shape to tmp_path and confirms
    it still loads via default_factory.
    """
    legacy_yaml = tmp_path / "mode_thresholds_legacy.yaml"
    legacy_yaml.write_text(
        """
mode_a:
  regen_budget_R: 3
  per_scene_cost_cap_usd: 0.0
  voice_fidelity_band:
    min: 0.6
    max: 0.88
mode_b:
  model_id: claude-opus-4-7
  per_scene_cost_cap_usd: 2.0
  regen_attempts: 1
  prompt_cache_ttl: 1h
oscillation:
  enabled: true
  max_axis_flips: 2
alerts:
  telegram_cool_down_seconds: 3600
  dedup_window_seconds: 3600
preflag_beats: []
voice_fidelity:
  anchor_set_sha: 28fd890bc4c8afc1d0e8cc33b444bc0978002b96fbd7516ca50460773e97df31
  pass_threshold: 0.78
  flag_band_min: 0.75
  flag_band_max: 0.78
  fail_threshold: 0.75
  memorization_flag_threshold: 0.95
""".strip(),
        encoding="utf-8",
    )
    # Monkeypatch SettingsConfigDict yaml_file to legacy path.
    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig

    monkeypatch.setitem(
        ModeThresholdsConfig.model_config, "yaml_file", str(legacy_yaml)
    )
    cfg = ModeThresholdsConfig()
    # default_factory kicked in → sampling_profiles has defaults.
    assert cfg.sampling_profiles.prose.temperature == 0.85
    assert cfg.sampling_profiles.dialogue_heavy.temperature == 0.7
    assert cfg.sampling_profiles.structural_complex.temperature == 0.6
