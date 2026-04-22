"""Verifies `uv run lint-imports` passes against the committed tree.

This is the happy-path test. The RULE-CATCHES-VIOLATION proof lives in
test_lint_rule_catches_violation.py (task 2).
"""

from __future__ import annotations

import subprocess


def test_lint_imports_passes() -> None:
    result = subprocess.run(
        ["uv", "run", "lint-imports"],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )
    assert result.returncode == 0, (
        f"lint-imports failed on clean tree.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_book_specifics_module_importable() -> None:
    from book_pipeline.book_specifics.corpus_paths import CORPUS_ROOT
    from book_pipeline.book_specifics.nahuatl_entities import NAHUATL_CANONICAL_NAMES

    assert str(CORPUS_ROOT).endswith("our-lady-of-champion")
    assert "Quetzalcoatl" in NAHUATL_CANONICAL_NAMES


def test_kernel_does_not_import_book_specifics() -> None:
    """Static grep fallback — even if lint-imports is misconfigured, no kernel source
    file should contain the literal substring 'book_specifics'."""
    import pathlib

    kernel_dirs = [
        pathlib.Path("src/book_pipeline/interfaces"),
        pathlib.Path("src/book_pipeline/observability"),
        pathlib.Path("src/book_pipeline/stubs"),
        pathlib.Path("src/book_pipeline/config"),
        pathlib.Path("src/book_pipeline/cli"),
        pathlib.Path("src/book_pipeline/openclaw"),
        pathlib.Path("src/book_pipeline/rag"),
    ]
    for d in kernel_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            assert "book_specifics" not in text, f"kernel file {py} imports book_specifics"


def test_lint_imports_mypy_scope_matches_phase_1_packages() -> None:
    """scripts/lint_imports.sh mypy step MUST be scoped to Phase 1 packages,
    not whole-tree `mypy src`. Whole-tree mypy can surface cross-module
    inference failures that didn't fail per-plan gates, creating a last-mile
    failure class the aggregate gate should not introduce."""
    import pathlib

    content = pathlib.Path("scripts/lint_imports.sh").read_text(encoding="utf-8")
    # Must NOT contain `mypy src` (whole-tree) as a standalone step.
    # Allowed: `mypy src/book_pipeline/...` (scoped per-package).
    for line in content.splitlines():
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#"):
            continue
        # `mypy src` at end-of-line or with only whitespace after is whole-tree
        if stripped == "uv run mypy src" or stripped.endswith(" mypy src"):
            raise AssertionError(
                f"scripts/lint_imports.sh contains whole-tree `mypy src` — must be "
                f"scoped to Phase 1 packages. Offending line: {line!r}"
            )
    # Must contain the scoped packages.
    required_packages = [
        "src/book_pipeline/interfaces",
        "src/book_pipeline/observability",
        "src/book_pipeline/config",
        "src/book_pipeline/openclaw",
        "src/book_pipeline/cli",
        "src/book_pipeline/book_specifics",
    ]
    for pkg in required_packages:
        assert pkg in content, f"scripts/lint_imports.sh missing mypy target: {pkg}"
