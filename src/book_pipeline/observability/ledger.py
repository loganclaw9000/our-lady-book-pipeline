"""OBS-02 SQLite metric ledger (D-17 + Plan 05-04 Task 1).

SQLite-backed idempotent ingester for `runs/events.jsonl` → `runs/metrics.sqlite3`.
Schema is additive-only and versioned in the ``schema_meta`` table so Phase 6
OBS-04 can migrate without rebuild. The ledger is NOT source of truth — it is
always rebuildable from events.jsonl via ``book-pipeline ingest-events``.

Key invariants:
  - ``PRIMARY KEY (event_id, axis)`` — one row per event-and-axis. Critic
    Events with ``extra.per_axis_scores`` expand into one row per axis; all
    other Events produce one row with ``axis=''``.
  - Idempotent upsert: ``INSERT ... ON CONFLICT(event_id, axis) DO NOTHING``
    (Pitfall 4 mitigation; SQLite >= 3.24 upsert).
  - Byte-offset tail-read (Pitfall 4): ``tail_read_since_offset`` stores the
    last-successful file offset in a sidecar file so subsequent ingest runs
    seek O(1) rather than rescan-all.

Security + durability:
  - Malformed JSON lines are skipped (not fatal); the ingester prints a
    warning to stderr per T-05-04-01.
  - last_offset sidecar written atomically via tmp + os.replace.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from book_pipeline.interfaces.types import Event

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT NOT NULL,
    axis TEXT NOT NULL DEFAULT '',
    scene_id TEXT,
    chapter_num INTEGER,
    attempt_number INTEGER,
    score REAL,
    severity TEXT,
    mode_tag TEXT,
    voice_fidelity REAL,
    cost_usd REAL,
    ts_iso TEXT NOT NULL,
    role TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    PRIMARY KEY (event_id, axis)
);
CREATE INDEX IF NOT EXISTS idx_events_ts_iso ON events(ts_iso);
CREATE INDEX IF NOT EXISTS idx_events_scene ON events(scene_id);
CREATE INDEX IF NOT EXISTS idx_events_chapter ON events(chapter_num);
CREATE TABLE IF NOT EXISTS schema_meta (
    version_int INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

# ``ON CONFLICT(event_id, axis) DO NOTHING`` is Pitfall 4's idempotency
# backstop; partial-ingest crashes re-run safely.
UPSERT_SQL = """
INSERT INTO events
  (event_id, axis, scene_id, chapter_num, attempt_number, score, severity,
   mode_tag, voice_fidelity, cost_usd, ts_iso, role, schema_version)
VALUES
  (:event_id, :axis, :scene_id, :chapter_num, :attempt_number, :score,
   :severity, :mode_tag, :voice_fidelity, :cost_usd, :ts_iso, :role,
   :schema_version)
ON CONFLICT(event_id, axis) DO NOTHING
"""


def init_schema(db_path: Path) -> None:
    """Create events + schema_meta tables + indexes; seed schema_meta v1."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta (version_int, applied_at) "
            "VALUES (1, CURRENT_TIMESTAMP)"
        )
        conn.commit()
    finally:
        conn.close()


