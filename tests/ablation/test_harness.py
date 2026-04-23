"""Tests for AblationRun harness (Plan 04-04 Task 2 — TEST-01 ablation side).

Covers 5 tests per plan <action> §3:
  A — AblationRun validates with all required fields + utc_timestamp().
  B — n_scenes >= 1 validator rejects n_scenes=0.
  C — create_ablation_run_skeleton creates {run_id}/{a,b,ablation_config.json}.
  D — Idempotent: re-calling skeleton preserves variant-subdir contents.
  E — ablation_config.json roundtrips through AblationRun.model_validate_json.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError


def test_A_ablation_run_validates(tmp_path: Path) -> None:
    """AblationRun(..complete field set..) constructs without error."""
    from book_pipeline.ablation.harness import AblationRun, utc_timestamp

    run = AblationRun(
        run_id="2026-04-23T18-00-00Z_sample",
        variant_a_config_sha="sha_a",
        variant_b_config_sha="sha_b",
        n_scenes=10,
        corpus_sha="sha_c",
        voice_pin_sha="sha_v",
        created_at=utc_timestamp(),
    )
    assert run.status == "pending"
    assert run.notes == ""
    assert run.n_scenes == 10
    # utc_timestamp returns ISO-8601 UTC with a 'Z' suffix.
    assert run.created_at.endswith("Z")


def test_B_n_scenes_positive_validator() -> None:
    """n_scenes=0 raises ValidationError (n_scenes must be >= 1)."""
    from book_pipeline.ablation.harness import AblationRun, utc_timestamp

    with pytest.raises(ValidationError):
        AblationRun(
            run_id="test_run",
            variant_a_config_sha="a",
            variant_b_config_sha="b",
            n_scenes=0,
            corpus_sha="c",
            voice_pin_sha="v",
            created_at=utc_timestamp(),
        )


def test_C_create_skeleton_creates_dirs(tmp_path: Path) -> None:
    """create_ablation_run_skeleton lays down runs/ablations/{run_id}/ tree."""
    from book_pipeline.ablation.harness import (
        AblationRun,
        create_ablation_run_skeleton,
        utc_timestamp,
    )

    run = AblationRun(
        run_id="test_run_C",
        variant_a_config_sha="a",
        variant_b_config_sha="b",
        n_scenes=5,
        corpus_sha="c",
        voice_pin_sha="v",
        created_at=utc_timestamp(),
    )
    out = create_ablation_run_skeleton(run, tmp_path)
    assert out == tmp_path / "test_run_C"
    assert (tmp_path / "test_run_C" / "ablation_config.json").is_file()
    assert (tmp_path / "test_run_C" / "a" / ".gitkeep").is_file()
    assert (tmp_path / "test_run_C" / "b" / ".gitkeep").is_file()


def test_D_skeleton_idempotent(tmp_path: Path) -> None:
    """Second call preserves contents of variant subdirs."""
    from book_pipeline.ablation.harness import (
        AblationRun,
        create_ablation_run_skeleton,
        utc_timestamp,
    )

    run = AblationRun(
        run_id="test_run_D",
        variant_a_config_sha="a",
        variant_b_config_sha="b",
        n_scenes=3,
        corpus_sha="c",
        voice_pin_sha="v",
        created_at=utc_timestamp(),
    )
    create_ablation_run_skeleton(run, tmp_path)

    # Seed a file in variant-a between calls.
    a_output = tmp_path / "test_run_D" / "a" / "phase6_result.json"
    a_output.write_text('{"score": 0.42}', encoding="utf-8")

    # Call a second time — must be idempotent.
    create_ablation_run_skeleton(run, tmp_path)

    assert a_output.is_file()
    assert a_output.read_text(encoding="utf-8") == '{"score": 0.42}'


def test_E_config_json_roundtrips(tmp_path: Path) -> None:
    """ablation_config.json is a valid AblationRun.model_validate_json input."""
    from book_pipeline.ablation.harness import (
        AblationRun,
        create_ablation_run_skeleton,
        utc_timestamp,
    )

    run = AblationRun(
        run_id="test_run_E",
        variant_a_config_sha="sha_a",
        variant_b_config_sha="sha_b",
        n_scenes=10,
        corpus_sha="sha_c",
        voice_pin_sha="sha_v",
        created_at=utc_timestamp(),
        notes="roundtrip check",
    )
    create_ablation_run_skeleton(run, tmp_path)
    cfg = (tmp_path / "test_run_E" / "ablation_config.json").read_text(
        encoding="utf-8"
    )
    reloaded = AblationRun.model_validate_json(cfg)
    assert reloaded == run
    assert reloaded.notes == "roundtrip check"
