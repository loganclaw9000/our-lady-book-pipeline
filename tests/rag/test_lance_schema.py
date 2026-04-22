"""Tests for book_pipeline.rag.lance_schema.

Behavior under test (from 02-01-PLAN.md <behavior>):
  - CHUNK_SCHEMA has exactly the 8 pyarrow fields specified:
      chunk_id (string), text (string), source_file (string),
      heading_path (string), rule_type (string), ingestion_run_id (string),
      chapter (int64, nullable), embedding (fixed_size_list<float32, 1024>).
  - open_or_create_table(tmp_path, "historical") creates a lance table with
    CHUNK_SCHEMA; re-opening returns a table with identical schema; opening a
    pre-existing table with a different schema raises RuntimeError.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest


def test_chunk_schema_has_eight_expected_fields() -> None:
    from book_pipeline.rag.lance_schema import CHUNK_SCHEMA

    expected = [
        ("chunk_id", pa.string(), False),
        ("text", pa.string(), False),
        ("source_file", pa.string(), False),
        ("heading_path", pa.string(), False),
        ("rule_type", pa.string(), False),
        ("ingestion_run_id", pa.string(), False),
        ("chapter", pa.int64(), True),  # nullable — W-5 revision
        # embedding is fixed_size_list<float32, 1024>; compared via .type below.
    ]
    assert len(CHUNK_SCHEMA) == 8, (
        f"expected 8 fields in CHUNK_SCHEMA, got {len(CHUNK_SCHEMA)}: "
        f"{[f.name for f in CHUNK_SCHEMA]}"
    )
    for name, arrow_type, nullable in expected:
        field = CHUNK_SCHEMA.field(name)
        assert field.type == arrow_type, (
            f"field {name}: expected type {arrow_type}, got {field.type}"
        )
        assert field.nullable == nullable, (
            f"field {name}: expected nullable={nullable}, got nullable={field.nullable}"
        )

    emb_field = CHUNK_SCHEMA.field("embedding")
    assert pa.types.is_fixed_size_list(emb_field.type), (
        f"embedding must be fixed_size_list, got {emb_field.type}"
    )
    assert emb_field.type.list_size == 1024, (
        f"embedding fixed_size_list must be length 1024, got {emb_field.type.list_size}"
    )
    assert emb_field.type.value_type == pa.float32(), (
        f"embedding element type must be float32, got {emb_field.type.value_type}"
    )
    assert emb_field.nullable is False


def test_chunk_schema_has_chapter_column() -> None:
    """W-5 regression guard: `chapter` column must be present (int64, nullable).

    arc_position retriever in Plan 04 filters on this column directly instead
    of the fragile `heading_path LIKE 'Chapter N %'` approach.
    """
    from book_pipeline.rag.lance_schema import CHUNK_SCHEMA

    names = [f.name for f in CHUNK_SCHEMA]
    assert "chapter" in names, f"chapter column missing from CHUNK_SCHEMA: {names}"
    ch_field = CHUNK_SCHEMA.field("chapter")
    assert ch_field.type == pa.int64()
    assert ch_field.nullable is True


def test_open_or_create_table_creates_then_reopens(tmp_path: Path) -> None:
    from book_pipeline.rag.lance_schema import CHUNK_SCHEMA, open_or_create_table

    db_dir = tmp_path / "lance_db"
    tbl_a = open_or_create_table(db_dir, "historical")
    assert tbl_a.schema == CHUNK_SCHEMA
    # Reopening should yield identical schema.
    tbl_b = open_or_create_table(db_dir, "historical")
    assert tbl_b.schema == CHUNK_SCHEMA
    # Same table name should still be listed in the db.
    import lancedb

    db = lancedb.connect(str(db_dir))
    assert "historical" in db.table_names()


def test_open_or_create_table_schema_mismatch_raises(tmp_path: Path) -> None:
    """If a table exists at the path with a different schema, open_or_create_table
    must raise RuntimeError (never silently migrate)."""
    import lancedb

    from book_pipeline.rag.lance_schema import open_or_create_table

    db_dir = tmp_path / "lance_db_mismatch"
    db_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(db_dir))
    wrong_schema = pa.schema(
        [
            pa.field("foo", pa.string(), nullable=False),
            pa.field("bar", pa.int64(), nullable=True),
        ]
    )
    db.create_table("historical", schema=wrong_schema, mode="create")

    with pytest.raises(RuntimeError, match="Schema mismatch"):
        open_or_create_table(db_dir, "historical")


def test_open_or_create_table_accepts_multiple_axes(tmp_path: Path) -> None:
    """Per-axis table creation: 5 axes coexist in one db_path."""
    from book_pipeline.rag.lance_schema import CHUNK_SCHEMA, open_or_create_table

    db_dir = tmp_path / "lance_db_multi"
    for axis in ("historical", "metaphysics", "entity_state", "arc_position", "negative_constraint"):
        tbl = open_or_create_table(db_dir, axis)
        assert tbl.schema == CHUNK_SCHEMA

    import lancedb

    db = lancedb.connect(str(db_dir))
    assert set(db.table_names()) >= {
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
    }
