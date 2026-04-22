"""SHA helpers for the voice-FT checkpoint pin — V-3 pitfall mitigation.

PITFALLS V-3 (Voice checkpoint pin drift / silent swap): the voice-FT drafter
MUST refuse to boot if the weights it loads do not match the SHA recorded in
config/voice_pin.yaml. Both sides of that comparison use compute_adapter_sha()
from this module so there is EXACTLY ONE algorithm.

Algorithm (load-bearing — two machines must reproduce the same digest):
  1. SHA256 accumulator.
  2. Stream adapter_model.safetensors in 1 MiB chunks into the accumulator.
  3. Stream adapter_config.json in 1 MiB chunks into the accumulator.
  4. hexdigest() — 64 lowercase hex chars.

File order is fixed (safetensors first, then config). Do not sort, do not glob,
do not include tokenizer files. The fixed order is the reason two independent
callers (pin-voice CLI + Phase 3 vLLM boot handshake) reproduce the same digest.

This module lives in the kernel: it MUST NOT import from book_specifics and
MUST NOT carry Our Lady of Champion-specific logic. The import-linter contract
1 (pyproject.toml) guards this on every commit.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from book_pipeline.config.voice_pin import VoicePinData

_CHUNK = 1024 * 1024  # 1 MiB
_SAFETENSORS = "adapter_model.safetensors"
_CONFIG = "adapter_config.json"


class VoicePinMismatch(Exception):
    """Raised when an adapter's recomputed SHA does not match voice_pin.yaml.

    Attributes carry enough context for operator diagnosis:
      - expected_sha: the SHA pinned in voice_pin.yaml (.checkpoint_sha).
      - actual_sha: the SHA compute_adapter_sha() returned for the loaded dir.
      - adapter_dir: the filesystem Path that was hashed.

    Phase 3 Plan 03 (vLLM boot handshake) catches this and routes the scene
    state to HARD_BLOCKED("checkpoint_sha_mismatch").
    """

    def __init__(self, expected_sha: str, actual_sha: str, adapter_dir: Path) -> None:
        self.expected_sha = expected_sha
        self.actual_sha = actual_sha
        self.adapter_dir = adapter_dir
        super().__init__(
            f"voice-pin SHA mismatch at {adapter_dir}: "
            f"expected={expected_sha}, actual={actual_sha}"
        )


def compute_adapter_sha(adapter_dir: Path) -> str:
    """Return the 64-char hex SHA256 over (safetensors || config.json).

    Args:
        adapter_dir: Path to the LoRA adapter directory. Must contain
            ``adapter_model.safetensors`` and ``adapter_config.json`` at the
            top level (not in checkpoint-*/ subdirs).

    Returns:
        64 lowercase hex chars. Stable across processes and machines given the
        same two files.

    Raises:
        FileNotFoundError: if either required file is missing.
    """
    adapter_dir = Path(adapter_dir).expanduser()
    safetensors = adapter_dir / _SAFETENSORS
    config = adapter_dir / _CONFIG
    if not safetensors.exists():
        raise FileNotFoundError(f"missing {safetensors}")
    if not config.exists():
        raise FileNotFoundError(f"missing {config}")
    h = hashlib.sha256()
    for f in (safetensors, config):
        with f.open("rb") as fh:
            while True:
                buf = fh.read(_CHUNK)
                if not buf:
                    break
                h.update(buf)
    return h.hexdigest()


def verify_pin(pin: VoicePinData, *, strict: bool = True) -> str:
    """Compute SHA over pin.checkpoint_path; raise VoicePinMismatch on mismatch.

    Args:
        pin: The VoicePinData loaded from config/voice_pin.yaml.
        strict: If True (default), raise VoicePinMismatch on mismatch. If
            False, return the actual computed SHA without raising — callers
            can downgrade the mismatch to a warning.

    Returns:
        The computed SHA (64 hex chars). On match, equals ``pin.checkpoint_sha``.
        On mismatch with strict=False, returns the ACTUAL SHA (not the pinned
        one) so callers can log both.

    Raises:
        FileNotFoundError: if pin.checkpoint_path does not contain the expected
            adapter files (propagated from compute_adapter_sha).
        VoicePinMismatch: if computed SHA != pin.checkpoint_sha and strict=True.
    """
    actual = compute_adapter_sha(Path(pin.checkpoint_path).expanduser())
    if actual != pin.checkpoint_sha and strict:
        raise VoicePinMismatch(
            expected_sha=pin.checkpoint_sha,
            actual_sha=actual,
            adapter_dir=Path(pin.checkpoint_path).expanduser(),
        )
    return actual