def _row_base(
    event_id: str,
    axis: str,
    ts_iso: str,
    role: str,
    scene_id: Any,
    chapter_num: Any,
    attempt_number: Any,
    mode_tag: Any,
    schema_version: str,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "axis": axis,
        "scene_id": scene_id,
        "chapter_num": chapter_num,
        "attempt_number": attempt_number,
        "score": None,
        "severity": None,
        "mode_tag": mode_tag,
        "voice_fidelity": None,
        "cost_usd": None,
        "ts_iso": ts_iso,
        "role": role,
        "schema_version": schema_version,
    }


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def event_to_rows(event: Event) -> list[dict[str, Any]]:
    """Expand one Event into ≥1 ledger rows.

    Role='critic' Events with ``extra.per_axis_scores`` produce one row per
    axis; other Events produce one row with ``axis=''``.
    """
    caller = event.caller_context or {}
    scene_id = caller.get("scene_id")
    chapter_num = _coerce_int(caller.get("chapter_num") or caller.get("chapter"))
    attempt_number = _coerce_int(caller.get("attempt_number"))

    extra = dict(event.extra or {})
    cost_usd = _coerce_float(extra.get("cost_usd"))
    voice_fidelity = _coerce_float(extra.get("voice_fidelity"))

    per_axis_scores = extra.get("per_axis_scores")
    per_axis_severities = extra.get("per_axis_severities") or {}

    if event.role == "critic" and isinstance(per_axis_scores, Mapping) and per_axis_scores:
        out: list[dict[str, Any]] = []
        for axis_name, score in per_axis_scores.items():
            row = _row_base(
                event_id=event.event_id,
                axis=str(axis_name),
                ts_iso=event.ts_iso,
                role=event.role,
                scene_id=scene_id,
                chapter_num=chapter_num,
                attempt_number=attempt_number,
                mode_tag=event.mode,
                schema_version=event.schema_version,
            )
            row["score"] = _coerce_float(score)
            severity: Any = None
            if isinstance(per_axis_severities, Mapping):
                severity = per_axis_severities.get(axis_name)
            row["severity"] = str(severity) if severity is not None else None
            row["cost_usd"] = cost_usd
            row["voice_fidelity"] = voice_fidelity
            out.append(row)
        return out

    row = _row_base(
        event_id=event.event_id,
        axis="",
        ts_iso=event.ts_iso,
        role=event.role,
        scene_id=scene_id,
        chapter_num=chapter_num,
        attempt_number=attempt_number,
        mode_tag=event.mode,
        schema_version=event.schema_version,
    )
    row["cost_usd"] = cost_usd
    row["voice_fidelity"] = voice_fidelity
    return [row]


def ingest_event_rows(db_path: Path, rows: Sequence[Mapping[str, Any]]) -> int:
    """Idempotent bulk upsert. Returns number of NEW rows inserted."""
    if not rows:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.executemany(UPSERT_SQL, [dict(r) for r in rows])
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return int(after - before)
    finally:
        conn.close()


def read_last_offset(offset_path: Path) -> int:
    """Return stored last-successful byte offset (0 on first run)."""
    if not offset_path.exists():
        return 0
    try:
        return int(offset_path.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        return 0


def persist_offset(offset_path: Path, offset: int) -> None:
    """Atomically write the new byte offset via tmp + os.replace."""
    offset_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = offset_path.with_suffix(offset_path.suffix + ".tmp")
    tmp.write_text(str(int(offset)), encoding="utf-8")
    os.replace(tmp, offset_path)


def tail_read_since_offset(
    jsonl_path: Path,
    offset_file: Path,
) -> Iterator[tuple[dict[str, Any], int]]:
    """Yield (event_dict, new_offset) for every line in jsonl_path past the
    stored offset. Malformed lines are skipped with a stderr warning.

    The ``new_offset`` is the file byte position AFTER the yielded line —
    callers persist it only after a successful upsert of the line's rows.
    """
    start_offset = read_last_offset(offset_file)
    if not jsonl_path.exists():
        return
    # File shrunk (unexpected; treat as corruption → rescan from 0).
    try:
        file_size = jsonl_path.stat().st_size
    except OSError:
        return
    if start_offset > file_size:
        start_offset = 0
    with jsonl_path.open("rb") as fh:
        fh.seek(start_offset)
        while True:
            line_bytes = fh.readline()
            if not line_bytes:
                break
            offset_after = fh.tell()
            try:
                payload = json.loads(line_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                print(
                    f"[ledger] skipping malformed events.jsonl line at "
                    f"offset {offset_after}: {exc}",
                    file=sys.stderr,
                )
                continue
            if not isinstance(payload, dict):
                continue
            yield payload, offset_after


__all__ = [
    "SCHEMA_SQL",
    "UPSERT_SQL",
    "event_to_rows",
    "ingest_event_rows",
    "init_schema",
    "persist_offset",
    "read_last_offset",
    "tail_read_since_offset",
]
