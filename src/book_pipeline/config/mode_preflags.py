"""PreflagConfig — typed loader for config/mode_preflags.yaml (Plan 05-01 D-04).

Reader at book_pipeline.drafter.preflag::is_preflagged consumes the
``preflagged_beats`` list via a frozenset membership check. Demotion to Mode-A
is by YAML removal + logged pre-commit audit; nothing silent.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource


class PreflagConfig(BaseSettings):
    """Root loader — validates and exposes ``preflagged_beats`` list."""

    preflagged_beats: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        yaml_file="config/mode_preflags.yaml",
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


__all__ = ["PreflagConfig"]
