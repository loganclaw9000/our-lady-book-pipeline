"""VoiceSamplesConfig — typed loader for config/voice_samples.yaml (Plan 05-01 D-03).

ModeBDrafter consumes ``passages`` as its voice-samples cached prefix. The
loader accepts an empty list (placeholder state); non-emptiness + word-count
band are enforced by ModeBDrafter.__init__ at instantiation time so production
runs fail loudly if the `book-pipeline curate-voice-samples` CLI hasn't run.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource


class VoiceSamplesConfig(BaseSettings):
    """Root loader — validates and exposes ``passages`` list of 400-600-word strings.

    Accepts two on-disk shapes (Forge interop, 2026-04-24):
      A) Native:  ``{passages: [str, str, ...]}``
      B) Forge:   ``{count: int, purpose: str, samples: [{body: str, ...}, ...]}``
                  Coerced to ``passages = [s.body for s in samples]`` at load time.
    """

    passages: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        yaml_file="config/voice_samples.yaml",
        extra="ignore",  # tolerate Forge's count/purpose/samples top-level keys
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_forge_shape(cls, data: Any) -> Any:
        """If `samples: [{body: ...}]` present, hoist .body strings into passages."""
        if isinstance(data, dict) and "samples" in data and "passages" not in data:
            samples = data.get("samples") or []
            if isinstance(samples, list):
                bodies = [
                    s["body"]
                    for s in samples
                    if isinstance(s, dict) and isinstance(s.get("body"), str)
                ]
                data = {**data, "passages": bodies}
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


__all__ = ["VoiceSamplesConfig"]
