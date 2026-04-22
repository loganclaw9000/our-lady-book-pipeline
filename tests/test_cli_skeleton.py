"""Smoke tests for the CLI skeleton — verifies FOUND-01 success criterion."""
from __future__ import annotations

import subprocess
import sys

from book_pipeline import __version__
from book_pipeline.cli.main import main


def test_version_flag_prints_version(capsys) -> None:
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_help_lists_version_subcommand(capsys) -> None:
    # argparse --help raises SystemExit
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    captured = capsys.readouterr()
    assert "version" in captured.out


def test_version_subcommand_runs(capsys) -> None:
    rc = main(["version"])
    assert rc == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_python_module_invocation() -> None:
    """python -m book_pipeline --version should print and exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "book_pipeline", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout
