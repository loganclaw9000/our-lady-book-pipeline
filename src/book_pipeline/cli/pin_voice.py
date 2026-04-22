"""book-pipeline pin-voice — write the REAL voice-FT pin SHA to config/voice_pin.yaml.

V-3 PITFALLS mitigation: the voice-FT drafter MUST refuse to boot if the
checkpoint SHA does not match voice_pin.yaml. This CLI is the ONE-TIME pin
event — it computes the SHA over (adapter_model.safetensors ||
adapter_config.json) and atomically writes the result under voice_pin: in
config/voice_pin.yaml.

Flow:
  1. compute_adapter_sha(adapter_dir) → 64-char hex.
  2. Probe `git -C /home/admin/paul-thinkpiece-pipeline rev-parse HEAD` with
     fallback to a literal source provenance string.
  3. Build VoicePinData (validates schema via pydantic at construction time).
  4. Atomic write: tempfile → os.replace → reload via VoicePinConfig() to
     assert round-trip cleanliness.
  5. Emit one role='voice_pin' Event with checkpoint_sha=<computed>.
  6. Print summary; exit 0.

On missing adapter files, print a clear error and exit 2.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from book_pipeline.cli.main import register_subcommand
from book_pipeline.interfaces.types import Event
from book_pipeline.observability import JsonlEventLogger, event_id, hash_text
from book_pipeline.voice_fidelity.sha import compute_adapter_sha

DEFAULT_YAML_PATH = "config/voice_pin.yaml"
DEFAULT_FT_RUN_ID = "v6_qwen3_32b"
DEFAULT_BASE_MODEL = "Qwen/Qwen3-32B"
DEFAULT_TRAINED_ON_DATE = "2026-04-14"
DEFAULT_PINNED_REASON = (
    "V6 qwen3-32b LoRA — newest stable voice-FT as of 2026-04-21 (V9/V10 did "
    "not materialize). SHA-pinned per V-3 mitigation."
)

_SOURCE_REPO = "paul-thinkpiece-pipeline"
_SOURCE_REPO_PATH = "/home/admin/paul-thinkpiece-pipeline"
_SOURCE_COMMIT_FALLBACK = "paul-thinkpiece-pipeline-worktree-2026-04-14"

_HEADER = """\
# voice_pin.yaml — pins the voice-FT checkpoint consumed by Mode-A drafter.
# Phase 3 Plan 01: REAL V6 qwen3-32b LoRA pin. SHA recomputed by
# book-pipeline pin-voice <adapter_dir>; runtime verified by
# book_pipeline.voice_fidelity.sha.verify_pin() at vLLM boot (V-3 mitigation).
"""


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "pin-voice",
        help=(
            "Compute SHA over a LoRA adapter dir + write it to config/voice_pin.yaml "
            "(V-3 mitigation: SHA enforced at vLLM boot)."
        ),
    )
    p.add_argument(
        "adapter_dir",
        help="Path to the LoRA adapter directory (must contain adapter_model.safetensors + adapter_config.json).",
    )
    p.add_argument(
        "--ft-run-id",
        default=DEFAULT_FT_RUN_ID,
        help=f"voice_pin.ft_run_id value (default: {DEFAULT_FT_RUN_ID}).",
    )
    p.add_argument(
        "--base-model",
        default=DEFAULT_BASE_MODEL,
        help=f"voice_pin.base_model (default: {DEFAULT_BASE_MODEL}).",
    )
    p.add_argument(
        "--trained-on-date",
        default=DEFAULT_TRAINED_ON_DATE,
        help=f"voice_pin.trained_on_date (default: {DEFAULT_TRAINED_ON_DATE}).",
    )
    p.add_argument(
        "--pinned-reason",
        default=DEFAULT_PINNED_REASON,
        help="voice_pin.pinned_reason (default: V6 rationale from Plan 03-01 CONTEXT).",
    )
    p.add_argument(
        "--yaml-path",
        default=DEFAULT_YAML_PATH,
        help=f"Output YAML path (default: {DEFAULT_YAML_PATH}).",
    )
    p.add_argument(
        "--events-path",
        default=None,
        help="Override events.jsonl path for testability (default: runs/events.jsonl).",
    )
    p.set_defaults(_handler=_run)


def _probe_source_commit_sha() -> str:
    """Best-effort probe of paul-thinkpiece-pipeline's HEAD SHA.

    Returns the HEAD SHA on success; otherwise a literal fallback string so
    pin consumers can still trace provenance.
    """
    try:
        result = subprocess.run(
            ["git", "-C", _SOURCE_REPO_PATH, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return _SOURCE_COMMIT_FALLBACK
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return _SOURCE_COMMIT_FALLBACK


def _build_voice_pin_dict(
    *,
    adapter_dir: Path,
    computed_sha: str,
    source_commit_sha: str,
    ft_run_id: str,
    base_model: str,
    trained_on_date: str,
    pinned_reason: str,
) -> dict[str, Any]:
    """Build the voice_pin payload dict. Shape matches VoicePinData.

    Construction validates via VoicePinConfig round-trip after write (the
    atomic-write step below). Here we return the plain dict for yaml.safe_dump.
    """
    today_iso = datetime.now(UTC).date().isoformat()
    return {
        "voice_pin": {
            "source_repo": _SOURCE_REPO,
            "source_commit_sha": source_commit_sha,
            "ft_run_id": ft_run_id,
            "checkpoint_path": str(adapter_dir.resolve()),
            "checkpoint_sha": computed_sha,
            "base_model": base_model,
            "trained_on_date": trained_on_date,
            "pinned_on_date": today_iso,
            "pinned_reason": pinned_reason,
            "vllm_serve_config": {
                "port": 8002,
                "max_model_len": 8192,
                "dtype": "bfloat16",
                "tensor_parallel_size": 1,
            },
        }
    }


def _atomic_write_yaml(payload: dict[str, Any], yaml_path: Path) -> None:
    """Write payload to yaml_path atomically (tempfile + os.replace).

    The VoicePinConfig() reload AFTER this returns is the pydantic-level
    validation gate (T-03-01-01 mitigation: invalid YAML never lands).
    """
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = yaml_path.with_suffix(yaml_path.suffix + ".tmp")
    body = _HEADER + yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    tmp_path.write_text(body, encoding="utf-8")
    os.replace(tmp_path, yaml_path)


def _build_event(
    *,
    adapter_dir: Path,
    computed_sha: str,
    source_commit_sha: str,
    ft_run_id: str,
    base_model: str,
    pinned_reason: str,
    latency_ms: int,
) -> Event:
    ts_iso = datetime.now(UTC).isoformat(timespec="milliseconds")
    prompt_h = hash_text(str(adapter_dir))
    eid = event_id(ts_iso, "voice_pin", "cli.pin_voice:_run", prompt_h)
    return Event(
        event_id=eid,
        ts_iso=ts_iso,
        role="voice_pin",
        model=ft_run_id,
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        latency_ms=latency_ms,
        temperature=None,
        top_p=None,
        caller_context={
            "module": "cli.pin_voice",
            "function": "pin_voice",
            "adapter_dir": str(adapter_dir),
        },
        output_hash=computed_sha,
        mode=None,
        rubric_version=None,
        checkpoint_sha=computed_sha,
        extra={
            "base_model": base_model,
            "source_commit_sha": source_commit_sha,
            "pinned_reason": pinned_reason,
        },
    )


def _run(args: argparse.Namespace) -> int:
    adapter_dir = Path(args.adapter_dir).expanduser()
    yaml_path = Path(args.yaml_path)

    start_ns = time.monotonic_ns()
    try:
        computed_sha = compute_adapter_sha(adapter_dir)
    except FileNotFoundError as exc:
        print(f"[FAIL] adapter SHA computation failed: {exc}", file=sys.stderr)
        return 2

    source_commit_sha = _probe_source_commit_sha()
    payload = _build_voice_pin_dict(
        adapter_dir=adapter_dir,
        computed_sha=computed_sha,
        source_commit_sha=source_commit_sha,
        ft_run_id=args.ft_run_id,
        base_model=args.base_model,
        trained_on_date=args.trained_on_date,
        pinned_reason=args.pinned_reason,
    )

    _atomic_write_yaml(payload, yaml_path)

    # Round-trip via VoicePinConfig ONLY if the output is at the canonical
    # config/voice_pin.yaml path — pydantic-settings hardcodes that yaml_file
    # lookup via SettingsConfigDict and we can't override without monkeypatching.
    # When --yaml-path points at the canonical location, the reload is live;
    # otherwise we validate the payload via direct VoicePinData construction.
    try:
        if yaml_path.resolve() == Path("config/voice_pin.yaml").resolve():
            from book_pipeline.config.voice_pin import VoicePinConfig

            cfg = VoicePinConfig()  # type: ignore[call-arg]
            # Touch the field so pydantic's validation error (if any) surfaces here.
            _ = cfg.voice_pin.checkpoint_sha
        else:
            from book_pipeline.config.voice_pin import VoicePinData

            VoicePinData(**payload["voice_pin"])
    except Exception as exc:
        print(f"[FAIL] voice_pin.yaml round-trip validation failed: {exc}", file=sys.stderr)
        return 3

    latency_ms = max(1, (time.monotonic_ns() - start_ns) // 1_000_000)
    event = _build_event(
        adapter_dir=adapter_dir,
        computed_sha=computed_sha,
        source_commit_sha=source_commit_sha,
        ft_run_id=args.ft_run_id,
        base_model=args.base_model,
        pinned_reason=args.pinned_reason,
        latency_ms=int(latency_ms),
    )
    events_path = Path(args.events_path) if args.events_path else None
    logger = JsonlEventLogger(path=events_path) if events_path else JsonlEventLogger()
    logger.emit(event)

    print(
        f"pinned voice_pin.yaml → ft_run_id={args.ft_run_id} "
        f"checkpoint_sha={computed_sha}"
    )
    return 0


register_subcommand("pin-voice", _add_parser)
