---
phase: 01-foundation-observability-baseline
plan: 05
subsystem: jsonl-event-logger-and-smoke-cli
tags: [observability, event-logger, jsonl, python-json-logger, xxhash, obs-01, foundation, phase-exit-criterion]
requirements_completed: [OBS-01]
dependency_graph:
  requires:
    - "01-01 (book_pipeline package + uv venv + CLI register_subcommand + SUBCOMMAND_IMPORTS pre-declared `book_pipeline.cli.smoke_event`)"
    - "01-02 (Event Pydantic model + EventLogger Protocol — consumed verbatim)"
    - "01-03 (VoicePinConfig — consumed for drafter-role checkpoint_sha)"
  provides:
    - "JsonlEventLogger concrete impl of EventLogger Protocol — importable from book_pipeline.observability"
    - "xxhash-based hash_text + event_id helpers — usable by every LLM caller in Phases 2+"
    - "`book-pipeline smoke-event` CLI (smoke_test + drafter roles) — Phase 1 exit-criterion command"
    - "Handler cache keyed by resolved path: multiple JsonlEventLogger instances share ONE FileHandler (no line duplication)"
    - "fsync-on-emit durability guarantee (ADR-003 append-only truth)"
    - "runs/.gitkeep — tracks runs/ in git; events.jsonl itself stays gitignored"
  affects:
    - "Phase 2+ every LLM caller constructs a JsonlEventLogger + emits one Event per call"
    - "Phase 3 DRAFT-01 replaces voice_pin.yaml's placeholder SHA with real hash + enforces bytes-on-disk verification (schema path wired here)"
    - "Phase 6 OBS-02 (archive + weekly checksum) reads from the same runs/events.jsonl this plan writes"
tech_stack:
  added:
    - "python-json-logger 3.x (already in pyproject via plan 01-01) — wired via the modern pythonjsonlogger.json.JsonFormatter import path"
    - "xxhash 3.x (already in pyproject via plan 01-01) — xxh64 dedup-grade hashing"
  patterns:
    - "Module-level handler cache (_HANDLERS_BY_PATH) keyed by Path.resolve() — two loggers pointing at the same file share one FileHandler; eliminates duplicate-line writes when code re-constructs a logger mid-process"
    - "FileHandler mode='a' + flush() + os.fsync() for line-atomic, crash-safe append — matches ADR-003's `runs/events.jsonl` contract"
    - "_EventJsonFormatter subclasses JsonFormatter + overrides add_fields to emit exactly Event.model_dump(mode='json') (no level/message clutter)"
    - "Lazy `from book_pipeline.config.voice_pin import VoicePinConfig` inside the drafter-role branch so --role smoke_test has zero config dependency"
    - "CLI registration via plan 01's API: module-level register_subcommand() at import time; SUBCOMMAND_IMPORTS already pre-declared this module name, so zero main.py edit"
    - "Distinct exit codes (10/11/12/13/14/15/16) so operators (and Phase 6 digest gate) can distinguish failure classes"
key_files:
  created:
    - "src/book_pipeline/observability/__init__.py"
    - "src/book_pipeline/observability/event_logger.py"
    - "src/book_pipeline/observability/hashing.py"
    - "src/book_pipeline/cli/smoke_event.py"
    - "tests/test_event_logger.py"
    - "tests/test_smoke_event_cli.py"
    - "runs/.gitkeep"
  modified: []
