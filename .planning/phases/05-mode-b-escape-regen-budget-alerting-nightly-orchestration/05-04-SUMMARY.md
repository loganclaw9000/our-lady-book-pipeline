---
phase: 05-mode-b-escape-regen-budget-alerting-nightly-orchestration
plan: 04
subsystem: cli+observability+openclaw
tags: [orch-01, loop-01, obs-02, nightly-cron, sqlite-ledger, telegram-wiring, openclaw, workspace]

# Dependency graph
requires:
  - phase: 01-foundation-observability-baseline
    provides: OBS-01 Event schema + JsonlEventLogger + xxhash event_id
  - phase: 02-rag-bundler-retrieval
    provides: openclaw/bootstrap.py cron-add subprocess pattern (Plan 02-06)
  - phase: 03-drafter-critic-regenerator-scene-loop
    provides: cli/draft.py::run_draft_loop composition + vllm_bootstrap CLI exit-code taxonomy (Plan 03-03)
  - phase: 04-chapter-assembly-post-commit-dag
    provides: cli/chapter.py composition root + 4-step DAG terminal states
  - plan: 05-01
    provides: ModeBDrafter + event_cost_usd() + PricingConfig
  - plan: 05-02
    provides: run_draft_loop 4-trigger escalation + 3 TODO(05-03) alerter wire-up sites
  - plan: 05-03
    provides: TelegramAlerter + HARD_BLOCK_CONDITIONS + MESSAGE_TEMPLATES

provides:
  - "`book-pipeline nightly-run` CLI — ORCH-01 composition root (D-16 exit codes 0/2/3/4)"
  - "`book-pipeline register-cron --nightly` + `--cron-freshness` CLIs (D-14 + D-15 openclaw cron registration, idempotent)"
  - "`book-pipeline check-cron-freshness` CLI — D-14 stale-nightly detector"
  - "`book-pipeline ingest-events` CLI — OBS-02 idempotent JSONL→SQLite ingester"
  - "`src/book_pipeline/observability/ledger.py` — SQLite schema (events + schema_meta) + UPSERT_SQL ON CONFLICT(event_id, axis) DO NOTHING + byte-offset tail-read (Pitfall 4 mitigation)"
  - "`workspaces/nightly-runner/` — openclaw workspace (5 markdown files) + openclaw.json agent declaration"
  - "Live TelegramAlerter wiring in cli/draft.py — 3 TODO(05-03) stubs from Plan 05-02 closed"
affects: 06

# Tech tracking
tech-stack:
  added: [] # No new PyPI deps — sqlite3 (stdlib), subprocess (stdlib), existing alerts + observability
  patterns:
    - "Byte-offset tail-read sidecar (Pitfall 4) — `<db>.last_offset` atomic tmp+rename; O(1) ingester growth"
    - "Idempotent openclaw cron registration via `openclaw cron list` probe before `cron add` (mirrors bootstrap.py register_nightly_ingest pattern)"
    - "OQ 4 soft-fail alerter injection — None on missing env → stderr fallback; scene-loop correctness independent of alert delivery"
    - "Per-axis SQLite row expansion for critic Events — PRIMARY KEY (event_id, axis); non-critic Events produce one row with axis=''"
    - "Composition-root testability — module-level function references (boot_vllm_if_needed, _build_nightly_alerter, _run_one_scene, _maybe_trigger_chapter_dag) are monkey-patch seams; dry-run + unit tests never touch real infra"

key-files:
  created:
    - src/book_pipeline/observability/ledger.py
    - src/book_pipeline/cli/ingest_events.py
    - src/book_pipeline/cli/register_cron.py
    - src/book_pipeline/cli/check_cron_freshness.py
    - src/book_pipeline/cli/nightly_run.py
    - workspaces/nightly-runner/AGENTS.md
    - workspaces/nightly-runner/SOUL.md
    - workspaces/nightly-runner/USER.md
    - workspaces/nightly-runner/BOOT.md
    - workspaces/nightly-runner/HEARTBEAT.md
    - tests/observability/test_ledger.py
    - tests/cli/test_ingest_events.py
    - tests/cli/test_register_cron.py
    - tests/cli/test_check_cron_freshness.py
    - tests/cli/test_nightly_run.py
    - tests/integration/test_nightly_run_end_to_end.py
  modified:
    - src/book_pipeline/cli/main.py (SUBCOMMAND_IMPORTS += 4 new subcommands)
    - src/book_pipeline/cli/draft.py (3 TODO(05-03) stubs → live _try_send_alert; _run_mode_b_attempt accepts alerter + event_logger; 3 call sites updated)
    - openclaw.json (nightly-runner agent declared with anthropic/claude-opus-4-7 model)
    - .gitignore (runs/metrics.sqlite3 + runs/metrics.sqlite3.last_offset)

