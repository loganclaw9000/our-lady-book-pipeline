"""Tests for book-pipeline vllm-bootstrap CLI (Plan 03-03 Task 2).

The CLI:
  1. Loads voice_pin.yaml; bails if checkpoint_sha is the Phase-1 placeholder.
  2. Renders the systemd unit via Jinja2 template + VoicePinData fields.
  3. --dry-run prints the unit, writes nothing.
  4. Without --dry-run: atomic write to ~/.config/systemd/user/ (override-able).
  5. --enable: daemon-reload + systemctl --user enable ...
  6. --start:  systemctl --user start + poll_health + boot_handshake.
  7. Emits role='vllm_bootstrap' Event summarizing the run.

Tests DO NOT actually run systemctl or hit the GPU — subprocess + httpx are
monkeypatched. The real serve happens in Plan 03-08 under a human-verify
checkpoint.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml


def _run_cli(args: list[str]) -> int:
    from book_pipeline.cli.main import main

    return main(["vllm-bootstrap", *args])


def _write_real_pin_yaml(yaml_path: Path) -> str:
    """Write a real pin yaml pointing at a tmp adapter dir alongside it.

    Returns the on-disk adapter dir path (a sibling under yaml_path's parent
    parent). Computes Forge-compatible SHA over fake adapter files so that
    dry-run SHA verify (Plan 05 Forge handoff dry_run_gate_v1.1) passes.
    """
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    # Sibling dir so adapter lives inside tmp_path (not a real /home/admin path).
    adapter_dir = yaml_path.parent.parent / "fake_adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    safetensors_bytes = b"S" * 64
    config_bytes = b'{"peft_type":"LORA"}'
    (adapter_dir / "adapter_model.safetensors").write_bytes(safetensors_bytes)
    (adapter_dir / "adapter_config.json").write_bytes(config_bytes)
    sha_safe = hashlib.sha256(safetensors_bytes).hexdigest()
    sha_cfg = hashlib.sha256(config_bytes).hexdigest()
    lines = [
        f"{sha_safe}  adapter_model.safetensors\n",
        f"{sha_cfg}  adapter_config.json\n",
    ]
    lines.sort()
    forge_digest = hashlib.sha256("".join(lines).encode("ascii")).hexdigest()

    yaml_path.write_text(
        yaml.safe_dump(
            {
                "voice_pin": {
                    "source_repo": "paul-thinkpiece-pipeline",
                    "source_commit_sha": "c571bb7b",
                    "ft_run_id": "v6_qwen35_27b",
                    "checkpoint_path": str(adapter_dir),
                    "checkpoint_sha": forge_digest,
                    "base_model": "Qwen/Qwen3.5-27B",
                    "trained_on_date": "2026-04-22",
                    "pinned_on_date": "2026-04-24",
                    "pinned_reason": "test",
                    "vllm_serve_config": {
                        "port": 8003,
                        "max_model_len": 4096,
                        "dtype": "bfloat16",
                        "tensor_parallel_size": 1,
                        "quantization": "bitsandbytes",
                        "gpu_memory_utilization": 0.55,
                        "safety_ceiling_max_gpu_util": 0.60,
                    },
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return str(adapter_dir)


def _write_placeholder_pin_yaml(yaml_path: Path) -> None:
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "voice_pin": {
                    "source_repo": "paul-thinkpiece-pipeline",
                    "source_commit_sha": "TBD",
                    "ft_run_id": "v6_qwen3_32b",
                    "checkpoint_path": "/home/admin/finetuning/output/paul-v6-qwen3-32b-lora",
                    "checkpoint_sha": "TBD-phase3",
                    "base_model": "Qwen/Qwen3-32B",
                    "trained_on_date": "2026-04-14",
                    "pinned_on_date": "2026-04-22",
                    "pinned_reason": "placeholder",
                    "vllm_serve_config": {
                        "port": 8002,
                        "max_model_len": 8192,
                        "dtype": "bfloat16",
                        "tensor_parallel_size": 1,
                    },
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _copy_template_into(project_root: Path) -> None:
    """Copy the real service template into the test's fake project root so the
    CLI can find it at its default path."""
    src = Path("config/systemd/vllm-paul-voice.service.j2")
    dst = project_root / "config" / "systemd" / "vllm-paul-voice.service.j2"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def test_vllm_bootstrap_dry_run_prints_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test 4: --dry-run prints a rendered unit to stdout + exits 0 + writes nothing."""
    _write_real_pin_yaml(tmp_path / "config" / "voice_pin.yaml")
    _copy_template_into(tmp_path)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)

    rc = _run_cli([
        "--dry-run",
        "--events-path", str(events_path),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "--enable-lora" in out
    assert "--lora-modules paul-voice=" in out  # adapter path varies w/ tmp_path
    assert "--port 8003" in out

    # Nothing written to ~/.config/systemd/user when --dry-run.
    systemd_user = tmp_path / ".config" / "systemd" / "user" / "vllm-paul-voice.service"
    assert not systemd_user.exists()


def test_vllm_bootstrap_tbd_placeholder_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test 5: TBD-phase3 placeholder voice_pin → non-zero exit + clear error message."""
    _write_placeholder_pin_yaml(tmp_path / "config" / "voice_pin.yaml")
    _copy_template_into(tmp_path)

    monkeypatch.chdir(tmp_path)

    rc = _run_cli(["--dry-run"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "pin-voice" in err.lower() or "tbd" in err.lower()


def test_vllm_bootstrap_emits_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 6: CLI emits one role='vllm_bootstrap' Event summarizing the run."""
    _write_real_pin_yaml(tmp_path / "config" / "voice_pin.yaml")
    _copy_template_into(tmp_path)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)

    rc = _run_cli([
        "--dry-run",
        "--events-path", str(events_path),
    ])
    assert rc == 0
    assert events_path.exists()
    lines = [ln for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    bootstrap_events = [
        json.loads(ln) for ln in lines if '"vllm_bootstrap"' in ln
    ]
    assert len(bootstrap_events) == 1
    ev = bootstrap_events[0]
    assert ev["role"] == "vllm_bootstrap"
    assert "start_status" in ev["caller_context"]
    assert "handshake_status" in ev["caller_context"]


def test_vllm_bootstrap_writes_unit_when_not_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI without --dry-run writes the unit to the override path (no systemd side effects)."""
    _write_real_pin_yaml(tmp_path / "config" / "voice_pin.yaml")
    _copy_template_into(tmp_path)
    events_path = tmp_path / "runs" / "events.jsonl"
    unit_path = tmp_path / "systemd-out" / "vllm-paul-voice.service"

    monkeypatch.chdir(tmp_path)

    rc = _run_cli([
        "--unit-path", str(unit_path),
        "--events-path", str(events_path),
    ])
    assert rc == 0
    assert unit_path.exists()
    body = unit_path.read_text(encoding="utf-8")
    assert "--enable-lora" in body
    assert "--port 8003" in body
