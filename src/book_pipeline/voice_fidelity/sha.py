"""SHA helpers for the voice-FT checkpoint pin — V-3 pitfall mitigation.

PITFALLS V-3 (Voice checkpoint pin drift / silent swap): the voice-FT drafter
MUST refuse to boot if the weights it loads do not match the SHA recorded in
config/voice_pin.yaml. Both sides of that comparison use compute_adapter_sha()
from this module so there is EXACTLY ONE algorithm.

Algorithm (load-bearing — must match Forge's MANIFEST.json verify_command):
  1. Compute sha256(adapter_model.safetensors), sha256(adapter_config.json).
  2. Sort the resulting hex lines alphabetically.
  3. SHA256 of those sorted lines (as emitted by `sha256sum FILES | sort`).
  4. hexdigest() — 64 lowercase hex chars.

This is bit-equivalent to the shell pipeline:
  cd <adapter_dir> && sha256sum adapter_model.safetensors adapter_config.json | sort | sha256sum

Forge's MANIFEST.json `verify_command` field encodes the same shell pipeline,
so the digest published by Forge at merge time and recomputed by this module
at vLLM boot must match byte-for-byte. 2026-04-24 Q1 closure: prior algorithm
was sha256(bytes||bytes) which silently diverged from Forge's manifest_digest.

This module lives in the kernel and MUST NOT carry Our Lady of
Champion-specific logic. Import-linter contract 1 (pyproject.toml) guards
the kernel/book-domain boundary on every commit.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from book_pipeline.config.voice_pin import VoicePinData

_CHUNK = 1024 * 1024  # 1 MiB
_SAFETENSORS = "adapter_model.safetensors"
_CONFIG = "adapter_config.json"


def _sha256_file(path: Path) -> str:
    """Stream a single file through sha256, return 64-char hex."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(_CHUNK)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


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
    """Return Forge-compatible manifest digest = sha256(`sha256sum FILES | sort`).

    Algorithm (must match Forge MANIFEST.json verify_command output):
      1. sha256(adapter_model.safetensors), sha256(adapter_config.json) per-file.
      2. Format each as ``"<hex>  <basename>\\n"`` (two spaces — `sha256sum` style).
      3. Sort lines alphabetically.
      4. sha256 of the sorted concatenation.

    Args:
        adapter_dir: Path to the LoRA adapter directory. Must contain
            ``adapter_model.safetensors`` and ``adapter_config.json`` at the
            top level (not in checkpoint-*/ subdirs).

    Returns:
        64 lowercase hex chars. Reproducible by any caller running
        ``cd <adapter_dir> && sha256sum adapter_model.safetensors adapter_config.json | sort | sha256sum``.

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

    lines = [
        f"{_sha256_file(safetensors)}  {_SAFETENSORS}\n",
        f"{_sha256_file(config)}  {_CONFIG}\n",
    ]
    lines.sort()
    return hashlib.sha256("".join(lines).encode("ascii")).hexdigest()


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
