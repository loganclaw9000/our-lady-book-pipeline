"""Plan 04-05 Task 2 — `book-pipeline ablate` CLI stub tests.

5 tests:
  1. --help exits 0 + usage contains --variant-a, --variant-b, --n
  2. Happy path: valid variants + voice_pin.yaml + resolved_model_revision.json
     → exit 0 + skeleton materialized on disk + stdout contains [ablate] +
     "Phase 6 TEST-03"
  3. Missing variant file → exit 2
  4. Invalid --run-id (regex fail) → exit 2 with stderr "invalid run_id"
  5. Variant config validation failure (malformed YAML) → exit 2
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


def test_ablate_help() -> None:
    """`book-pipeline ablate --help` exits 0 with --variant-a/--variant-b/--n."""
    result = subprocess.run(
        ["uv", "run", "book-pipeline", "ablate", "--help"],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )
    assert result.returncode == 0, (
        f"ablate --help failed: stdout={result.stdout} stderr={result.stderr}"
    )
    out = result.stdout
    assert "--variant-a" in out
    assert "--variant-b" in out
    assert "--n" in out


def _write_minimal_voice_pin(path: Path) -> None:
    """Write a minimal config/voice_pin.yaml matching VoicePinConfig shape."""
    data = {
        "voice_pin": {
            "source_repo": "paul-thinkpiece-pipeline",
            "source_commit_sha": "abc123def456" + "0" * 28,
            "ft_run_id": "test_run",
            "checkpoint_path": "/tmp/test/checkpoint",
            "checkpoint_sha": "deadbeefcafe" + "0" * 52,
            "base_model": "Qwen/Qwen3-8B",
            "trained_on_date": "2026-01-01",
            "pinned_on_date": "2026-01-02",
            "pinned_reason": "test",
            "vllm_serve_config": {
                "port": 8002,
                "max_model_len": 8192,
                "dtype": "bfloat16",
                "tensor_parallel_size": 1,
            },
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _write_valid_variant(path: Path) -> None:
    """Write a valid mode_thresholds.yaml-shaped YAML for ModeThresholdsConfig."""
    # Mirror config/mode_thresholds.yaml in full so ModeThresholdsConfig validates.
    data = {
        "mode_a": {
            "regen_budget_R": 3,
            "per_scene_cost_cap_usd": 0.0,
            "voice_fidelity_band": {"min": 0.6, "max": 0.88},
        },
        "mode_b": {
            "model_id": "claude-opus-4-7",
            "per_scene_cost_cap_usd": 2.0,
            "regen_attempts": 1,
            "prompt_cache_ttl": "1h",
        },
        "oscillation": {"enabled": True, "max_axis_flips": 2},
        "alerts": {
            "telegram_cool_down_seconds": 3600,
            "dedup_window_seconds": 3600,
        },
        "preflag_beats": [],
        "voice_fidelity": {
            "anchor_set_sha": "a" * 64,
            "pass_threshold": 0.78,
            "flag_band_min": 0.75,
            "flag_band_max": 0.78,
            "fail_threshold": 0.75,
            "memorization_flag_threshold": 0.95,
        },
        "sampling_profiles": {
            "prose": {
                "temperature": 0.85,
                "top_p": 0.92,
                "repetition_penalty": 1.05,
                "max_tokens": 2048,
            },
            "dialogue_heavy": {
                "temperature": 0.7,
                "top_p": 0.90,
                "repetition_penalty": 1.05,
                "max_tokens": 2048,
            },
            "structural_complex": {
                "temperature": 0.6,
                "top_p": 0.88,
                "repetition_penalty": 1.05,
                "max_tokens": 2048,
            },
        },
        "critic_backend": {
            "kind": "claude_code_cli",
            "model": "claude-opus-4-7",
            "timeout_s": 180,
            "max_budget_usd_per_scene": 1.0,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _write_indexes_stub(tmp_path: Path) -> None:
    """Write indexes/resolved_model_revision.json with ingestion_run_id."""
    indexes = tmp_path / "indexes"
    indexes.mkdir(parents=True, exist_ok=True)
    (indexes / "resolved_model_revision.json").write_text(
        json.dumps({"ingestion_run_id": "ing_test_abc", "sha": "sha_abc"})
    )


def test_ablate_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Happy path: valid variants + voice_pin.yaml + resolved_model_revision
    → exit 0 + skeleton + stdout.
    """
    import book_pipeline.cli.ablate as ablate_mod

    monkeypatch.chdir(tmp_path)

    variant_a = tmp_path / "config" / "variant_a.yaml"
    variant_b = tmp_path / "config" / "variant_b.yaml"
    _write_valid_variant(variant_a)
    _write_valid_variant(variant_b)
    _write_minimal_voice_pin(tmp_path / "config" / "voice_pin.yaml")
    _write_indexes_stub(tmp_path)

    args = argparse.Namespace(
        variant_a=variant_a,
        variant_b=variant_b,
        n=5,
        run_id="ablation_test_001",
        ablations_root=tmp_path / "runs" / "ablations",
    )
    rc = ablate_mod._run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "[ablate]" in out
    assert "Phase 6 TEST-03" in out

    # Skeleton exists.
    run_dir = tmp_path / "runs" / "ablations" / "ablation_test_001"
    assert run_dir.is_dir()
    assert (run_dir / "a").is_dir()
    assert (run_dir / "b").is_dir()
    assert (run_dir / "ablation_config.json").is_file()


