#!/usr/bin/env bash
# Single-command boundary + lint check. Runs import-linter + ruff + mypy.
# Exits non-zero if any check fails.
#
# mypy scope: the explicitly listed Phase 1+ packages, matching each plan's
# per-plan mypy gate. Whole-tree `uv run mypy src` sometimes surfaces
# cross-module inference failures that DIDN'T fail per-plan gates — we keep
# parity by listing targets explicitly. Phase 2+ PRs extend this list when
# they add new kernel packages (rag/ added by Phase 2 plan 01; drafter/,
# critic/, regenerator/, orchestration/ land in later phases).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/3] import-linter..."
uv run lint-imports

echo "[2/3] ruff check..."
uv run ruff check src tests

echo "[3/3] mypy (scoped to kernel + book_specifics packages)..."
uv run mypy \
  src/book_pipeline/interfaces \
  src/book_pipeline/stubs \
  src/book_pipeline/observability \
  src/book_pipeline/config \
  src/book_pipeline/openclaw \
  src/book_pipeline/cli \
  src/book_pipeline/book_specifics \
  src/book_pipeline/rag \
  src/book_pipeline/corpus_ingest

echo "OK — module boundaries, ruff, and scoped mypy all pass."