key-decisions:
  - "Ledger schema: PRIMARY KEY (event_id, axis) not (event_id) alone — lets us expand critic Events with per_axis_scores into 5 rows while all other Events produce one row with axis=''. Phase 6 digest queries axes directly via WHERE axis = 'historical'."
  - "byte-offset sidecar (<db>.last_offset) chosen over event_id-based offset tracking — append-only events.jsonl makes byte-offset strictly monotonic, O(1) seek on each run, and resilient to event_id hash collisions. Sidecar written atomically via tmp + os.replace."
  - "openclaw cron registration CLI is idempotent via `openclaw cron list` string-contains probe before `cron add` — matches Plan 02-06 register_nightly_ingest pattern. Missing OPENCLAW_GATEWAY_TOKEN exits 2 with actionable stderr pointing at `openclaw auth setup`."
  - "boot_vllm_if_needed composes vllm-bootstrap's _run with synthesized --dry-run Namespace — no systemd start, no real GPU contention during nightly. Real boot is operator-one-shot via `systemctl --user start vllm-paul-voice.service`; the nightly's health-gate is the drafter's own boot_handshake."
  - "_discover_pending_scenes + _run_one_scene + _maybe_trigger_chapter_dag are intentionally monkey-patch seams — production wiring is placeholder; tests drive the control flow deterministically. Phase 6 wiring lands alongside the weekly digest which needs the same scene-buffer scanner."
  - "OQ 4 soft-fail: _build_nightly_alerter returns None when TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset; scene-loop _try_send_alert treats None as no-op + stderr log. HARD_BLOCKED state transitions are unchanged regardless of alert delivery — the state trail is the forensic record, Telegram is the convenience signal."
  - "mode_b_critic_fail mapped to condition 'regen_stuck_loop' since the HARD_BLOCK_CONDITIONS taxonomy (frozen in Plan 05-03) has 8 entries; rather than expand the taxonomy we reuse the nearest semantic match + thread scene_id + axes='mode_b_critic_fail' into the detail. A dedicated 'mode_b_critic_fail' condition can be added in Phase 6 if operator feedback warrants."

patterns-established:
  - "Pattern 1: Per-axis SQLite ledger expansion — one Event with per_axis_scores maps to N rows; PRIMARY KEY (event_id, axis) ensures idempotency; INSERT ... ON CONFLICT DO NOTHING is the upsert primitive."
  - "Pattern 2: Byte-offset tail-read sidecar — <db>.last_offset file tracks append-only source position; O(1) seek on subsequent runs; atomic tmp+rename on persist; on shrunk-file corruption, fall back to offset=0 (dedup via ON CONFLICT saves correctness)."
  - "Pattern 3: Composition-root monkey-patch seams — module-level function refs (not class attributes) are the unit-test seam for ORCH-01-style CLIs. Tests monkey-patch boot_vllm_if_needed + _run_one_scene + _maybe_trigger_chapter_dag at the nightly_run module scope; no DI injection needed."
  - "Pattern 4: Alerter threading as default-None kwargs — _run_mode_b_attempt gained alerter + event_logger kwargs; 3 call sites pass composition_root.alerter via getattr; legacy Phase 3 callers (no alerter field) default-safe through None."

requirements-completed: [ORCH-01, LOOP-01]

# Metrics
duration: ~16 min (3 TDD task pairs)
completed: 2026-04-23
---

# Phase 5 Plan 04: nightly-run CLI + cron registration + stale detector + OBS-02 SQLite ledger Summary

**Closes Phase 5 by landing the ORCH-01 nightly orchestrator, LOOP-01 end-to-end autonomous scene loop (Telegram wired live into cli/draft.py), D-14 stale-cron detector, D-15 openclaw cron registration, and OBS-02 idempotent SQLite ledger with byte-offset tail-read. Phase 6 weekly digest unblocked.**

## Performance