decisions:
  - "Used python-json-logger's NEW module path `pythonjsonlogger.json.JsonFormatter` rather than the legacy `pythonjsonlogger.jsonlogger` that the plan's <action> snippet wrote. Reason: python-json-logger 3.x emits a DeprecationWarning on every import from the legacy path. Since this module is the source-of-truth observability layer consumed by every Phase 2+ caller, shipping a known-deprecated import would mean every downstream test prints a DeprecationWarning for the rest of the project's life. The new path is identical in semantics; only the import changes."
  - "Ruff's SIM105 suggestion accepted: `contextlib.suppress(OSError)` around os.fsync(). The test patches `book_pipeline.observability.event_logger.os.fsync`, which still resolves through module-level `os` lookup even inside a `with contextlib.suppress` — so the fsync-called test still works, and the source is idiomatic."
  - "Module-level _HANDLERS_BY_PATH cache is PROCESS-LOCAL. Separate processes (e.g. multiple openclaw agent workspaces running the pipeline concurrently) each open their OWN FileHandler for the same runs/events.jsonl. That's intended: append-mode FileHandlers are safe for concurrent writers at the line granularity — each writer's payload is flushed + fsync'd as one syscall so lines don't interleave. Single-process re-construction is the only case that needs de-duplication, and the cache covers it."
  - "Kept ruff's UP017 fix (`datetime.UTC` alias replacing `timezone.utc`) — tests still pass, and matches the style the rest of the repo moved to in 01-02."
  - "`# type: ignore[call-arg]` added on `VoicePinConfig()` zero-arg call inside smoke_event.py — same pattern plan 03 established in `loader.py` for pydantic-settings instantiation that mypy --strict can't see through."
  - "Drafter-role path is LAZILY imported: --role smoke_test never imports VoicePinConfig. This means a broken voice_pin.yaml does not break the generic smoke path — operators can still verify OBS-01 is live even if config has a regression, and distinguish the failure via exit code 16 only when --role drafter is requested."
  - "NO main.py edit. Plan 01 pre-declared `book_pipeline.cli.smoke_event` in SUBCOMMAND_IMPORTS; creating the module with a module-level `register_subcommand(...)` call is sufficient. This matches plan 03's and plan 04's pattern — Wave 2/3 plans do not mutate plan 01's dispatcher."
metrics:
  duration_minutes: 5
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 7
  files_modified: 0
  tests_added: 18
  tests_passing: 104
commits:
  - hash: d4b0699
    type: test
    summary: RED — 13 failing tests for JsonlEventLogger + xxhash helpers
  - hash: 3cb4996
    type: feat
    summary: GREEN — JsonlEventLogger + xxhash helpers (OBS-01 concrete)
  - hash: 540520c
    type: feat
    summary: book-pipeline smoke-event CLI (smoke_test + drafter roles)
---

# Phase 1 Plan 5: JsonlEventLogger + Smoke-Event CLI Summary

**One-liner:** OBS-01 is LIVE — concrete `JsonlEventLogger` (stdlib logging + python-json-logger, append-only FileHandler with fsync-on-emit, idempotent per-path handler cache) satisfies the EventLogger Protocol from plan 02, xxhash helpers give every Phase 2+ caller a dedup-grade fingerprint, and the `book-pipeline smoke-event` CLI proves end-to-end round-trip for both the generic smoke path AND the phase-goal drafter-role path that wires `config/voice_pin.yaml` -> `Event.checkpoint_sha` -> `runs/events.jsonl` -> `Event.model_validate_json` round-trip.

## What Shipped

A working observability plane that Phase 1 exits on:

- **`book_pipeline.observability.JsonlEventLogger`** — one-line-per-emit append-only JSONL writer. Construction is idempotent per path (module-level handler cache keyed by `Path.resolve()`). `emit(event)` calls `handler.flush()` + `os.fsync()` before returning (durability over throughput per ADR-003 + ARCHITECTURE.md §10.2). Implements the `EventLogger` Protocol from plan 02 — `isinstance(JsonlEventLogger(), EventLogger)` is True.
- **`book_pipeline.observability.hash_text`** — xxh64 hex digest of a UTF-8 string; 16-char output, deterministic across processes. Meant for `prompt_hash`, `output_hash`, and anywhere a dedup-grade fingerprint is wanted. NOT for cryptographic integrity (STACK.md + ADR-003 explicit).
- **`book_pipeline.observability.event_id`** — xxh64 hex over `ts|role|caller|prompt_hash`. 16-char output. Callers use this to populate `Event.event_id`.
- **`book-pipeline smoke-event`** CLI — two role paths:
    - `--role smoke_test` (default): constructs a canonical `role='smoke_test'` Event with zero voice-pin dependency, emits via `JsonlEventLogger`, re-reads the last line, parses through `Event.model_validate_json`, asserts event_id round-trip. This IS Phase 1's OBS-01 exit criterion.
    - `--role drafter`: constructs a `role='drafter'`, `mode='A'` Event whose `checkpoint_sha` is read live from `VoicePinConfig().voice_pin.checkpoint_sha`, whose `model` is `f"{ft_run_id}@{base_model}"` assembled from the same config, emits through the same JSONL logger, re-reads, and asserts byte-exact SHA round-trip.
