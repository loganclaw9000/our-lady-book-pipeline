"""Tests for book-pipeline pin-voice CLI (Plan 03-01 Task 3).

The CLI:
  1. Computes SHA over adapter_model.safetensors + adapter_config.json.
  2. Probes `git -C /home/admin/paul-thinkpiece-pipeline rev-parse HEAD` with
     graceful fallback.
  3. Writes VoicePinData-valid YAML atomically (tempfile + os.replace).
  4. Reloads via VoicePinConfig() to validate the round-trip.
  5. Emits one role='voice_pin' Event to runs/events.jsonl.

Tests cover: fake-adapter round-trip (happy path), missing adapter (exits
non-zero), SHA round-trip is byte-exact, and Event was emitted with the
computed SHA.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from book_pipeline.voice_fidelity.sha import compute_adapter_sha


def _write_fake_adapter(adapter_dir: Path) -> tuple[bytes, bytes]:
    """Materialize a tiny valid adapter dir. Returns the (safetensors, config) bytes."""
    adapter_dir.mkdir(parents=True, exist_ok=True)
    safetensors_bytes = b"S" * 32  # 32 bytes stands in for the weight file
    config_bytes = b'{"peft_type":"LORA","r":16}'
    (adapter_dir / "adapter_model.safetensors").write_bytes(safetensors_bytes)
    (adapter_dir / "adapter_config.json").write_bytes(config_bytes)
    return safetensors_bytes, config_bytes


def _run_pin_voice(args: list[str]) -> int:
    """Invoke book-pipeline pin-voice <args> via the main() entry point."""
    from book_pipeline.cli.main import main

    return main(["pin-voice", *args])


def test_pin_voice_writes_valid_yaml_reloads_via_voice_pin_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 1: Happy path — pin-voice exits 0, writes a yaml that VoicePinConfig
    reloads without error.

    We chdir into tmp_path so the relative --yaml-path + --events-path land
    under the test's scratch space, AND so VoicePinConfig() (which uses
    SettingsConfigDict yaml_file='config/voice_pin.yaml') reads the tmp copy.
    """
    adapter_dir = tmp_path / "adapter"
    _write_fake_adapter(adapter_dir)

    events_path = tmp_path / "runs" / "events.jsonl"
    yaml_path = tmp_path / "config" / "voice_pin.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(tmp_path)

    rc = _run_pin_voice([
        str(adapter_dir),
        "--yaml-path", str(yaml_path),
        "--events-path", str(events_path),
        "--ft-run-id", "v6_qwen3_32b",
        "--base-model", "Qwen/Qwen3-32B",
        "--trained-on-date", "2026-04-14",
        "--pinned-reason", "test",
    ])
    assert rc == 0, "pin-voice must exit 0 on happy path"

    # YAML reloads cleanly via VoicePinConfig (which reads config/voice_pin.yaml).
    from book_pipeline.config.voice_pin import VoicePinConfig

    cfg = VoicePinConfig()  # type: ignore[call-arg]
    assert cfg.voice_pin.ft_run_id == "v6_qwen3_32b"
    assert cfg.voice_pin.base_model == "Qwen/Qwen3-32B"
    assert len(cfg.voice_pin.checkpoint_sha) == 64
    assert cfg.voice_pin.checkpoint_sha != "TBD-phase3"


def test_pin_voice_exits_nonzero_on_missing_adapter_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 2: Missing adapter dir → non-zero exit + stderr line."""
    missing = tmp_path / "does_not_exist"
    yaml_path = tmp_path / "config" / "voice_pin.yaml"
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)

    rc = _run_pin_voice([
        str(missing),
        "--yaml-path", str(yaml_path),
        "--events-path", str(events_path),
    ])
    assert rc != 0, "pin-voice must exit non-zero when adapter dir is missing"


def test_pin_voice_sha_in_yaml_matches_compute_adapter_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 3: YAML's voice_pin.checkpoint_sha matches compute_adapter_sha() byte-exactly."""
    adapter_dir = tmp_path / "adapter"
    safetensors_bytes, config_bytes = _write_fake_adapter(adapter_dir)

    yaml_path = tmp_path / "config" / "voice_pin.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)

    rc = _run_pin_voice([
        str(adapter_dir),
        "--yaml-path", str(yaml_path),
        "--events-path", str(events_path),
    ])
    assert rc == 0

    # Manually compute reference SHA.
    expected = hashlib.sha256(safetensors_bytes + config_bytes).hexdigest()
    # Sanity check against our production helper.
    assert compute_adapter_sha(adapter_dir) == expected

    # Read back the yaml directly (not via pydantic) to confirm byte-exact SHA.
    written = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert written["voice_pin"]["checkpoint_sha"] == expected


def test_pin_voice_emits_role_voice_pin_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 4: pin-voice emits exactly one role='voice_pin' Event with the
    computed SHA in checkpoint_sha + output_hash."""
    adapter_dir = tmp_path / "adapter"
    safetensors_bytes, config_bytes = _write_fake_adapter(adapter_dir)

    yaml_path = tmp_path / "config" / "voice_pin.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)

    rc = _run_pin_voice([
        str(adapter_dir),
        "--yaml-path", str(yaml_path),
        "--events-path", str(events_path),
    ])
    assert rc == 0

    expected_sha = hashlib.sha256(safetensors_bytes + config_bytes).hexdigest()

    assert events_path.exists(), "events.jsonl must be created"
    lines = [
        ln
        for ln in events_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    voice_pin_events = [json.loads(ln) for ln in lines if '"voice_pin"' in ln]
    assert len(voice_pin_events) == 1, f"expected 1 voice_pin event, got {len(voice_pin_events)}"
    ev = voice_pin_events[0]
    assert ev["role"] == "voice_pin"
    assert ev["checkpoint_sha"] == expected_sha
    assert ev["output_hash"] == expected_sha
    assert ev["caller_context"]["module"] == "cli.pin_voice"
    assert ev["caller_context"]["function"] == "pin_voice"
    assert ev["caller_context"]["adapter_dir"] == str(adapter_dir)
