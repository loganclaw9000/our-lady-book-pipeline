"""Unified config loader — used by ``book-pipeline validate-config`` CLI
and (later) by the orchestrator startup.

Any ValidationError propagates; ``validate-config`` formats it. Startup code
outside the CLI can call this too and let the exception reach its own error
boundary.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings

from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
from book_pipeline.config.rag_retrievers import RagRetrieversConfig
from book_pipeline.config.rubric import RubricConfig
from book_pipeline.config.secrets import SecretsConfig
from book_pipeline.config.voice_pin import VoicePinConfig


def load_all_configs() -> dict[str, BaseSettings]:
    """Load all four typed YAML configs + SecretsConfig.

    Raises:
        ValidationError: if any field is missing or malformed.
        FileNotFoundError: if a required config file is absent.
        yaml.YAMLError: if a config file has invalid YAML syntax.
    """
    # mypy strict flags zero-arg BaseSettings() as a missing-kwarg call, but
    # pydantic-settings populates fields from the YAML / env sources wired in
    # each model's settings_customise_sources. Silence the false positive per
    # the documented pydantic-settings usage pattern.
    return {
        "voice_pin": VoicePinConfig(),  # type: ignore[call-arg]
        "rubric": RubricConfig(),  # type: ignore[call-arg]
        "rag_retrievers": RagRetrieversConfig(),  # type: ignore[call-arg]
        "mode_thresholds": ModeThresholdsConfig(),  # type: ignore[call-arg]
        "secrets": SecretsConfig(),
    }
