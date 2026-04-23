---
phase: 03-mode-a-drafter-scene-critic-basic-regen
plan: 09-GAP
type: execute-summary
subsystem: critic, regenerator, llm-client
status: complete
wave: gap-closure
tags: [llm-backend, claude-code-cli, cost-reduction, subscription, ADR-004-kernel]
dependency-graph:
  requires: [03-05-SUMMARY, 03-06-SUMMARY, 03-07-SUMMARY]
  provides: [backend-swappable-critic, backend-swappable-regenerator, claude-code-cli-backend]
  affects: [03-08-SUMMARY]  # operator runbook no longer requires ANTHROPIC_API_KEY
tech-stack:
  added:
    - "claude CLI (Claude Code) >= 2.0 via subprocess"
    - "httpx (already transitively present) for synthetic anthropic transport pair"
  patterns:
    - "factory-based backend selection via pydantic-settings config block"
    - "error-class parity — shim raises anthropic.APIConnectionError / APIStatusError so existing tenacity retry decorators work unchanged"
    - "duck-typed .messages surface; no Protocol refactor on downstream consumers"
key-files:
  created:
    - src/book_pipeline/llm_clients/__init__.py
    - src/book_pipeline/llm_clients/claude_code.py
    - src/book_pipeline/llm_clients/factory.py
    - tests/llm_clients/__init__.py
    - tests/llm_clients/test_claude_code_client.py
    - .planning/phases/03-mode-a-drafter-scene-critic-basic-regen/03-09-GAP-SUMMARY.md
  modified:
    - config/mode_thresholds.yaml  # +critic_backend: block
    - src/book_pipeline/config/mode_thresholds.py  # +CriticBackendConfig model
    - src/book_pipeline/cli/draft.py  # composition root uses build_llm_client()
    - pyproject.toml  # +book_pipeline.llm_clients in import-linter kernel list
    - scripts/lint_imports.sh  # +llm_clients in mypy scope
decisions:
  - "Default backend = claude_code_cli — operator is on Claude Max subscription; per-call billing would be pure waste"
  - "Shim raises anthropic.APIConnectionError / APIStatusError (not a new class hierarchy) so existing tenacity.retry_if_exception_type in SceneLocalRegenerator keeps working unchanged. Retry semantics identical across backends"
  - "No Protocol refactor on SceneCritic / SceneLocalRegenerator constructors — they already accept anthropic_client: Any. The duck-typed seam was already in place; the fix is surgical"
  - "Do NOT set CLAUDE_CODE_SIMPLE=1 on subprocess env (plan specified it; empirical verification showed it disables OAuth keychain reads and breaks the entire feature)"
  - "Drop-in anthropic SDK import at module top-level (not lazy) — anthropic is already a core dep in pyproject.toml and lazy-loading forced type: ignore[misc] everywhere it leaked"
metrics:
  duration_min: 45
  tests_added: 32
  tests_passing: 432  # 400 prior baseline + 31 unit + 1 slow integration
  loc_added: ~700  # 440 src + 260 test
completed_at: 2026-04-22
---

# Phase 3 Gap-Closure Summary — `claude -p` CLI Backend for Critic + Regenerator

## One-liner

Added `claude -p --json-schema` subprocess backend as the default for `SceneCritic` and `SceneLocalRegenerator`, replacing per-call Anthropic SDK billing with subscription-covered OAuth inference; Anthropic SDK remains as a config-toggled fallback. No changes to Critic/Regenerator internals — the switch happens at the CLI composition root via a `build_llm_client(config)` factory.

## Problem statement

Operator directive (2026-04-21): *"I'm not paying for extra API calls when we have Claude at home."*

Phase 3 shipped `SceneCritic` + `SceneLocalRegenerator` wired against `anthropic.Anthropic()` directly. That path bills every Opus 4.7 call (~$0.29 per scene critic per verified CLI telemetry) against `ANTHROPIC_API_KEY` even though the operator has a Claude Max subscription that covers flat-rate inference via the `claude` CLI.

## Solution

Backend-swappable critic: a tiny shim (`ClaudeCodeMessagesClient`) that duck-types the minimum `anthropic.Anthropic().messages` surface SceneCritic (`.parse`) and SceneLocalRegenerator (`.create`) actually consume, driven by `subprocess.run` against `claude -p --output-format json`.

Selection via `config/mode_thresholds.yaml`:

```yaml
critic_backend:
  kind: claude_code_cli       # default — OAuth, subscription-covered
  model: claude-opus-4-7
  timeout_s: 180
  max_budget_usd_per_scene: 1.0
```

Switching to the legacy SDK path is `kind: anthropic_sdk` — no code change needed.

## Architecture

