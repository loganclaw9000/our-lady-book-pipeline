"""VoiceSamplesConfig — typed loader for config/voice_samples.yaml (Plan 05-01 D-03).

ModeBDrafter consumes ``passages`` as its voice-samples cached prefix. The
loader accepts an empty list (placeholder state); non-emptiness + word-count
band are enforced by ModeBDrafter.__init__ at instantiation time so production
runs fail loudly if the `book-pipeline curate-voice-samples` CLI hasn't run.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource


class VoiceSamplesConfig(BaseSettings):
    """Root loader — validates and exposes ``passages`` list of 400-600-word strings."""

    passages: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        yaml_file="config/voice_samples.yaml",
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


__all__ = ["VoiceSamplesConfig"]
