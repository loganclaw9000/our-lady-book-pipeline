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

# Plan 07-02 (PHYSICS-04 / D-22): the 6th retriever (CB-01 / continuity_bible)
# is OPTIONAL in the config — pre-Plan-07-02 configs validate without it via
# the existing 5-name REQUIRED_RETRIEVERS contract; post-Plan-07-02 configs
# may include it as the 6th entry, and the validator allows the superset.
OPTIONAL_RETRIEVERS: frozenset[str] = frozenset({"continuity_bible"})


class EmbeddingsConfig(BaseModel):
    """Shared embedding model config — one instance drives all 5 retrievers."""

    model: str
    model_revision: str
    dim: int = Field(ge=1)
    device: str


class RerankerConfig(BaseModel):
    """BGE reranker-v2-m3 cross-encoder config (Plan 02-06 additive section).

    Defaults reflect the values Plan 02-03 hardcoded in BgeReranker.__init__;
    the loader accepts legacy configs that omit the `reranker:` section
    (defaults take over). Custom values in the YAML override the defaults.

    model_revision: resolved at first successful ingest and persisted to
    indexes/resolved_model_revision.json (per W-4 policy — never written
    back to this YAML file).
    """

    model: str = "BAAI/bge-reranker-v2-m3"
    model_revision: str = "TBD-phase2"
    device: str = "cuda:0"
    candidate_k: int = Field(default=50, ge=1)
    final_k: int = Field(default=8, ge=1)


class BundlerConfig(BaseModel):
    """ContextPack assembler — caps payload at max_bytes per RAG-03.

    Plan 07-02 additive section: `per_axis_byte_caps` (optional) lets ops
    pin per-retriever soft caps in the config (currently used for the new
    'continuity_bible' axis at 8KB per Assumption A5; legacy axes inherit
    PER_AXIS_SOFT_CAPS from book_pipeline.rag.budget when absent).
    """

    max_bytes: int = Field(ge=1024)
    assembly_strategy: str
    enforce_cap: bool
    emit_conflicts_to: str
    per_axis_byte_caps: dict[str, int] = Field(default_factory=dict)


class RetrieverConfig(BaseModel):
    """One typed retriever — index path + source files + chunk strategy."""

    index_path: str
    source_files: list[str]
    chunk_strategy: str
    auto_update_from: str | None = None


class RagRetrieversConfig(BaseSettings):
    """Root loader — validates and exposes the 5 retrievers + embeddings + bundler + reranker."""

    embeddings: EmbeddingsConfig
    bundler: BundlerConfig
    retrievers: dict[str, RetrieverConfig]
    # Plan 02-06: additive section. Legacy configs (without a reranker: block)
    # validate via defaults. The default_factory is the hinge that keeps the
    # Phase 1 freeze policy honest ("OPTIONAL additions only").
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)

    model_config = SettingsConfigDict(
        yaml_file="config/rag_retrievers.yaml",
        extra="forbid",
    )

    @field_validator("retrievers")
    @classmethod
    def _check_required_retrievers(
        cls, v: dict[str, RetrieverConfig]
    ) -> dict[str, RetrieverConfig]:
        # The 5 frozen retriever names MUST all be present (Plan 02 contract).
        # Plan 07-02: continuity_bible is an OPTIONAL 6th retriever; any extra
        # keys must come from OPTIONAL_RETRIEVERS — unknown keys still fail.
        keys = set(v.keys())
        missing = REQUIRED_RETRIEVERS - keys
        unexpected = keys - REQUIRED_RETRIEVERS - OPTIONAL_RETRIEVERS
        if missing or unexpected:
            raise ValueError(
                f"retrievers must include {sorted(REQUIRED_RETRIEVERS)} "
                f"(optional: {sorted(OPTIONAL_RETRIEVERS)}); "
                f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
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
