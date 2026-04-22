"""`book-pipeline ingest` — runs CorpusIngester against the 10 bible files.

This module is the documented CLI-composition seam between kernel
(book_pipeline.corpus_ingest) and book_specifics
(book_pipeline.book_specifics.{corpus_paths,heading_classifier}). Per
pyproject.toml import-linter contract 1, the two edges
`book_pipeline.cli.ingest -> book_pipeline.book_specifics.*` are the ONLY
permitted cross-boundary imports. Every other kernel module stays ignorant of
book_specifics.

Flags:
  --dry-run             Print the routing plan + mtime-check result without writing.
  --force               Bypass mtime idempotency check (always rebuild).
  --indexes-dir PATH    LanceDB directory (default: indexes/).
  --json                Emit IngestionReport as JSON rather than pretty text.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from book_pipeline.book_specifics.corpus_paths import CORPUS_FILES, OUTLINE
from book_pipeline.book_specifics.heading_classifier import classify_brief_heading
from book_pipeline.cli.main import register_subcommand
from book_pipeline.config.rag_retrievers import RagRetrieversConfig
from book_pipeline.corpus_ingest import CorpusIngester
from book_pipeline.corpus_ingest.mtime_index import (
    corpus_mtime_map,
    read_mtime_index,
    read_resolved_model_revision,
)
from book_pipeline.observability import JsonlEventLogger
from book_pipeline.rag import BgeM3Embedder

_TBD_PATTERN = re.compile(r"^TBD-.*$")


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "ingest",
        help=(
            "Run CorpusIngester against the Our Lady of Champion corpus; "
            "populates 5 LanceDB tables under indexes/."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print routing plan + mtime status; do not write any tables.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Bypass mtime idempotency check — always rebuild.",
    )
    p.add_argument(
        "--indexes-dir",
        default="indexes",
        help="LanceDB directory (default: indexes/).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit IngestionReport as JSON instead of pretty text.",
    )
    p.set_defaults(_handler=_run)


def _resolve_revision(
    config_revision: str, indexes_dir: Path
) -> str | None:
    """Determine the revision SHA to pass to BgeM3Embedder.

    Behavior per W-4:
      - If config value is "latest-stable" OR matches /^TBD-.*/, load
        indexes/resolved_model_revision.json; if it exists, use its sha.
        If missing (first run), return None so embedder resolves from HF.
      - Else, return the config value verbatim (it's the pin).
    """
    if config_revision == "latest-stable" or _TBD_PATTERN.match(config_revision):
        persisted = read_resolved_model_revision(indexes_dir)
        if persisted is not None:
            return persisted["sha"]
        return None
    return config_revision


def _run(args: argparse.Namespace) -> int:
    indexes_dir = Path(args.indexes_dir)

    # Load config — use the typed loader so we validate all 4 configs at startup.
    cfg = RagRetrieversConfig()  # type: ignore[call-arg]

    # Print routing plan + mtime diagnostic on --dry-run (no writes).
    if args.dry_run:
        flat: list[Path] = []
        seen: set[Path] = set()
        for files in CORPUS_FILES.values():
            for p in files:
                if p not in seen:
                    seen.add(p)
                    flat.append(p)
        print("Routing plan:")
        for axis, paths in CORPUS_FILES.items():
            print(f"  {axis}:")
            for p in paths:
                print(f"    {p}")
        missing = [str(p) for p in flat if not p.is_file()]
        if missing:
            print(f"\nMissing files ({len(missing)}):", file=sys.stderr)
            for m in missing:
                print(f"  {m}", file=sys.stderr)
            return 2
        stored = read_mtime_index(indexes_dir)
        current = corpus_mtime_map(flat)
        would_skip = stored == current and not args.force
        print()
        print(f"Indexes dir:       {indexes_dir}")
        print(f"Stored mtimes:     {len(stored)} files")
        print(f"Current mtimes:    {len(current)} files")
        print(f"Would skip:        {would_skip}")
        return 0

    # Resolve revision per W-4.
    revision = _resolve_revision(cfg.embeddings.model_revision, indexes_dir)
    embedder = BgeM3Embedder(
        model_name=cfg.embeddings.model,
        revision=revision,
        device=cfg.embeddings.device,
    )

    ingester = CorpusIngester(
        source_files_by_axis=CORPUS_FILES,
        embedder=embedder,
        event_logger=JsonlEventLogger(),
        heading_classifier=classify_brief_heading,
    )
    report = ingester.ingest(indexes_dir, force=args.force)

    # Plan 02-06: post-ingest ArcPositionRetriever.reindex() hook.
    # CorpusIngester ingests outline.md as plain markdown chunks routed to
    # the arc_position axis by the filename router (Plan 02-02). After a
    # non-skipped ingest, overwrite those rows with beat-ID-stable rows
    # (Plan 02-04 RAG-02 guarantee). B-2: reindex() takes no args; all state
    # lives on the retriever (outline_path, embedder, reranker, ingestion_run_id).
    if not report.skipped:
        # Local imports keep mypy + import-linter scope tight; these kernel
        # imports do NOT cross into book_specifics (OUTLINE is already
        # resolved above).
        from book_pipeline.rag.reranker import BgeReranker
        from book_pipeline.rag.retrievers.arc_position import ArcPositionRetriever

        reranker = BgeReranker(
            model_name=cfg.reranker.model, device=cfg.reranker.device
        )
        arc = ArcPositionRetriever(
            db_path=indexes_dir,
            outline_path=OUTLINE,
            embedder=embedder,
            reranker=reranker,
            ingestion_run_id=report.ingestion_run_id,
        )
        arc.reindex()  # B-2: no args — state from __init__
        arc_note = "arc_position reindex: beat-ID-stable rows written"
    else:
        arc_note = None

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"[{'SKIP' if report.skipped else 'OK'}] CorpusIngester.ingest")
        print(f"  ingestion_run_id:     {report.ingestion_run_id or '(skipped)'}")
        print(f"  embed_model_revision: {report.embed_model_revision or '(skipped)'}")
        print(f"  db_version:           {report.db_version}")
        print(f"  wall_time_ms:         {report.wall_time_ms}")
        print(f"  source_files:         {len(report.source_files)}")
        for axis, count in sorted(report.chunk_counts_per_axis.items()):
            print(f"    {axis:22s} {count} chunks")
        if not report.skipped:
            # W-4: tell the user where the resolved revision is persisted.
            print(
                f"  resolved_model_revision: {indexes_dir / 'resolved_model_revision.json'}"
            )
            print(
                "  (config/rag_retrievers.yaml is NOT modified by the ingester — W-4)"
            )
        if arc_note is not None:
            print(f"  {arc_note}")
    return 0


register_subcommand("ingest", _add_parser)


__all__: list[str] = []
