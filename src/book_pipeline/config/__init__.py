"""book_pipeline.config — typed YAML + env config loaders.

FOUND-02 surface: 4 YAML configs under ``config/`` + ``.env`` for secrets,
each loaded into a Pydantic-Settings model that validates at instantiation.
``load_all_configs()`` is the one-call entry point used by the
``book-pipeline validate-config`` CLI and by the orchestrator.

Models:
    VoicePinConfig        — voice-FT checkpoint pin (Phase 3 populates SHA)
    RubricConfig          — 5-axis critic rubric
    RagRetrieversConfig   — 5 typed RAG retrievers + bundler
    ModeThresholdsConfig  — Mode A/B dial per ADR-001
    SecretsConfig         — env/.env-sourced secrets (never logged)
"""

from book_pipeline.config.loader import load_all_configs
from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
from book_pipeline.config.rag_retrievers import RagRetrieversConfig
from book_pipeline.config.rubric import RubricConfig
from book_pipeline.config.secrets import SecretsConfig
from book_pipeline.config.sources import YamlConfigSettingsSource
from book_pipeline.config.voice_pin import VoicePinConfig

__all__ = [
    "ModeThresholdsConfig",
    "RagRetrieversConfig",
    "RubricConfig",
    "SecretsConfig",
    "VoicePinConfig",
    "YamlConfigSettingsSource",
    "load_all_configs",
]
