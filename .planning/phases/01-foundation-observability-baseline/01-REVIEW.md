---
phase: 01-foundation-observability-baseline
reviewed: 2026-04-21T00:00:00Z
depth: standard
files_reviewed: 42
files_reviewed_list:
  - pyproject.toml
  - ruff.toml
  - mypy.ini
  - .pre-commit-config.yaml
  - openclaw.json
  - scripts/lint_imports.sh
  - config/rubric.yaml
  - config/rag_retrievers.yaml
  - config/mode_thresholds.yaml
  - config/voice_pin.yaml
  - src/book_pipeline/cli/main.py
  - src/book_pipeline/cli/version.py
  - src/book_pipeline/cli/validate_config.py
  - src/book_pipeline/cli/openclaw_cmd.py
  - src/book_pipeline/cli/smoke_event.py
  - src/book_pipeline/interfaces/__init__.py
  - src/book_pipeline/interfaces/types.py
  - src/book_pipeline/interfaces/event_logger.py
  - src/book_pipeline/interfaces/drafter.py
  - src/book_pipeline/interfaces/retriever.py
  - src/book_pipeline/interfaces/scene_state_machine.py
  - src/book_pipeline/stubs/__init__.py
  - src/book_pipeline/stubs/event_logger.py
  - src/book_pipeline/stubs/drafter.py
  - src/book_pipeline/stubs/retriever.py
  - src/book_pipeline/stubs/scene_state_machine.py
  - src/book_pipeline/config/loader.py
  - src/book_pipeline/config/rubric.py
  - src/book_pipeline/config/rag_retrievers.py
  - src/book_pipeline/config/mode_thresholds.py
  - src/book_pipeline/config/voice_pin.py
  - src/book_pipeline/config/secrets.py
  - src/book_pipeline/config/sources.py
  - src/book_pipeline/openclaw/bootstrap.py
  - src/book_pipeline/observability/event_logger.py
  - src/book_pipeline/observability/hashing.py
  - src/book_pipeline/book_specifics/corpus_paths.py
  - src/book_pipeline/book_specifics/nahuatl_entities.py
  - tests/test_event_logger.py
  - tests/test_import_contracts.py
  - tests/test_lint_rule_catches_violation.py
  - tests/test_interfaces.py
  - tests/test_config.py
  - tests/test_types.py
  - tests/test_smoke_event_cli.py
  - tests/test_openclaw.py
  - tests/test_validate_config_cli.py
  - tests/test_cli_skeleton.py
findings:
  critical: 0
  warning: 3
  info: 1
  total: 4
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-04-21
**Depth:** standard
**Files Reviewed:** 42 (all Phase 1 source files listed above; interfaces cross-checked as a group)
**Status:** issues_found

## Summary

Phase 1 is solid infrastructure. The core correctness properties all hold: `prompt_hash` is a
hash (not content), `SecretStr` wraps every secret value, the five-axis rubric validator rejects
wrong axis names, fsync fires on every emit, handler idempotency is correctly implemented and
tested, and the kernel->book_specifics boundary is clean in the committed tree.

Three warnings are raised. None are blockers to merging Phase 1, but two of them (WR-01 and
WR-02) will cause real problems in Phase 2+ if not addressed before drafter/critic events start
carrying live prompts.

---

## Warnings

### WR-01: Raw prompt text written into `Event.extra` — sets a dangerous Phase 2+ precedent

**File:** `src/book_pipeline/cli/smoke_event.py:113,165`

**Issue:** Both `_build_smoke_event()` and `_build_drafter_smoke_event()` write the full,
verbatim prompt string into `Event.extra["prompt"]`. The smoke prompts themselves are benign
constants, but this pattern is now in the codebase as a copy-target. The event logger's security
note (`event_logger.py:15-22`) explicitly prohibits putting prompt content in `extra` or
`caller_context`, because every Event lands in `runs/events.jsonl` on disk. Phase 2+ drafter and
critic callers that copy this shape will serialize multi-kilobyte raw prompts — potentially
containing injected user text or corpus excerpts — into the permanent event log.

The field was presumably added to make the smoke JSONL line human-readable for Phase 1
inspection. That is a valid goal, but it should be achieved differently.

**Fix:** Remove `"prompt"` from `extra` in both smoke builders, or rename it to
`"prompt_preview"` capped to a fixed length (e.g., 80 chars) so it is visually clear this is a
truncated label, not a round-trippable value. The full prompt round-trip is already verified via
`prompt_hash`; the raw text adds no test coverage value.

```python
# _build_smoke_event: replace line 113
extra={"purpose": "phase1_exit_criterion"},

# _build_drafter_smoke_event: replace lines 163-168
extra={
    "purpose": "phase1_voice_pin_sha_wiring",
    "ft_run_id": ft_run_id,
    "base_model": base_model,
},
```

Additionally, consider adding a one-line assertion to `test_event_logger.py` or
`test_smoke_event_cli.py` that `extra` does not contain a `"prompt"` key after Phase 2+
callers land — a lint check is stronger than a comment.

---

### WR-02: Import-linter boundary does not cover `config`, `cli`, or `openclaw` packages

**File:** `pyproject.toml:63-84`

**Issue:** The two import-linter contracts in `pyproject.toml` list only
`book_pipeline.interfaces`, `book_pipeline.observability`, and `book_pipeline.stubs` as
`source_modules`. The `book_pipeline.config`, `book_pipeline.cli`, and `book_pipeline.openclaw`
packages are not protected. A Phase 2+ developer who imports `book_pipeline.book_specifics` from
inside `config/` or `cli/` will not be caught by `lint-imports`, and the test in
`test_import_contracts.py:test_kernel_does_not_import_book_specifics` (the grep fallback) also
only scans `interfaces`, `observability`, and `stubs`.

This is a coverage gap, not a current violation — none of those packages import `book_specifics`
today. But it is the gap most likely to be violated accidentally in Phase 2 when the config
loader is extended to reference corpus paths.

**Fix:** Add `book_pipeline.config`, `book_pipeline.cli`, and `book_pipeline.openclaw` to the
`source_modules` list of the first contract in `pyproject.toml`. Also extend the grep fallback
in `test_import_contracts.py:test_kernel_does_not_import_book_specifics`:

```python
# pyproject.toml — first contract source_modules becomes:
source_modules = [
    "book_pipeline.interfaces",
    "book_pipeline.observability",
    "book_pipeline.stubs",
    "book_pipeline.config",
    "book_pipeline.cli",
    "book_pipeline.openclaw",
]
```

Note: Per the comment in `pyproject.toml:50-60`, import-linter 2.x requires these modules to
exist at lint time. All three exist today, so adding them is safe.

---

### WR-03: `_HANDLERS_BY_PATH` accumulates open `FileHandler` objects for every `tmp_path` used in tests

**File:** `src/book_pipeline/observability/event_logger.py:41,83`

**Issue:** The module-level `_HANDLERS_BY_PATH` dict caches a `logging.FileHandler` (with an
open file descriptor) for every resolved path ever passed to `_get_or_create_handler`. Tests use
pytest's `tmp_path` fixture, which gives each test a unique directory. With 13 test functions in
`test_event_logger.py` plus additional invocations in `test_smoke_event_cli.py`, the pytest
process opens and retains O(N) file descriptors pointing at tmp directories that pytest will
later try to delete. On Linux this generally succeeds silently (files can be unlinked while open),
but if the test suite grows significantly (Phase 2+ adds test_rag, test_drafter, etc.) this
becomes a slow file-descriptor leak that can exhaust the process limit in CI.

There is no `__del__`, `close()`, or context-manager cleanup path on `JsonlEventLogger` or on
`_HANDLERS_BY_PATH` entries.

**Fix:** Add a module-level cleanup function used by a pytest `autouse` fixture in
`tests/conftest.py`, OR document this as a known intentional trade-off (the cache is designed
for a long-running production process where there is exactly one log path). A conftest teardown
is the minimal fix:

```python
# tests/conftest.py (create this file)
import pytest
import book_pipeline.observability.event_logger as _el

@pytest.fixture(autouse=True)
def _clear_handler_cache():
    yield
    with _el._HANDLER_LOCK:
        for handler in _el._HANDLERS_BY_PATH.values():
            handler.close()
        _el._HANDLERS_BY_PATH.clear()
```

This also ensures `test_handler_idempotent` cannot accidentally pass because two calls to
`JsonlEventLogger(path=p)` in different test functions happen to reuse a leftover cached handler
from a prior test's path collision (unlikely with `tmp_path`, but not impossible if a test
constructs a path manually).

---

## Info

### IN-01: `lint-imports` hook fires only at `pre-push`, not `pre-commit` — boundary violations can be committed locally

**File:** `.pre-commit-config.yaml:23`

**Issue:** The import-linter hook is configured `stages: [pre-push]`. Ruff and the standard
pre-commit hooks run at `pre-commit` stage and will catch most issues before a local commit, but
a kernel-to-book_specifics import violation will pass through `git commit` without any hook
firing. It is caught only at `git push` (or in CI / `pytest`).

This is a deliberate design choice (noted implicitly by using `stages: [pre-push]`) and not a
defect — the proof test in `test_lint_rule_catches_violation.py` means any push with a violation
will fail CI. It is listed here so the team is aware the pre-commit stage is unprotected, which
matters if someone works offline or uses `--no-push` workflows.

No change required. The test coverage compensates.

---

_Reviewed: 2026-04-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
