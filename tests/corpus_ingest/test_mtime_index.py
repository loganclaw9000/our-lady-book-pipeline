"""Tests for book_pipeline.corpus_ingest.mtime_index.

Behavior under test (Plan 02-02 Task 2):
  - read_mtime_index returns {} when file missing, or the parsed JSON dict.
  - write_mtime_index writes mapping atomically (sort_keys + indent).
  - round-trip: write→read preserves equality.
  - corpus_mtime_map returns {abs_path_str: float_mtime} for a list of Paths.
  - W-4: read_resolved_model_revision returns None when absent, dict when present.
  - W-4: write_resolved_model_revision persists {sha, model, resolved_at}.
"""

from __future__ import annotations

import json
from pathlib import Path


def test_read_mtime_index_missing_returns_empty_dict(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.mtime_index import read_mtime_index

    assert read_mtime_index(tmp_path) == {}


def test_write_then_read_mtime_index_round_trip(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.mtime_index import (
        read_mtime_index,
        write_mtime_index,
    )

    payload = {"/abs/a.md": 1234567.5, "/abs/b.md": 9876543.25}
    write_mtime_index(tmp_path, payload)
    read_back = read_mtime_index(tmp_path)
    assert read_back == payload


def test_write_mtime_index_creates_indexes_dir(tmp_path: Path) -> None:
    """indexes_dir is created if missing."""
    from book_pipeline.corpus_ingest.mtime_index import write_mtime_index

    nested = tmp_path / "nested" / "indexes"
    assert not nested.exists()
    write_mtime_index(nested, {"/a": 1.0})
    assert (nested / "mtime_index.json").is_file()


def test_corpus_mtime_map_returns_abs_float_mtimes(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.mtime_index import corpus_mtime_map

    f1 = tmp_path / "a.md"
    f2 = tmp_path / "b.md"
    f1.write_text("a", encoding="utf-8")
    f2.write_text("b", encoding="utf-8")
    m = corpus_mtime_map([f1, f2])
    assert len(m) == 2
    for k, v in m.items():
        # Absolute paths.
        assert k == str(Path(k).resolve())
        # Float mtimes.
        assert isinstance(v, float)


# ---------------------------------------------------------------------------
# W-4: resolved model revision persistence (replaces YAML write-back).
# ---------------------------------------------------------------------------


def test_read_resolved_model_revision_missing_returns_none(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.mtime_index import read_resolved_model_revision

    assert read_resolved_model_revision(tmp_path) is None


def test_write_then_read_resolved_model_revision_round_trip(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.mtime_index import (
        read_resolved_model_revision,
        write_resolved_model_revision,
    )

    write_resolved_model_revision(tmp_path, sha="abc123", model="BAAI/bge-m3")
    read_back = read_resolved_model_revision(tmp_path)
    assert read_back is not None
    assert read_back["sha"] == "abc123"
    assert read_back["model"] == "BAAI/bge-m3"
    assert "resolved_at" in read_back
    # ISO timestamp format sanity check.
    assert "T" in read_back["resolved_at"]


def test_write_resolved_model_revision_creates_dir_and_valid_json(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.mtime_index import write_resolved_model_revision

    nested = tmp_path / "deep" / "indexes"
    assert not nested.exists()
    write_resolved_model_revision(nested, sha="xyz", model="BAAI/bge-m3")
    target = nested / "resolved_model_revision.json"
    assert target.is_file()
    # Valid JSON.
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["sha"] == "xyz"
    assert payload["model"] == "BAAI/bge-m3"
