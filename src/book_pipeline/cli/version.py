"""book-pipeline version subcommand (also demonstrates the subcommand registration pattern)."""
from __future__ import annotations

import argparse

from book_pipeline import __version__
from book_pipeline.cli.main import register_subcommand


def _add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("version", help="Print the book-pipeline version string")
    p.set_defaults(_handler=_run)


def _run(_args: argparse.Namespace) -> int:
    print(f"book-pipeline {__version__}")
    return 0


register_subcommand("version", _add_parser)
