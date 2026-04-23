"""book-pipeline CLI entry point with subcommand registration.

Subcommand modules self-register by calling `register_subcommand` at import time.
main() imports each subcommand module in the SUBCOMMAND_IMPORTS list.

To add a new subcommand (e.g. in plan 03/04/05):
  1. Create src/book_pipeline/cli/<name>.py with a module-level call:
       register_subcommand("<name>", _add_parser)
     where _add_parser(subparsers: argparse._SubParsersAction) -> None
     configures its parser and sets parser.set_defaults(_handler=<fn>).
  2. Append the module import to SUBCOMMAND_IMPORTS below.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
from collections.abc import Callable

from book_pipeline import __version__

SUBCOMMANDS: dict[str, Callable[[argparse._SubParsersAction[argparse.ArgumentParser]], None]] = {}

# All Phase 1 subcommand modules pre-declared here. _load_subcommands() tolerates
# ImportError for modules not yet created (Wave 2/3 plans add their modules without
# editing this file). Every subcommand module calls register_subcommand at import time.
SUBCOMMAND_IMPORTS: list[str] = [
    "book_pipeline.cli.version",
    "book_pipeline.cli.validate_config",   # created by plan 03
    "book_pipeline.cli.openclaw_cmd",      # created by plan 04
    "book_pipeline.cli.smoke_event",       # created by plan 05
    "book_pipeline.cli.ingest",            # created by phase-2 plan 02
    "book_pipeline.cli.pin_voice",         # created by phase-3 plan 01
    "book_pipeline.cli.curate_anchors",    # created by phase-3 plan 02
    "book_pipeline.cli.vllm_bootstrap",    # created by phase-3 plan 03
    "book_pipeline.cli.draft",             # created by phase-3 plan 07
    # Plan 04-05: chapter, chapter_status, ablate
    "book_pipeline.cli.chapter",
    "book_pipeline.cli.chapter_status",
    "book_pipeline.cli.ablate",
    # Plan 05-01: curate-voice-samples for Mode-B drafter voice-samples prefix
    "book_pipeline.cli.curate_voice_samples",
]


def register_subcommand(
    name: str,
    adder: Callable[[argparse._SubParsersAction[argparse.ArgumentParser]], None],
) -> None:
    """Register a subcommand. Called at import time by each subcommand module."""
    SUBCOMMANDS[name] = adder


def _load_subcommands() -> None:
    """Import each subcommand module. Tolerates ImportError so Wave 2/3 plans can
    land their modules without plan 01 being edited after the fact.
    """
    for dotted in SUBCOMMAND_IMPORTS:
        # Module not yet created by its owning plan — skip silently.
        with contextlib.suppress(ImportError):
            importlib.import_module(dotted)


def main(argv: list[str] | None = None) -> int:
    _load_subcommands()
    parser = argparse.ArgumentParser(
        prog="book-pipeline",
        description="Autonomous novel drafting pipeline for Our Lady of Champion.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"book-pipeline {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name in sorted(SUBCOMMANDS):
        SUBCOMMANDS[name](subparsers)
    args = parser.parse_args(argv)
    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))
