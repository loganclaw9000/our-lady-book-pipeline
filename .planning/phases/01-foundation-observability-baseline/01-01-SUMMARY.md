---
phase: 01-foundation-observability-baseline
plan: 01
subsystem: packaging-cli-skeleton
tags: [uv, packaging, cli, argparse, dispatcher, foundation]
requirements_completed: [FOUND-01]
dependency_graph:
  requires: []
  provides:
    - "uv-managed Python 3.12 venv via `uv sync`"
    - "book_pipeline package importable after install"
    - "CLI entry point `book-pipeline` via [project.scripts]"
    - "Subcommand registration API (register_subcommand + SUBCOMMAND_IMPORTS)"
    - "python -m book_pipeline invocation"
    - "Dev tooling (ruff, mypy, pre-commit, pytest) installed and configured"
  affects:
    - "Plan 01-02 (Pydantic Settings config loader + validate-config subcommand)"
    - "Plan 01-03 (openclaw workspace bootstrap + openclaw subcommand)"
    - "Plan 01-04 (EventLogger observability + smoke-event subcommand)"
    - "Plan 01-05 (13 Protocol interfaces + stub implementations)"
    - "Plan 01-06 (module-boundary import-linter rule)"
tech_stack:
  added:
    - "uv 0.11.7 (package manager)"
    - "anthropic 0.96.x (locked)"
    - "pydantic 2.x + pydantic-settings 2.x"
    - "PyYAML 6.x"
    - "lancedb 0.30.x"
    - "sentence-transformers 5.x (BGE-M3 driver)"
    - "httpx, tenacity, python-json-logger, xxhash, tiktoken"
    - "pytest 9.x + pytest-asyncio"
    - "ruff, mypy (strict), pre-commit, rich, import-linter"
    - "torch 2.11 (pulled transitively by sentence-transformers — CPU/GPU agnostic at install)"
  patterns:
    - "argparse subparser dispatch with module-level self-registration (plugin-style, zero-edit extensibility for plans 03/04/05)"
    - "SUBCOMMAND_IMPORTS declarative list + importlib tolerating ImportError so later plans ship modules without editing main.py"
    - "src/ layout with [tool.hatch.build.targets.wheel] packages = ['src/book_pipeline']"
key_files:
  created:
    - "pyproject.toml"
    - ".python-version"
    - "ruff.toml"
    - "mypy.ini"
    - ".pre-commit-config.yaml"
    - ".env.example"
    - "src/book_pipeline/__init__.py"
    - "src/book_pipeline/__main__.py"
    - "src/book_pipeline/cli/__init__.py"
    - "src/book_pipeline/cli/main.py"
    - "src/book_pipeline/cli/version.py"
    - "tests/__init__.py"
    - "tests/test_cli_skeleton.py"
    - "uv.lock"
  modified: []
decisions:
  - "CLI dispatcher uses importlib + try/except ImportError rather than hard imports, so Wave 2/3 plans (03/04/05) can add their subcommand modules without coming back to edit this file's dispatch table. SUBCOMMAND_IMPORTS is the sorted registry; order is irrelevant because SUBCOMMANDS is keyed by name."
  - "Python pin is 3.12 (per CONTEXT.md D-01) — overrides STACK.md's 3.11 recommendation. Host has 3.12.3 and all deps resolve clean."
  - "Hatchling build-backend with src/ layout chosen over flat layout so `import book_pipeline` can never accidentally work without install (catches venv drift early)."
  - "`--version` is provided both as a top-level `--version` flag (via argparse `action='version'`) AND as a subcommand. The flag form satisfies FOUND-01 SC-1 verbatim; the subcommand form exists because it's the simplest possible demonstration of the registration pattern for plan authors to copy."
metrics:
  duration_minutes: 7
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 14
  files_modified: 0
  tests_added: 4
  tests_passing: 4
commits:
  - hash: 83943dc
    type: chore
    summary: uv packaging config + dev tooling
  - hash: eaa0b89
    type: feat
    summary: book_pipeline package skeleton + CLI dispatcher with subcommand registration
---

# Phase 1 Plan 1: Foundation Packaging + CLI Skeleton Summary

**One-liner:** uv-managed Python 3.12 package with argparse CLI dispatcher that self-registers subcommands via `register_subcommand` and tolerant `SUBCOMMAND_IMPORTS`, letting plans 03/04/05 add commands without editing `main.py`.

## What Shipped

A working, greenfield-to-runnable Python package:

- `uv sync` from a clean clone produces a complete dev venv in ~15 seconds (all 11 core + 7 dev deps locked in `uv.lock`, 1461 lines).
- `uv run book-pipeline --version` prints `book-pipeline 0.1.0` and exits 0.
- `uv run book-pipeline version` (subcommand form) prints the same and exits 0.
- `uv run book-pipeline --help` lists `version` as a subcommand with description.
- `uv run python -m book_pipeline --version` also works (script-independent invocation path).
- `uv run pytest tests/test_cli_skeleton.py -x` — 4 passed in 0.08s.

## The CLI Dispatcher Contract (for plans 03/04/05)

**Extension procedure** (documented in `src/book_pipeline/cli/main.py` module docstring):

1. Create `src/book_pipeline/cli/<name>.py`.
2. Inside that module, define an `_add_parser(subparsers: argparse._SubParsersAction) -> None` that:
   - Calls `subparsers.add_parser("<name>", help="...")`
   - Calls `p.set_defaults(_handler=<fn>)` where `<fn>(args: argparse.Namespace) -> int`
3. Module-level, call `register_subcommand("<name>", _add_parser)`.
4. Append `"book_pipeline.cli.<name>"` to the `SUBCOMMAND_IMPORTS` list in `main.py`.

**Why the tolerate-ImportError pattern:** Plan 01-01 (this plan) is the *only* plan that edits `main.py`. Plans 03/04/05 ship their subcommand modules; `main.py` already lists them in `SUBCOMMAND_IMPORTS`. If a plan is not yet executed, `importlib.import_module` raises `ImportError` and `_load_subcommands` silently skips. This is a deliberate zero-coupling design so Wave 2/3 plans don't need to coordinate edits with each other on a shared file.

The canonical example is `src/book_pipeline/cli/version.py` — 19 lines, complete reference implementation of the pattern.

## Verification Evidence

All acceptance criteria from the plan:

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `pyproject.toml` has `book-pipeline = "book_pipeline.cli.main:main"` | PASS | grep confirmed |
| `pyproject.toml` has `requires-python = ">=3.12,<3.13"` | PASS | grep confirmed |
| All 11 core deps listed | PASS | grep count = 11 matches |
| All 7 dev deps listed | PASS | grep count = 7 matches |
| `.python-version` is `3.12` | PASS | exact match |
| `.env.example` has `ANTHROPIC_API_KEY=` | PASS | grep confirmed |
| `ruff.toml` has `target-version = "py312"` | PASS | grep confirmed |
| `mypy.ini` has `python_version = 3.12` and `strict = True` | PASS | both present |
| `.pre-commit-config.yaml` has ruff hook + check-yaml | PASS | both present |
| `uv sync` succeeds | PASS | produced uv.lock (1461 lines) |
| `uv run book-pipeline --version` → `book-pipeline 0.1.0` | PASS | stdout confirmed |
| `uv run book-pipeline version` → `book-pipeline 0.1.0` | PASS | stdout confirmed |
| `uv run book-pipeline --help` contains `version` and `COMMAND` | PASS | both in output |
| `uv run python -m book_pipeline --version` | PASS | exit 0, version printed |
| `pytest tests/test_cli_skeleton.py -x` all 4 pass | PASS | 4 passed in 0.08s |
| `main.py` contains `def register_subcommand` | PASS | grep confirmed |
| `main.py` contains `SUBCOMMAND_IMPORTS: list[str]` | PASS | grep confirmed |

## Deviations from Plan

### Environment Setup

**[Env] Installed uv at /home/admin/.local/bin/uv**
- **Found during:** Task 2 pre-run
- **Issue:** `uv` not present on host (`which uv` returned not-found)
- **Fix:** Ran `curl -LsSf https://astral.sh/uv/install.sh | sh` as the plan itself instructed in its optional fallback. Installed uv 0.11.7.
- **Files modified:** none in repo (binary installed in user's local bin)
- **Commit:** not applicable (no repo change)

### Worktree-location Note (for orchestrator awareness)

The worktree this executor was spawned into (`/home/admin/paul-thinkpiece-pipeline/.claude/worktrees/agent-a5c80416`) was a stale worktree pointing at the **wrong repository** (`paul-thinkpiece-pipeline` instead of `our-lady-book-pipeline`). All actual work was performed in `/home/admin/Source/our-lady-book-pipeline/` because:
- The plan file itself only exists there.
- The base commit `43d118b04e7…` mentioned in the worktree_branch_check only exists in `our-lady-book-pipeline` (confirmed: `git -C /home/admin/Source/our-lady-book-pipeline log` shows it as HEAD).
- The plan's `<verify>` blocks all hardcode `cd /home/admin/Source/our-lady-book-pipeline && ...`.
- The commits landed on `main` branch of the correct repo (`/home/admin/Source/our-lady-book-pipeline/`), not the stale worktree branch.

No auto-fixes applied beyond this; flagging for the orchestrator to decide if future worktree-creation logic needs to be corrected.

### Auto-fixed Issues

None. The plan was detailed and self-contained; no Rule 1/2/3 fixes were needed during execution.

## Authentication Gates

None encountered. (Expected for a scaffolding phase — no LLM calls, no secrets read at runtime.)

## Deferred Issues

None. All tests green on first run.

## Known Stubs

None. All created components are fully functional. `SUBCOMMAND_IMPORTS` lists modules that do not yet exist (`validate_config`, `openclaw_cmd`, `smoke_event`) — these are *placeholders for future plans* and are documented as such in the module docstring. The `ImportError` tolerance is the correct behavior, not a stub.

## Threat Flags

No new threat surface introduced beyond what Plan 01-01's own `<threat_model>` declared. Specifically:

- T-01-01 (dep tampering) — mitigated: `uv.lock` committed; major versions pinned for anthropic.
- T-01-02 (secrets disclosure) — mitigated: `.env` already gitignored; `.env.example` contains no real values.
- T-01-03 (pre-commit EoP) — accepted: only ruff + hygiene hooks configured.

## Self-Check: PASSED

Verified post-write:
- FOUND: pyproject.toml, .python-version, ruff.toml, mypy.ini, .pre-commit-config.yaml, .env.example
- FOUND: src/book_pipeline/__init__.py, src/book_pipeline/__main__.py, src/book_pipeline/cli/__init__.py, src/book_pipeline/cli/main.py, src/book_pipeline/cli/version.py
- FOUND: tests/__init__.py, tests/test_cli_skeleton.py, uv.lock
- FOUND: commit 83943dc, commit eaa0b89