```
ModeThresholdsConfig.critic_backend: CriticBackendConfig
                    │
                    ▼
cli/draft.py → build_llm_client(critic_backend_cfg)
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
 ClaudeCodeMessagesClient   anthropic.Anthropic()
   (subprocess shim)         (native SDK)
         │                     │
         └──────────┬──────────┘
                    ▼
         SceneCritic / SceneLocalRegenerator
         (anthropic_client: Any — unchanged)
```

## Files

### New: `src/book_pipeline/llm_clients/claude_code.py` (~460 LOC)

- `ClaudeCodeMessagesClient` — top-level shim exposing `.messages.parse()` / `.messages.create()`.
- `ParseResponse` / `CreateResponse` — dataclasses mimicking `anthropic.types.ParsedMessage` / `anthropic.types.Message`. Carry `.parsed_output`, `.usage` (with `input_tokens`/`output_tokens`/`cache_read_input_tokens`), `.model`, and a `model_dump()` method for the CRIT-04 audit record.
- `_invoke_claude_cli()` — the subprocess dispatcher. Builds argv, runs with hard timeout, translates failure modes to the right exception class.
- `ClaudeCodeCliError` — our own non-retryable error type (malformed JSON, schema violation, missing binary).
- Retry-eligible failures (timeout, transient stderr signatures like `502`/`529`/`connection`, `is_error=true` payloads) surface as `anthropic.APIConnectionError` / `APIStatusError` — so `SceneLocalRegenerator`'s existing `tenacity.retry_if_exception_type((APIConnectionError, APIStatusError))` decorator keeps working unchanged.

### New: `src/book_pipeline/llm_clients/factory.py` (~75 LOC)

- `build_llm_client(backend_config) -> Any` — dispatches on `.kind`.
- `LLMMessagesClient` Protocol — documents the `.messages.parse` / `.messages.create` surface (for mypy + reviewer reference; not enforced via `@runtime_checkable`, since SceneCritic's existing test fakes don't inherit from it).

### New: `src/book_pipeline/llm_clients/__init__.py`

Re-exports `ClaudeCodeMessagesClient`, `ClaudeCodeCliError`, `build_llm_client`, `LLMMessagesClient`, `CriticBackendKind`.

### Modified: `src/book_pipeline/config/mode_thresholds.py`

Added `CriticBackendConfig` Pydantic model + `critic_backend: CriticBackendConfig = Field(default_factory=CriticBackendConfig)` on `ModeThresholdsConfig`. Legacy mode_thresholds.yaml files without a `critic_backend:` block still validate (and get the `claude_code_cli` default).

### Modified: `config/mode_thresholds.yaml`

Appended `critic_backend:` block with `kind: claude_code_cli` default.

### Modified: `src/book_pipeline/cli/draft.py`

The composition root now reads `mode_thresholds_cfg.critic_backend` and calls `build_llm_client()` to obtain the messages-client. The `model_id=` kwarg on `SceneCritic` and `SceneLocalRegenerator` is now wired from `critic_backend_cfg.model` instead of being hardcoded to the Anthropic SDK default. The `from anthropic import Anthropic` import moved out of the composition root — `build_llm_client` owns it.

### Modified: `pyproject.toml`

Added `book_pipeline.llm_clients` to the `Kernel packages MUST NOT import from book_specifics` import-linter source_modules list. The new package lives in the kernel and is protected by the standard ADR-004 boundary.

### Modified: `scripts/lint_imports.sh`

Added `src/book_pipeline/llm_clients` to the mypy scope.

### New: `tests/llm_clients/test_claude_code_client.py` (32 tests, 1 slow)