- **`runs/.gitkeep`** — `runs/` is now tracked; `runs/events.jsonl` stays gitignored per `.gitignore` pattern `runs/*.jsonl`.
- **18 new tests** (13 event_logger + 5 smoke-event CLI) all green; full suite 104 passing.
- **mypy --strict clean** on all 4 new/touched source files (`src/book_pipeline/observability` + `src/book_pipeline/cli/smoke_event.py`).
- **ruff + ruff-format clean** on every file this plan touched.

## Frozen Event Schema (v1.0) — Wiring Confirmed

The plan 02 Event model (18 fields, `schema_version="1.0"`) round-trips through JSONL with byte-exact fidelity. Plan 05 confirms via tests:

- `test_schema_version_frozen_1_0` — every emitted line has `schema_version == "1.0"`
- `test_all_required_fields_in_jsonl` — schema_version, event_id, ts_iso, role, model, prompt_hash, input_tokens, output_tokens, latency_ms, output_hash all present in every line
- `test_optional_fields_roundtrip_as_none` — mode, checkpoint_sha, rubric_version all round-trip as None when not set
- `test_checkpoint_sha_roundtrips_when_populated` — load-bearing for the drafter-role smoke; the phase-goal SHA fidelity

The Event schema is now de-facto frozen: it's written to disk, read back, and re-parsed on every emit. Any future field rename/removal would break `Event.model_validate_json`, which task 2's CLI checks every time it runs — the smoke CLI is effectively a schema-drift canary for the rest of the project.

## Usage Pattern for Phase 2+ Callers

```python
# Every Phase 2+ LLM caller follows this shape:
from book_pipeline.observability import JsonlEventLogger, event_id, hash_text
from book_pipeline.interfaces.types import Event
from datetime import UTC, datetime
import time

logger = JsonlEventLogger()  # writes runs/events.jsonl (default)

t0 = time.time()
# ... make the LLM call ...
latency_ms = int((time.time() - t0) * 1000)

ts = datetime.now(UTC).isoformat(timespec="milliseconds")
prompt_h = hash_text(prompt_text)
output_h = hash_text(response_text)

logger.emit(Event(
    event_id=event_id(ts, role, caller_fqname, prompt_h),
    ts_iso=ts,
    role="drafter",                      # or critic / regenerator / ...
    model="vllm://paul-v6-qwen3-32b",    # or claude-opus-4-7, ...
    prompt_hash=prompt_h,
    input_tokens=usage.input_tokens,
    cached_tokens=usage.cached_tokens,
    output_tokens=usage.output_tokens,
    latency_ms=latency_ms,
    temperature=gen_cfg.temperature,
    top_p=gen_cfg.top_p,
    caller_context={
        "module": __name__,
        "function": "draft_scene",
        "scene_id": scene.id,
        "chapter_num": scene.chapter,
    },
    output_hash=output_h,
    mode="A",                            # Mode A/B per ADR-001
    rubric_version=None,                 # populated by critic events
    checkpoint_sha=voice_pin.checkpoint_sha,  # populated for Mode-A drafter (V-3 pitfall)
    extra={},
))
```

**Security note (callers MUST honor):** never place secrets into `caller_context` or `extra`. Event payloads are source-of-truth per ADR-003; they land on disk in `runs/events.jsonl`. The docstring on `JsonlEventLogger` documents this; the drafter/critic/regen code authored in Phase 3 will be audited against this rule.

## Smoke-Event CLI Contract

### Invocations + Expected Output

**Default / generic smoke (OBS-01 Phase 1 exit criterion):**

```
$ uv run book-pipeline smoke-event --path /tmp/_smoke.jsonl
[OK] OBS-01 smoke test passed.
     role:            smoke_test
     path:            /tmp/_smoke.jsonl
     total lines:     1
     last event_id:   5ccc5dc50c37a7de
     last ts_iso:     2026-04-22T03:13:12.691+00:00
     schema_version:  1.0
```

**Drafter role (phase-goal voice-pin SHA schema wiring):**

```
$ uv run book-pipeline smoke-event --role drafter --path /tmp/_drafter.jsonl
[OK] OBS-01 smoke test passed.
     role:            drafter
     path:            /tmp/_drafter.jsonl
     total lines:     1
     last event_id:   292cdfa86bccac6c
     last ts_iso:     2026-04-22T03:13:13.383+00:00
     schema_version:  1.0
     mode:            A
     checkpoint_sha:  TBD-phase3
     model:           v9_or_v10_latest_stable@Qwen/Qwen3-32B
```

