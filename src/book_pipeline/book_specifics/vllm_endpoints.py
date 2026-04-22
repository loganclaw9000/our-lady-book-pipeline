"""vLLM endpoint + LoRA-module defaults for paul-voice on port 8002.

Book-domain constants that tell the CLI composition layer WHERE the vLLM
instance lives and WHAT the served LoRA adapter is called.

Kernel NEVER imports this module; the CLI composition seam
(cli/vllm_bootstrap.py) passes these values into VllmClient at construction.
import-linter contract 1 pins this boundary (ignore_imports entry for the
CLI-only bridge documented in pyproject.toml).
"""
from __future__ import annotations

DEFAULT_BASE_URL: str = "http://127.0.0.1:8002/v1"
LORA_MODULE_NAME: str = "paul-voice"
HEALTH_POLL_TIMEOUT_S: float = 90.0
HEALTH_POLL_INTERVAL_S: float = 3.0

__all__ = [
    "DEFAULT_BASE_URL",
    "HEALTH_POLL_INTERVAL_S",
    "HEALTH_POLL_TIMEOUT_S",
    "LORA_MODULE_NAME",
]