| # | Test | What it verifies |
| --- | --- | --- |
| 1 | `test_parse_builds_expected_argv_with_schema_and_system` | parse() builds `claude -p --output-format json --json-schema <schema> --model ... --append-system-prompt <text> <user_prompt>` — all flags in order, Pydantic schema dumped, user prompt is final positional, timeout honored, usage fields flow through to ParseResponse. |
| 2 | `test_parse_flattens_multi_block_system` | Multiple system blocks joined with double-newlines. |
| 3 | `test_parse_omits_system_flag_when_none` | No system=None → no `--append-system-prompt` in argv. |
| 4 | `test_create_builds_argv_without_schema_and_returns_content_text` | create() omits `--json-schema`; `.content[0].text` carries CLI's `result` field. |
| 5 | `test_parse_raises_api_connection_error_on_timeout` | `subprocess.TimeoutExpired` → `APIConnectionError` (retry-eligible). |
| 6 | `test_parse_raises_claude_code_cli_error_when_binary_missing` | `FileNotFoundError` → `ClaudeCodeCliError` (non-retry). |
| 7 | `test_parse_raises_api_connection_error_on_transient_nonzero_exit` | Non-zero exit with "502/connection" stderr → `APIConnectionError`. |
| 8 | `test_parse_raises_claude_code_cli_error_on_terminal_nonzero_exit` | Non-zero exit with non-transient stderr → `ClaudeCodeCliError`. |
| 9 | `test_parse_raises_api_status_error_on_is_error_true` | `is_error=true` payload → `APIStatusError` (synthetic httpx.Response attached). |
| 10 | `test_parse_raises_on_malformed_json_stdout` | Non-JSON stdout → `ClaudeCodeCliError`. |
| 11 | `test_parse_raises_on_structured_output_validation_failure` | `structured_output` violating Pydantic constraints → `ClaudeCodeCliError`. |
| 12 | `test_parse_raises_when_structured_output_missing` | Missing `structured_output` key → `ClaudeCodeCliError`. |
| 13 | `test_create_raises_on_missing_result_field` | Missing `result` string → `ClaudeCodeCliError`. |
| 14 | `test_parse_does_not_set_claude_code_simple_env` | Regression guard against plan's original (incorrect) spec. |
| 15 | `test_parse_does_not_use_shell` | argv-as-list, no `shell=True`; dangerous prompt content passed as literal final arg (shell-injection structurally impossible). |
| 16-23 | `_flatten_system` / `_flatten_messages` / `_usage_from_payload` / `_model_from_payload` helper unit tests | String passthrough, empty-text skip, role marking, block-content lists, missing-field tolerance, bracket-decoration stripping. |
| 24-27 | `test_build_llm_client_*` factory tests | Default = ClaudeCodeMessagesClient; `kind=anthropic_sdk` → Anthropic SDK instance; unknown kind → ValueError; timeout from config honored. |
| 28-29 | `test_scene_critic_drives_claude_code_client_end_to_end` / `test_scene_local_regenerator_drives_claude_code_client_end_to_end` | **Composition check — the whole point of the feature.** `SceneCritic` + `SceneLocalRegenerator` both drive the new shim correctly end-to-end with mocked subprocess, write audit files, emit events, return `DraftResponse` / `CriticResponse` as expected. |
| 30 (slow) | `test_real_claude_cli_roundtrip_with_schema` | **Actual `claude -p` CLI invocation** (OAuth). Verifies that the real CLI hasn't drifted from the schema we depend on — `structured_output` present, `is_error=false`, non-zero output token count. Skipped unless `pytest -m slow`. **Passed against the real CLI on 2026-04-22.** |

## Verification

### Baseline tests — no regressions

```
$ uv run pytest -q -m "not slow"
431 passed, 4 deselected, 216 warnings in 52s
```

(400 pre-existing + 31 new unit. Slow CLI test passes separately: 32/32 in that file.)

### Lint-imports

```
$ bash scripts/lint_imports.sh
[1/3] import-linter...
  Kernel packages MUST NOT import from book_specifics KEPT
  Interfaces MUST NOT import from concrete kernel implementations KEPT
  Contracts: 2 kept, 0 broken.
[2/3] ruff check... All checks passed!
[3/3] mypy (scoped to kernel + book_specifics packages)...
  Success: no issues found in 101 source files
```

### Real CLI smoke (slow)

```
$ uv run pytest -q tests/llm_clients/ -m slow
1 passed in 15s
```

Verified against `claude -p` at `/home/admin/.local/bin/claude`, OAuth session, no `ANTHROPIC_API_KEY` required.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Removed `CLAUDE_CODE_SIMPLE=1` env var from subprocess invocation**

- **Found during:** Real-CLI integration test (slow test)
- **Issue:** Plan spec said *"Set `env={**os.environ, 'CLAUDE_CODE_SIMPLE': '1'}` to skip CLAUDE.md auto-discovery (we provide our own system prompt)."* Empirical verification: setting that env var disables OAuth keychain reads in the same way `--bare` does, forcing the shim back onto `ANTHROPIC_API_KEY` billing. The real CLI returned `{"is_error": true, "result": "Not logged in · Please run /login"}`.
- **Fix:** `_hermetic_env()` now returns `dict(os.environ)` unmodified with a docstring documenting why. Test `test_parse_does_not_set_claude_code_simple_env` is a regression guard.
- **Files modified:** `src/book_pipeline/llm_clients/claude_code.py`, `tests/llm_clients/test_claude_code_client.py`
- **Impact:** This bug was in the plan spec itself, not in existing code. Had to surface it via live CLI verification before merging.

**2. [Rule 3 — Blocking] anthropic SDK exceptions require real httpx.Response**

- **Found during:** Unit test `test_parse_raises_api_status_error_on_is_error_true`
- **Issue:** `anthropic.APIStatusError.__init__` dereferences `response.request` — passing `response=None` raises `AttributeError`.
- **Fix:** Added `_synthetic_anthropic_transport()` helper that builds a minimal `httpx.Request`/`httpx.Response` pair so our shim raises the exact exception classes SceneLocalRegenerator's tenacity retry is watching for.
- **Files modified:** `src/book_pipeline/llm_clients/claude_code.py`

