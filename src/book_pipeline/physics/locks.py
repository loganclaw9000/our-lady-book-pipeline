"""PovLock storage + loader (Plan 07-01 PHYSICS-02).

Loads config/pov_locks.yaml into typed PovLock objects. Activation semantics
encoded in PovLock.applies_to() per Pitfall 8 (07-RESEARCH.md lines 614-639):
active_from_chapter is INCLUSIVE; expires_at_chapter is EXCLUSIVE; None means
never expires.

D-21 + OQ-01 (a) RESOLVED 2026-04-25: Itzcoatl 1st-person lock activates at
ch15. ch01-04 baseline read-only. ch05-14 historical artifacts (no retrofit).
ch09 retry NOT gated.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource
from book_pipeline.physics.schema import Perspective


class PovLock(BaseModel):
    """Per-character POV invariant lock.

    Inclusive lower bound (active_from_chapter), exclusive upper bound
    (expires_at_chapter). None upper = never expires.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    character: str
    perspective: Perspective
    active_from_chapter: int = Field(ge=1, le=999)
    expires_at_chapter: int | None = Field(default=None, ge=1, le=999)
    rationale: str = Field(min_length=1)

    def applies_to(self, chapter: int) -> bool:
        if chapter < self.active_from_chapter:
            return False
        # Inclusive lower bound (above) + exclusive upper bound (below) per
        # Pitfall 8 (07-RESEARCH.md lines 614-639).
        return not (
            self.expires_at_chapter is not None
            and chapter >= self.expires_at_chapter
        )


class PovLockConfig(BaseSettings):
    """Top-level YAML loader. Reads config/pov_locks.yaml via YamlConfigSettingsSource."""

    locks: list[PovLock] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        yaml_file="config/pov_locks.yaml",
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


def load_pov_locks(yaml_path: str | Path | None = None) -> dict[str, PovLock]:
    """Load pov_locks.yaml into a dict keyed by lowercase character name.

    Args:
        yaml_path: Optional override (default: config/pov_locks.yaml via
            PovLockConfig). When supplied, the YAML is parsed via PyYAML
            safe_load + model_validate (no env / dotenv / secret sources).
            T-07-10 mitigation: yaml.safe_load only (never yaml.load).

    Returns:
        dict mapping lowercase character name -> PovLock. Multiple locks per
        character are NOT supported in v1; the last entry wins on duplicate
        character keys (test_locks would catch this if introduced — defensive
        only).
    """
    if yaml_path is not None:
        path = Path(yaml_path)
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        cfg = PovLockConfig.model_validate(raw)
    else:
        cfg = PovLockConfig()  # reads config/pov_locks.yaml via Settings sources
    return {lock.character.lower(): lock for lock in cfg.locks}


__all__ = ["PovLock", "PovLockConfig", "load_pov_locks"]
