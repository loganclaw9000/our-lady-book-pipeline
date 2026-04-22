"""LanceDB schema + table helper for the 5 RAG axes.

One table per axis — `historical`, `metaphysics`, `entity_state`, `arc_position`,
`negative_constraint` — all share the same 8-column CHUNK_SCHEMA. The schema is
additive-only: columns may be appended in future plans, but NEVER renamed or
reordered (Plan 2+ ingestion writes rows against these column names).

W-5 revision: `chapter` (int64, nullable) was added at schema-creation time so
the arc_position retriever (Plan 04) can filter by exact chapter equality,
replacing a fragile `heading_path LIKE 'Chapter N %'` approach. `chapter` is
nullable because only chunks from `outline.md` / `brief.md` have chapter
context; rule-card chunks from `engineering.md`, `glossary.md`, `maps.md`
do not.

`open_or_create_table` enforces the schema on reopen: if the on-disk table
has a different schema, it raises RuntimeError rather than silently migrating.
Plan 02 relies on this — a re-ingest against a drifted index must fail
closed, not degrade silently (PITFALLS R-4 is precisely the failure mode this
guard prevents from compounding).
"""

from __future__ import annotations

from pathlib import Path

import lancedb
import pyarrow as pa
from lancedb.table import Table

from book_pipeline.rag.embedding import EMBEDDING_DIM

CHUNK_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("chunk_id", pa.string(), nullable=False),
        pa.field("text", pa.string(), nullable=False),
        pa.field("source_file", pa.string(), nullable=False),
        pa.field("heading_path", pa.string(), nullable=False),
        pa.field("rule_type", pa.string(), nullable=False),
        pa.field("ingestion_run_id", pa.string(), nullable=False),
        pa.field("chapter", pa.int64(), nullable=True),
        pa.field(
            "embedding",
            pa.list_(pa.float32(), EMBEDDING_DIM),
            nullable=False,
        ),
    ]
)


def open_or_create_table(db_path: Path, axis_name: str) -> Table:
    """Open the LanceDB table for `axis_name` at `db_path`, creating it with
    CHUNK_SCHEMA if absent.

    Args:
      db_path: Directory holding the LanceDB database. Created if missing.
      axis_name: One of `historical`, `metaphysics`, `entity_state`,
        `arc_position`, `negative_constraint`. Per config/rag_retrievers.yaml
        these are the 5 frozen retriever names.

    Raises:
      RuntimeError: if a table with `axis_name` exists at `db_path` with a
        schema that doesn't match CHUNK_SCHEMA. Never silently migrates.
    """
    db_path.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(db_path))
    # lancedb 0.30.x: `table_names()` is deprecated in favor of `list_tables()`,
    # but `list_tables()` returns a ListTablesResponse object whose __contains__
    # iterates (key, value) pairs — not table names. We use the deprecated
    # `table_names()` which returns a plain list[str] and still works in 0.30.x.
    # TODO(Plan 02+): switch to `list_tables().tables` when the deprecation
    # removes `table_names()`; all callers of this helper are self-contained.
    existing_tables = db.table_names()
    if axis_name in existing_tables:
        tbl = db.open_table(axis_name)
        if tbl.schema != CHUNK_SCHEMA:
            raise RuntimeError(
                f"Schema mismatch on table {axis_name!r} at {db_path!s}: "
                f"expected CHUNK_SCHEMA, got {tbl.schema}"
            )
        return tbl
    return db.create_table(axis_name, schema=CHUNK_SCHEMA, mode="create")


__all__ = ["CHUNK_SCHEMA", "open_or_create_table"]
