"""Tests for OBS-02 SQLite ledger (Plan 05-04 Task 1, D-17).

Covers:
  - init_schema: creates events + schema_meta tables; schema_meta carries
    version=1.
  - ingest_event_rows: idempotent INSERT ... ON CONFLICT(event_id, axis) DO
    NOTHING; two runs yield same row count.
  - event_to_rows: per-axis expansion — role='critic' Events with
    extra.per_axis_scores map to one ledger row per axis.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from book_pipeline.interfaces.types import Event
from book_pipeline.observability.ledger import (
    event_to_rows,
    ingest_event_rows,
    init_schema,
)


def _row_dict_for(event_id_str: str, axis: str = "", role: str = "drafter") -> dict:
    return {
        "event_id": event_id_str,
        "axis": axis,
        "scene_id": "ch01_sc01",
        "chapter_num": 1,
        "attempt_number": 1,
        "score": None,
        "severity": None,
        "mode_tag": "A",
        "voice_fidelity": None,
        "cost_usd": 0.01,
        "ts_iso": "2026-04-23T12:00:00Z",
        "role": role,
        "schema_version": "1.0",
    }


def test_init_schema_creates_tables(tmp_path: Path) -> None:
    """init_schema creates events + schema_meta tables; version=1 seeded."""
    db = tmp_path / "metrics.sqlite3"
    init_schema(db)

    conn = sqlite3.connect(str(db))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        names = [row[0] for row in cur.fetchall()]
        assert "events" in names, f"events missing; got {names!r}"
        assert "schema_meta" in names, f"schema_meta missing; got {names!r}"

        cur = conn.execute("SELECT version_int FROM schema_meta")
        rows = cur.fetchall()
        assert rows and rows[0][0] == 1, f"expected version_int=1; got {rows!r}"
    finally:
        conn.close()


def test_ingest_event_rows_inserts_new(tmp_path: Path) -> None:
    """Three distinct event_ids -> 3 new rows."""
    db = tmp_path / "metrics.sqlite3"
    init_schema(db)
    rows = [_row_dict_for(f"ev{i:03d}") for i in range(3)]
    inserted = ingest_event_rows(db, rows)
    assert inserted == 3, f"expected 3 new rows; got {inserted}"

    conn = sqlite3.connect(str(db))
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        assert count == 3, f"expected DB count=3; got {count}"
    finally:
        conn.close()


def test_ingest_event_rows_idempotent(tmp_path: Path) -> None:
    """Re-ingesting the same rows: second call returns 0; DB count stays 3."""
    db = tmp_path / "metrics.sqlite3"
    init_schema(db)
    rows = [_row_dict_for(f"ev{i:03d}") for i in range(3)]
    first = ingest_event_rows(db, rows)
    second = ingest_event_rows(db, rows)
    assert first == 3
    assert second == 0, f"expected 0 new on re-ingest; got {second}"

    conn = sqlite3.connect(str(db))
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        assert count == 3, f"expected DB count still 3; got {count}"
    finally:
        conn.close()


def test_ingest_event_rows_per_axis_expansion(tmp_path: Path) -> None:
    """One critic Event with per_axis_scores -> 5 ledger rows with matching
    event_id + distinct axis values."""
    db = tmp_path / "metrics.sqlite3"
    init_schema(db)
    ev = Event(
        event_id="critic_ev_001",
        ts_iso="2026-04-23T12:00:00Z",
        role="critic",
        model="claude-opus-4-7",
        prompt_hash="ph",
        input_tokens=100,
        cached_tokens=0,
        output_tokens=50,
        latency_ms=500,
        caller_context={"scene_id": "ch01_sc01", "chapter_num": 1, "attempt_number": 2},
        output_hash="oh",
        rubric_version="v1",
        extra={
            "per_axis_scores": {
                "historical": 85,
                "metaphysics": 70,
                "arc": 80,
                "donts": 95,
                "voice": 90,
            },
            "per_axis_severities": {
                "historical": "low",
                "metaphysics": "mid",
                "arc": "low",
                "donts": "low",
                "voice": "low",
            },
        },
    )
    rows = event_to_rows(ev)
    assert len(rows) == 5, f"expected 5 rows (one per axis); got {len(rows)}"
    axes = {r["axis"] for r in rows}
    assert axes == {"historical", "metaphysics", "arc", "donts", "voice"}
    for r in rows:
        assert r["event_id"] == "critic_ev_001"

    inserted = ingest_event_rows(db, rows)
    assert inserted == 5, f"expected 5 new rows; got {inserted}"

    conn = sqlite3.connect(str(db))
    try:
        cur = conn.execute(
            "SELECT axis, score, severity FROM events WHERE event_id = 'critic_ev_001' ORDER BY axis"
        )
        fetched = cur.fetchall()
        axis_to_score = {a: (s, sev) for (a, s, sev) in fetched}
        assert axis_to_score["historical"] == (85.0, "low")
        assert axis_to_score["metaphysics"] == (70.0, "mid")
    finally:
        conn.close()
