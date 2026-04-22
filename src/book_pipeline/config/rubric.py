"""RubricConfig — typed loader for config/rubric.yaml.

The 5-axis critic rubric. Axis names are FROZEN at v1: {historical, metaphysics,
entity, arc, donts}. Renaming or adding an axis requires bumping
``rubric_version`` (events carry rubric_version so historical data stays
interpretable).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource

REQUIRED_AXES: frozenset[str] = frozenset({"historical", "metaphysics", "entity", "arc", "donts"})


class AxisSeverity(BaseModel):
    """Normalized severity thresholds (0.0-1.0) for one rubric axis."""

    low: float = Field(ge=0.0, le=1.0)
    mid: float = Field(ge=0.0, le=1.0)
    high: float = Field(ge=0.0, le=1.0)


class RubricAxis(BaseModel):
    """One rubric axis — description + severity thresholds + gate weight."""

    description: str
    severity_thresholds: AxisSeverity
    weight: float = Field(ge=0.0, le=2.0)


class RubricConfig(BaseSettings):
    """Root loader — validates and exposes the 5-axis rubric."""

    rubric_version: str
    axes: dict[str, RubricAxis]

    model_config = SettingsConfigDict(
        yaml_file="config/rubric.yaml",
        extra="forbid",
    )

    @field_validator("axes")
    @classmethod
    def _check_5_axes(cls, v: dict[str, RubricAxis]) -> dict[str, RubricAxis]:
        if set(v.keys()) != REQUIRED_AXES:
            raise ValueError(
                f"axes must be exactly {sorted(REQUIRED_AXES)}, got {sorted(v.keys())}"
            )
        return v

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
