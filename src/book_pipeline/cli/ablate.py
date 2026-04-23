"""`book-pipeline ablate` — Phase 4 TEST-01 stub.

Plan 04-05. Validates two variant configs, computes SHA pins over every
dimension of reproducibility (variant configs, corpus ingestion run id,
voice-FT checkpoint), constructs an ``AblationRun`` Pydantic instance, and
calls ``create_ablation_run_skeleton`` to lay out ``runs/ablations/{run_id}/``.

No ablation logic runs here. Phase 6 TEST-03 wires the A/B loop on top of
the locked on-disk shape this command produces.

Self-contained — no book-domain imports. No LLM calls, no git mutations,
no network I/O.

Flags:
  --variant-a PATH    Variant A config YAML (required; ModeThresholdsConfig shape).
  --variant-b PATH    Variant B config YAML (required; same shape).
  --n N               Number of scenes in the A/B run (required; ge 1).
  --run-id ID         Optional run_id override (regex ^[A-Za-z0-9_.-]{1,64}$);
                      defaults to ``ablation_{utc_timestamp()}``.
  --ablations-root P  Root dir for skeletons (default: runs/ablations).

Exit codes:
  0  Skeleton materialized.
  2  Config validation failure / missing variant / invalid run_id.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from book_pipeline.ablation.harness import (
    AblationRun,
    create_ablation_run_skeleton,
    utc_timestamp,
)
from book_pipeline.cli.main import register_subcommand
from book_pipeline.config.mode_thresholds import (
    AlertsConfig,
    CriticBackendConfig,
    ModeAConfig,
    ModeBConfig,
    OscillationConfig,
    VoiceFidelityConfig,
)
from book_pipeline.drafter.sampling_profiles import SamplingProfiles


class _ModeThresholdsShape(BaseModel):
    """Non-Settings Pydantic model mirroring ModeThresholdsConfig's fields.

    Used to validate caller-supplied variant YAMLs without triggering
    pydantic-settings' ``settings_customise_sources`` (which would require
    the project-default ``config/mode_thresholds.yaml`` to exist on the
    filesystem — a bad constraint for ablation variants that live elsewhere).
    """

    mode_a: ModeAConfig
    mode_b: ModeBConfig
    oscillation: OscillationConfig
    alerts: AlertsConfig
    preflag_beats: list[str]
    voice_fidelity: VoiceFidelityConfig
    sampling_profiles: SamplingProfiles = Field(default_factory=SamplingProfiles)
    critic_backend: CriticBackendConfig = Field(default_factory=CriticBackendConfig)

    model_config = {"extra": "forbid"}

# Regex + defense-in-depth check: run_id must be 1-64 chars of
# [A-Za-z0-9_.-], not start with `.` or `-`, not end with `.`, and not be
# a pure dot-sequence (`.`, `..`, `...`). This blocks path traversal via
# `run_dir = ablations_root / run_id` (CR-01 mitigation).
_RUN_ID_RE = re.compile(r"^(?![.-])[A-Za-z0-9_.-]{1,64}(?<![.])$")


def _validate_run_id(run_id: str) -> None:
    """Reject run_ids that enable path traversal or escape ablations_root."""
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run_id {run_id!r}")
    # Defense-in-depth: reject any segment of only dots (e.g. `...`).
    if run_id in {".", ".."} or set(run_id) == {"."}:
        raise ValueError(f"run_id must not be a dot-sequence: {run_id!r}")


def _default_run_id() -> str:
    """Build the default run_id. ``utc_timestamp()`` returns a UTC ISO8601
    timestamp with ``:`` separators — those would break both the run_id regex
    and path handling, so we normalize to ``_`` + strip trailing ``Z``."""
    ts = utc_timestamp()
    sanitized = ts.replace(":", "_").replace(".", "_").rstrip("Z")
    return f"ablation_{sanitized}"[:64]


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "ablate",
        help=(
            "TEST-01 ablation stub — validate two variant configs + compute "
            "SHA pins + materialize runs/ablations/{run_id}/ skeleton. "
            "Actual A/B execution lands in Phase 6 TEST-03."
        ),
    )
    p.add_argument(
        "--variant-a",
        type=Path,
        required=True,
        help="Path to variant A config YAML (ModeThresholdsConfig shape).",
    )
    p.add_argument(
        "--variant-b",
        type=Path,
        required=True,
        help="Path to variant B config YAML (same shape).",
    )
    p.add_argument(
        "--n",
        type=int,
        required=True,
        help="Number of scenes in the A/B ablation run (>= 1).",
    )
    p.add_argument(
        "--run-id",
        type=str,
        default=None,
        help=(
            "Optional run_id (regex ^[A-Za-z0-9_.-]{1,64}$); default "
            "ablation_<utc-timestamp>."
        ),
    )
    p.add_argument(
        "--ablations-root",
        type=Path,
        default=Path("runs/ablations"),
        help="Root dir for ablation skeletons (default: runs/ablations).",
    )
    p.set_defaults(_handler=_run)


def _compute_file_sha(path: Path) -> str:
    """Return first-40 chars of sha256(file_bytes). Repo convention — short
    hex over the content; full sha256 is wasteful for a display column."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:40]