### Exit Codes

| Code | Class              | Meaning                                                          |
| ---- | ------------------ | ---------------------------------------------------------------- |
| 0    | success            | emit + round-trip + (drafter) SHA match all OK                   |
| 10   | emit failure       | `JsonlEventLogger.emit()` raised                                 |
| 11   | missing file       | target JSONL path not created                                    |
| 12   | empty file         | target JSONL present but empty after emit                        |
| 13   | parse failure      | `Event.model_validate_json(last_line)` raised                    |
| 14   | event_id mismatch  | round-tripped id ≠ emitted id                                    |
| 15   | drafter-shape mismatch | checkpoint_sha, role, or mode round-tripped with a different value than the Event carried |
| 16   | config load failure (drafter only) | VoicePinConfig() raised (missing file, ValidationError, etc.)   |

### Registration

Module-level `register_subcommand("smoke-event", _add_parser)` at the bottom of `src/book_pipeline/cli/smoke_event.py` fires at import time. Plan 01 pre-declared `"book_pipeline.cli.smoke_event"` in `SUBCOMMAND_IMPORTS`, so the `--help` listing and dispatch come online as soon as the module exists. Zero main.py edits required.

## Voice-Pin SHA Schema Path — The Phase Goal

The Phase 1 goal is "a runnable package skeleton with EventLogger live AND voice-pin SHA verification wired". The *verification* (comparing loaded checkpoint bytes vs the pinned SHA on every vLLM handshake) belongs to Phase 3 DRAFT-01. The *schema path* — the wiring that lets a checkpoint SHA flow from config into an observability event — is entirely this plan's deliverable.

The flow:

```
config/voice_pin.yaml                           <-- human-edited / Phase 3 pin event writes real hash
    |
    | VoicePinConfig()  (plan 03)
    v
vp_cfg.voice_pin.checkpoint_sha                 <-- read live, no caching, no hardcoding
    |
    | Event(checkpoint_sha=pin_sha, ...)        (plan 02 type contract)
    v
JsonlEventLogger.emit(event)                    (plan 05 concrete impl)
    |
    | FileHandler mode='a' + fsync
    v
runs/events.jsonl                               (source of truth per ADR-003)
    |
    | Event.model_validate_json(last_line)      (round-trip canary)
    v
parsed.checkpoint_sha == vp_cfg...checkpoint_sha  <-- assert same bytes
```

Every step of this chain is exercised by `uv run book-pipeline smoke-event --role drafter` AND by `tests/test_smoke_event_cli.py::test_smoke_event_drafter_role_wires_voice_pin_sha`. Phase 3 DRAFT-01 plugs in bytes-on-disk verification at the `vp_cfg` boundary — the rest of this chain is already load-tested.

**Tampering-scenario proof-of-runtime-read (manual verification during execution):** mutating `config/voice_pin.yaml`'s `checkpoint_sha` from `"TBD-phase3"` to `"TAMPER-TEST-xyz"`, then running `uv run book-pipeline smoke-event --role drafter`, produces a JSONL line whose `checkpoint_sha` field reads `"TAMPER-TEST-xyz"`. This proves the CLI reads the value at runtime — it is NOT hardcoded. The test suite does not mutate the shared config file (it would race with parallel tests), but the acceptance criterion is grep-verifiable: the literal string `vp_cfg.voice_pin.checkpoint_sha` appears at one and only one site (`src/book_pipeline/cli/smoke_event.py:135`).

## Verification Evidence

Plan `<success_criteria>` + task `<acceptance_criteria>`:

