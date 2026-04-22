---
phase: 01-foundation-observability-baseline
fixed_at: 2026-04-21T00:00:00Z
review_path: .planning/phases/01-foundation-observability-baseline/01-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 1: Code Review Fix Report

**Fixed at:** 2026-04-21
**Source review:** .planning/phases/01-foundation-observability-baseline/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (WR-01, WR-02, WR-03; IN-01 deliberately excluded per task instructions)
- Fixed: 3
- Skipped: 0

All three warning fixes were applied cleanly. After each fix, `pytest` (111 tests) and
`scripts/lint_imports.sh` (import-linter + ruff + mypy) passed with no regressions.

---

## Fixed Issues

### WR-01: Raw prompt text written into `Event.extra`

**Files modified:** `src/book_pipeline/cli/smoke_event.py`
**Commit:** `efa5f5e`
**Applied fix:** Removed `"prompt": SMOKE_PROMPT` from `_build_smoke_event()` extra dict (line 113)
and `"prompt": DRAFTER_SMOKE_PROMPT` from `_build_drafter_smoke_event()` extra dict (line 165).
Both builders now contain only structured metadata keys (`"purpose"`, `"ft_run_id"`,
`"base_model"`). The prompt constants are still used for `hash_text()` to populate
`prompt_hash` — only the raw text serialisation into the event log was removed.
The `SMOKE_PROMPT` and `DRAFTER_SMOKE_PROMPT` module-level constants were left in place as they
are the canonical inputs to `hash_text()`; removing them would change the hash values and break
the round-trip assertions.

---

### WR-02: Import-linter boundary does not cover `config`, `cli`, or `openclaw` packages

**Files modified:** `pyproject.toml`, `tests/test_import_contracts.py`
**Commit:** `4dd62d2`
**Applied fix:** Added `book_pipeline.config`, `book_pipeline.cli`, and `book_pipeline.openclaw`
to the `source_modules` list of the first import-linter contract in `pyproject.toml` (the
"Kernel packages MUST NOT import from book_specifics" contract). Also extended the
`kernel_dirs` list in `test_kernel_does_not_import_book_specifics()` in
`tests/test_import_contracts.py` with the same three packages so the grep fallback covers
them too. `lint-imports` was re-run and confirmed both contracts KEPT with the expanded scope
(53 files, 96 dependencies analyzed).

---

### WR-03: `_HANDLERS_BY_PATH` accumulates open `FileHandler` objects across tests

**Files modified:** `tests/conftest.py` (new file)
**Commit:** `d1a1b6c`
**Applied fix:** Created `tests/conftest.py` with an `autouse` fixture
`_clear_handler_cache` that, after every test, acquires `_HANDLER_LOCK`, calls
`handler.close()` on every cached `FileHandler`, and clears `_HANDLERS_BY_PATH`.
This ensures pytest's `tmp_path` directories are not blocked by open file descriptors
and that the idempotency test cannot pass spuriously due to cross-test handler reuse.
A blank line was added between the stdlib `import pytest` and the first-party
`import book_pipeline...` to satisfy ruff's I001 import-sort rule.

---

## Deferred / Info Findings

### IN-01: `lint-imports` hook fires only at `pre-push`, not `pre-commit`

**File:** `.pre-commit-config.yaml:23`
**Reason:** Deliberate design — deferred per task instructions. The `stages: [pre-push]`
configuration is intentional. The proof test in `test_lint_rule_catches_violation.py`
compensates by catching violations in CI and on every `git push`. No change made.

---

_Fixed: 2026-04-21_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
