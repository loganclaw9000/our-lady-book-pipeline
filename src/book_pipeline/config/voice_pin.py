"""VoicePinConfig — typed loader for config/voice_pin.yaml.

Pins the voice-FT checkpoint (from paul-thinkpiece-pipeline) that Mode-A
drafter will load via vLLM in Phase 3. The ``checkpoint_sha`` field is a
placeholder in Phase 1; Phase 3's DRAFT-01 replaces it with the real hash
and enforces a runtime SHA match at vLLM-serve handshake.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource


class VllmServeConfig(BaseModel):
    """vLLM-serve flags for the voice-FT checkpoint.

    Extended 2026-04-24 (Forge handoff): quantization + gpu_memory_utilization +
    safety_ceiling_max_gpu_util added to honor DGX Spark unified-memory wedge
    constraints. Defaults stay backwards-compatible with prior pin shape.
    """

    port: int = Field(ge=1024, le=65535)
    max_model_len: int = Field(ge=512)
    dtype: Literal["bfloat16", "float16", "fp8", "nvfp4"]
    tensor_parallel_size: int = Field(ge=1, le=8)
    quantization: Literal["bitsandbytes", "fp8", "nvfp4", "none"] = "none"
    gpu_memory_utilization: float = Field(default=0.85, ge=0.10, le=0.95)
    safety_ceiling_max_gpu_util: float = Field(default=0.85, ge=0.10, le=0.95)


class VoicePinData(BaseModel):
    """Payload of the ``voice_pin:`` top-level key in voice_pin.yaml."""

    source_repo: str
    source_commit_sha: str
    ft_run_id: str
    checkpoint_path: str
    checkpoint_sha: str
    base_model: str
    trained_on_date: str
    pinned_on_date: str
    pinned_reason: str
    vllm_serve_config: VllmServeConfig


class VoicePinConfig(BaseSettings):
    """Root loader — validates and exposes ``voice_pin`` structured data."""

    voice_pin: VoicePinData

    model_config = SettingsConfigDict(
        yaml_file="config/voice_pin.yaml",
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