| Criterion                                                                                                                        | Status | Evidence                                                                                          |
| -------------------------------------------------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------- |
| Concrete `JsonlEventLogger` at `src/book_pipeline/observability/event_logger.py` using stdlib logging + python-json-logger       | PASS   | File exists; uses `from pythonjsonlogger.json import JsonFormatter` + stdlib `logging`             |
| Handler idempotency verified — two loggers x two emits = 2 JSONL lines, not 3 or 4                                                | PASS   | `test_handler_idempotent` green                                                                    |
| fsync-on-emit enabled (durability test passes)                                                                                   | PASS   | `test_fsync_called` green (patches `os.fsync`, asserts call_count ≥ 1)                            |
| `book-pipeline smoke-event --role smoke_test` emits valid JSONL with all required fields                                         | PASS   | Live CLI run above; `test_smoke_event_emits_and_roundtrips` green; `test_all_required_fields_in_jsonl` green |
| `book-pipeline smoke-event --role drafter` reads `VoicePinConfig().voice_pin.checkpoint_sha`, populates Event, emits, round-trips | PASS   | Live CLI run above; `test_smoke_event_drafter_role_wires_voice_pin_sha` green                      |
| xxhash helpers for prompt_hash / output_hash                                                                                      | PASS   | `book_pipeline.observability.hash_text` + `event_id` exported; `test_hash_text_determinism` + `test_event_id_shape` green |
| OBS-01 coverage acknowledged                                                                                                      | PASS   | Requirements list (`requirements: [OBS-01]`) frontmatter                                           |
| FOUND-01 coverage acknowledged (CLI scaffold usable, smoke-event listed in help)                                                  | PASS   | Plan 01-01 originally provided FOUND-01; this plan exercises it by registering a 4th subcommand end-to-end |
| All 13 event logger tests + 5 smoke CLI tests pass                                                                                | PASS   | `uv run pytest tests/test_event_logger.py tests/test_smoke_event_cli.py` -> 18 passed             |
| mypy --strict clean on `src/book_pipeline/observability` + `src/book_pipeline/cli/smoke_event.py`                                 | PASS   | "Success: no issues found in 4 source files"                                                       |
| ruff check clean on new/touched files                                                                                             | PASS   | "All checks passed!" on plan-05 scope                                                              |
| ruff format --check clean on new/touched files                                                                                    | PASS   | "5 files already formatted"                                                                        |
| Plan-02 schema frozen — emitted line has schema_version="1.0"                                                                     | PASS   | `test_schema_version_frozen_1_0` green                                                             |
| `runs/.gitkeep` tracked; `runs/events.jsonl` remains gitignored                                                                   | PASS   | `git status` shows `runs/.gitkeep` committed; `.gitignore` rule `runs/*.jsonl` intact              |
| Full suite regression                                                                                                             | PASS   | 104 / 104 passing in 1.72s                                                                         |
| Grep: `register_subcommand("smoke-event"` in smoke_event.py                                                                       | PASS   | 1 match on line 253                                                                                |
| Grep: `from book_pipeline.config.voice_pin import VoicePinConfig` in smoke_event.py                                               | PASS   | 1 match on line 131                                                                                |
| Grep: `def _build_drafter_smoke_event` in smoke_event.py                                                                          | PASS   | 1 match on line 120                                                                                |
| Grep: `vp_cfg.voice_pin.checkpoint_sha` in smoke_event.py                                                                         | PASS   | 1 match on line 135 — proves SHA is read from config, not hardcoded                                |
| Grep: `"book_pipeline.cli.smoke_event"` in `src/book_pipeline/cli/main.py` SUBCOMMAND_IMPORTS                                     | PASS   | 1 match on line 30 (plan 01-01 pre-declaration)                                                    |
| Tampering scenario: flip voice_pin.yaml.checkpoint_sha -> emitted line reflects new value                                         | PASS   | Manual verification during execution (documented above; JSONL line contained "TAMPER-TEST-xyz")   |
| Grep (phase-goal): `jq '.checkpoint_sha' /tmp/_drafter.jsonl` = `grep checkpoint_sha config/voice_pin.yaml`                        | PASS   | jsonl sha: "TBD-phase3"; yaml sha: "TBD-phase3" — byte-identical                                   |

Plan `<verify>` block commands executed:

