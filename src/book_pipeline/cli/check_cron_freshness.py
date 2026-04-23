"""book-pipeline check-cron-freshness — D-14 stale-cron detector.

Plan 05-04 Task 2. Reads `runs/events.jsonl`, finds the most-recent
`role='nightly_run'` Event, compares its `ts_iso` against now. If older
than `--threshold-hours` (default 36h) — or the Event is absent entirely —
emits a Telegram alert `stale_cron_detected` and exits 3.

Runs as its own openclaw cron entry at 08:00 PT (D-14): independent of the
02:00 nightly so a broken nightly cron cannot self-silence the detector.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from book_pipeline.alerts.telegram import TelegramAlerter, TelegramPermanentError
from book_pipeline.cli.main import register_subcommand

DEFAULT_EVENTS_PATH = Path("runs/events.jsonl")
DEFAULT_THRESHOLD_HOURS = 36


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "check-cron-freshness",
        help=(
            "D-14 stale-cron detector: emit stale_cron_detected Telegram "
            "alert if the last role='nightly_run' Event in runs/events.jsonl "
            "is older than --threshold-hours (default 36)."
        ),
    )
    p.add_argument(
        "--events",
        default=str(DEFAULT_EVENTS_PATH),
        help=f"Path to events.jsonl (default: {DEFAULT_EVENTS_PATH}).",
    )
    p.add_argument(
        "--threshold-hours",
        type=int,
        default=DEFAULT_THRESHOLD_HOURS,
        help=f"Stale threshold in hours (default: {DEFAULT_THRESHOLD_HOURS}).",
    )
    p.set_defaults(_handler=_run)


def _build_alerter() -> TelegramAlerter | None:
    """Build a TelegramAlerter from env; None when env incomplete.

    Tests monkeypatch this entire function to inject a fake alerter.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return None
    return TelegramAlerter(
        bot_token=token,
        chat_id=chat_id,
        cooldown_path=Path("runs/alert_cooldowns.json"),
    )


def _parse_ts(ts_iso: str) -> datetime | None:
    """Parse an RFC3339-ish timestamp; return None on failure.

    Accepts trailing 'Z' and offsets; coerces to UTC-aware datetime.
    """
    if not ts_iso:
        return None
    # `datetime.fromisoformat` (py>=3.11) accepts "...Z"; belt-and-braces:
    raw = ts_iso.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _latest_nightly_run_ts(events_path: Path) -> datetime | None:
    """Scan events.jsonl for the most-recent role='nightly_run' Event.

    Returns None if the file is absent or no such event exists.
    """
    if not events_path.exists():
        return None
    latest: datetime | None = None
    with events_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("role") != "nightly_run":
                continue
            ts = _parse_ts(str(payload.get("ts_iso", "")))
            if ts is None:
                continue
            if latest is None or ts > latest:
                latest = ts
    return latest


def _run(args: argparse.Namespace) -> int:
    events_path = Path(args.events)
    threshold_hours = int(args.threshold_hours)

    latest = _latest_nightly_run_ts(events_path)
    now = datetime.now(UTC)

    if latest is None:
        hours_since: float = math.inf
    else:
        hours_since = (now - latest).total_seconds() / 3600.0

    if latest is not None and hours_since <= threshold_hours:
        print(
            f"[check-cron-freshness] last nightly_run Event was "
            f"{hours_since:.1f}h ago (<= {threshold_hours}h) — OK."
        )
        return 0

    # Stale or absent.
    hours_display: Any = (
        "never" if math.isinf(hours_since) else f"{hours_since:.1f}"
    )

    print(
        f"[check-cron-freshness] STALE — last nightly_run ts was "
        f"{hours_display}h ago (threshold={threshold_hours}h).",
        file=sys.stderr,
    )

    alerter = _build_alerter()
    if alerter is not None:
        try:
            alerter.send_alert(
                "stale_cron_detected",
                {"hours_since": hours_display},
            )
        except TelegramPermanentError as exc:
            # OQ 4: soft-fail — alert delivery failure does not change the
            # stale verdict (exit 3 still returned).
            print(
                f"[check-cron-freshness] alert delivery failed: {exc}",
                file=sys.stderr,
            )
    else:
        print(
            "[check-cron-freshness] Telegram not configured — "
            "alert degraded to stderr only (OQ 4 soft-fail).",
            file=sys.stderr,
        )
    return 3


register_subcommand("check-cron-freshness", _add_parser)


__all__ = ["_run"]
