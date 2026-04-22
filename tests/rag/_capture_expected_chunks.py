#!/usr/bin/env python3
"""Utility (NOT a test) -- captures a baseline snapshot of ingested chunks.

Run AFTER a real successful `uv run book-pipeline ingest --force` to pin
`tests/rag/fixtures/expected_chunks.jsonl` as the Plan 02-06 baseline
probe set. The fixture is a PROBE -- it lets the golden-query gate
distinguish "chunk isn't in the index at all" from "chunk is present
but didn't rank top-8".

    uv run python tests/rag/_capture_expected_chunks.py [--indexes-dir PATH]

Each output line is a JSON object:

    {
      "axis": "historical",
      "chunk_id": "...",
      "source_file": "/abs/path/our-lady-of-champion-brief.md",
      "heading_path": "Premise",
      "ingestion_run_id": "ing_...",
      "chapter": null
    }

Filename starts with `_` so pytest's default collector doesn't try to run
it (collection_ignore via name prefix). Import path stays flat under
`tests/rag/` for discoverability; `__init__.py` at `tests/rag/` keeps it
importable but not collected.

Regeneration semantics: running this script OVERWRITES the fixture. That
is intentional -- the fixture is a pin, not an assertion. A re-pin after
a deliberate chunker/embedder change is exactly the workflow this
supports. Commit the resulting fixture with the ingestion_run_id in the
plan SUMMARY for reproducibility.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from book_pipeline.rag.lance_schema import open_or_create_table

AXES = (
    "historical",
    "metaphysics",
    "entity_state",
    "arc_position",
    "negative_constraint",
)

DEFAULT_INDEXES_DIR = Path(__file__).resolve().parents[2] / "indexes"
DEFAULT_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "expected_chunks.jsonl"


def capture(indexes_dir: Path, fixture_path: Path) -> int:
    """Walk all 5 axis tables; stream chunk metadata to fixture_path.

    Returns the total number of rows written.
    """
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with fixture_path.open("w", encoding="utf-8") as f:
        for axis in AXES:
            tbl = open_or_create_table(indexes_dir, axis)
            if tbl.count_rows() == 0:
                continue
            rows = tbl.to_arrow().to_pylist()
            for row in rows:
                record = {
                    "axis": axis,
                    "chunk_id": row["chunk_id"],
                    "source_file": row["source_file"],
                    "heading_path": row["heading_path"],
                    "ingestion_run_id": row["ingestion_run_id"],
                    "chapter": row.get("chapter"),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a baseline snapshot of ingested chunks into "
            "tests/rag/fixtures/expected_chunks.jsonl. Run after `book-pipeline "
            "ingest --force` completes successfully."
        )
    )
    parser.add_argument(
        "--indexes-dir",
        type=Path,
        default=DEFAULT_INDEXES_DIR,
        help="LanceDB directory (default: <repo>/indexes/).",
    )
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Fixture output path (default: tests/rag/fixtures/expected_chunks.jsonl).",
    )
    args = parser.parse_args()

    if not args.indexes_dir.exists():
        print(
            f"ERROR: indexes directory not found: {args.indexes_dir}\n"
            "Run `uv run book-pipeline ingest --force` first."
        )
        return 2

    total = capture(args.indexes_dir, args.fixture_path)
    print(f"Wrote {total} rows across {len(AXES)} axes -> {args.fixture_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
