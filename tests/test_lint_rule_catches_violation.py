"""Proof test: the import-linter rule from FOUND-05 actually catches violations.

Why this test matters: if a developer accidentally deletes a source_module from
a contract in pyproject.toml, the contract silently stops enforcing. This test
writes a tiny violating file, runs lint-imports, asserts non-zero exit, then
cleans up. Without this test, FOUND-05 enforcement is theater.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

VIOLATION_FILE = Path("src/book_pipeline/observability/_lint_violation_probe.py")
VIOLATION_SOURCE = '''"""TEMPORARY file used by tests/test_lint_rule_catches_violation.py.

This file should NEVER exist outside the scope of that test — if you see it in
a commit, delete it. It exists only to prove import-linter catches a kernel ->
book_specifics import.
"""

from book_pipeline.book_specifics import corpus_paths  # noqa: F401  — intentional violation
'''


@pytest.fixture
def violation_fixture() -> Iterator[Path]:
    """Create the violating file; yield; delete unconditionally."""
    VIOLATION_FILE.write_text(VIOLATION_SOURCE, encoding="utf-8")
    try:
        yield VIOLATION_FILE
    finally:
        if VIOLATION_FILE.exists():
            VIOLATION_FILE.unlink()


def test_violation_file_does_not_exist_in_clean_tree() -> None:
    """Guard: the violation file must not be committed. If this fails, the previous
    test run didn't clean up — delete the file manually."""
    assert not VIOLATION_FILE.exists(), (
        f"{VIOLATION_FILE} was not cleaned up from a prior test run. "
        f"Delete it manually before re-running."
    )


def test_lint_imports_detects_kernel_to_book_specifics_violation(
    violation_fixture: Path,
) -> None:
    """FOUND-05 rule proof: injecting kernel->book_specifics import makes lint-imports fail."""
    result = subprocess.run(
        ["uv", "run", "lint-imports"],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )
    assert result.returncode != 0, (
        "lint-imports exited 0 DESPITE a deliberate kernel->book_specifics import. "
        "The FOUND-05 rule is not enforcing.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "book_specifics" in combined or "kernel packages" in combined, (
        "lint-imports failed, but output doesn't mention book_specifics or the "
        "contract name — verify the rule is catching the right thing.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_lint_imports_passes_again_after_cleanup() -> None:
    """After the violation fixture tears down, the tree should be clean again."""
    # Defensive: ensure no violation file lingering
    if VIOLATION_FILE.exists():
        VIOLATION_FILE.unlink()
    result = subprocess.run(
        ["uv", "run", "lint-imports"],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )
    assert result.returncode == 0, (
        f"lint-imports should pass on clean tree.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
