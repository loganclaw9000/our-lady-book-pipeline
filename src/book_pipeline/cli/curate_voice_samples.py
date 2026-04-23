"""book-pipeline curate-voice-samples — build config/voice_samples.yaml.

Plan 05-01 Task 3 / D-03. The CLI:
  1. Iterates candidate .txt files from --source-dir (or
     book_specifics.voice_samples.DEFAULT_SOURCE_DIRS).
  2. Classifies each file's sub-genre by filename convention
     (narrative_*.txt / essay_*.txt / analytic_*.txt).
  3. Filters by word_count in [SLACK_WORD_MIN, SLACK_WORD_MAX] (300-700).
  4. Selects TARGET_COUNT passages balanced across GENRE_BALANCE (2/2/1).
  5. Writes voice_samples.yaml atomically (tmp+rename).
  6. Exits 0 on success, 1 on insufficient candidates.

This module is the CLI composition seam to book_specifics.voice_samples;
kernel modules never import voice_samples directly (import-linter contract
1 exemption — 4th exemption under Plan 03-02 precedent).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from book_pipeline.book_specifics.voice_samples import (
    DEFAULT_SOURCE_DIRS,
    GENRE_BALANCE,
    SLACK_WORD_MAX,
    SLACK_WORD_MIN,
    TARGET_COUNT,
    TARGET_WORD_MAX,
    TARGET_WORD_MIN,
    classify_filename,
)
from book_pipeline.cli.main import register_subcommand

DEFAULT_OUT_PATH = "config/voice_samples.yaml"


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "curate-voice-samples",
        help=(
            "Build config/voice_samples.yaml from curated 400-600-word "
            "passages in --source-dir (Mode-B drafter voice-samples prefix)."
        ),
    )
    p.add_argument(
        "--out",
        default=DEFAULT_OUT_PATH,
        help=f"Output YAML path (default: {DEFAULT_OUT_PATH}).",
    )
    p.add_argument(
        "--source-dir",
        action="append",
        default=None,
        help=(
            "Source directory of candidate .txt files (repeatable). "
            "Files are classified by filename prefix: narrative_/essay_/analytic_. "
            f"Default: {[str(p) for p in DEFAULT_SOURCE_DIRS]}"
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written; do not modify --out.",
    )
    p.set_defaults(_handler=_run)


def _gather_candidates(
    source_dirs: list[Path],
) -> dict[str, list[tuple[Path, str]]]:
    """Walk source dirs; return {sub_genre: [(path, text), ...]} filtered by word count."""
    buckets: dict[str, list[tuple[Path, str]]] = {
        "narrative": [],
        "essay": [],
        "analytic": [],
    }
    for src in source_dirs:
        if not src.is_dir():
            print(
                f"WARNING: source dir {src} not found — skipping.",
                file=sys.stderr,
            )
            continue
        # Sort for deterministic output across runs.
        for path in sorted(src.glob("*.txt")):
            sub_genre = classify_filename(path.name)
            if sub_genre is None:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            wc = len(text.split())
            if wc < SLACK_WORD_MIN or wc > SLACK_WORD_MAX:
                print(
                    f"  skip {path.name}: word_count={wc} outside "
                    f"{SLACK_WORD_MIN}-{SLACK_WORD_MAX} slack band.",
                    file=sys.stderr,
                )
                continue
            buckets[sub_genre].append((path, text))
    return buckets


def _select_balanced(
    buckets: dict[str, list[tuple[Path, str]]],
) -> list[tuple[Path, str]]:
    """Take GENRE_BALANCE[g] from each bucket; total == TARGET_COUNT when possible."""
    selected: list[tuple[Path, str]] = []
    for genre in ("narrative", "essay", "analytic"):
        take = GENRE_BALANCE[genre]
        selected.extend(buckets.get(genre, [])[:take])
    return selected


def _atomic_write_yaml(out_path: Path, passages: list[str]) -> None:
    """Atomic tmp+rename write (mirror Plan 03-02 pattern)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        {"passages": passages},
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=10_000,  # avoid wrapping long prose
    )
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, out_path)


def _run(args: argparse.Namespace) -> int:
    source_dirs: list[Path]
    if args.source_dir:
        source_dirs = [Path(p) for p in args.source_dir]
    else:
        source_dirs = list(DEFAULT_SOURCE_DIRS)

    buckets = _gather_candidates(source_dirs)
    selected = _select_balanced(buckets)

    if len(selected) < 3:
        total_available = sum(len(v) for v in buckets.values())
        print(
            f"[FAIL] curate-voice-samples: only {len(selected)} passages selected "
            f"(need >=3 for ModeBDrafter D-03 validator). Total in-band "
            f"candidates across all source dirs: {total_available}.",
            file=sys.stderr,
        )
        print("Options:", file=sys.stderr)
        print(
            f"  (a) supply more --source-dir paths containing "
            f"narrative_/essay_/analytic_ *.txt files in the {TARGET_WORD_MIN}"
            f"-{TARGET_WORD_MAX} word band.",
            file=sys.stderr,
        )
        print(
            f"  (b) widen --source-dir to a directory containing at least "
            f"{TARGET_COUNT} in-band passages with the naming convention.",
            file=sys.stderr,
        )
        return 1

    passages = [text for (_, text) in selected]

    if args.dry_run:
        print(f"[dry-run] would write {len(passages)} passages to {args.out}:")
        for path, text in selected:
            wc = len(text.split())
            print(f"  - {path.name} ({wc} words)")
        return 0

    out_path = Path(args.out)
    _atomic_write_yaml(out_path, passages)

    print(f"[ok] wrote {len(passages)} voice samples to {out_path}")
    for path, text in selected:
        wc = len(text.split())
        print(f"  - {path.name} ({wc} words)")
    return 0


register_subcommand("curate-voice-samples", _add_parser)


__all__: list[str] = []
