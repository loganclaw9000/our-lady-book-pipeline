"""CorpusIngester — the concrete CORPUS-01 ingestion pipeline.

Responsibilities (Plan 02-02 Task 2):
  1. Compute a per-file mtime map; if it equals the stored mtime_index.json
     and force=False, return an IngestionReport(skipped=True) and emit NO Event.
  2. Otherwise, drop-and-recreate the 5 axis tables (truncate semantics),
     chunk each source file, route each chunk to a target axis (applying the
     injected heading_classifier for multi-axis files — W-3), embed in batches,
     insert rows matching CHUNK_SCHEMA (including the `chapter` column — W-5).
  3. Persist indexes/resolved_model_revision.json (W-4: never touches yaml).
  4. Persist indexes/mtime_index.json.
  5. Emit exactly one Event(role="corpus_ingester", ...) with all required
     extras for CORPUS-01 observability.

Kernel discipline: this module imports nothing from the book-specific package.
Book-specific concerns (CORPUS_FILES mapping, heading classifier) are injected
by the composition seam (book_pipeline.cli.ingest).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import lancedb
from pydantic import BaseModel, ConfigDict

from book_pipeline.corpus_ingest.mtime_index import (
    corpus_mtime_map,
    read_mtime_index,
    write_mtime_index,
    write_resolved_model_revision,
)
from book_pipeline.corpus_ingest.router import AXIS_NAMES
from book_pipeline.interfaces.types import Event
from book_pipeline.observability.hashing import event_id, hash_text
from book_pipeline.rag import CHUNK_SCHEMA, chunk_markdown, open_or_create_table

DB_VERSION: str = "lancedb>=0.30.2"
_BATCH_SIZE: int = 32

# WR-03: crash-safety marker files. `.ingest_in_progress` is written at the
# START of a non-skipped ingest and removed only after mtime_index.json is
# written. If the process dies mid-ingest the marker survives, and the next
# run forces a full re-ingest regardless of mtime. `.last_ingestion_ok` is
# written after a successful run so Phase 3 can diagnose "when did the last
# ingest complete?".
_INGEST_IN_PROGRESS_MARKER: str = ".ingest_in_progress"
_LAST_INGEST_OK_MARKER: str = ".last_ingestion_ok"


class IngestionReport(BaseModel):
    """Structured return value from CorpusIngester.ingest."""

    model_config = ConfigDict(extra="forbid")

    ingestion_run_id: str
    source_files: list[str]
    chunk_counts_per_axis: dict[str, int]
    embed_model_revision: str
    db_version: str
    skipped: bool
    wall_time_ms: int


class _EmbedderProtocol(Protocol):
    """Structural type for the embedder — matches BgeM3Embedder and fakes."""

    model_name: str

    @property
    def revision_sha(self) -> str: ...

    def embed_texts(self, texts: list[str]) -> Any: ...


class _EventLoggerProtocol(Protocol):
    """Structural type for the event logger — matches JsonlEventLogger."""

    def emit(self, event: Event) -> None: ...


class CorpusIngester:
    """Ingestion pipeline — chunk + embed + write to 5 LanceDB tables.

    Parameters:
      source_files_by_axis: {axis_name: [Path, ...]}. The SAME path may appear
        in multiple axes (e.g. brief.md in both historical + metaphysics); the
        ingester dedupes to a single chunking pass per file and routes each
        chunk to exactly ONE target axis (via heading_classifier if multi-axis,
        else the single axis).
      embedder: any object exposing `model_name`, `revision_sha` property, and
        `embed_texts(list[str]) -> ndarray (n, 1024) float32`.
      event_logger: any object with `.emit(Event)`. On non-skipped ingests,
        exactly one Event is emitted just before ingest returns.
      heading_classifier: optional callable str -> str | None. Called for each
        chunk of a multi-axis file; if it returns one of the file's axes, that
        axis is used; otherwise the chunk falls back to the file's PRIMARY
        axis (first entry in source_files_by_axis's insertion order for that
        file). Single-axis files ignore this callable.
    """

    def __init__(
        self,
        source_files_by_axis: dict[str, list[Path]],
        embedder: _EmbedderProtocol,
        event_logger: _EventLoggerProtocol,
        heading_classifier: Callable[[str], str | None] | None = None,
    ) -> None:
        self.source_files_by_axis = source_files_by_axis
        self.embedder = embedder
        self.event_logger = event_logger
        self.heading_classifier = heading_classifier

    # ---- Internal helpers -------------------------------------------------

    def _flat_source_files(self) -> list[Path]:
        """Deduplicated, ordered list of source Paths across all axes.

        Order: insertion order of axes in source_files_by_axis, then files
        within each axis list. Deduplication preserves first occurrence.
        """
        seen: set[Path] = set()
        out: list[Path] = []
        for files in self.source_files_by_axis.values():
            for p in files:
                if p not in seen:
                    seen.add(p)
                    out.append(p)
        return out

    def _file_axes(self, path: Path) -> list[str]:
        """Return the ordered list of axes `path` appears in (primary first)."""
        axes: list[str] = []
        for axis, files in self.source_files_by_axis.items():
            if path in files:
                axes.append(axis)
        return axes

    def _axes_with_any_source(self) -> set[str]:
        """Axes that have at least one source file. Only these get tables
        truncated + recreated on rebuild (empty axes get empty tables made
        by open_or_create_table but are never truncated — they hold zero rows
        anyway)."""
        return {
            axis
            for axis, files in self.source_files_by_axis.items()
            if files
        }

    def _drop_tables_for_rebuild(self, db: lancedb.DBConnection) -> None:
        """Drop all 5 axis tables (if present) so the subsequent insert is a
        clean rebuild. Idempotent — missing tables are ignored."""
        # lancedb 0.30.x: table_names() returns list[str]; list_tables() has
        # the __contains__ regression. See rag/lance_schema.py TODO comment.
        existing = set(db.table_names())
        for axis in AXIS_NAMES:
            if axis in existing:
                db.drop_table(axis)

    @staticmethod
    def _make_ingestion_run_id(
        source_files: list[Path],
        revision_sha: str,
        mtimes: dict[str, float],
    ) -> str:
        """ing_<utc ts compact>_<8-char xxhash> — unique per ingest.

        The timestamp uses sub-second precision (microseconds) so rapid rebuilds
        (e.g. force-rebuild immediately after a first ingest) still get distinct
        ids. The hash incorporates the mtime map so that two ingests of the same
        file set with different mtimes (rebuild path) always diverge, even if
        they happen within the same microsecond (e.g. mocked clocks)."""
        now = datetime.now(UTC)
        ts_compact = now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond:06d}Z"
        digest_input = json.dumps(
            sorted(str(p) for p in source_files)
            + [revision_sha]
            + [f"{k}:{v}" for k, v in sorted(mtimes.items())]
            + [ts_compact]  # ensures uniqueness even for identical inputs
        )
        short_hash = hash_text(digest_input)[:8]
        return f"ing_{ts_compact}_{short_hash}"

    def _resolve_chunk_axis(
        self, chunk_heading: str, file_axes: list[str]
    ) -> str:
        """Decide which axis this chunk goes to.

        - Single-axis file: trivial; one answer.
        - Multi-axis file: ask heading_classifier; if it returns one of the
          file's axes, use that; else fall back to the primary (first) axis.
        """
        if len(file_axes) == 1:
            return file_axes[0]
        primary = file_axes[0]
        if self.heading_classifier is None:
            return primary
        classified = self.heading_classifier(chunk_heading)
        if classified is not None and classified in file_axes:
            return classified
        return primary

    # ---- Public API -------------------------------------------------------

    def ingest(
        self, indexes_dir: Path, *, force: bool = False
    ) -> IngestionReport:
        """Ingest the corpus into LanceDB under indexes_dir.

        See class docstring for step-by-step behavior. Returns an
        IngestionReport; emits one Event when skipped=False; emits no Event
        when skipped=True.
        """
        start_epoch = time.monotonic()
        flat_sources = self._flat_source_files()
        current_mtimes = corpus_mtime_map(flat_sources) if flat_sources else {}

        # --- WR-03 crash-safety check --------------------------------------
        # If an in-progress marker exists from a prior crashed run, the index
        # state is unknown (possibly half-populated after drop+rebuild). Force
        # a full re-ingest regardless of mtime match.
        in_progress_marker = indexes_dir / _INGEST_IN_PROGRESS_MARKER
        crash_recovery = in_progress_marker.exists()

        # --- Idempotency check --------------------------------------------
        stored_mtimes = read_mtime_index(indexes_dir)
        if (
            not force
            and not crash_recovery
            and stored_mtimes == current_mtimes
            and flat_sources
        ):
            # No changes — skip. Do not touch tables, do not emit Event.
            zero_counts = {axis: 0 for axis in AXIS_NAMES}
            return IngestionReport(
                ingestion_run_id="",
                source_files=sorted(str(p) for p in flat_sources),
                chunk_counts_per_axis=zero_counts,
                embed_model_revision="",
                db_version=DB_VERSION,
                skipped=True,
                wall_time_ms=int((time.monotonic() - start_epoch) * 1000),
            )

        # --- Non-skipped ingest -------------------------------------------
        # Resolve revision_sha early (triggers lazy embedder load in production;
        # returns the pre-set value in fakes).
        revision_sha = self.embedder.revision_sha
        ingestion_run_id = self._make_ingestion_run_id(
            flat_sources, revision_sha, current_mtimes
        )

        # Connect + drop tables that will be rebuilt.
        indexes_dir.mkdir(parents=True, exist_ok=True)

        # WR-03: write the in-progress marker BEFORE dropping tables. If the
        # process dies anywhere between here and mtime_index.json being
        # written, the marker survives + forces the next invocation to
        # re-ingest. On clean completion we remove the marker below.
        in_progress_marker.write_text(
            json.dumps(
                {
                    "started_at_iso": datetime.now(UTC).isoformat(),
                    "ingestion_run_id": ingestion_run_id,
                    "crash_recovery": crash_recovery,
                }
            ),
            encoding="utf-8",
        )

        db = lancedb.connect(str(indexes_dir))
        self._drop_tables_for_rebuild(db)

        # Open (re-create) each axis table that has at least one source.
        # Axes with no sources stay untouched (no empty tables are created —
        # Plan 02-03..05 retrievers will create their tables on demand or
        # Plan 02-02 follow-up adds empty-table scaffolding if needed).
        active_axes = sorted(self._axes_with_any_source())
        tables: dict[str, Any] = {
            axis: open_or_create_table(indexes_dir, axis) for axis in active_axes
        }

        # Route all chunks by target axis.
        rows_by_axis: dict[str, list[dict[str, Any]]] = {
            axis: [] for axis in active_axes
        }

        for source_path in flat_sources:
            file_axes = self._file_axes(source_path)
            if not file_axes:
                continue
            text = source_path.read_text(encoding="utf-8")
            chunks = chunk_markdown(
                text,
                str(source_path),
                ingestion_run_id=ingestion_run_id,
            )
            # Decide axis per chunk, then group by axis for batch embedding.
            for chunk in chunks:
                target_axis = self._resolve_chunk_axis(
                    chunk.heading_path, file_axes
                )
                rows_by_axis[target_axis].append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text,
                        "source_file": chunk.source_file,
                        "heading_path": chunk.heading_path,
                        "rule_type": chunk.rule_type,
                        "ingestion_run_id": chunk.ingestion_run_id,
                        "chapter": chunk.chapter,
                        # Plan 05-03: corpus ingest does not stamp
                        # source_chapter_sha — only entity_state reindex
                        # writes a non-null value. Explicit None so the row
                        # dict matches CHUNK_SCHEMA.
                        "source_chapter_sha": None,
                        # embedding filled below in batches.
                    }
                )

        # Embed + insert per axis.
        chunk_counts_per_axis: dict[str, int] = {axis: 0 for axis in AXIS_NAMES}
        for axis, rows in rows_by_axis.items():
            if not rows:
                continue
            # Embed in batches of _BATCH_SIZE.
            texts = [r["text"] for r in rows]
            embeddings_parts = []
            for i in range(0, len(texts), _BATCH_SIZE):
                batch = texts[i : i + _BATCH_SIZE]
                arr = self.embedder.embed_texts(batch)
                embeddings_parts.append(arr)
            # Stack and attach to each row.
            import numpy as np  # local import keeps top-level clean

            if embeddings_parts:
                all_embeddings = np.vstack(embeddings_parts)
            else:
                all_embeddings = np.empty((0, 1024), dtype=np.float32)
            for row_idx, row in enumerate(rows):
                # LanceDB accepts python lists for fixed_size_list<float32>.
                row["embedding"] = all_embeddings[row_idx].tolist()
            tables[axis].add(rows)
            chunk_counts_per_axis[axis] = len(rows)

        # --- W-4: persist resolved_model_revision.json --------------------
        write_resolved_model_revision(
            indexes_dir,
            sha=revision_sha,
            model=self.embedder.model_name,
        )

        # --- Persist mtime index ------------------------------------------
        write_mtime_index(indexes_dir, current_mtimes)

        # WR-03: mtime index + tables are both written. Remove the
        # in-progress marker and drop a success marker that Phase 3 can
        # read for diagnostics ("when did the last ingest complete?").
        in_progress_marker.unlink(missing_ok=True)
        (indexes_dir / _LAST_INGEST_OK_MARKER).write_text(
            json.dumps(
                {
                    "completed_at_iso": datetime.now(UTC).isoformat(),
                    "ingestion_run_id": ingestion_run_id,
                }
            ),
            encoding="utf-8",
        )

        wall_time_ms = int((time.monotonic() - start_epoch) * 1000)
        sorted_source_strs = sorted(str(p) for p in flat_sources)

        # --- Emit Event ---------------------------------------------------
        ts_iso = datetime.now(UTC).isoformat()
        prompt_h = hash_text(json.dumps(sorted_source_strs))
        # output_hash = xxhash of sorted (axis, count) tuples for stable
        # fingerprinting of the ingest outcome.
        output_payload = json.dumps(
            sorted(chunk_counts_per_axis.items()),
            sort_keys=True,
        )
        output_h = hash_text(output_payload)
        caller = "corpus_ingest.ingester:CorpusIngester.ingest"
        eid = event_id(ts_iso, "corpus_ingester", caller, prompt_h)
        event = Event(
            event_id=eid,
            ts_iso=ts_iso,
            role="corpus_ingester",
            model="BAAI/bge-m3",
            prompt_hash=prompt_h,
            input_tokens=0,
            output_tokens=sum(chunk_counts_per_axis.values()),
            latency_ms=wall_time_ms,
            caller_context={
                "module": "corpus_ingest",
                "function": "ingest",
            },
            output_hash=output_h,
            extra={
                "ingestion_run_id": ingestion_run_id,
                "source_files": sorted_source_strs,
                "chunk_counts_per_axis": chunk_counts_per_axis,
                "embed_model_revision": revision_sha,
                "db_version": DB_VERSION,
                "wall_time_ms": wall_time_ms,
            },
        )
        self.event_logger.emit(event)

        return IngestionReport(
            ingestion_run_id=ingestion_run_id,
            source_files=sorted_source_strs,
            chunk_counts_per_axis=chunk_counts_per_axis,
            embed_model_revision=revision_sha,
            db_version=DB_VERSION,
            skipped=False,
            wall_time_ms=wall_time_ms,
        )


__all__ = ["CHUNK_SCHEMA", "CorpusIngester", "IngestionReport"]
