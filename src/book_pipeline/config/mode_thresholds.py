"""ModeThresholdsConfig — typed loader for config/mode_thresholds.yaml.

Mode-A (voice-FT local) / Mode-B (frontier) dial thresholds per ADR-001,
plus oscillation + Telegram alert tuning.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource


class VoiceFidelityBand(BaseModel):
    """OBS-03 voice-fidelity band (per V-2 pitfall)."""

    min: float = Field(ge=0.0, le=1.0)
    max: float = Field(ge=0.0, le=1.0)


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