def _load_and_validate_variant(path: Path) -> None:
    """Parse YAML + construct ModeThresholdsConfig with YAML-only source.

    Raises ValidationError / YAMLError / ValueError on shape issues. Unlike
    ``ModeThresholdsConfig()`` (which hits ``config/mode_thresholds.yaml`` by
    default), we explicitly parse the caller's YAML and pass its dict to the
    Pydantic model — the variant files live outside the project-default
    config/ tree.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"variant config at {path} is not a YAML mapping"
        )
    _ModeThresholdsShape.model_validate(data)


def _resolve_corpus_sha(indexes_dir: Path) -> str:
    """Pull corpus_sha from indexes/resolved_model_revision.json.

    Returns 'unknown' if the file is absent; Phase 4 accepts this — Phase 6
    TEST-03 can fail-fast if it wants a stricter gate.
    """
    path = indexes_dir / "resolved_model_revision.json"
    if not path.exists():
        return "unknown"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "unknown"
    return str(
        data.get("ingestion_run_id") or data.get("sha") or "unknown"
    )


def _resolve_voice_pin_sha() -> str:
    """Load VoicePinConfig and extract voice_pin.checkpoint_sha.

    Returns 'unknown' if VoicePinConfig cannot be loaded (missing yaml etc).
    """
    try:
        from book_pipeline.config.voice_pin import VoicePinConfig

        cfg = VoicePinConfig()  # type: ignore[call-arg]
        return str(cfg.voice_pin.checkpoint_sha)
    except Exception:
        return "unknown"


def _run(args: argparse.Namespace) -> int:
    variant_a: Path = Path(args.variant_a)
    variant_b: Path = Path(args.variant_b)
    n: int = int(args.n)

    # --- Existence checks ---
    if not variant_a.is_file():
        print(f"Error: --variant-a not found at {variant_a}", file=sys.stderr)
        return 2
    if not variant_b.is_file():
        print(f"Error: --variant-b not found at {variant_b}", file=sys.stderr)
        return 2

    if n < 1:
        print(f"Error: --n must be >= 1 (got {n})", file=sys.stderr)
        return 2

    # --- Shape validation ---
    try:
        _load_and_validate_variant(variant_a)
    except (ValidationError, yaml.YAMLError, ValueError) as exc:
        print(
            f"Error: --variant-a failed validation: {exc}",
            file=sys.stderr,
        )
        return 2
    try:
        _load_and_validate_variant(variant_b)
    except (ValidationError, yaml.YAMLError, ValueError) as exc:
        print(
            f"Error: --variant-b failed validation: {exc}",
            file=sys.stderr,
        )
        return 2

    # --- run_id ---
    run_id: str = args.run_id if args.run_id is not None else _default_run_id()
    try:
        _validate_run_id(run_id)
    except ValueError as exc:
        print(
            f"Error: invalid run_id {run_id!r}; "
            f"must match ^[A-Za-z0-9_.-]{{1,64}}$ and must not be a "
            f"dot-sequence ({exc})",
            file=sys.stderr,
        )
        return 2

    # --- SHAs ---
    sha_a = _compute_file_sha(variant_a)
    sha_b = _compute_file_sha(variant_b)
    corpus_sha = _resolve_corpus_sha(Path("indexes"))
    voice_pin_sha = _resolve_voice_pin_sha()

    # --- Build + materialize ---
    run = AblationRun(
        run_id=run_id,
        variant_a_config_sha=sha_a,
        variant_b_config_sha=sha_b,
        n_scenes=n,
        corpus_sha=corpus_sha,
        voice_pin_sha=voice_pin_sha,
        created_at=utc_timestamp(),
    )
    run_dir = create_ablation_run_skeleton(run, Path(args.ablations_root))

    # --- Print summary ---
    print(f"[ablate] run_id={run_id}")
    print(f"[ablate] variant_a_config_sha={sha_a}")
    print(f"[ablate] variant_b_config_sha={sha_b}")
    print(
        f"[ablate] n_scenes={n}  corpus_sha={corpus_sha}  "
        f"voice_pin_sha={voice_pin_sha}"
    )
    print(
        f"[ablate] skeleton={run_dir}/ created (a/, b/, ablation_config.json)"
    )
    print("[ablate] Phase 6 TEST-03 will drive actual variant execution.")
    return 0


register_subcommand("ablate", _add_parser)


__all__: list[str] = [
    "_run",
]


# Suppress mypy unused-import on _Any — reserved for future type hints.
_: Any = None