```
$ uv run pytest tests/test_event_logger.py -x -v
13 passed in 0.15s

$ uv run mypy src/book_pipeline/observability
Success: no issues found in 3 source files

$ uv run book-pipeline smoke-event --path /tmp/_smoke_test_events.jsonl
[OK] OBS-01 smoke test passed.
     role: smoke_test
     ...

$ uv run book-pipeline smoke-event --role drafter --path /tmp/_smoke_test_events.jsonl
[OK] OBS-01 smoke test passed.
     role: drafter
     ...
     checkpoint_sha: TBD-phase3
     model: v9_or_v10_latest_stable@Qwen/Qwen3-32B

$ uv run pytest tests/test_smoke_event_cli.py -x -v
5 passed in 0.22s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] python-json-logger modern import path used instead of the deprecated module**

- **Found during:** Task 1 GREEN — `uv run pytest tests/test_event_logger.py` emitted a `DeprecationWarning: pythonjsonlogger.jsonlogger has been moved to pythonjsonlogger.json` on every test run.
- **Issue:** The plan's `<action>` snippet wrote `from pythonjsonlogger import jsonlogger` and `class _EventJsonFormatter(jsonlogger.JsonFormatter)`. python-json-logger 3.x (installed via plan 01-01) has moved this symbol to `pythonjsonlogger.json.JsonFormatter`; the old path warns on import. Shipping a known-deprecated import in the module every Phase 2+ caller will import would print a DeprecationWarning in every downstream test run for the life of the project.
- **Fix:** Changed to `from pythonjsonlogger.json import JsonFormatter` and subclassed `JsonFormatter` directly. Semantics identical; zero test changes needed. Verified `pythonjsonlogger.json.JsonFormatter` exists in the installed package.
- **Files modified:** `src/book_pipeline/observability/event_logger.py`
- **Commit:** `3cb4996`

**2. [Rule 3 - Blocking] `# type: ignore[call-arg]` on `VoicePinConfig()` per plan 03's documented pattern**

- **Found during:** Task 2 mypy pass — `src/book_pipeline/cli/smoke_event.py:133: error: Missing named argument "voice_pin" for "VoicePinConfig"  [call-arg]`
- **Issue:** mypy --strict can't see through `BaseSettings.__init__` to the YAML source that populates `voice_pin`. This is the identical issue plan 03 hit in `loader.py` and documented as the standard pydantic-settings usage pattern.
- **Fix:** Added `# type: ignore[call-arg]` tight to the single call site, with a 4-line comment block explaining why and cross-referencing plan 03's decision.
- **Files modified:** `src/book_pipeline/cli/smoke_event.py`
- **Commit:** `540520c`

**3. [Style] Ruff fixes applied**

