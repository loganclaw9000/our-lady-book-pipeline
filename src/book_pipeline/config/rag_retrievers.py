"""RagRetrieversConfig — typed loader for config/rag_retrievers.yaml.

5 typed RAG retrievers + shared embedding model + ContextPack bundler config.
Retriever names are FROZEN: {historical, metaphysics, entity_state,
arc_position, negative_constraint}.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource

REQUIRED_RETRIEVERS: frozenset[str] = frozenset(
    {"historical", "metaphysics", "entity_state", "arc_position", "negative_constraint"}
)


class EmbeddingsConfig(BaseModel):
    """Shared embedding model config — one instance drives all 5 retrievers."""

    model: str
    model_revision: str
    dim: int = Field(ge=1)
    device: str


class BundlerConfig(BaseModel):
    """ContextPack assembler — caps payload at max_bytes per RAG-03."""

    max_bytes: int = Field(ge=1024)
    assembly_strategy: str
    enforce_cap: bool
    emit_conflicts_to: str


class RetrieverConfig(BaseModel):
    """One typed retriever — index path + source files + chunk strategy."""

    index_path: str
    source_files: list[str]
    chunk_strategy: str
    auto_update_from: str | None = None


class RagRetrieversConfig(BaseSettings):
    """Root loader — validates and exposes the 5 retrievers + embeddings + bundler."""

    embeddings: EmbeddingsConfig
    bundler: BundlerConfig
    retrievers: dict[str, RetrieverConfig]

    model_config = SettingsConfigDict(
        yaml_file="config/rag_retrievers.yaml",
        extra="forbid",
    )

    @field_validator("retrievers")
    @classmethod
    def _check_5_retrievers(cls, v: dict[str, RetrieverConfig]) -> dict[str, RetrieverConfig]:
        if set(v.keys()) != REQUIRED_RETRIEVERS:
            raise ValueError(
                f"retrievers must be exactly {sorted(REQUIRED_RETRIEVERS)}, got {sorted(v.keys())}"
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
