"""`book-pipeline chapter-status [<chapter_num>]` — LOOP-04 inspection CLI.

Plan 04-05. Read-only view onto Phase 4 state:

  - No args: pretty-print `.planning/pipeline_state.json` (or a hint
    message if the file doesn't exist yet).

  - With <chapter_num>: read
    `drafts/chapter_buffer/ch{NN:02d}.state.json` via
    `ChapterStateRecord.model_validate_json`, print state + dag_step +
    chapter_sha + first-5 blockers + last-3 history entries.

This module performs NO book-domain imports (no exemption required in
pyproject.toml).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from book_pipeline.cli.main import register_subcommand
from book_pipeline.interfaces.types import ChapterStateRecord


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "chapter-status",
        help=(
            "Show Phase 4 chapter status. No args: prints "
            ".planning/pipeline_state.json. With <chapter_num>: prints "
            "drafts/chapter_buffer/ch{NN:02d}.state.json summary."
        ),
    )
    p.add_argument(
        "chapter_num",
        type=int,
        nargs="?",
        default=None,
        help="Optional chapter number; omit to print the pipeline-level view.",
    )
    p.set_defaults(_handler=_run)


def _run(args: argparse.Namespace) -> int:
    chapter_num = args.chapter_num

    if chapter_num is None:
        return _print_pipeline_state()

    if chapter_num <= 0:
        print(f"Error: chapter_num must be a positive integer (got {chapter_num})")
        return 2
    return _print_chapter_record(int(chapter_num))


def _print_pipeline_state() -> int:
    """Pretty-print `.planning/pipeline_state.json` or emit a hint."""
    path = Path(".planning/pipeline_state.json")
    if not path.exists():
        print(
            "No pipeline state yet. Run `book-pipeline chapter <N>` to start."
        )
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: pipeline_state.json is malformed: {exc}")
        return 2
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def _print_chapter_record(chapter_num: int) -> int:
    """Print a per-chapter ChapterStateRecord summary."""
    state_path = (
        Path("drafts/chapter_buffer") / f"ch{chapter_num:02d}.state.json"
    )
    if not state_path.exists():
        print(f"No chapter buffer state for ch{chapter_num:02d}.")
        return 0
    try:
        record = ChapterStateRecord.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        print(f"Error: ch{chapter_num:02d}.state.json is malformed: {exc}")
        return 2

    blockers_str = (
        "none"
        if not record.blockers
        else ", ".join(record.blockers[:5])
        + ("" if len(record.blockers) <= 5 else f" (+{len(record.blockers) - 5} more)")
    )
    state_value = getattr(record.state, "value", str(record.state))
    chapter_sha = record.chapter_sha or "-"

    print(f"Chapter {chapter_num:02d}")
    print(f"  state: {state_value}")
    print(f"  dag_step: {record.dag_step}")
    print(f"  chapter_sha: {chapter_sha}")
    print(f"  blockers: {blockers_str}")
    print("  history (last 3):")
    last3 = record.history[-3:] if len(record.history) > 3 else record.history
    if not last3:
        print("    (none)")
    else:
        for entry in last3:
            from_s = entry.get("from", "?")
            to_s = entry.get("to", "?")
            ts = entry.get("ts_iso", "?")
            note = entry.get("note", "")
            print(f"    {from_s} → {to_s}  @ {ts}  note={note}")
    return 0


register_subcommand("chapter-status", _add_parser)


__all__: list[str] = [
    "_run",
]
