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
    file should contain the literal substring 'book_specifics'.

    Documented CLI-composition exemptions (see pyproject.toml contract 1
    ignore_imports): `src/book_pipeline/cli/ingest.py` is the composition seam
    between kernel (corpus_ingest) and book_specifics and is allowed to import
    corpus_paths + heading_classifier. Every other kernel file remains under
    the substring-level guard.
    """
    import pathlib

    kernel_dirs = [
        pathlib.Path("src/book_pipeline/interfaces"),
        pathlib.Path("src/book_pipeline/observability"),
        pathlib.Path("src/book_pipeline/stubs"),
        pathlib.Path("src/book_pipeline/config"),
        pathlib.Path("src/book_pipeline/cli"),
        pathlib.Path("src/book_pipeline/openclaw"),
        pathlib.Path("src/book_pipeline/rag"),
        pathlib.Path("src/book_pipeline/corpus_ingest"),
        # Phase 3 plan 01: 4 new kernel packages (drafter, critic, regenerator,
        # voice_fidelity). Each lands with at least an __init__.py; scan them
        # too so book_specifics drift is caught from Phase 3 onward.
        pathlib.Path("src/book_pipeline/drafter"),
        pathlib.Path("src/book_pipeline/critic"),
        pathlib.Path("src/book_pipeline/regenerator"),
        pathlib.Path("src/book_pipeline/voice_fidelity"),
        # Phase 4 plan 01: 4 new kernel packages (chapter_assembler,
        # entity_extractor, retrospective, ablation). Each lands as an
        # empty __init__.py anchor; downstream Phase 4 plans fill them in.
        pathlib.Path("src/book_pipeline/chapter_assembler"),
        pathlib.Path("src/book_pipeline/entity_extractor"),
        pathlib.Path("src/book_pipeline/retrospective"),
        pathlib.Path("src/book_pipeline/ablation"),
    ]
    # Phase 2 plan 02 + 06 / Phase 3 plans 02-03 + 03-07: CLI-composition
    # exemptions per pyproject ignore_imports.
    # - cli/ingest.py: kernel corpus_ingest + book_specifics.{corpus_paths,heading_classifier}
    # - cli/_entity_list.py: bundler entity_list DI + book_specifics.nahuatl_entities
    # - cli/curate_anchors.py: OBS-03 anchor curation + book_specifics.anchor_sources
    # - cli/vllm_bootstrap.py: vLLM unit + handshake + book_specifics.vllm_endpoints
    # - cli/draft.py: full scene-loop composition root (Plan 03-07) bridging
    #   book_specifics.{vllm_endpoints,training_corpus,corpus_paths,nahuatl_entities}
    documented_exemptions = {
        pathlib.Path("src/book_pipeline/cli/ingest.py"),
        pathlib.Path("src/book_pipeline/cli/_entity_list.py"),
        pathlib.Path("src/book_pipeline/cli/curate_anchors.py"),
        pathlib.Path("src/book_pipeline/cli/vllm_bootstrap.py"),
        pathlib.Path("src/book_pipeline/cli/draft.py"),
    }
    for d in kernel_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            if py in documented_exemptions:
                continue
            text = py.read_text(encoding="utf-8")
            assert "book_specifics" not in text, f"kernel file {py} imports book_specifics"


def test_phase_3_kernel_packages_importable() -> None:
    """Phase 3 plan 01: the 4 new kernel packages must be importable.

    Drafter, critic, regenerator, and voice_fidelity are introduced as empty
    kernel packages that downstream Phase 3 plans fill in. They exist from
    plan 03-01 onward so import-linter contracts can reference them.
    """
    import importlib

    for pkg in (
        "book_pipeline.drafter",
        "book_pipeline.critic",
        "book_pipeline.regenerator",
        "book_pipeline.voice_fidelity",
    ):
        importlib.import_module(pkg)


def test_phase_3_packages_listed_in_both_contracts() -> None:
    """Phase 3 plan 01: the 4 new kernel packages must be appended to BOTH
    import-linter contracts (source_modules of contract 1, forbidden_modules
    of contract 2). Matches the Phase 2 Plan 01 / 02 extension-policy
    precedent."""
    import pathlib

    content = pathlib.Path("pyproject.toml").read_text(encoding="utf-8")
    for pkg in (
        "book_pipeline.drafter",
        "book_pipeline.critic",
        "book_pipeline.regenerator",
        "book_pipeline.voice_fidelity",
    ):
        # Each Phase 3 kernel package appears in contract 1 source_modules AND
        # contract 2 forbidden_modules → at least 2 occurrences total.
        assert content.count(f'"{pkg}"') >= 2, (
            f"Phase 3 kernel package {pkg!r} must appear in BOTH import-linter "
            f"contracts in pyproject.toml."
        )


def test_phase_3_packages_in_lint_imports_mypy_scope() -> None:
    """Phase 3 plan 01: scripts/lint_imports.sh mypy targets must include the
    4 new Phase 3 kernel packages.
    """
    import pathlib

    content = pathlib.Path("scripts/lint_imports.sh").read_text(encoding="utf-8")
    for target in (
        "src/book_pipeline/drafter",
        "src/book_pipeline/critic",
        "src/book_pipeline/regenerator",
        "src/book_pipeline/voice_fidelity",
    ):
        assert target in content, (
            f"scripts/lint_imports.sh missing Phase 3 mypy target: {target}"
        )


def test_phase_4_kernel_packages_importable() -> None:
    """Phase 4 plan 01: the 4 new kernel packages must be importable.

    chapter_assembler, entity_extractor, retrospective, and ablation are
    introduced as empty kernel packages that downstream Phase 4 plans (04-02
    ConcatAssembler, 04-03 OpusEntityExtractor + OpusRetrospectiveWriter,
    04-04 AblationRun harness) fill in. They exist from plan 04-01 onward so
    import-linter contracts can reference them.
    """
    import importlib

    for pkg in (
        "book_pipeline.chapter_assembler",
        "book_pipeline.entity_extractor",
        "book_pipeline.retrospective",
        "book_pipeline.ablation",
    ):
        importlib.import_module(pkg)


def test_phase_4_packages_listed_in_both_contracts() -> None:
    """Phase 4 plan 01: the 4 new kernel packages must be appended to BOTH
    import-linter contracts (source_modules of contract 1, forbidden_modules
    of contract 2). Matches the Phase 2 Plan 01 / Phase 3 Plan 01 extension-
    policy precedent."""
    import pathlib

    content = pathlib.Path("pyproject.toml").read_text(encoding="utf-8")
    for pkg in (
        "book_pipeline.chapter_assembler",
        "book_pipeline.entity_extractor",
        "book_pipeline.retrospective",
        "book_pipeline.ablation",
    ):
        # Each Phase 4 kernel package appears in contract 1 source_modules AND
        # contract 2 forbidden_modules → at least 2 occurrences total.
        assert content.count(f'"{pkg}"') >= 2, (
            f"Phase 4 kernel package {pkg!r} must appear in BOTH import-linter "
            f"contracts in pyproject.toml."
        )


def test_phase_4_packages_in_lint_imports_mypy_scope() -> None:
    """Phase 4 plan 01: scripts/lint_imports.sh mypy targets must include the
    4 new Phase 4 kernel packages.
    """
    import pathlib

    content = pathlib.Path("scripts/lint_imports.sh").read_text(encoding="utf-8")
    for target in (
        "src/book_pipeline/chapter_assembler",
        "src/book_pipeline/entity_extractor",
        "src/book_pipeline/retrospective",
        "src/book_pipeline/ablation",
    ):
        assert target in content, (
            f"scripts/lint_imports.sh missing Phase 4 mypy target: {target}"
        )


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
