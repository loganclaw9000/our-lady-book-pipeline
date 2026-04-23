"""Tests for `book-pipeline ingest-events` CLI (Plan 05-04 Task 1, OBS-02).

Covers:
  - Happy path: seed events.jsonl with 10 events; CLI ingests; exit 0;
    DB has >= 10 rows; last_offset sidecar file written.
  - Incremental: append 5 more events; re-run CLI; DB now 15 rows; offset advanced.
  - Discoverable via `book-pipeline --help`.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path


def _seed_events_jsonl(path: Path, count: int, start_ix: int = 0) -> None:
    """Append `count` minimal Event-shaped JSON lines to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for i in range(start_ix, start_ix + count):
            ev = {
                "schema_version": "1.0",
                "event_id": f"ev{i:05d}",
                "ts_iso": f"2026-04-23T12:00:{i % 60:02d}Z",
                "role": "drafter",
                "model": "paul-voice-latest",
                "prompt_hash": f"ph{i}",
                "input_tokens": 100,
                "cached_tokens": 0,
                "output_tokens": 50,
                "latency_ms": 500,
                "caller_context": {"scene_id": f"ch01_sc{i % 10:02d}"},
                "output_hash": f"oh{i}",
                "mode": "A",
                "rubric_version": None,
                "checkpoint_sha": "abc",
                "extra": {},
            }
            fh.write(json.dumps(ev) + "\n")


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run book-pipeline via uv (mirrors Plan 05-01 CLI-test pattern)."""
    return subprocess.run(
        ["uv", "run", "book-pipeline", *args],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )


def test_cli_discoverable() -> None:
    """book-pipeline --help lists ingest-events subcommand."""
    result = _run_cli(["--help"])
    assert result.returncode == 0, result.stderr
    assert "ingest-events" in result.stdout


def test_cli_ingest_events_happy_path(tmp_path: Path) -> None:
    """Ingest 10 events; exit 0; DB has 10 rows; last_offset sidecar written."""
    events = tmp_path / "runs" / "events.jsonl"
    db = tmp_path / "metrics.sqlite3"
    _seed_events_jsonl(events, 10)

    result = _run_cli(
        ["ingest-events", "--db", str(db), "--events", str(events)]
    )
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr}\nstdout={result.stdout}"
    )
    assert db.exists(), "DB file not created"

    conn = sqlite3.connect(str(db))
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        assert count >= 10, f"expected >=10 rows; got {count}"
    finally:
        conn.close()

    offset_path = Path(str(db) + ".last_offset")
    assert offset_path.exists(), f"last_offset sidecar missing at {offset_path}"
    offset_val = int(offset_path.read_text().strip())
    assert offset_val > 0, f"offset should be >0; got {offset_val}"


def test_cli_ingest_events_incremental(tmp_path: Path) -> None:
    """Second run picks up newly-appended events; idempotent upsert preserves total."""
    events = tmp_path / "runs" / "events.jsonl"
    db = tmp_path / "metrics.sqlite3"
    _seed_events_jsonl(events, 10)

    first = _run_cli(
        ["ingest-events", "--db", str(db), "--events", str(events)]
    )
    assert first.returncode == 0, first.stderr

    offset_path = Path(str(db) + ".last_offset")
    first_offset = int(offset_path.read_text().strip())

    # Append 5 more events.
    _seed_events_jsonl(events, 5, start_ix=10)

    second = _run_cli(
        ["ingest-events", "--db", str(db), "--events", str(events)]
    )
    assert second.returncode == 0, second.stderr

    conn = sqlite3.connect(str(db))
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        assert count == 15, f"expected 15 rows total; got {count}"
    finally:
        conn.close()

    second_offset = int(offset_path.read_text().strip())
    assert second_offset > first_offset, (
        f"offset did not advance; first={first_offset} second={second_offset}"
    )
