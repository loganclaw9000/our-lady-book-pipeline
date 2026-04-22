"""`book-pipeline smoke-event` — Phase 1 exit-criterion smoke test for OBS-01.

Per CONTEXT.md D-06 + phase testbed_emphasis: a dummy scene-request event must
round-trip through EventLogger and land in runs/events.jsonl before Phase 1
is accepted.

This command has two role paths:

  --role smoke_test (default)
      Generic smoke test; role='smoke_test', no voice pin. Exercises the
      bare-minimum OBS-01 contract: construct Event -> emit -> re-read -> parse.

  --role drafter
      Drafter-shaped event with checkpoint_sha loaded from config/voice_pin.yaml
      via VoicePinConfig. Wires the voice-pin SHA schema path end-to-end (phase
      goal "voice-pin SHA verification wired"). Real SHA verification against
      loaded weights lands in Phase 3 DRAFT-01; this plan only proves the
      config -> Event -> JSONL path, so voice_pin.yaml's placeholder
      'TBD-phase3' is sufficient.

Steps (both roles):
    1. Construct a canonical Event (smoke_test or drafter).
    2. Emit via JsonlEventLogger.
    3. Read back last line of runs/events.jsonl.
    4. Parse via Event.model_validate_json.
    5. Assert event_id round-trips.
    6. (drafter only) Assert checkpoint_sha round-trips AND matches voice_pin.yaml.
    7. Print summary; exit 0 on success.

Distinct exit codes:
    0   success
    10  emit() raised
    11  target file not created
    12  target file empty after emit
    13  round-trip parse failed
    14  event_id mismatch
    15  checkpoint_sha or drafter-shape mismatch (drafter only)
    16  voice_pin config load failed (drafter only)
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from book_pipeline.cli.main import register_subcommand
from book_pipeline.interfaces.types import Event
from book_pipeline.observability import JsonlEventLogger, event_id, hash_text

SMOKE_PROMPT = "phase1 smoke event: if you can read this line in runs/events.jsonl, OBS-01 is live."
DRAFTER_SMOKE_PROMPT = "phase1 drafter-role smoke: voice-pin SHA schema path wired."


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "smoke-event",
        help=(
            "Emit a canonical Phase 1 smoke Event to runs/events.jsonl and "
            "verify round-trip (OBS-01 exit criterion)."
        ),
    )
    p.add_argument(
        "--path",
        default="runs/events.jsonl",
        help="Target JSONL path (default: runs/events.jsonl).",
    )
    p.add_argument(
        "--role",
        choices=["smoke_test", "drafter"],
        default="smoke_test",
        help=(
            "smoke_test (default): generic OBS-01 exit-criterion smoke. "
            "drafter: emits role='drafter' + mode='A' + checkpoint_sha loaded "
            "from config/voice_pin.yaml — wires the voice-pin SHA schema path."
        ),
    )
    p.set_defaults(_handler=_run)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _build_smoke_event() -> Event:
    ts = _now_iso()
    prompt_h = hash_text(SMOKE_PROMPT)
    output_h = hash_text("ok")
    eid = event_id(ts, "smoke_test", "book_pipeline.cli.smoke_event:_run", prompt_h)
    return Event(
        event_id=eid,
        ts_iso=ts,
        role="smoke_test",
        model="book-pipeline-smoke",
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        latency_ms=0,
        temperature=None,
        top_p=None,
        caller_context={
            "module": "book_pipeline.cli.smoke_event",
            "function": "_run",
        },
        output_hash=output_h,
        mode=None,
        rubric_version=None,
        checkpoint_sha=None,
        extra={"purpose": "phase1_exit_criterion"},
    )


def _build_drafter_smoke_event() -> tuple[Event, str]:
    """Build drafter-role Event with checkpoint_sha from VoicePinConfig.

    Returns (event, expected_sha) so the caller can assert the round-trip.
    Raises on config load failure — the caller translates the exception to
    CLI exit code 16.

    Lazy import of VoicePinConfig so that `--role smoke_test` does not require
    config/voice_pin.yaml to exist or be valid (keeps the generic smoke path
    dependency-free).
    """
    from book_pipeline.config.voice_pin import VoicePinConfig

    # pydantic-settings populates `voice_pin` from the YAML source wired in
    # settings_customise_sources; mypy --strict can't see through BaseSettings
    # __init__, so this ignore is the documented plan-03 pattern (same as
    # loader.py). The ignore is tight to the call site.
    vp_cfg = VoicePinConfig()  # type: ignore[call-arg]
    pin_sha = vp_cfg.voice_pin.checkpoint_sha  # "TBD-phase3" (Phase 1 placeholder)
    ft_run_id = vp_cfg.voice_pin.ft_run_id
    base_model = vp_cfg.voice_pin.base_model

    ts = _now_iso()
    prompt_h = hash_text(DRAFTER_SMOKE_PROMPT)
    output_h = hash_text("ok")
    eid = event_id(ts, "drafter", "book_pipeline.cli.smoke_event:_run_drafter", prompt_h)
    event = Event(
        event_id=eid,
        ts_iso=ts,
        role="drafter",
        model=f"{ft_run_id}@{base_model}",
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        latency_ms=0,
        temperature=None,
        top_p=None,
        caller_context={
            "module": "book_pipeline.cli.smoke_event",
            "function": "_run_drafter",
        },
        output_hash=output_h,
        mode="A",
        rubric_version=None,
        checkpoint_sha=pin_sha,
        extra={
            "purpose": "phase1_voice_pin_sha_wiring",
            "ft_run_id": ft_run_id,
            "base_model": base_model,
        },
    )
    return event, pin_sha


def _run(args: argparse.Namespace) -> int:
    path = Path(args.path)
    logger = JsonlEventLogger(path=path)

    expected_sha: str | None
    if args.role == "drafter":
        try:
            event, expected_sha = _build_drafter_smoke_event()
        except Exception as exc:
            print(f"[FAIL] voice_pin config load failed: {exc}", file=sys.stderr)
            return 16
    else:
        event = _build_smoke_event()
        expected_sha = None

    try:
        logger.emit(event)
    except Exception as exc:
        print(f"[FAIL] emit() raised: {exc}", file=sys.stderr)
        return 10

    if not path.exists():
        print(f"[FAIL] {path} was not created", file=sys.stderr)
        return 11

    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        print(f"[FAIL] {path} is empty after emit", file=sys.stderr)
        return 12

    last_line = lines[-1]
    try:
        parsed = Event.model_validate_json(last_line)
    except Exception as exc:
        print(f"[FAIL] round-trip parse failed: {exc}", file=sys.stderr)
        print(f"       last line: {last_line[:200]}...", file=sys.stderr)
        return 13

    if parsed.event_id != event.event_id:
        print(
            f"[FAIL] event_id mismatch: wrote {event.event_id}, read {parsed.event_id}",
            file=sys.stderr,
        )
        return 14

    if args.role == "drafter":
        # Phase-goal assertion: the voice-pin SHA schema path must round-trip
        # through config -> Event -> JSONL -> parse with byte-exact fidelity.
        if parsed.checkpoint_sha != expected_sha:
            print(
                f"[FAIL] checkpoint_sha mismatch: voice_pin.yaml has "
                f"{expected_sha!r}, emitted Event round-tripped as "
                f"{parsed.checkpoint_sha!r}",
                file=sys.stderr,
            )
            return 15
        if parsed.role != "drafter" or parsed.mode != "A":
            print(
                f"[FAIL] drafter-role Event shape wrong: role={parsed.role!r}, "
                f"mode={parsed.mode!r} (expected role='drafter', mode='A')",
                file=sys.stderr,
            )
            return 15

    print("[OK] OBS-01 smoke test passed.")
    print(f"     role:            {parsed.role}")
    print(f"     path:            {path}")
    print(f"     total lines:     {len(lines)}")
    print(f"     last event_id:   {parsed.event_id}")
    print(f"     last ts_iso:     {parsed.ts_iso}")
    print(f"     schema_version:  {parsed.schema_version}")
    if args.role == "drafter":
        print(f"     mode:            {parsed.mode}")
        print(f"     checkpoint_sha:  {parsed.checkpoint_sha}")
        print(f"     model:           {parsed.model}")
    return 0


register_subcommand("smoke-event", _add_parser)