**3. [Rule 3 — Blocking] mypy `call-arg` errors on anthropic exception construction**

- **Found during:** `bash scripts/lint_imports.sh` mypy step
- **Issue:** Lazy-loading the anthropic exception classes via `_anthropic_exceptions()` stripped their concrete signatures, so mypy couldn't verify the `message=`/`request=`/`response=` kwargs.
- **Fix:** Imported `APIConnectionError`/`APIStatusError` at module top-level (anthropic is already a core dep; lazy-load was premature optimization). Removed `type: ignore[misc]` comments that were no longer needed.
- **Files modified:** `src/book_pipeline/llm_clients/claude_code.py`

### Scope additions beyond the plan

**4. [Rule 2 — Critical] Added `book_pipeline.llm_clients` to import-linter kernel list**

- **Why:** The new package sits in the kernel and must be guarded by the ADR-004 "no kernel → book_specifics" boundary. Without this line in `pyproject.toml`, a future plan could accidentally import from `book_specifics` and only detect the regression via whole-project audit.
- **Files modified:** `pyproject.toml`, `scripts/lint_imports.sh` (+mypy scope)

## Authentication gates

None. The feature is designed to *remove* an auth gate (operator no longer needs `ANTHROPIC_API_KEY` for the default backend — `claude` CLI's OAuth handles credentials automatically).

## Impact on Plan 03-08 (deferred smoke)

Plan 03-08's operator runbook listed `ANTHROPIC_API_KEY` as a hard blocker. With the new default backend, that blocker goes away — as long as the operator has `claude auth` configured (which they do — evidenced by the slow integration test passing). The other blockers from 03-08 (vLLM bootstrap, GPU preflight) are unchanged.

## Impact on test suite

- **Phase 3 tests still mock the SDK-style fake directly** (tests/critic/fixtures.FakeAnthropicClient, test_scene_local._FakeAnthropicClient). Those fakes duck-type the same surface and continue to work unchanged — no refactor needed. The new backend is a production-time concern, not a test seam.
- **Two end-to-end tests** (`test_scene_critic_drives_claude_code_client_end_to_end`, `test_scene_local_regenerator_drives_claude_code_client_end_to_end`) compose the new shim through the real SceneCritic + SceneLocalRegenerator with `subprocess.run` mocked — these prove the composition works end-to-end without actually shelling out.
- **One slow integration test** (`test_real_claude_cli_roundtrip_with_schema`) actually hits `claude -p`. Skipped by default; run via `pytest -m slow`. This is our canary for CLI-schema drift.

## Cost model

Per the `total_cost_usd` field returned by `claude -p` on an actual scene-sized request (~7 input tokens + 41K cached prompt + 125 output tokens): $0.28 of telemetry-internal accounting, $0.00 of real billing under a Max plan. The SDK backend would charge $0.28 against `ANTHROPIC_API_KEY`.

**Zero pay-per-call cost to operate the full Phase 3 scene loop with the default backend.**

## Known Stubs

None.

## Threat Flags

None. The new code path uses `subprocess.run` with argv-as-list (structurally immune to shell injection) and inherits OAuth credentials from the operator's already-authenticated CLI — no new network trust boundary, no new credential storage, no new schema surface.

## Commit plan

This gap-closure lands as two focused commits under the `feat(03.1):` prefix:

1. `feat(03.1): add claude-code CLI backend for critic + regenerator` — new `llm_clients/` package + config surface + tests.
2. `feat(03.1): wire composition root to claude_code_cli backend by default` — `cli/draft.py` + `mode_thresholds.yaml` + `pyproject.toml` + `scripts/lint_imports.sh`.

## Self-Check: PASSED

- [x] `src/book_pipeline/llm_clients/claude_code.py` — FOUND
- [x] `src/book_pipeline/llm_clients/factory.py` — FOUND
- [x] `src/book_pipeline/llm_clients/__init__.py` — FOUND
- [x] `tests/llm_clients/test_claude_code_client.py` — FOUND
- [x] `config/mode_thresholds.yaml` `critic_backend:` block — PRESENT
- [x] `CriticBackendConfig` Pydantic model on `ModeThresholdsConfig` — PRESENT (verified via `python -c` instantiation)
- [x] `cli/draft.py` uses `build_llm_client(critic_backend_cfg)` — PRESENT
- [x] `bash scripts/lint_imports.sh` — GREEN (import-linter + ruff + mypy)
- [x] `pytest -q -m "not slow"` — 431 PASSED, 4 DESELECTED
- [x] `pytest -q tests/llm_clients/` — 32 PASSED (31 unit + 1 slow real-CLI integration)
- [x] Real `claude -p` CLI invocation verified — OAuth works, no ANTHROPIC_API_KEY needed
