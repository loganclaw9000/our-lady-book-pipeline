"""book-pipeline curate-anchors — rebuild config/voice_anchors/anchor_set_v1.yaml.

OBS-03 anchor curation. The CLI:
  1. Iterates ANCHOR_CANDIDATES (book-domain pointers from book_specifics).
  2. Applies selection heuristics → candidate rows tagged by sub_genre.
  3. Pre-flight quota check (W-3/W-5): abort with structured stderr if any
     sub-genre is short of its quota.
  4. Applies per-sub-genre quotas → final AnchorSet.
  5. Saves config/voice_anchors/anchor_set_v1.yaml atomically.
  6. (unless --skip-embed) Loads BgeM3Embedder, computes centroid,
     writes indexes/voice_anchors/embeddings.parquet.
  7. Runs check_anchor_dominance → non-fatal warnings.
  8. Rewrites config/mode_thresholds.yaml voice_fidelity.anchor_set_sha atomically.
  9. Emits one role='anchor_curator' Event.
  10. Prints summary, exits 0.

V-1 minimums (escape-hatchable via --override-quotas but warned): essay >=6,
analytic >=6, narrative >=4.

This module is the CLI-composition seam to book_specifics.anchor_sources;
kernel modules never import anchor_sources directly.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import xxhash
import yaml

from book_pipeline.book_specifics.anchor_sources import (
    CandidateRow,
    anchor_candidates,
    select_rows_from_candidate,
)
from book_pipeline.cli.main import register_subcommand
from book_pipeline.interfaces.types import Event
from book_pipeline.observability import JsonlEventLogger, event_id, hash_text
from book_pipeline.voice_fidelity.anchors import (
    Anchor,
    AnchorSet,
    check_anchor_dominance,
    compute_centroid,
)

DEFAULT_YAML_PATH = "config/voice_anchors/anchor_set_v1.yaml"
DEFAULT_THRESHOLDS_PATH = "config/mode_thresholds.yaml"
DEFAULT_EMBEDDINGS_PATH = "indexes/voice_anchors/embeddings.parquet"
DEFAULT_SOURCE_LIMIT = 2000

DEFAULT_QUOTAS = {"essay": 8, "analytic": 8, "narrative": 6}
V1_MINIMUMS = {"essay": 6, "analytic": 6, "narrative": 4}


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "curate-anchors",
        help=(
            "Rebuild config/voice_anchors/anchor_set_v1.yaml + embeddings.parquet "
            "+ pin anchor_set_sha in config/mode_thresholds.yaml (OBS-03)."
        ),
    )
    p.add_argument(
        "--yaml-path",
        default=DEFAULT_YAML_PATH,
        help=f"anchor set yaml output path (default: {DEFAULT_YAML_PATH}).",
    )
    p.add_argument(
        "--thresholds-path",
        default=DEFAULT_THRESHOLDS_PATH,
        help=f"mode_thresholds.yaml path (default: {DEFAULT_THRESHOLDS_PATH}).",
    )
    p.add_argument(
        "--embeddings-path",
        default=DEFAULT_EMBEDDINGS_PATH,
        help=f"embeddings parquet path (default: {DEFAULT_EMBEDDINGS_PATH}).",
    )
    p.add_argument(
        "--source-limit",
        type=int,
        default=DEFAULT_SOURCE_LIMIT,
        help=f"max rows scanned per source (default: {DEFAULT_SOURCE_LIMIT}).",
    )
    p.add_argument(
        "--skip-embed",
        action="store_true",
        help="Skip BGE-M3 embedding + parquet write (tests + fast path).",
    )
    p.add_argument(
        "--override-quotas",
        default=None,
        help=(
            "Comma-separated quota overrides, e.g. "
            "essay=4,analytic=8,narrative=6. Values below V-1 minimums "
            "(essay>=6, analytic>=6, narrative>=4) warn but proceed."
        ),
    )
    p.add_argument(
        "--events-path",
        default=None,
        help="Override events.jsonl path for testability (default: runs/events.jsonl).",
    )
    p.set_defaults(_handler=_run)


# --- Quotas --------------------------------------------------------------


def _parse_quota_overrides(raw: str | None) -> dict[str, int]:
    if not raw:
        return dict(DEFAULT_QUOTAS)
    out = dict(DEFAULT_QUOTAS)
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"malformed --override-quotas segment: {chunk!r}")
        key, val = chunk.split("=", 1)
        key = key.strip()
        if key not in DEFAULT_QUOTAS:
            raise ValueError(
                f"--override-quotas key {key!r} not in {list(DEFAULT_QUOTAS)}"
            )
        out[key] = int(val.strip())
    return out


def _warn_below_v1_minimums(quotas: dict[str, int]) -> None:
    for sg, floor in V1_MINIMUMS.items():
        if quotas[sg] < floor:
            print(
                f"WARNING: --override-quotas {sg}={quotas[sg]} is below PITFALLS "
                f"V-1 minimum ({floor}). Proceeding (escape hatch is deliberate).",
                file=sys.stderr,
            )


def _emit_quota_failure(
    quotas: dict[str, int], available: dict[str, int]
) -> None:
    print("QUOTA CHECK FAILED:", file=sys.stderr)
    for sg in ("essay", "analytic", "narrative"):
        need = quotas.get(sg, 0)
        have = available.get(sg, 0)
        if have < need:
            diff = need - have
            print(
                f"  {sg:10s} need {need:2d}, have {have:2d} (SHORT by {diff})",
                file=sys.stderr,
            )
        else:
            print(
                f"  {sg:10s} need {need:2d}, have {have:2d} (ok)",
                file=sys.stderr,
            )
    print("", file=sys.stderr)
    print("Options:", file=sys.stderr)
    failing = [sg for sg in quotas if available.get(sg, 0) < quotas[sg]]
    if failing:
        new_quotas = ",".join(
            f"{sg}={min(quotas[sg], available.get(sg, 0))}" for sg in quotas
        )
        print(
            f"  (a) lower the failing quota: "
            f"book-pipeline curate-anchors --override-quotas {new_quotas}",
            file=sys.stderr,
        )
    print(
        "  (b) widen the source by adding another entry to "
        "book_specifics.anchor_sources.ANCHOR_CANDIDATES",
        file=sys.stderr,
    )
    print(
        "  (c) raise --source-limit if rows were truncated before classification",
        file=sys.stderr,
    )


# --- Selection + build ---------------------------------------------------


def _gather_candidate_rows(source_limit: int) -> list[CandidateRow]:
    """Iterate ANCHOR_CANDIDATES, gather rows passing the selection filter."""
    collected: list[CandidateRow] = []
    for candidate in anchor_candidates():
        path = candidate["path"]
        if not path.is_file():
            print(
                f"WARNING: anchor source {candidate['source_label']} path "
                f"{path} not found — skipping.",
                file=sys.stderr,
            )
            continue
        rows = list(select_rows_from_candidate(candidate, limit=source_limit))
        collected.extend(rows)
    return collected


def _apply_quotas(
    rows: list[CandidateRow], quotas: dict[str, int]
) -> list[CandidateRow]:
    """Bucket rows by sub_genre then take the first `quota[sg]` per bucket.

    Order preservation: rows arrive in source-order; we keep that order
    deterministic by bucketing in a dict[list] and slicing.
    """
    buckets: dict[str, list[CandidateRow]] = {"essay": [], "analytic": [], "narrative": []}
    for r in rows:
        sg = r["sub_genre"]
        if sg in buckets:
            buckets[sg].append(r)
    out: list[CandidateRow] = []
    # Emit in canonical order so the YAML is stable.
    for sg in ("essay", "analytic", "narrative"):
        out.extend(buckets[sg][: quotas[sg]])
    return out


def _row_to_anchor(row: CandidateRow, idx: int) -> Anchor:
    prov_sha = xxhash.xxh64(row["row_json_bytes"]).hexdigest()
    # ID format: <source_label_hint>_<sub_genre>_<idx>. Include source hint
    # so the ID remains informative across source types.
    src_hint = Path(row["source_file"]).stem  # e.g., 'train_filtered'
    anchor_id = f"{src_hint}_{row['sub_genre']}_{idx:03d}"
    return Anchor(
        id=anchor_id,
        text=row["text"],
        sub_genre=row["sub_genre"],
        source_file=row["source_file"],
        source_line_range=f"{row['source_line']}-{row['source_line']}",
        provenance_sha=prov_sha,
    )


# --- Thresholds-yaml atomic rewrite --------------------------------------


def _rewrite_thresholds_anchor_set_sha(
    thresholds_path: Path, new_sha: str
) -> None:
    """Rewrite voice_fidelity.anchor_set_sha in thresholds_path atomically.

    Preserves the rest of the YAML; only the one scalar changes. The file
    MUST already contain a voice_fidelity block (Plan 03-02 seeds the
    default values during mode_thresholds.yaml edit).
    """
    if not thresholds_path.is_file():
        raise FileNotFoundError(f"{thresholds_path} does not exist")
    data = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "voice_fidelity" not in data:
        raise ValueError(
            f"{thresholds_path} does not contain a voice_fidelity section"
        )
    data["voice_fidelity"]["anchor_set_sha"] = new_sha
    body = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    tmp = thresholds_path.with_suffix(thresholds_path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, thresholds_path)


# --- Embeddings parquet write --------------------------------------------


def _write_embeddings_parquet(
    anchors: AnchorSet, embeddings: np.ndarray, parquet_path: Path
) -> None:
    """Write the per-anchor embedding matrix to parquet."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    ids = [a.id for a in anchors.anchors]
    sub_genres = [a.sub_genre for a in anchors.anchors]
    # Store each embedding row as a list<float32>. pyarrow's fixed-size-list
    # support varies across versions; list is universally supported.
    emb_list = [row.tolist() for row in embeddings.astype(np.float32)]
    table = pa.table(
        {
            "id": pa.array(ids, type=pa.string()),
            "sub_genre": pa.array(sub_genres, type=pa.string()),
            "embedding": pa.array(emb_list, type=pa.list_(pa.float32())),
        }
    )
    pq.write_table(table, parquet_path)  # type: ignore[no-untyped-call]


# --- Event emission ------------------------------------------------------


def _build_event(
    *,
    anchor_set_sha: str,
    embedder_revision: str,
    num_anchors: int,
    sub_genre_counts: dict[str, int],
    dominance_warnings: list[str],
    latency_ms: int,
) -> Event:
    ts_iso = datetime.now(UTC).isoformat(timespec="milliseconds")
    prompt_h = hash_text(anchor_set_sha)
    eid = event_id(ts_iso, "anchor_curator", "cli.curate_anchors:_run", prompt_h)
    return Event(
        event_id=eid,
        ts_iso=ts_iso,
        role="anchor_curator",
        model=f"bge-m3-{embedder_revision}",
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=num_anchors,
        latency_ms=latency_ms,
        temperature=None,
        top_p=None,
        caller_context={
            "module": "cli.curate_anchors",
            "function": "curate",
            "num_anchors": num_anchors,
            "sub_genre_counts": sub_genre_counts,
        },
        output_hash=anchor_set_sha,
        mode=None,
        rubric_version=None,
        checkpoint_sha=None,
        extra={
            "anchor_set_sha": anchor_set_sha,
            "embedder_revision": embedder_revision,
            "dominance_warnings": dominance_warnings,
        },
    )


# --- Main flow -----------------------------------------------------------


