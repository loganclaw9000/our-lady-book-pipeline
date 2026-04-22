"""ModeThresholdsConfig — typed loader for config/mode_thresholds.yaml.

Mode-A (voice-FT local) / Mode-B (frontier) dial thresholds per ADR-001,
plus oscillation + Telegram alert tuning.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource
from book_pipeline.drafter.sampling_profiles import SamplingProfiles


class VoiceFidelityBand(BaseModel):
    """OBS-03 voice-fidelity band (per V-2 pitfall)."""

    min: float = Field(ge=0.0, le=1.0)
    max: float = Field(ge=0.0, le=1.0)


class VoiceFidelityConfig(BaseModel):
    """OBS-03 voice-fidelity scoring thresholds + anchor set pin.

    Landed by Plan 03-02 Task 2. The `anchor_set_sha` is the 64-hex SHA over
    the curated anchor YAML (see `book_pipeline.voice_fidelity.anchors.AnchorSet.sha`);
    curate-anchors CLI rewrites it whenever the anchor set changes.

    Threshold invariants (enforced by `_check_threshold_interval`):
      - fail_threshold == flag_band_min
      - pass_threshold == flag_band_max
      - fail_threshold <= pass_threshold
      - pass_threshold < memorization_flag_threshold
    """

    anchor_set_sha: str
    pass_threshold: float = Field(ge=0.0, le=1.0)
    flag_band_min: float = Field(ge=0.0, le=1.0)
    flag_band_max: float = Field(ge=0.0, le=1.0)
    fail_threshold: float = Field(ge=0.0, le=1.0)
    memorization_flag_threshold: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_threshold_interval(self) -> VoiceFidelityConfig:
        if self.fail_threshold > self.pass_threshold:
            raise ValueError(
                f"fail_threshold ({self.fail_threshold}) must be <= "
                f"pass_threshold ({self.pass_threshold})"
            )
        if self.pass_threshold >= self.memorization_flag_threshold:
            raise ValueError(
                f"pass_threshold ({self.pass_threshold}) must be < "
                f"memorization_flag_threshold "
                f"({self.memorization_flag_threshold})"
            )
        if self.flag_band_min != self.fail_threshold:
            raise ValueError(
                f"flag_band_min ({self.flag_band_min}) must equal "
                f"fail_threshold ({self.fail_threshold})"
            )
        if self.flag_band_max != self.pass_threshold:
            raise ValueError(
                f"flag_band_max ({self.flag_band_max}) must equal "
                f"pass_threshold ({self.pass_threshold})"
            )
        return self


class ModeAConfig(BaseModel):
    """Mode A (local voice-FT) dial."""

    regen_budget_R: int = Field(ge=0)
    per_scene_cost_cap_usd: float = Field(ge=0.0)
    voice_fidelity_band: VoiceFidelityBand


class ModeBConfig(BaseModel):
    """Mode B (Anthropic frontier) dial."""

    model_id: str
    per_scene_cost_cap_usd: float = Field(ge=0.0)
    regen_attempts: int = Field(ge=0)
    prompt_cache_ttl: str


class OscillationConfig(BaseModel):
    """Oscillation detector — catches regen flip-flops across axes."""

    enabled: bool
    max_axis_flips: int = Field(ge=1)


class AlertsConfig(BaseModel):
    """Telegram alert tuning per ALERT-02."""

    telegram_cool_down_seconds: int = Field(ge=0)
    dedup_window_seconds: int = Field(ge=0)


class ModeThresholdsConfig(BaseSettings):
    """Root loader — the mode-dial configuration surface."""

    mode_a: ModeAConfig
    mode_b: ModeBConfig
    oscillation: OscillationConfig
    alerts: AlertsConfig
    preflag_beats: list[str]
    voice_fidelity: VoiceFidelityConfig
    # Plan 03-04: DRAFT-02 per-scene-type sampling profiles. default_factory
    # means legacy mode_thresholds.yaml files (without a sampling_profiles:
    # block) still validate — the drafter gets plan-pinned defaults.
    sampling_profiles: SamplingProfiles = Field(default_factory=SamplingProfiles)

    model_config = SettingsConfigDict(
        yaml_file="config/mode_thresholds.yaml",
        extra="forbid",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )
