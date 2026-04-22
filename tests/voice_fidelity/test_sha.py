"""Tests for book_pipeline.voice_fidelity.sha — V-3 pitfall mitigation helpers.

Covers compute_adapter_sha (deterministic algorithm, file-order load-bearing),
verify_pin (strict + non-strict paths), and VoicePinMismatch attribute surface.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from book_pipeline.config.voice_pin import VllmServeConfig, VoicePinData
from book_pipeline.voice_fidelity.sha import (
    VoicePinMismatch,
    compute_adapter_sha,
    verify_pin,
)

_SAFETENSORS_NAME = "adapter_model.safetensors"
_CONFIG_NAME = "adapter_config.json"


def _write_fake_adapter(adapter_dir: Path, *, safetensors_bytes: bytes, config_bytes: bytes) -> None:
    adapter_dir.mkdir(parents=True, exist_ok=True)
    (adapter_dir / _SAFETENSORS_NAME).write_bytes(safetensors_bytes)
    (adapter_dir / _CONFIG_NAME).write_bytes(config_bytes)


def _make_pin(
    *,
    checkpoint_path: str,
    checkpoint_sha: str,
    ft_run_id: str = "v6_qwen3_32b",
) -> VoicePinData:
    return VoicePinData(
        source_repo="paul-thinkpiece-pipeline",
        source_commit_sha="abc1234",
        ft_run_id=ft_run_id,
        checkpoint_path=checkpoint_path,
        checkpoint_sha=checkpoint_sha,
        base_model="Qwen/Qwen3-32B",
        trained_on_date="2026-04-14",
        pinned_on_date="2026-04-21",
        pinned_reason="test",
        vllm_serve_config=VllmServeConfig(
            port=8002,
            max_model_len=8192,
            dtype="bfloat16",
            tensor_parallel_size=1,
        ),
    )


def test_compute_adapter_sha_matches_manual_concat_reference(tmp_path: Path) -> None:
    """Test 1: The SHA algorithm is SHA256 over (safetensors_bytes || config_bytes).
    Two independent machines must reproduce the same digest — the test proves the
    algorithm is byte-exact, not just 'something deterministic'.
    """
    safetensors_bytes = b"S" * 8
    config_bytes = b"{}"
    _write_fake_adapter(tmp_path, safetensors_bytes=safetensors_bytes, config_bytes=config_bytes)

    expected = hashlib.sha256(safetensors_bytes + config_bytes).hexdigest()
    actual = compute_adapter_sha(tmp_path)

    assert actual == expected
    assert len(actual) == 64
    assert all(c in "0123456789abcdef" for c in actual)


def test_compute_adapter_sha_raises_when_safetensors_missing(tmp_path: Path) -> None:
    """Test 2: FileNotFoundError when adapter_model.safetensors missing."""
    (tmp_path / _CONFIG_NAME).write_bytes(b"{}")
    with pytest.raises(FileNotFoundError, match="adapter_model.safetensors"):
        compute_adapter_sha(tmp_path)


def test_compute_adapter_sha_raises_when_config_missing(tmp_path: Path) -> None:
    """Test 3: FileNotFoundError when adapter_config.json missing."""
    (tmp_path / _SAFETENSORS_NAME).write_bytes(b"S" * 8)
    with pytest.raises(FileNotFoundError, match="adapter_config.json"):
        compute_adapter_sha(tmp_path)


@pytest.mark.slow
def test_compute_adapter_sha_on_real_v6_adapter_dir() -> None:
    """Test 4: Real V6 adapter dir returns a 64-char lowercase hex string.

    Marked @pytest.mark.slow — reads the multi-GB safetensors file. Default
    pytest runs skip it via -m "not slow" (pre-push hook config).
    """
    adapter_dir = Path("/home/admin/finetuning/output/paul-v6-qwen3-32b-lora")
    if not adapter_dir.exists():
        pytest.skip(f"real V6 adapter dir not available at {adapter_dir}")
    sha = compute_adapter_sha(adapter_dir)
    assert len(sha) == 64
    assert all(c in "0123456789abcdef" for c in sha)


def test_verify_pin_returns_sha_silently_on_match(tmp_path: Path) -> None:
    """Test 5: verify_pin returns the computed SHA when it matches the pin."""
    safetensors_bytes = b"abcd" * 4
    config_bytes = b'{"peft_type":"LORA"}'
    _write_fake_adapter(tmp_path, safetensors_bytes=safetensors_bytes, config_bytes=config_bytes)
    expected_sha = hashlib.sha256(safetensors_bytes + config_bytes).hexdigest()

    pin = _make_pin(checkpoint_path=str(tmp_path), checkpoint_sha=expected_sha)
    # Should NOT raise; returns the computed SHA (equal to pin.checkpoint_sha).
    result = verify_pin(pin)
    assert result == expected_sha


def test_verify_pin_raises_on_mismatch_strict(tmp_path: Path) -> None:
    """Test 6: verify_pin(strict=True) raises VoicePinMismatch on SHA mismatch."""
    _write_fake_adapter(tmp_path, safetensors_bytes=b"real", config_bytes=b"{}")
    wrong_sha = "0" * 64
    pin = _make_pin(checkpoint_path=str(tmp_path), checkpoint_sha=wrong_sha)

    actual_sha = hashlib.sha256(b"real" + b"{}").hexdigest()

    with pytest.raises(VoicePinMismatch) as excinfo:
        verify_pin(pin, strict=True)

    assert excinfo.value.expected_sha == wrong_sha
    assert excinfo.value.actual_sha == actual_sha
    assert excinfo.value.adapter_dir == Path(str(tmp_path)).expanduser()
    # Clear __str__ message for operator diagnosis.
    msg = str(excinfo.value)
    assert wrong_sha in msg
    assert actual_sha in msg


def test_verify_pin_returns_actual_on_mismatch_non_strict(tmp_path: Path) -> None:
    """Test 7: verify_pin(strict=False) returns the computed actual SHA
    (NOT the pin) without raising — callers downgrade mismatch to warning.
    """
    _write_fake_adapter(tmp_path, safetensors_bytes=b"xyz", config_bytes=b"[]")
    wrong_sha = "f" * 64
    pin = _make_pin(checkpoint_path=str(tmp_path), checkpoint_sha=wrong_sha)

    actual_sha = hashlib.sha256(b"xyz" + b"[]").hexdigest()
    result = verify_pin(pin, strict=False)
    assert result == actual_sha
    assert result != wrong_sha