def _run(args: argparse.Namespace) -> int:
    start_ns = time.monotonic_ns()

    yaml_path = Path(args.yaml_path)
    thresholds_path = Path(args.thresholds_path)
    embeddings_path = Path(args.embeddings_path)

    # Parse quota overrides.
    try:
        quotas = _parse_quota_overrides(args.override_quotas)
    except ValueError as exc:
        print(f"[FAIL] --override-quotas parse error: {exc}", file=sys.stderr)
        return 2
    _warn_below_v1_minimums(quotas)

    # Gather candidate rows.
    all_rows = _gather_candidate_rows(args.source_limit)
    available_counts: dict[str, int] = dict(
        Counter(r["sub_genre"] for r in all_rows)
    )
    # Normalize keys (all 3 sub-genres present even if 0).
    for sg in DEFAULT_QUOTAS:
        available_counts.setdefault(sg, 0)

    # Pre-flight quota check.
    if any(available_counts[sg] < quotas[sg] for sg in quotas):
        _emit_quota_failure(quotas, available_counts)
        return 3

    # Apply quotas, build anchor set.
    selected = _apply_quotas(all_rows, quotas)
    anchors_list = [_row_to_anchor(r, i) for i, r in enumerate(selected)]
    anchor_set = AnchorSet(anchors=anchors_list)
    anchor_sha = anchor_set.sha

    # Save anchor_set_v1.yaml.
    anchor_set.save_to_yaml(yaml_path)

    # Embed + write parquet, unless --skip-embed.
    embedder_revision = "skipped"
    dominance_warnings: list[str] = []
    if not args.skip_embed:
        from book_pipeline.rag import BgeM3Embedder

        embedder: Any = BgeM3Embedder()  # revision resolved lazily; caller can override via config
        centroid = compute_centroid(anchor_set, embedder)
        embedder_revision = embedder.revision_sha
        # Re-embed to get the full matrix (compute_centroid already ran,
        # but doesn't expose the raw matrix; this is a small re-cost).
        raw_matrix = embedder.embed_texts([a.text for a in anchor_set.anchors])
        _write_embeddings_parquet(anchor_set, raw_matrix, embeddings_path)
        dominance_warnings = check_anchor_dominance(
            anchor_set, embedder, threshold=0.15
        )
        if dominance_warnings:
            print(
                f"WARNING: {len(dominance_warnings)} anchor(s) dominate the "
                f"centroid (contribution > 0.15): {dominance_warnings}",
                file=sys.stderr,
            )
        # Silence unused-variable lint — centroid is needed for the warning
        # scan + future per-sub-genre extension.
        _ = centroid

    # Pin SHA in mode_thresholds.yaml.
    _rewrite_thresholds_anchor_set_sha(thresholds_path, anchor_sha)

    # Sub-genre counts in the FINAL set (widened to dict[str, int] for Event).
    raw_counts = Counter(a.sub_genre for a in anchor_set.anchors)
    final_counts: dict[str, int] = {str(k): int(v) for k, v in raw_counts.items()}
    for sg in DEFAULT_QUOTAS:
        final_counts.setdefault(sg, 0)

    latency_ms = max(1, (time.monotonic_ns() - start_ns) // 1_000_000)

    # Emit the anchor_curator event.
    event = _build_event(
        anchor_set_sha=anchor_sha,
        embedder_revision=embedder_revision,
        num_anchors=len(anchor_set.anchors),
        sub_genre_counts=final_counts,
        dominance_warnings=dominance_warnings,
        latency_ms=int(latency_ms),
    )
    events_path = Path(args.events_path) if args.events_path else None
    logger = JsonlEventLogger(path=events_path) if events_path else JsonlEventLogger()
    logger.emit(event)

    # Summary.
    sha_short = f"{anchor_sha[:16]}...{anchor_sha[-4:]}"
    rev_short = (
        f"{embedder_revision[:16]}..."
        if len(embedder_revision) >= 20
        else embedder_revision
    )
    print(
        f"✓ pinned anchor_set_sha={sha_short} | "
        f"{len(anchor_set.anchors)} anchors | "
        f"BGE-M3 revision={rev_short}"
    )
    print(
        f"  sub_genre_counts: essay={final_counts['essay']} "
        f"analytic={final_counts['analytic']} "
        f"narrative={final_counts['narrative']}"
    )
    if dominance_warnings:
        print(f"  dominance warnings: {dominance_warnings}")
    return 0


register_subcommand("curate-anchors", _add_parser)


__all__: list[str] = []
