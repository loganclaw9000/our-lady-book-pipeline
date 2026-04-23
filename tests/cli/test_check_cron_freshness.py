"""Tests for `book-pipeline check-cron-freshness` CLI (Plan 05-04 Task 2, D-14).

Covers:
  - Recent role='nightly_run' Event (1h ago) → exit 0; no alert sent.
  - Stale role='nightly_run' (40h ago, >36h threshold) → exit 3; alert
    sent with condition='stale_cron_detected'.
  - No role='nightly_run' Event ever → exit 3; alert sent.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from book_pipeline.cli import check_cron_freshness as ccf


class _FakeAlerter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def send_alert(self, condition: str, detail: dict[str, Any]) -> bool:
        self.calls.append((condition, dict(detail)))
        return True


def _write_events(events_path: Path, rows: list[dict[str, Any]]) -> None:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _now_minus(hours: float) -> str:
    ts = datetime.now(UTC) - timedelta(hours=hours)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_freshness_recent_event_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = tmp_path / "runs" / "events.jsonl"
    _write_events(
        events,
        [
            {
                "schema_version": "1.0",
                "event_id": "ev1",
                "ts_iso": _now_minus(1),  # 1h ago
                "role": "nightly_run",
                "model": "n/a",
                "prompt_hash": "ph",
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 1,
                "caller_context": {},
                "output_hash": "oh",
                "extra": {},
            }
        ],
    )
    alerter = _FakeAlerter()
    monkeypatch.setattr(ccf, "_build_alerter", lambda: alerter)

    args = argparse.Namespace(
        events=str(events),
        threshold_hours=36,
    )
    rc = ccf._run(args)
    assert rc == 0, f"expected exit 0 on fresh event; got {rc}"
    assert alerter.calls == [], f"no alert should have been sent; got {alerter.calls!r}"


def test_freshness_stale_triggers_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = tmp_path / "runs" / "events.jsonl"
    _write_events(
        events,
        [
            {
                "schema_version": "1.0",
                "event_id": "ev1",
                "ts_iso": _now_minus(40),  # 40h ago → stale (>36h)
                "role": "nightly_run",
                "model": "n/a",
                "prompt_hash": "ph",
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 1,
                "caller_context": {},
                "output_hash": "oh",
                "extra": {},
            }
        ],
    )
    alerter = _FakeAlerter()
    monkeypatch.setattr(ccf, "_build_alerter", lambda: alerter)

    args = argparse.Namespace(
        events=str(events),
        threshold_hours=36,
    )
    rc = ccf._run(args)
    assert rc == 3, f"expected exit 3 on stale detection; got {rc}"

    assert len(alerter.calls) == 1, f"expected 1 alert; got {alerter.calls!r}"
    condition, detail = alerter.calls[0]
    assert condition == "stale_cron_detected"
    assert "hours_since" in detail


def test_freshness_absent_triggers_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """events.jsonl never has role='nightly_run' → treat as stale."""
    events = tmp_path / "runs" / "events.jsonl"
    _write_events(
        events,
        [
            {
                "schema_version": "1.0",
                "event_id": "ev1",
                "ts_iso": _now_minus(1),
                "role": "drafter",
                "model": "paul-voice-latest",
                "prompt_hash": "ph",
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 1,
                "caller_context": {},
                "output_hash": "oh",
                "extra": {},
            }
        ],
    )
    alerter = _FakeAlerter()
    monkeypatch.setattr(ccf, "_build_alerter", lambda: alerter)

    args = argparse.Namespace(
        events=str(events),
        threshold_hours=36,
    )
    rc = ccf._run(args)
    assert rc == 3, f"expected exit 3 when nightly_run absent; got {rc}"
    assert len(alerter.calls) == 1, f"expected 1 alert; got {alerter.calls!r}"
    condition, _detail = alerter.calls[0]
    assert condition == "stale_cron_detected"
