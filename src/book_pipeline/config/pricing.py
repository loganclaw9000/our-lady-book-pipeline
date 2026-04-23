"""PricingConfig — typed loader for config/pricing.yaml (Plan 05-01 D-17).

Each entry maps a model_id to ModelPricing (frozen dataclass in
book_pipeline.observability.pricing). Negative USD rates are rejected at
load time — a malformed pricing file is a mid-run cost blowout risk.

Pitfall 5 reminder: openclaw/cron_jobs.json carries outdated $15/$75 Opus 4.7
numbers. Plan 05-01 test_pricing_yaml_loads is the drift canary — if that
test fails because this config ships $15, somebody rebased over authoritative
platform.claude.com pricing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource

if TYPE_CHECKING:
    from book_pipeline.observability.pricing import ModelPricing


class ModelPricingEntry(BaseModel):
    """Pydantic shape for one pricing row.

    Mirror of book_pipeline.observability.pricing.ModelPricing but declared
    here (config layer) as a Pydantic BaseModel. The observability module
    hosts the @dataclass(frozen=True) variant used by the pure cost kernel;
    consumers read from PricingConfig().by_model which converts to the
    frozen dataclass at property-access time.
    """

    input_usd_per_mtok: float = Field(ge=0.0)
    output_usd_per_mtok: float = Field(ge=0.0)
    cache_read_usd_per_mtok: float = Field(ge=0.0)
    cache_write_1h_usd_per_mtok: float = Field(ge=0.0)
    cache_write_5m_usd_per_mtok: float = Field(ge=0.0)

    @field_validator(
        "input_usd_per_mtok",
        "output_usd_per_mtok",
        "cache_read_usd_per_mtok",
        "cache_write_1h_usd_per_mtok",
        "cache_write_5m_usd_per_mtok",
    )
    @classmethod
    def _reject_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"USD rate must be >= 0, got {v}")
        return v


class PricingConfig(BaseSettings):
    """Root loader — validates and exposes ``by_model`` dict of ModelPricing."""

    by_model_raw: dict[str, ModelPricingEntry] = Field(
        default_factory=dict, alias="by_model"
    )

    model_config = SettingsConfigDict(
        yaml_file="config/pricing.yaml",
        extra="forbid",
        populate_by_name=True,
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

    @property
    def by_model(self) -> dict[str, ModelPricing]:
        """Return {model_id: ModelPricing} — frozen dataclass for spend tracker."""
        # Lazy import to avoid circular (observability imports interfaces; config
        # is importable from anywhere).
        from book_pipeline.observability.pricing import ModelPricing

        return {
            model_id: ModelPricing(
                input_usd_per_mtok=entry.input_usd_per_mtok,
                output_usd_per_mtok=entry.output_usd_per_mtok,
                cache_read_usd_per_mtok=entry.cache_read_usd_per_mtok,
                cache_write_1h_usd_per_mtok=entry.cache_write_1h_usd_per_mtok,
                cache_write_5m_usd_per_mtok=entry.cache_write_5m_usd_per_mtok,
            )
            for model_id, entry in self.by_model_raw.items()
        }


__all__ = ["ModelPricingEntry", "PricingConfig"]
