"""ModeThresholdsConfig — typed loader for config/mode_thresholds.yaml.

Mode-A (voice-FT local) / Mode-B (frontier) dial thresholds per ADR-001,
plus oscillation + Telegram alert tuning.

Phase 3 gap-closure (2026-04-21): added ``critic_backend:`` block for
backend-swappable critic inference (claude-code CLI vs Anthropic SDK).
Default = ``claude_code_cli`` — operator is on a Claude Max subscription
and flat-rate inference via the CLI is strictly cheaper than per-call
API billing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
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


class RegenConfig(BaseModel):
    """Plan 05-02 D-05/D-06 — R-cap + per-scene USD spend cap.

    Additive under the Phase 1 freeze — no existing ModeThresholdsConfig
    field is renamed or removed.

    ``r_cap_mode_a`` = number of Mode-A regen attempts allowed BEFORE
    escalating to Mode-B (default 3 → 4 total attempts = 1 initial + 3
    regens). Attempt #4's critic-fail triggers Mode-B escalation.

    ``spend_cap_usd_per_scene`` = hard abort threshold for cumulative USD
    spend on one scene across drafter / critic / regenerator / mode_b
    events (default $0.75 per D-06).
    """

    r_cap_mode_a: int = Field(default=3, gt=0)
    spend_cap_usd_per_scene: float = Field(default=0.75, gt=0.0)


class PhysicsRepetitionThresholds(BaseModel):
    """One threshold profile for repetition_loop (default OR liturgical).

    Plan 07-04 PHYSICS-09 + Pitfall 10. ``identical_line_count_max`` is the
    MAX permitted number of distinct identical lines — ``>=N+1`` fails.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trigram_repetition_rate_max: float = Field(default=0.15, ge=0.0, le=1.0)
    identical_line_count_max: int = Field(default=2, ge=0)


class PhysicsRepetitionConfig(BaseModel):
    """physics_repetition section: default + liturgical_treatment thresholds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default: PhysicsRepetitionThresholds = Field(
        default_factory=PhysicsRepetitionThresholds
    )
    liturgical_treatment: PhysicsRepetitionThresholds = Field(
        default_factory=lambda: PhysicsRepetitionThresholds(
            trigram_repetition_rate_max=0.40,
            identical_line_count_max=5,
        )
    )


class CriticBackendConfig(BaseModel):
    """Which backend SceneCritic + SceneLocalRegenerator use for Opus calls.

    Phase 3 gap-closure (2026-04-21): the operator is on a Claude Max
    subscription; flat-rate inference via the ``claude`` CLI subprocess
    is strictly cheaper than per-call Anthropic API billing. Default
    backend = ``claude_code_cli``. Explicit opt-in to the SDK path
    (requires ``ANTHROPIC_API_KEY``) via ``kind: anthropic_sdk``.

    ``max_budget_usd_per_scene`` is surfaced for future ``--max-budget-usd``
    enforcement on the CLI subprocess; currently advisory only.

    All fields have defaults so legacy mode_thresholds.yaml files without a
    ``critic_backend:`` block still validate.
    """

    kind: Literal["claude_code_cli", "anthropic_sdk"] = "claude_code_cli"
    model: str = "claude-opus-4-7"
    timeout_s: int = Field(default=180, ge=1)
    max_budget_usd_per_scene: float = Field(default=1.0, ge=0.0)


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
    # Phase 3 gap-closure: backend-swappable critic. default_factory means
    # legacy mode_thresholds.yaml files without a critic_backend: block
    # still validate (and get the claude_code_cli default — operator
    # directive 2026-04-21).
    critic_backend: CriticBackendConfig = Field(default_factory=CriticBackendConfig)
    # Plan 05-02 D-05 + D-06: R-cap + per-scene USD spend cap. default_factory
    # means legacy mode_thresholds.yaml files without a `regen:` block still
    # validate (getting 3 / $0.75 defaults).
    regen: RegenConfig = Field(default_factory=RegenConfig)
    # Plan 07-04 PHYSICS-09: repetition_loop treatment-conditional thresholds.
    # default_factory means legacy mode_thresholds.yaml files without a
    # `physics_repetition:` block still validate (getting Pitfall 10 defaults).
    physics_repetition: PhysicsRepetitionConfig = Field(
        default_factory=PhysicsRepetitionConfig
    )

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
