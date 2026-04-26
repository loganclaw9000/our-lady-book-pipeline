"""RubricConfig — typed loader for config/rubric.yaml.

The 5-axis critic rubric. Axis names are FROZEN at v1: {historical, metaphysics,
entity, arc, donts}. Renaming or adding an axis requires bumping
``rubric_version`` (events carry rubric_version so historical data stays
interpretable).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource

# Phase 7 Plan 04 PHYSICS-07: extend from 5 to 13 axes. The 5 originals
# (historical / metaphysics / entity / arc / donts) stay; 6 new LLM-judged
# axes ride on the existing single-call structured-output path
# (pov_fidelity / motivation_fidelity / treatment_fidelity / content_ownership
#  / named_quantity_drift / scene_buffer_similarity); 2 deterministic pre-LLM
# short-circuits (stub_leak / repetition_loop) are filled by physics scans
# BEFORE the Anthropic call (D-27 hard reject + D-19 degenerate-loop).
#
# Display order is owned by AXES_ORDERED in book_pipeline.critic.scene.
REQUIRED_AXES: frozenset[str] = frozenset({
    "historical",
    "metaphysics",
    "entity",
    "arc",
    "donts",
    # Phase 7 atomics — D-26:
    "pov_fidelity",
    "motivation_fidelity",
    "treatment_fidelity",
    "content_ownership",
    "named_quantity_drift",
    "scene_buffer_similarity",
    # Phase 7 atomics — pre-LLM deterministic short-circuits (Plan 07-04):
    "stub_leak",
    "repetition_loop",
})
# Plan 04-02 (CRIT-02): chapter critic enforces the original 5-axis set
# only. Named separately so future evolution of scene vs chapter axes
# remains decoupled. Phase 7 atomics are scene-grain only.
CHAPTER_REQUIRED_AXES: frozenset[str] = frozenset(
    {"historical", "metaphysics", "entity", "arc", "donts"}
)


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


class ChapterAxisConfig(BaseModel):
    """One chapter-rubric axis — description + 0..5 pass threshold + weight.

    Chapter critic scores on 0..5 (stricter than scene's 0..100 band). The
    schema still stores 0..100 floats (via x20 normalization); threshold
    logic lives in ChapterCritic._post_process.
    """

    description: str
    score_threshold_0to5: int = Field(ge=0, le=5, default=3)
    weight: float = Field(ge=0.0, le=2.0, default=1.0)


class ChapterRubricConfig(BaseModel):
    """The chapter-level 5-axis rubric block (Plan 04-02)."""

    rubric_version: str
    axes: dict[str, ChapterAxisConfig]

    @field_validator("axes")
    @classmethod
    def _check_chapter_axes(
        cls, v: dict[str, ChapterAxisConfig]
    ) -> dict[str, ChapterAxisConfig]:
        if set(v.keys()) != CHAPTER_REQUIRED_AXES:
            raise ValueError(
                f"chapter_axes must be exactly {sorted(CHAPTER_REQUIRED_AXES)}, "
                f"got {sorted(v.keys())}"
            )
        return v


class RubricConfig(BaseSettings):
    """Root loader — validates and exposes BOTH the scene and chapter rubrics.

    Phase 4 Plan 04-02 extends this additively: the scene `rubric_version` +
    `axes` fields are preserved byte-for-byte; `chapter_rubric` is a new
    required field parsed from `chapter_rubric_version` + `chapter_axes`
    keys at the YAML root.
    """

    rubric_version: str
    axes: dict[str, RubricAxis]
    # --- Phase 4 Plan 04-02 additions (built in __init__ from flat YAML keys) ---
    chapter_rubric: ChapterRubricConfig

    model_config = SettingsConfigDict(
        yaml_file="config/rubric.yaml",
        extra="allow",  # flat YAML keys `chapter_rubric_version` + `chapter_axes`
    )

    @field_validator("axes")
    @classmethod
    def _check_5_axes(cls, v: dict[str, RubricAxis]) -> dict[str, RubricAxis]:
        if set(v.keys()) != REQUIRED_AXES:
            raise ValueError(
                f"axes must be exactly {sorted(REQUIRED_AXES)}, got {sorted(v.keys())}"
            )
        return v

    @model_validator(mode="before")
    @classmethod
    def _collapse_chapter_keys(cls, data: Any) -> Any:
        """Collapse flat YAML keys `chapter_rubric_version` + `chapter_axes`
        into a nested `chapter_rubric` dict consumed by ChapterRubricConfig.

        Additive — leaves all scene-rubric keys untouched.
        """
        if not isinstance(data, dict):
            return data
        if "chapter_rubric" in data:
            return data  # already nested; nothing to do
        cv = data.pop("chapter_rubric_version", None)
        ca = data.pop("chapter_axes", None)
        if cv is not None or ca is not None:
            data["chapter_rubric"] = {
                "rubric_version": cv,
                "axes": ca or {},
            }
        return data

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
