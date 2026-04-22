"""Per-scene-type sampling profiles for DRAFT-02.

Plan 03-04 Task 1. Three profiles (prose, dialogue_heavy, structural_complex)
govern vLLM sampling params dispatched by ModeADrafter based on scene_type.
Defaults live in config/mode_thresholds.yaml sampling_profiles: block and are
loaded via ModeThresholdsConfig.sampling_profiles (kernel→kernel import;
import-linter contract 1 allows).

This module lives in the kernel and MUST NOT carry book-domain-specific logic.
The profiles themselves are generic writing-generation knobs.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

VALID_SCENE_TYPES: frozenset[str] = frozenset(
    {"prose", "dialogue_heavy", "structural_complex"}
)


class SamplingProfile(BaseModel):
    """One sampling profile — temperature / top_p / repetition_penalty / max_tokens."""

    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(gt=0.0, le=1.0)
    repetition_penalty: float = Field(ge=1.0, le=2.0)
    max_tokens: int = Field(ge=128)


class SamplingProfiles(BaseModel):
    """Three per-scene-type profiles, with plan-pinned defaults (DRAFT-02)."""

    prose: SamplingProfile = Field(
        default_factory=lambda: SamplingProfile(
            temperature=0.85, top_p=0.92, repetition_penalty=1.05, max_tokens=2048
        )
    )
    dialogue_heavy: SamplingProfile = Field(
        default_factory=lambda: SamplingProfile(
            temperature=0.7, top_p=0.90, repetition_penalty=1.05, max_tokens=2048
        )
    )
    structural_complex: SamplingProfile = Field(
        default_factory=lambda: SamplingProfile(
            temperature=0.6, top_p=0.88, repetition_penalty=1.05, max_tokens=2048
        )
    )


def resolve_profile(profiles: SamplingProfiles, scene_type: str) -> SamplingProfile:
    """Look up a SamplingProfile by scene_type.

    Args:
        profiles: SamplingProfiles config block (typically from ModeThresholdsConfig).
        scene_type: One of VALID_SCENE_TYPES.

    Returns:
        SamplingProfile matching scene_type.

    Raises:
        ValueError: scene_type not in VALID_SCENE_TYPES.
    """
    if scene_type not in VALID_SCENE_TYPES:
        raise ValueError(
            f"unknown scene_type {scene_type!r}; expected one of {sorted(VALID_SCENE_TYPES)}"
        )
    # Direct attribute access — mapping would re-impose runtime lookup cost.
    if scene_type == "prose":
        return profiles.prose
    if scene_type == "dialogue_heavy":
        return profiles.dialogue_heavy
    # structural_complex
    return profiles.structural_complex


__all__ = [
    "VALID_SCENE_TYPES",
    "SamplingProfile",
    "SamplingProfiles",
    "resolve_profile",
]