def test_ablate_missing_variant_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nonexistent --variant-a path → exit 2."""
    import book_pipeline.cli.ablate as ablate_mod

    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(
        variant_a=tmp_path / "does_not_exist.yaml",
        variant_b=tmp_path / "also_missing.yaml",
        n=1,
        run_id="abl_missing",
        ablations_root=tmp_path / "runs" / "ablations",
    )
    rc = ablate_mod._run(args)
    assert rc == 2


def test_ablate_invalid_run_id_returns_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    """--run-id '../evil' → exit 2 with stderr 'invalid run_id'."""
    import book_pipeline.cli.ablate as ablate_mod

    monkeypatch.chdir(tmp_path)
    variant_a = tmp_path / "config" / "variant_a.yaml"
    variant_b = tmp_path / "config" / "variant_b.yaml"
    _write_valid_variant(variant_a)
    _write_valid_variant(variant_b)
    _write_minimal_voice_pin(tmp_path / "config" / "voice_pin.yaml")
    _write_indexes_stub(tmp_path)

    args = argparse.Namespace(
        variant_a=variant_a,
        variant_b=variant_b,
        n=1,
        run_id="../evil",
        ablations_root=tmp_path / "runs" / "ablations",
    )
    rc = ablate_mod._run(args)
    assert rc == 2

    err = capsys.readouterr().err
    assert "invalid run_id" in err.lower()


def test_ablate_config_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed variant YAML (missing required fields) → exit 2."""
    import book_pipeline.cli.ablate as ablate_mod

    monkeypatch.chdir(tmp_path)

    # Variant A is malformed (missing required fields — not a valid
    # ModeThresholdsConfig shape).
    bad_variant = tmp_path / "config" / "variant_a.yaml"
    bad_variant.parent.mkdir(parents=True, exist_ok=True)
    bad_variant.write_text("mode_a:\n  regen_budget_R: 99\n")  # no other required fields

    good_variant = tmp_path / "config" / "variant_b.yaml"
    _write_valid_variant(good_variant)
    _write_minimal_voice_pin(tmp_path / "config" / "voice_pin.yaml")
    _write_indexes_stub(tmp_path)

    args = argparse.Namespace(
        variant_a=bad_variant,
        variant_b=good_variant,
        n=1,
        run_id="abl_validation_fail",
        ablations_root=tmp_path / "runs" / "ablations",
    )
    rc = ablate_mod._run(args)
    assert rc == 2