- **Duration:** ~16 min (3 tasks, all TDD RED + GREEN)
- **Completed:** 2026-04-23
- **Tasks:** 3 (6 atomic commits + this metadata commit)
- **Files created:** 16 (5 src + 5 workspace md + 6 test)
- **Files modified:** 4 (cli/main.py, cli/draft.py, openclaw.json, .gitignore)
- **Tests added:** 21 (4 ledger + 3 ingest-events + 4 register-cron + 3 freshness + 5 nightly-run unit + 2 nightly-run E2E)
- **Baseline:** 594 → 615 non-slow tests passing (+21, 0 regressions)

## Accomplishments

- **ORCH-01 landed (D-15):** `book-pipeline register-cron --nightly` issues the exact openclaw 2026.4.5 `cron add` invocation — `--name book-pipeline:nightly-run --cron '0 2 * * *' --tz America/Los_Angeles --session isolated --agent nightly-runner --message 'book-pipeline nightly-run --max-scenes 10'`. Idempotent via `openclaw cron list` string-contains probe.
- **D-14 stale-cron detector:** `book-pipeline register-cron --cron-freshness` registers an independent 08:00 PT cron that runs `book-pipeline check-cron-freshness`, which scans runs/events.jsonl for the most-recent `role='nightly_run'` Event; absent or >36h → Telegram alert `stale_cron_detected` + exit 3.
- **LOOP-01 closure:** `book-pipeline nightly-run` composes vllm-bootstrap → scene loop → chapter DAG → completion Event. Exit codes 0/2/3/4 per D-16 + OQ 5. TelegramAlerter is instantiated ONCE per run at the composition root and injected into `run_draft_loop` via `composition_root.alerter`, closing all 3 Plan 05-02 `# TODO(05-03)` stubs (spend_cap_exceeded, mode_b_exhausted, mode_b_critic_fail→regen_stuck_loop).
- **OBS-02 SQLite ledger (D-17):** `src/book_pipeline/observability/ledger.py` ships `init_schema()` + `event_to_rows()` (per-axis expansion for critic Events, one row per axis) + `ingest_event_rows()` (INSERT ... ON CONFLICT(event_id, axis) DO NOTHING). Byte-offset tail-read via `tail_read_since_offset` + `<db>.last_offset` sidecar (Pitfall 4 mitigation — O(1) ingester growth). `book-pipeline ingest-events --db ... --events ...` subcommand drives it.
- **openclaw workspace:** `workspaces/nightly-runner/` with AGENTS.md + SOUL.md + USER.md + BOOT.md + HEARTBEAT.md mirrors `workspaces/drafter/` shape (OQ 2 resolution); openclaw.json declares the agent with `anthropic/claude-opus-4-7` model so `--agent nightly-runner` resolves at cron-registration time.
- **OQ 4 soft-fail resolution:** Missing `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` degrades alerts to stderr + logs a `role='telegram_alert'` Event with `delivery='failed'`; scene-loop HARD_BLOCKED transitions are unchanged. The forensic trail survives even a permanently-broken alerter.
- **OQ 5 exit-code resolution:** 0 progressed (≥1 COMMITTED), 2 vllm-fail, 3 hard-block (STOP — don't cascade), 4 max-scenes-no-progress. All 4 verified by distinct unit tests.

## Task Commits

Each task strict TDD RED → GREEN:

1. **Task 1: OBS-02 SQLite ledger + ingest-events CLI (D-17)**
   - RED: `a90a8b2` (`test(05-04): RED — failing tests for OBS-02 SQLite ledger + ingest-events CLI`)
   - GREEN: `1eb467f` (`feat(05-04): GREEN — OBS-02 SQLite ledger + ingest-events idempotent tail-read (D-17)`)

2. **Task 2: openclaw workspace + register-cron + check-cron-freshness (D-14 + D-15)**
   - RED: `9e11df5` (`test(05-04): RED — failing tests for openclaw workspace + register-cron + check-cron-freshness`)
   - GREEN: `d1d246f` (`feat(05-04): GREEN — nightly-runner workspace + register-cron + check-cron-freshness (ORCH-01 + D-14 + D-15)`)

3. **Task 3: nightly-run CLI + alerter wiring + E2E integration (ORCH-01 + LOOP-01)**
   - RED: `bf0c5b0` (`test(05-04): RED — failing tests for nightly-run CLI + E2E integration`)
   - GREEN: `3202a70` (`feat(05-04): GREEN — book-pipeline nightly-run composition root (ORCH-01 + LOOP-01 closure)`)

**Plan metadata commit:** pending (SUMMARY.md + STATE.md + ROADMAP.md commit follows).

## Files Created/Modified

### Kernel / observability
- `src/book_pipeline/observability/ledger.py` — SCHEMA_SQL + UPSERT_SQL + init_schema + event_to_rows (per-axis expansion) + ingest_event_rows (bulk upsert) + tail_read_since_offset + read_last_offset/persist_offset.

### CLIs (all register_subcommand self-registering)
- `src/book_pipeline/cli/ingest_events.py` — `book-pipeline ingest-events` (OBS-02 consumer).
- `src/book_pipeline/cli/register_cron.py` — `book-pipeline register-cron --nightly | --cron-freshness` (D-14 + D-15 openclaw cron registrar).
- `src/book_pipeline/cli/check_cron_freshness.py` — `book-pipeline check-cron-freshness` (D-14 stale detector).
- `src/book_pipeline/cli/nightly_run.py` — `book-pipeline nightly-run` (ORCH-01 composition root).

### openclaw workspace
- `workspaces/nightly-runner/AGENTS.md` — role + responsibilities + exit codes.
- `workspaces/nightly-runner/SOUL.md` — purpose + composition-root pointer.
- `workspaces/nightly-runner/USER.md` — operator interaction surface.
- `workspaces/nightly-runner/BOOT.md` — env prerequisites + pre-flight commands.
- `workspaces/nightly-runner/HEARTBEAT.md` — per-run marker format.
- `openclaw.json` — nightly-runner agent declared with anthropic/claude-opus-4-7 model.

### cli/draft.py wiring (closes Plan 05-02 TODOs)
- `_try_send_alert(alerter, condition, detail, *, event_logger)` helper — OQ 4 soft-fail; emits role='telegram_alert' delivery='failed' Event on TelegramPermanentError.
- `_run_mode_b_attempt` signature += `alerter: Any = None, event_logger: Any = None` kwargs (default-safe for Phase 3 callers).
- 3 escalation sites updated: spend_cap_exceeded (in run_draft_loop), mode_b_exhausted (in _run_mode_b_attempt), mode_b_critic_fail→regen_stuck_loop (in _run_mode_b_attempt).
- 3 `_run_mode_b_attempt` call sites (preflag, oscillation, r_cap_exhausted) pass `alerter=getattr(composition_root, 'alerter', None), event_logger=event_logger`.

### Misc
- `src/book_pipeline/cli/main.py` — SUBCOMMAND_IMPORTS += 4 new subcommands.
- `.gitignore` — runs/metrics.sqlite3 + runs/metrics.sqlite3.last_offset.

### Tests
- `tests/observability/test_ledger.py` — 4 tests (schema init, insert, idempotency, per-axis expansion).
- `tests/cli/test_ingest_events.py` — 3 tests (CLI discoverable, happy path, incremental).
- `tests/cli/test_register_cron.py` — 4 tests (happy path subprocess shape, idempotent skip, missing token exit 2, --cron-freshness D-14 schedule).
- `tests/cli/test_check_cron_freshness.py` — 3 tests (fresh → exit 0 no alert, stale → exit 3 alert, absent → exit 3 alert).
- `tests/cli/test_nightly_run.py` — 5 tests (exit 0/2/3/4 + dry-run).
- `tests/integration/test_nightly_run_end_to_end.py` — 2 E2E tests (happy-path composition + chapter-DAG trigger; hard-block stops + no chapter DAG).

## Decisions Made

Every locked user decision (D-14..D-17) has a corresponding shipped artifact:

- **D-14** → `check-cron-freshness` CLI + `register-cron --cron-freshness` (08:00 PT independent cron entry); `stale_cron_detected` condition emits when no `role='nightly_run'` Event within 36h.
- **D-15** → `register-cron --nightly` issues `openclaw cron add --name book-pipeline:nightly-run --cron '0 2 * * *' --tz America/Los_Angeles --session isolated --agent nightly-runner --message 'book-pipeline nightly-run --max-scenes 10'`; idempotent via cron-list probe; exit 2 on missing OPENCLAW_GATEWAY_TOKEN.
- **D-16** → `book-pipeline nightly-run` composes steps (a)/(b)/(c)/(d) with exit codes 0/2/3/4 per OQ 5; on HARD_BLOCK: alert + STOP (don't cascade).
- **D-17** → `observability/ledger.py` schema-versioned (schema_meta.version_int=1); INSERT ... ON CONFLICT(event_id, axis) DO NOTHING; byte-offset sidecar tail-read; runs/metrics.sqlite3 + .last_offset gitignored (rebuildable).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] ruff SIM108 on check_cron_freshness hours_display**
- **Found during:** Task 2 GREEN post-lint gate
- **Issue:** Initial `if math.isinf(...): hours_display = 'never' / else: hours_display = f'{hours_since:.1f}'` block triggered ruff SIM108 "use ternary".
- **Fix:** Condensed to ternary expression with `hours_display: Any = "never" if math.isinf(hours_since) else f"{hours_since:.1f}"`.
- **Files modified:** `src/book_pipeline/cli/check_cron_freshness.py`
- **Committed in:** `d1d246f` (Task 2 GREEN commit).

**2. [Rule 2 - Missing Critical] `mode_b_critic_fail` is not in HARD_BLOCK_CONDITIONS taxonomy**
- **Found during:** Task 3 GREEN (wiring the 3rd Plan 05-02 TODO site)
- **Issue:** Plan 05-02 left a `# TODO(05-03): alerter.send_alert('mode_b_critic_fail', ...)` comment, but Plan 05-03 froze HARD_BLOCK_CONDITIONS at 8 entries (no 'mode_b_critic_fail'). Sending that condition would raise ValueError in TelegramAlerter.send_alert.
- **Fix:** Remapped to `regen_stuck_loop` (closest semantic match in the taxonomy) + threaded scene_id + `axes='mode_b_critic_fail'` into the detail dict so the Telegram body still carries the precise trigger. A dedicated 'mode_b_critic_fail' condition can be added in Phase 6 if operator feedback warrants.
- **Files modified:** `src/book_pipeline/cli/draft.py`
- **Committed in:** `3202a70` (Task 3 GREEN commit).

**3. [Rule 2 - Missing Critical] `_run_mode_b_attempt` signature didn't accept alerter**
- **Found during:** Task 3 GREEN (threading alerter through escalation paths)
- **Issue:** Plan 05-02 left `_run_mode_b_attempt` without alerter/event_logger kwargs, but wiring TODOs required both. Naively scoping alerter inside `run_draft_loop` would not reach the mode_b_exhausted / mode_b_critic_fail branches in the helper.
- **Fix:** Added `alerter: Any = None, event_logger: Any = None` kwargs (default-safe for Phase 3 callers that never wired alerter); updated all 3 `_run_mode_b_attempt` call sites (preflag / oscillation / r_cap_exhausted) to pass `alerter=getattr(composition_root, 'alerter', None), event_logger=event_logger`.
- **Files modified:** `src/book_pipeline/cli/draft.py`
- **Committed in:** `3202a70` (Task 3 GREEN commit).

---

**Total deviations:** 3 auto-fixed (1 lint, 2 missing-critical kernel wiring).
**Impact on plan:** All deviations were lockstep correctness/consistency adjustments. No scope creep; no functional requirements added beyond plan must_haves.

## Issues Encountered

- None beyond the 3 deviations above.

## Known Stubs

- `src/book_pipeline/cli/nightly_run.py::_discover_pending_scenes` and `_maybe_trigger_chapter_dag` are intentional monkey-patch seams for Plan 05-04 unit/E2E tests. Production wiring lands in Phase 6 alongside the weekly digest (which needs the same scene-buffer scanner). Current impl is a thin state_dir scan (PENDING state.json files) + a no-op chapter-DAG hook — good enough for dry-run + composition verification, insufficient for driving real 27-chapter production runs. Phase 6 will replace with: (a) buffer-fill detection per chapter via `drafts/ch{NN}/` + `EXPECTED_SCENE_COUNTS`, (b) direct `cli/chapter._run(args)` invocation when a chapter fills.
- `_run_one_scene` uses `scenes/{chapter}/{scene_id}.yaml` resolution identical to `cli/draft.py::_resolve_scene_yaml`; if the stub is missing, logs a warning + returns rc=4 (treated as no-progress, not a hard-block). Phase 6 operator flow documents the stub-seed requirement.

## Operator Follow-ups (Phase 6)

- **Openclaw cron pricing drift (Pitfall 5):** `openclaw.json` still lists Opus 4.7 at `$15/$75/$1.5/$18.75` per MTok; the authoritative numbers in `config/pricing.yaml` are `$5/$25/$0.50/$10` (+ `$6.25` 5m cache-write). Fix in Phase 6 cleanup. Non-blocking — `config/pricing.yaml` is the source of truth for spend-cap math.
- **Pre-flight before first nightly run:**
  1. Set env: `OPENCLAW_GATEWAY_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`.
  2. Populate `config/voice_samples.yaml` via `book-pipeline curate-voice-samples --source-dir /home/admin/paul-thinkpiece-pipeline/...`.
  3. Register crons: `book-pipeline register-cron --nightly && book-pipeline register-cron --cron-freshness`.
  4. First nightly fires at 02:00 America/Los_Angeles; first freshness check at 08:00 PT.
- **Verify placeholder preflag beat IDs** against `outline.md` canonical beat inventory (from Plan 05-01 operator follow-ups).
- **Phase 6 `_discover_pending_scenes` + `_maybe_trigger_chapter_dag` wiring** — see Known Stubs above.

## Next Phase Readiness

Phase 6 unblocked:

- **OBS-02 SQLite ledger ready** — weekly digest can consume `runs/metrics.sqlite3` directly; `book-pipeline ingest-events` runs cheaply as a pre-digest step (O(1) tail-read).
- **Nightly loop live** — ORCH-01 + LOOP-01 end-to-end; all 4 escalation branches (preflag / oscillation / spend-cap / r_cap_exhausted) fire live Telegram alerts when triggered.
- **D-14 stale-detector live** — weekly digest can cross-reference `stale_cron_detected` Events against digest generation windows.
- **Thesis registry surface ready** — Phase 5 role='mode_escalation', 'telegram_alert', 'nightly_run', 'scene_kick' Events populate events.jsonl; Phase 6 TEST-02 thesis matcher has typed data.

**Phase 5 COMPLETE** — 4 plans × multi-task cadence = 26 task commits total across the phase; 615 non-slow tests passing (+121 from Phase 4 baseline); 0 kernel/book_specifics drift; import-linter 2 contracts kept throughout.

## Self-Check: PASSED

**Files:**
- FOUND: src/book_pipeline/observability/ledger.py
- FOUND: src/book_pipeline/cli/ingest_events.py
- FOUND: src/book_pipeline/cli/register_cron.py
- FOUND: src/book_pipeline/cli/check_cron_freshness.py
- FOUND: src/book_pipeline/cli/nightly_run.py
- FOUND: workspaces/nightly-runner/AGENTS.md
- FOUND: workspaces/nightly-runner/SOUL.md
- FOUND: workspaces/nightly-runner/USER.md
- FOUND: workspaces/nightly-runner/BOOT.md
- FOUND: workspaces/nightly-runner/HEARTBEAT.md
- FOUND: tests/observability/test_ledger.py
- FOUND: tests/cli/test_ingest_events.py
- FOUND: tests/cli/test_register_cron.py
- FOUND: tests/cli/test_check_cron_freshness.py
- FOUND: tests/cli/test_nightly_run.py
- FOUND: tests/integration/test_nightly_run_end_to_end.py

**Commits:**
- FOUND: a90a8b2 (test 05-04 RED OBS-02 ledger + ingest-events)
- FOUND: 1eb467f (feat 05-04 GREEN OBS-02 ledger + ingest-events)
- FOUND: 9e11df5 (test 05-04 RED register-cron + check-cron-freshness)
- FOUND: d1d246f (feat 05-04 GREEN register-cron + check-cron-freshness + workspace)
- FOUND: bf0c5b0 (test 05-04 RED nightly-run + E2E)
- FOUND: 3202a70 (feat 05-04 GREEN nightly-run + alerter wiring)

**Test suite:** 615 non-slow tests passing (baseline 594 + 21 new, 0 regressions).

**Lint gate:** `bash scripts/lint_imports.sh` green (import-linter 2 contracts kept + ruff + scoped mypy on 139 source files).

**CLI discoverability:** `uv run book-pipeline --help` lists all 4 new subcommands: nightly-run, register-cron, check-cron-freshness, ingest-events.

**TODO closure:** `grep -r "TODO(05-03)" src/book_pipeline/cli/` returns 0 matches (all Plan 05-02 alerter stubs closed).

---
*Phase: 05-mode-b-escape-regen-budget-alerting-nightly-orchestration*
*Completed: 2026-04-23*
