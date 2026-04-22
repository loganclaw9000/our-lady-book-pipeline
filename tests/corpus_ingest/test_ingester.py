"""Tests for book_pipeline.corpus_ingest.ingester.CorpusIngester.

Behavior under test (Plan 02-02 Task 2):
  - First ingest populates LanceDB tables per axis, returns IngestionReport
    with skipped=False, chunk_counts_per_axis matching fixture expectations.
    Emits exactly one Event with role="corpus_ingester".
  - Second ingest (no mtime changes) returns skipped=True, no new Event.
  - Third ingest (after `touch` on one source) returns skipped=False, new
    ingestion_run_id, tables rebuilt.
  - W-3: For multi-axis file (brief_seed.md in both historical + metaphysics),
    chunks whose heading is classified to "metaphysics" land in that table;
    other chunks fall back to the file's primary axis (first in the list).
  - W-4: After first non-skipped ingest, indexes/resolved_model_revision.json
    exists with {sha, model, resolved_at}. The test-fixture yaml file is NEVER
    modified by the ingester.
  - W-5: Rows inserted into LanceDB include the `chapter` column (may be None).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np

# ---------------------------------------------------------------------------
# Fixtures: fake embedder, fake event logger, fake heading_classifier.
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mini_corpus"


class _FakeEmbedder:
    """Stand-in for BgeM3Embedder. Returns deterministic (n, 1024) arrays, never
    loads a real model. revision_sha returns a fixed test value.

    Attributes match the real embedder (model_name, revision_sha property).
    """

    model_name: str = "BAAI/bge-m3"

    def __init__(self, revision_sha: str = "fake-sha-abc123") -> None:
        self._revision_sha = revision_sha
        self.call_count = 0

    @property
    def revision_sha(self) -> str:
        return self._revision_sha

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        self.call_count += 1
        n = len(texts)
        if n == 0:
            return np.empty((0, 1024), dtype=np.float32)
        # Deterministic by hash of input for reproducibility.
        seed = abs(hash(tuple(texts))) % (2**32)
        rng = np.random.default_rng(seed=seed)
        arr = rng.standard_normal((n, 1024)).astype(np.float32)
        # Normalize.
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        arr = arr / norms
        return arr.astype(np.float32)


class _FakeEventLogger:
    """Captures emitted Events in a list for inspection."""

    emitted: ClassVar[list[Any]]

    def __init__(self) -> None:
        self.emitted = []

    def emit(self, event: Any) -> None:
        self.emitted.append(event)


def _fake_heading_classifier(heading_path: str) -> str | None:
    """Return 'metaphysics' when heading contains 'Metaphysics' or 'Engine';
    None otherwise. Used to exercise the W-3 path (injected classifier routes
    chunks of multi-axis files per heading)."""
    if not heading_path:
        return None
    if "Metaphysics" in heading_path or "Engine" in heading_path:
        return "metaphysics"
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _copy_corpus_to(tmp_path: Path) -> Path:
    """Copy the fixture corpus into tmp_path so tests can mutate mtimes safely."""
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    for fname in ("historical_seed.md", "metaphysics_seed.md", "brief_seed.md"):
        (corpus / fname).write_text(
            (FIXTURES_DIR / fname).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return corpus


def _build_source_files_by_axis(corpus: Path) -> dict[str, list[Path]]:
    """Simulate CORPUS_FILES for the fixture:
    - historical_seed.md   → ["historical"]  (primary for that file)
    - metaphysics_seed.md  → ["metaphysics"]
    - brief_seed.md        → ["historical", "metaphysics"]  (multi-axis; W-3)
    """
    return {
        "historical": [corpus / "historical_seed.md", corpus / "brief_seed.md"],
        "metaphysics": [corpus / "metaphysics_seed.md", corpus / "brief_seed.md"],
        "entity_state": [],
        "arc_position": [],
        "negative_constraint": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ingestion_report_shape() -> None:
    """IngestionReport is a Pydantic model with the documented fields."""
    from book_pipeline.corpus_ingest.ingester import IngestionReport

    rep = IngestionReport(
        ingestion_run_id="ing_20260421T000000Z_deadbeef",
        source_files=["/a.md"],
        chunk_counts_per_axis={
            "historical": 1,
            "metaphysics": 0,
            "entity_state": 0,
            "arc_position": 0,
            "negative_constraint": 0,
        },
        embed_model_revision="fake-sha-abc123",
        db_version="lancedb>=0.30.2",
        skipped=False,
        wall_time_ms=42,
    )
    assert rep.skipped is False
    assert rep.embed_model_revision == "fake-sha-abc123"


def test_first_ingest_populates_tables_and_emits_one_event(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )

    report = ing.ingest(indexes_dir)
    assert report.skipped is False
    assert report.embed_model_revision == "fake-sha-abc123"
    # Every axis in the AXIS_NAMES tuple must appear in chunk_counts_per_axis
    # (even 0 for axes with no sources).
    expected_axes = {
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
    }
    assert set(report.chunk_counts_per_axis.keys()) == expected_axes
    assert sum(report.chunk_counts_per_axis.values()) > 0, (
        f"expected >0 chunks total, got {report.chunk_counts_per_axis}"
    )
    # historical + metaphysics should have chunks; the 3 unused axes should be 0.
    assert report.chunk_counts_per_axis["historical"] > 0
    assert report.chunk_counts_per_axis["metaphysics"] > 0
    assert report.chunk_counts_per_axis["entity_state"] == 0
    assert report.chunk_counts_per_axis["arc_position"] == 0
    assert report.chunk_counts_per_axis["negative_constraint"] == 0

    # Exactly one Event emitted.
    assert len(logger.emitted) == 1
    ev = logger.emitted[0]
    assert ev.role == "corpus_ingester"
    assert ev.model == "BAAI/bge-m3"
    # Extras.
    assert "ingestion_run_id" in ev.extra
    assert "source_files" in ev.extra
    assert "chunk_counts_per_axis" in ev.extra
    assert "embed_model_revision" in ev.extra
    assert "db_version" in ev.extra
    assert "wall_time_ms" in ev.extra


def test_second_ingest_with_no_changes_skips_and_no_event(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    # First ingest establishes the mtime index.
    r1 = ing.ingest(indexes_dir)
    assert r1.skipped is False
    assert len(logger.emitted) == 1

    # Second ingest with no changes → skipped, no new event.
    r2 = ing.ingest(indexes_dir)
    assert r2.skipped is True, f"expected skipped=True on second ingest, got {r2}"
    assert len(logger.emitted) == 1, (
        f"no new Event should be emitted on skip, got {len(logger.emitted)}"
    )


def test_third_ingest_after_touch_rebuilds_and_new_run_id(tmp_path: Path) -> None:
    import os
    import time

    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    r1 = ing.ingest(indexes_dir)
    first_run_id = r1.ingestion_run_id

    # Touch one file with a strictly later mtime.
    target = corpus / "historical_seed.md"
    future_mtime = time.time() + 10.0
    os.utime(target, (future_mtime, future_mtime))

    # Second ingest against mutated mtime → rebuild.
    r2 = ing.ingest(indexes_dir)
    assert r2.skipped is False, "mtime change must trigger rebuild"
    assert r2.ingestion_run_id != first_run_id, (
        "new ingestion_run_id expected on rebuild"
    )
    assert len(logger.emitted) == 2, (
        f"expected a second Event on rebuild, got {len(logger.emitted)}"
    )


def test_force_flag_bypasses_mtime_check(tmp_path: Path) -> None:
    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    r1 = ing.ingest(indexes_dir)
    assert r1.skipped is False

    # No file changes — but force=True should rebuild anyway.
    r2 = ing.ingest(indexes_dir, force=True)
    assert r2.skipped is False
    assert r2.ingestion_run_id != r1.ingestion_run_id


def test_w4_resolved_model_revision_json_written(tmp_path: Path) -> None:
    """W-4: after first successful ingest, indexes/resolved_model_revision.json
    contains {sha, model, resolved_at}."""
    import json

    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    emb = _FakeEmbedder(revision_sha="fake-sha-abc123")
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    ing.ingest(indexes_dir)

    target = indexes_dir / "resolved_model_revision.json"
    assert target.is_file(), "resolved_model_revision.json must exist post-ingest (W-4)"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["sha"] == "fake-sha-abc123"
    assert payload["model"] == "BAAI/bge-m3"
    assert "resolved_at" in payload


def test_w4_yaml_config_is_not_modified(tmp_path: Path) -> None:
    """W-4 regression guard: ingester must NEVER modify config/rag_retrievers.yaml.

    Uses an in-fixture yaml file; asserts bytes unchanged pre/post ingest.
    """
    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    # Write a dummy yaml under tmp_path/config/.
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = config_dir / "rag_retrievers.yaml"
    original_yaml = (
        "# Dummy yaml for the W-4 regression test.\n"
        "embeddings:\n"
        "  model: BAAI/bge-m3\n"
        "  model_revision: TBD-phase2\n"
    )
    yaml_path.write_text(original_yaml, encoding="utf-8")
    before_bytes = yaml_path.read_bytes()

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    ing.ingest(indexes_dir)

    after_bytes = yaml_path.read_bytes()
    assert before_bytes == after_bytes, (
        "W-4: ingester must NOT modify config yaml; bytes-on-disk differ."
    )


def test_w3_multi_axis_file_routes_by_heading_classifier(tmp_path: Path) -> None:
    """W-3: chunks of brief_seed.md with headings matching the classifier land
    in the metaphysics axis; others fall back to the file's primary axis
    (historical, per source_files_by_axis ordering)."""
    import lancedb

    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    ing.ingest(indexes_dir)

    db = lancedb.connect(str(indexes_dir))
    metaphysics_rows = db.open_table("metaphysics").to_arrow().to_pylist()
    historical_rows = db.open_table("historical").to_arrow().to_pylist()

    brief_meta = [
        r for r in metaphysics_rows if r["source_file"].endswith("brief_seed.md")
    ]
    brief_hist = [
        r for r in historical_rows if r["source_file"].endswith("brief_seed.md")
    ]

    assert len(brief_meta) > 0, (
        "brief_seed.md has Metaphysics-tagged headings; expected ≥1 chunk in metaphysics table"
    )
    assert len(brief_hist) > 0, (
        "brief_seed.md has untagged (Premise, Historical Framework) headings; "
        "expected ≥1 chunk in historical table (fallback to primary axis)"
    )

    # Every brief chunk in metaphysics must have a heading with Metaphysics or Engine.
    for r in brief_meta:
        hp = r["heading_path"]
        assert "Metaphysics" in hp or "Engine" in hp, (
            f"brief chunk in metaphysics table has non-metaphysics heading {hp!r}"
        )


def test_w5_chapter_column_present_in_rows(tmp_path: Path) -> None:
    """W-5: inserted LanceDB rows include the `chapter` column (may be None).

    No fixture chunk carries a chapter breadcrumb, so all values should be None,
    but the column itself must be present on every row.
    """
    import lancedb

    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    ing.ingest(indexes_dir)

    db = lancedb.connect(str(indexes_dir))
    tbl = db.open_table("historical")
    rows = tbl.to_arrow().to_pylist()
    assert rows, "expected at least one row in the historical table"
    # Every row dict must carry a `chapter` key (per CHUNK_SCHEMA); value may
    # be None for these non-chapter fixtures, but the key must exist.
    for row in rows:
        assert "chapter" in row, (
            f"chapter column missing from row; keys={sorted(row.keys())}"
        )


def test_rebuild_truncates_tables(tmp_path: Path) -> None:
    """On non-skipped re-ingest, each axis's table is fully rebuilt — row count
    after rebuild should equal row count after the first build (not 2x)."""
    import os
    import time

    import lancedb

    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    ing.ingest(indexes_dir)

    db = lancedb.connect(str(indexes_dir))
    count_before = db.open_table("historical").count_rows()

    # Touch one file and rebuild.
    target = corpus / "historical_seed.md"
    future_mtime = time.time() + 20.0
    os.utime(target, (future_mtime, future_mtime))
    ing.ingest(indexes_dir)

    db2 = lancedb.connect(str(indexes_dir))
    count_after = db2.open_table("historical").count_rows()
    assert count_after == count_before, (
        f"rebuild should produce the same row count (not append): "
        f"before={count_before}, after={count_after}"
    )


def test_handoff_is_not_ingested(tmp_path: Path) -> None:
    """Negative test: if source_files_by_axis has no handoff file, ingester should
    never produce chunks for it. This is a sanity check on the axis-scoped ingest."""
    from book_pipeline.corpus_ingest.ingester import CorpusIngester

    corpus = _copy_corpus_to(tmp_path)
    indexes_dir = tmp_path / "indexes"
    src_by_axis = _build_source_files_by_axis(corpus)

    # Write a handoff file in the corpus dir; it should be ignored since it's
    # not in any axis list (mirrors real routing for handoff.md).
    (corpus / "handoff_seed.md").write_text(
        "# Handoff\nThis must not appear in any axis.\n",
        encoding="utf-8",
    )

    emb = _FakeEmbedder()
    logger = _FakeEventLogger()
    ing = CorpusIngester(
        source_files_by_axis=src_by_axis,
        embedder=emb,
        event_logger=logger,
        heading_classifier=_fake_heading_classifier,
    )
    ing.ingest(indexes_dir)

    import lancedb

    db = lancedb.connect(str(indexes_dir))
    for axis in ("historical", "metaphysics"):
        rows = db.open_table(axis).to_arrow().to_pylist()
        for r in rows:
            assert not r["source_file"].endswith("handoff_seed.md"), (
                f"handoff content leaked into {axis} axis"
            )
