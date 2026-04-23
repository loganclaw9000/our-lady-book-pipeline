"""AblationRun config + on-disk skeleton (TEST-01 foundation).

Phase 4 ships the config shape + directory layout so Phase 6 TEST-03 has
an established on-disk contract to build against. This module contains
NO execution logic; actual variant-A vs variant-B runs land in Phase 6.

Kernel package — no book-domain imports. Import-linter contract 1
(pyproject.toml) enforces the boundary on every commit.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class AblationRun(BaseModel):
    """Pydantic config for one A/B ablation run.

    Carries SHA pins for every dimension of reproducibility required by
    TEST-03 (config, corpus, checkpoint). `run_id` is typically an ISO
    timestamp with microsecond precision — caller supplies; harness does
    not generate.
    """

    run_id: str
    variant_a_config_sha: str
    variant_b_config_sha: str
    n_scenes: int = Field(ge=1)
    corpus_sha: str
    voice_pin_sha: str
    created_at: str
    status: Literal["pending", "running", "complete", "failed"] = "pending"
    notes: str = ""


def create_ablation_run_skeleton(
    run: AblationRun,
    ablations_root: Path = Path("runs/ablations"),
) -> Path:
    """Create `{ablations_root}/{run.run_id}/{a,b}/` + `ablation_config.json`.

    Idempotent: if the run dir exists, the config JSON is rewritten but
    variant subdirectories are not emptied. Returns the run root path.

    Defense-in-depth (CR-01): resolve both ablations_root and the computed
    run_dir, then assert run_dir is a descendant of ablations_root before
    any mkdir. Blocks path traversal if the caller supplies a run_id that
    slipped past the CLI regex (e.g. programmatic callers).
    """
    ablations_root_resolved = Path(ablations_root).resolve()
    run_dir = (ablations_root_resolved / run.run_id).resolve()
    # Containment check — run_dir must be a strict descendant of the root.
    try:
        run_dir.relative_to(ablations_root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"run_id {run.run_id!r} escapes ablations_root "
            f"{ablations_root_resolved}: resolved run_dir={run_dir}"
        ) from exc
    if run_dir == ablations_root_resolved:
        raise ValueError(
            f"run_id {run.run_id!r} resolves to the ablations_root itself"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "a").mkdir(exist_ok=True)
    (run_dir / "b").mkdir(exist_ok=True)
    (run_dir / "a" / ".gitkeep").touch(exist_ok=True)
    (run_dir / "b" / ".gitkeep").touch(exist_ok=True)
    config_path = run_dir / "ablation_config.json"
    # Atomic: tmp + rename (matches orchestrator state persistence pattern).
    tmp = config_path.with_suffix(".json.tmp")
    tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, config_path)
    return run_dir


def utc_timestamp() -> str:
    """Return microsecond-precision UTC ISO-8601 usable as a run_id prefix."""
    return (
        datetime.now(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


__all__ = ["AblationRun", "create_ablation_run_skeleton", "utc_timestamp"]
