"""book-pipeline ingest-events — OBS-02 idempotent JSONL → SQLite ingester.

Plan 05-04 Task 1 (D-17). Tail-reads runs/events.jsonl since last persisted
byte offset, upserts into runs/metrics.sqlite3 via ``INSERT ... ON CONFLICT
(event_id, axis) DO NOTHING``. Idempotent re-runs yield the same row count.

The byte-offset sidecar ``<db>.last_offset`` is the Pitfall 4 mitigation:
subsequent runs seek O(1) instead of rescanning all of events.jsonl.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from book_pipeline.cli.main import register_subcommand
from book_pipeline.interfaces.types import Event
from book_pipeline.observability.ledger import (
    event_to_rows,
    ingest_event_rows,
    init_schema,
    persist_offset,
    tail_read_since_offset,
)

DEFAULT_DB_PATH = Path("runs/metrics.sqlite3")
DEFAULT_EVENTS_PATH = Path("runs/events.jsonl")


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "ingest-events",
        help=(
            "Idempotently ingest runs/events.jsonl tail into the OBS-02 "
            "SQLite ledger at runs/metrics.sqlite3."
        ),
    )
    p.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"Target SQLite ledger path (default: {DEFAULT_DB_PATH}).",
    )
    p.add_argument(
        "--events",
        default=str(DEFAULT_EVENTS_PATH),
        help=f"Source events.jsonl path (default: {DEFAULT_EVENTS_PATH}).",
    )
    p.set_defaults(_handler=_run)


def _run(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    events_path = Path(args.events)
    offset_path = Path(str(db_path) + ".last_offset")

    init_schema(db_path)

    ingested_lines = 0
    new_rows = 0
    last_offset: int | None = None
    for payload, offset_after in tail_read_since_offset(events_path, offset_path):
        try:
            event = Event.model_validate(payload)
        except (ValueError, TypeError) as exc:
            # Pydantic validation error on a line — skip but don't stop.
            print(
                f"[ingest-events] skipping invalid event payload: {exc}",
                file=sys.stderr,
            )
            last_offset = offset_after
            continue
        rows = event_to_rows(event)
        inserted = ingest_event_rows(db_path, rows)
        new_rows += inserted
        ingested_lines += 1
        last_offset = offset_after

    if last_offset is not None:
        persist_offset(offset_path, last_offset)

    summary = {
        "db": str(db_path),
        "events": str(events_path),
        "lines_scanned": ingested_lines,
        "new_rows": new_rows,
        "last_offset": last_offset,
    }
    print(f"[ingest-events] {json.dumps(summary)}")
    return 0


register_subcommand("ingest-events", _add_parser)


__all__ = ["_run"]
