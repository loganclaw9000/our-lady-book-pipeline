"""book-pipeline vllm-bootstrap — render + (optionally) install + start the vLLM unit.

CLI composition seam: this module imports from book_pipeline.book_specifics.
vllm_endpoints (sanctioned per pyproject.toml ignore_imports). Kernel modules
(drafter/vllm_client, drafter/systemd_unit) stay book-domain-clean.

Flow:
  1. Load VoicePinConfig() — bail with exit 2 if checkpoint_sha is the Phase-1
     'TBD-phase3' placeholder ("run book-pipeline pin-voice first").
  2. Render the systemd unit via Jinja2 template (from config/systemd/).
  3. If --dry-run: print unit to stdout + emit role='vllm_bootstrap' Event + exit 0.
  4. Otherwise: atomic write to ~/.config/systemd/user/vllm-paul-voice.service
     (override via --unit-path).
  5. If --enable: daemon-reload + systemctl --user enable. Failures logged.
  6. If --start:  systemctl --user start + poll_health + boot_handshake(pin).
     - VoicePinMismatch → exit 3 (SHA drift — voice_pin.yaml disagrees with
       the served LoRA).
     - VllmHandshakeError → exit 4 (vLLM up but wrong or no LoRA).
  7. Print summary + emit role='vllm_bootstrap' Event.

Operator note: --enable / --start are opt-in because they have real
side effects (systemd unit registration, GPU memory). The first REAL boot
lives in Plan 03-08 under a human-verify checkpoint. This CLI's unit tests
monkeypatch subprocess + httpx to stay side-effect-free.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from book_pipeline.book_specifics.vllm_endpoints import (
    DEFAULT_BASE_URL,
    HEALTH_POLL_INTERVAL_S,
    HEALTH_POLL_TIMEOUT_S,
    LORA_MODULE_NAME,
)
from book_pipeline.cli.main import register_subcommand
from book_pipeline.drafter.systemd_unit import (
    daemon_reload,
    poll_health,
    render_unit,
    systemctl_user,
    write_unit,
)
from book_pipeline.drafter.vllm_client import (
    VllmClient,
    VllmHandshakeError,
)
from book_pipeline.interfaces.types import Event
from book_pipeline.observability import JsonlEventLogger, event_id, hash_text
from book_pipeline.voice_fidelity.sha import VoicePinMismatch

DEFAULT_TEMPLATE_PATH = "config/systemd/vllm-paul-voice.service.j2"
DEFAULT_UNIT_NAME = "vllm-paul-voice.service"
DEFAULT_VENV_PYTHON = "/home/admin/finetuning/venv_cu130/bin/python"
DEFAULT_ENVIRONMENT_FILE = "/home/admin/finetuning/cu130.env"
DEFAULT_GPU_MEMORY_UTILIZATION = 0.85
TBD_PLACEHOLDER = "TBD-phase3"


def _default_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / DEFAULT_UNIT_NAME


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "vllm-bootstrap",
        help=(
            "Render + install + (optionally) start the vLLM paul-voice "
            "systemd --user unit. SHA-gated boot handshake (V-3 live)."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered unit to stdout + emit Event; write nothing.",
    )
    p.add_argument(
        "--unit-path",
        default=None,
        help=(
            "Override the unit output path "
            "(default: ~/.config/systemd/user/vllm-paul-voice.service)."
        ),
    )
    p.add_argument(
        "--enable",
        action="store_true",
        help="After write: daemon-reload + systemctl --user enable vllm-paul-voice.service.",
    )
    p.add_argument(
        "--start",
        action="store_true",
        help=(
            "After enable: systemctl --user start + poll /v1/models + "
            "boot_handshake (V-3 SHA gate)."
        ),
    )
    p.add_argument(
        "--environment-file",
        default=DEFAULT_ENVIRONMENT_FILE,
        help=f"EnvironmentFile= value for the unit (default: {DEFAULT_ENVIRONMENT_FILE}).",
    )
    p.add_argument(
        "--venv-python",
        default=DEFAULT_VENV_PYTHON,
        help=f"Python interpreter for ExecStart (default: {DEFAULT_VENV_PYTHON}).",
    )
    p.add_argument(
        "--template-path",
        default=DEFAULT_TEMPLATE_PATH,
        help=f"Jinja2 template path (default: {DEFAULT_TEMPLATE_PATH}).",
    )
    p.add_argument(
        "--events-path",
        default=None,
        help="Override runs/events.jsonl (default: runs/events.jsonl).",
    )
    p.set_defaults(_handler=_run)


def _render_voice_pin_unit(
    pin: Any,
    *,
    template_path: Path,
    venv_python: str,
    environment_file: str,
) -> str:
    # Honor pin-declared gpu_memory_utilization (Forge handoff added this).
    # Defensive cap against Spark wedge: clamp to safety_ceiling_max_gpu_util.
    serve_cfg = pin.vllm_serve_config
    gpu_util = min(
        serve_cfg.gpu_memory_utilization,
        serve_cfg.safety_ceiling_max_gpu_util,
    )
    return render_unit(
        template_path,
        base_model=pin.base_model,
        adapter_path=pin.checkpoint_path,
        port=serve_cfg.port,
        dtype=serve_cfg.dtype,
        max_model_len=serve_cfg.max_model_len,
        tensor_parallel_size=serve_cfg.tensor_parallel_size,
        gpu_memory_utilization=gpu_util,
        quantization=serve_cfg.quantization,
        venv_python=venv_python,
        environment_file=environment_file,
        ft_run_id=pin.ft_run_id,
    )


def _emit_bootstrap_event(
    *,
    args: argparse.Namespace,
    events_path: Path | None,
    unit_path: Path | None,
    dry_run: bool,
    enable_status: str,
    start_status: str,
    handshake_status: str,
    pin_sha: str,
    latency_ms: int,
) -> None:
    ts_iso = datetime.now(UTC).isoformat(timespec="milliseconds")
    prompt_h = hash_text(str(unit_path) if unit_path else "<dry-run>")
    eid = event_id(ts_iso, "vllm_bootstrap", "cli.vllm_bootstrap:_run", prompt_h)
    ev = Event(
        event_id=eid,
        ts_iso=ts_iso,
        role="vllm_bootstrap",
        model=LORA_MODULE_NAME,
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        latency_ms=latency_ms,
        temperature=None,
        top_p=None,
        caller_context={
            "module": "cli.vllm_bootstrap",
            "function": "_run",
            "args": {k: str(v) for k, v in vars(args).items() if not k.startswith("_")},
            "unit_path": str(unit_path) if unit_path else None,
            "dry_run": dry_run,
            "enable_status": enable_status,
            "start_status": start_status,
            "handshake_status": handshake_status,
        },
        output_hash=pin_sha,
        mode=None,
        rubric_version=None,
        checkpoint_sha=pin_sha,
        extra={},
    )
    logger = JsonlEventLogger(path=events_path) if events_path else JsonlEventLogger()
    logger.emit(ev)


def _run(args: argparse.Namespace) -> int:
    start_ns = time.monotonic_ns()
    # 1. Load VoicePinConfig; bail on TBD-phase3 placeholder.
    try:
        from book_pipeline.config.voice_pin import VoicePinConfig

        cfg = VoicePinConfig()  # type: ignore[call-arg]
    except Exception as exc:
        print(f"[FAIL] could not load voice_pin.yaml: {exc}", file=sys.stderr)
        return 2
    pin = cfg.voice_pin
    if pin.checkpoint_sha == TBD_PLACEHOLDER or pin.checkpoint_sha.startswith("TBD"):
        print(
            "[FAIL] voice_pin.yaml still contains the TBD-phase3 placeholder — "
            "run `book-pipeline pin-voice <adapter_dir>` first to compute the real SHA.",
            file=sys.stderr,
        )
        return 2

    # Warn (non-fatal) if EnvironmentFile path does not exist; systemd tolerates
    # leading '-' in EnvironmentFile= (already in the template) so absence is
    # non-fatal at unit start, but operator awareness is useful.
    if args.environment_file and not Path(args.environment_file).exists():
        print(
            f"[WARN] EnvironmentFile {args.environment_file} does not exist on disk; "
            "systemd will start the unit anyway (leading '-' prefix in template).",
            file=sys.stderr,
        )

    # 2. Render the unit.
    try:
        content = _render_voice_pin_unit(
            pin,
            template_path=Path(args.template_path),
            venv_python=args.venv_python,
            environment_file=args.environment_file,
        )
    except (FileNotFoundError, KeyError) as exc:
        print(f"[FAIL] unit render failed: {exc}", file=sys.stderr)
        return 2

    # 2.5. dry_run_gate_v1.1 — verify pin SHA against on-disk adapter BEFORE
    # the live --start handshake too. Catches digest drift pre-boot. Forge
    # collab amendment 2026-04-24.
    try:
        from book_pipeline.voice_fidelity.sha import compute_adapter_sha

        actual_sha = compute_adapter_sha(Path(pin.checkpoint_path))
        if actual_sha != pin.checkpoint_sha:
            print(
                f"[FAIL] dry-run SHA verify failed: pin.checkpoint_sha "
                f"= {pin.checkpoint_sha[:16]}... != adapter on-disk "
                f"= {actual_sha[:16]}... at {pin.checkpoint_path}. "
                f"Run `book-pipeline pin-voice {pin.checkpoint_path}` to repin.",
                file=sys.stderr,
            )
            return 3
        print(
            f"[OK] dry-run SHA verify: {actual_sha[:16]}... matches pin",
            file=sys.stderr,
        )
    except FileNotFoundError as exc:
        print(
            f"[FAIL] dry-run SHA verify: adapter files missing at "
            f"{pin.checkpoint_path}: {exc}",
            file=sys.stderr,
        )
        return 3

    enable_status = "skipped"
    start_status = "skipped"
    handshake_status = "skipped"
    unit_path: Path | None = None
    events_path = Path(args.events_path) if args.events_path else None

    # 3. Dry-run: print + emit + exit 0.
    if args.dry_run:
        print(content)
        latency_ms = max(1, (time.monotonic_ns() - start_ns) // 1_000_000)
        _emit_bootstrap_event(
            args=args,
            events_path=events_path,
            unit_path=None,
            dry_run=True,
            enable_status="skipped",
            start_status="skipped",
            handshake_status="skipped",
            pin_sha=pin.checkpoint_sha,
            latency_ms=int(latency_ms),
        )
        return 0

    # 4. Write unit atomically.
    unit_path = Path(args.unit_path) if args.unit_path else _default_unit_path()
    write_unit(unit_path.parent, unit_path.name, content)

    rc = 0

    # 5. --enable
    if args.enable:
        ok_dr, _, err_dr = daemon_reload()
        ok_en, _, err_en = systemctl_user("enable", DEFAULT_UNIT_NAME)
        if ok_dr and ok_en:
            enable_status = "ok"
        else:
            enable_status = f"fail(daemon-reload={ok_dr},enable={ok_en}):{err_dr}|{err_en}"
            print(f"[WARN] enable failed: {enable_status}", file=sys.stderr)

    # 6. --start
    if args.start:
        ok_start, _, err_start = systemctl_user("start", DEFAULT_UNIT_NAME)
        if not ok_start:
            start_status = f"fail:{err_start}"
            print(f"[FAIL] systemctl start failed: {err_start}", file=sys.stderr)
            rc = 5
        else:
            healthy = poll_health(
                DEFAULT_BASE_URL,
                timeout_s=HEALTH_POLL_TIMEOUT_S,
                interval_s=HEALTH_POLL_INTERVAL_S,
            )
            start_status = "ok" if healthy else "timeout"
            if not healthy:
                print(
                    f"[FAIL] /v1/models did not become healthy within "
                    f"{HEALTH_POLL_TIMEOUT_S}s",
                    file=sys.stderr,
                )
                rc = 5
            else:
                client = VllmClient(
                    base_url=DEFAULT_BASE_URL,
                    event_logger=(
                        JsonlEventLogger(path=events_path)
                        if events_path
                        else JsonlEventLogger()
                    ),
                    lora_module_name=LORA_MODULE_NAME,
                )
                try:
                    client.boot_handshake(pin)
                    handshake_status = "ok"
                except VoicePinMismatch as exc:
                    handshake_status = "voice_pin_mismatch"
                    print(
                        f"[FAIL] boot_handshake SHA mismatch: expected="
                        f"{exc.expected_sha}, actual={exc.actual_sha}",
                        file=sys.stderr,
                    )
                    rc = 3
                except VllmHandshakeError as exc:
                    handshake_status = f"handshake_error:{exc}"
                    print(f"[FAIL] boot_handshake: {exc}", file=sys.stderr)
                    rc = 4
                finally:
                    client.close()

    # 7. Summary + Event.
    latency_ms = max(1, (time.monotonic_ns() - start_ns) // 1_000_000)
    _emit_bootstrap_event(
        args=args,
        events_path=events_path,
        unit_path=unit_path,
        dry_run=False,
        enable_status=enable_status,
        start_status=start_status,
        handshake_status=handshake_status,
        pin_sha=pin.checkpoint_sha,
        latency_ms=int(latency_ms),
    )
    print(
        f"vllm-bootstrap → unit_path={unit_path} enable={enable_status} "
        f"start={start_status} handshake={handshake_status}"
    )
    return rc


# Silence unused-import for os (kept for future os.getenv overrides).
_ = os

register_subcommand("vllm-bootstrap", _add_parser)