- **Found during:** Task 1/2 ruff runs.
- **Issues:**
    - SIM105 on the fsync try/except: rewrote as `with contextlib.suppress(OSError):` (idiomatic; test mock of `os.fsync` still works because module-level `os` lookup is preserved).
    - UP017 on `timezone.utc`: replaced with `from datetime import UTC`; the rest of the repo moved to this alias in plan 01-02.
    - RUF100 on 3 unused `# noqa: BLE001` directives: removed (project's ruff config does not enable BLE001).
    - Ruff-format: cosmetic reformatting of `hashing.py` and `smoke_event.py` into the project's canonical style.
- **Files modified:** `src/book_pipeline/observability/event_logger.py`, `src/book_pipeline/observability/hashing.py`, `src/book_pipeline/cli/smoke_event.py`
- **Commits:** `3cb4996` (event_logger + hashing), `540520c` (smoke_event)

No Rule 4 (architectural) deviations. No checkpoints reached. No tests skipped. No auth gates encountered.

### Out-of-scope discoveries (NOT fixed, logged here for the orchestrator)

Full-repo `uv run mypy src/` surfaced one unrelated error in plan 01-04's module:

- `src/book_pipeline/cli/openclaw_cmd.py:52: error: "print_help" of "ArgumentParser" does not return a value (it only ever returns None)`

Full-repo `uv run ruff check src/ tests/` surfaced several unrelated errors in plan 01-01 / plan 01-04 files (version.py, bootstrap.py, test_cli_skeleton.py, test_openclaw.py).

Per the execution-scope boundary rule, these are pre-existing in other plans' files and are NOT mine to fix in this plan. They should be logged to the phase's deferred-items list if the orchestrator wants them cleaned up before Phase 1 exit. None affect OBS-01's success criteria — this plan's own scope (`src/book_pipeline/observability/` + `src/book_pipeline/cli/smoke_event.py`) is mypy-strict AND ruff clean.

## Authentication Gates

None. This plan is local-only: no network, no LLM calls, no secrets consumed at runtime. `SecretsConfig` is NOT touched by this plan — `VoicePinConfig` is the only config loaded, and it only has placeholder fields.

## Deferred Issues

None for this plan's scope. Every acceptance criterion has an automated check; every verify-block command runs green on the current main branch.

**Future work already named in the plan (scheduled follow-ons, not deferred bugs):**

- Phase 3 DRAFT-01 replaces `voice_pin.yaml`'s `checkpoint_sha: "TBD-phase3"` with the real SHA and adds bytes-on-disk verification at the vLLM-serve handshake. The schema path this plan wires will then carry real data.
- Phase 6 OBS-02 introduces monthly archive + weekly checksum for `runs/events.jsonl` per ADR-003's durability guarantee. The append-only contract is established here; the archival machinery arrives later.
- Logfire additional handler (deferred per STACK.md). Not needed for Phase 1 — JSONL is source-of-truth.

## Known Stubs

None. Every artifact produced by this plan is fully functional on day one:

- `JsonlEventLogger.emit` writes real bytes to real JSONL files.
- `hash_text` / `event_id` compute real xxh64 digests.
- `book-pipeline smoke-event` makes real round-trip assertions against real files.

The `"TBD-phase3"` checkpoint_sha value in `config/voice_pin.yaml` is NOT a stub in the UI sense — it's an explicitly-documented phase-later pin point owned by plan 03, readable live, and correctly propagates through the observability chain. Phase 3 DRAFT-01 replaces it with the real SHA; the schema path this plan wires is unchanged by that future swap.

## Threat Flags

No new threat surface beyond plan's `<threat_model>`:

- **T-05-01 (Tampering — events.jsonl edited after write) — MITIGATED:** `FileHandler(mode='a')` enforced in code (grep-verifiable: `grep 'mode="a"' src/book_pipeline/observability/event_logger.py` = 1 match). Phase 6 OBS-02 adds the monthly archive + weekly checksum in ADR-003; Phase 1 establishes the append-only contract.
- **T-05-02 (Information Disclosure — Secrets in caller_context/extra) — MITIGATED:** Module docstring on `event_logger.py` explicitly documents "callers MUST NOT place secrets (API keys, tokens) into Event.caller_context or Event.extra"; Phase 3 drafter/critic/regen code audit will enforce.
- **T-05-03 (DoS — huge event payload) — ACCEPTED (per plan):** Phase 1 events are O(100 bytes) per line; Phase 6 OBS-02 introduces blob-store separation for large prompts.
- **T-05-04 (Repudiation — crash loss) — MITIGATED:** `os.fsync()` after every emit; `test_fsync_called` verifies by patching the sysstcall.
- **T-05-05 (Tampering — schema drift) — MITIGATED:** `Event.schema_version = "1.0"` asserted on every emit (`test_schema_version_frozen_1_0`); downstream consumers can filter by version; plan 02's `test_event_has_18_fields_total` already blocks silent field additions.
- **T-05-06 (Tampering — checkpoint_sha doesn't match loaded weights) — ACCEPTED (Phase 1) / MITIGATED (Phase 3):** Phase 1 emits whatever voice_pin.yaml says; Phase 3 DRAFT-01 adds bytes-on-disk verification. The schema path this plan wires has byte-exact SHA fidelity through write + read + parse (`test_checkpoint_sha_roundtrips_when_populated` + `test_smoke_event_drafter_role_wires_voice_pin_sha`).

No new threat flags surfaced during execution.

## Self-Check: PASSED

Artifact verification (files on disk):

- FOUND: `src/book_pipeline/observability/__init__.py` (3-symbol `__all__`: JsonlEventLogger, event_id, hash_text)
- FOUND: `src/book_pipeline/observability/event_logger.py` (class `JsonlEventLogger` + `class _EventJsonFormatter` + `_get_or_create_handler` + module-level `_HANDLERS_BY_PATH` + `DEFAULT_PATH = Path("runs/events.jsonl")` + `mode="a"` grep-verifiable)
- FOUND: `src/book_pipeline/observability/hashing.py` (`hash_text` + `event_id`, xxh64-backed)
- FOUND: `src/book_pipeline/cli/smoke_event.py` (two role paths, 7 exit-code classes, `register_subcommand("smoke-event", _add_parser)` at module scope)
- FOUND: `tests/test_event_logger.py` (13 tests covering all behaviors from plan task 1)
- FOUND: `tests/test_smoke_event_cli.py` (5 tests including the drafter-role phase-goal wiring)
- FOUND: `runs/.gitkeep` (empty file, tracked)

Commit verification on `main` branch of `/home/admin/Source/our-lady-book-pipeline/`:

- FOUND: `d4b0699` (test RED — 13 failing tests)
- FOUND: `3cb4996` (feat GREEN — JsonlEventLogger + xxhash helpers)
- FOUND: `540520c` (feat — smoke-event CLI, smoke_test + drafter roles)

All 3 per-task commits landed on `main` branch. OBS-01 is LIVE.
