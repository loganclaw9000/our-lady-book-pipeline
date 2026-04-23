---
phase: 05-mode-b-escape-regen-budget-alerting-nightly-orchestration
plan: 02
subsystem: regenerator+chapter_assembler+cli
tags: [regen-budget, oscillation, spend-cap, mode-b-escalation, scene-kick, loop-04]

# Dependency graph
requires:
  - phase: 03-drafter-critic-regenerator-scene-loop
    provides: cli/draft.py run_draft_loop composition root (SceneStateMachine R=3 loop) + SceneCritic CriticResponse/CriticIssue shapes
  - phase: 04-chapter-assembly-post-commit-dag
    provides: ChapterDagOrchestrator._step1_canon CHAPTER_FAIL branch (extension point for scene-kick routing)
  - plan: 05-01
    provides: ModeBDrafter + ModeBDrafterBlocked, is_preflagged() + load_preflag_set(), event_cost_usd() + ModelPricing + PricingConfig
provides:
  - detect_oscillation() pure function (REGEN-04) — N vs N-2 axis+severity comparison with mid/high gate (D-07)
  - extract_implicated_scene_ids() + kick_implicated_scenes() helpers (LOOP-04 / Phase 4 SC4 closure per D-10)
  - cli/draft.py 4-trigger escalation (preflag / spend_cap / oscillation / r_cap_exhausted) + single role='mode_escalation' Event shape (D-08)
  - RegenConfig extension on ModeThresholdsConfig (regen.r_cap_mode_a=3 + regen.spend_cap_usd_per_scene=0.75)
  - CHAPTER_FAIL_SCENE_KICKED ChapterState enum value (substate distinct from terminal CHAPTER_FAIL)
affects: 05-03, 05-04, 06

# Tech tracking
tech-stack:
  added:
    - No new PyPI deps — all composition from Plan 05-01 + Phase 3/4 pieces
  patterns:
    - Pure function kernel (detect_oscillation, extract_implicated_scene_ids) over Pydantic models
    - Atomic tmp+rename for state mutation (_persist_scene_state clones Plan 03-07 pattern)
    - Archive-before-reset for reversible surgery (kick_implicated_scenes moves md to archive/ BEFORE state transition)
    - Single-Event escalation emission (D-08 canonical shape) with trigger discriminant
    - In-memory severity tracking (attempt_severities) decouples oscillation detector from EventLogger implementation

key-files:
  created:
    - src/book_pipeline/regenerator/oscillation.py
    - src/book_pipeline/chapter_assembler/scene_kick.py
    - tests/regenerator/test_oscillation.py
    - tests/chapter_assembler/test_scene_kick.py
    - tests/cli/test_draft_escalation.py
    - tests/cli/test_draft_spend_cap.py
    - tests/integration/test_scene_loop_escalation.py
  modified:
    - src/book_pipeline/cli/draft.py (escalation helpers + run_draft_loop 4-branch routing)
    - src/book_pipeline/chapter_assembler/dag.py (_step1_canon CHAPTER_FAIL scene-kick routing)
    - src/book_pipeline/interfaces/types.py (additive ChapterState.CHAPTER_FAIL_SCENE_KICKED)
    - src/book_pipeline/config/mode_thresholds.py (additive RegenConfig + regen field)
    - config/mode_thresholds.yaml (regen block)
    - tests/chapter_assembler/test_dag.py (+2 routing tests)
    - tests/interfaces/test_chapter_state_machine.py (11-value enum-count update)

key-decisions:
  - "Oscillation detector compares N vs N-2 (D-07) — NOT N vs N-1. Mid/high severity only; low severity ignored. Decouples signal from event_logger surface by synthesizing critic events from locally-tracked attempt_severities in cli/draft.py (production SceneCritic emits OBS-01 events; unit tests often stub)."
  - "Scene-kick regex widened to r'\\bch(\\d+)_sc(\\d+)\\b' (word-boundary, not anchored) vs Plan 03-07's _SCENE_ID_RE — because CriticIssue.location is free-text with embedded refs. Defensive int-cast + canonical zero-pad canonicalizes 'ch1_sc2' -> 'ch01_sc02'."
  - "D-06 spend-cap check fires BEFORE oscillation check in the regen-fail branch: $0.75 is unrecoverable, oscillation is a signal for Mode-B which costs more. Order: spend_cap -> oscillation -> r_cap_exhausted."
  - "Composition-root additions (preflag_set, mode_b_drafter, pricing_by_model, spend_cap_usd_per_scene) are all optional via getattr — preserves Phase 3 test_draft_loop backward compat (all 11 existing scene-loop tests still pass without modification)."
  - "CHAPTER_FAIL_SCENE_KICKED is a NEW ChapterState enum value (11th total), distinct from terminal CHAPTER_FAIL. DAG treats both as step-1 terminal (no canon commit, no subsequent DAG steps)."
  - "Archive pattern (A8): kicked scene's drafts/ch{NN}/{scene_id}.md moves to drafts/ch{NN}/archive/{scene_id}_rev{K:02d}.md BEFORE the state record is reset to PENDING. This preserves recovery artifact even if state write fails."
  - "Alerter integration deferred to Plan 05-03: 3 `# TODO(05-03): alerter.send_alert(...)` comment sites mark the Telegram wiring hooks (spend_cap_exceeded, mode_b_exhausted, mode_b_critic_fail)."

patterns-established:
  - "Pattern 1: Synthetic-Event adapter — when a downstream pure-function kernel (detect_oscillation) expects OBS-01 Event shape but the local caller has richer structured data (CriticResponse), synthesize minimal events on the fly rather than forcing the pure function to accept two input shapes."
  - "Pattern 2: Optional composition-root fields via getattr — Phase N+1 extensions to a Phase N composition seam land as optional SimpleNamespace attributes. Default-safe for Phase N callers that don't wire them."
  - "Pattern 3: Archive-before-mutate for reversible state resets — write recovery artifact to archive/ FIRST, then mutate state. Failure between the two leaves archive recoverable; failure after state mutation still has atomic tmp+rename backstop."

requirements-completed: [REGEN-02, REGEN-03, REGEN-04, LOOP-04]

# Metrics
duration: ~1h
completed: 2026-04-23
---

# Phase 5 Plan 02: Regen-Budget + Oscillation + Mode-B Escalation + Surgical Scene-Kick Summary

**R-cap + per-scene spend-cap + N-vs-N-2 oscillation detector + 4-trigger Mode-B escalation via single role='mode_escalation' Event; closes Phase 4 SC4 deferral with surgical scene-kick routing on CHAPTER_FAIL.**

## Performance

- **Duration:** ~1h (3 tasks sequential TDD)
- **Completed:** 2026-04-23
- **Tasks:** 3 (all RED + GREEN cadence — 6 atomic commits)
- **Files created:** 7
- **Files modified:** 7
- **Tests added:** 31 new tests across 5 new test files + 2 updated
- **Baseline:** 542 -> 573 non-slow tests passing (+31, zero regressions)

## Accomplishments

- **REGEN-04 landed (D-07):** `detect_oscillation(critic_events, min_history=2) -> (fired, common)` at `src/book_pipeline/regenerator/oscillation.py`. Compares attempts N and N-2 axis+severity sets; fires only on mid/high matches; attempt-1 cannot oscillate.
- **REGEN-02 landed (D-05 + D-06):** `RegenConfig` additively extends `ModeThresholdsConfig` with `r_cap_mode_a=3` + `spend_cap_usd_per_scene=0.75`. Phase 1 freeze respected — no existing fields renamed/removed. `config/mode_thresholds.yaml` gains new `regen:` block.
- **REGEN-03 landed (D-08):** Every escalation emits exactly ONE `role='mode_escalation'` Event with `extra={from_mode, to_mode, trigger ∈ {preflag|oscillation|spend_cap_exceeded|r_cap_exhausted}, issue_ids}`. Integration test parametrizes all 4 branches.
- **LOOP-01 scene-loop extended (D-09):** `cli/draft.py::run_draft_loop` wraps the Phase 3 R=3 loop with 4 escalation paths in the correct order: preflag (pre-loop), spend_cap -> oscillation -> r_cap_exhausted (at each regen-fail boundary). `_run_mode_b_attempt` helper encapsulates Mode-B + critic-gate + ModeBDrafterBlocked.
- **LOOP-04 landed (D-10) — Phase 4 SC4 closure:** `extract_implicated_scene_ids()` parses `CriticIssue.location` via widened regex `\bch(\d+)_sc(\d+)\b` with defensive int-cast + canonical zero-pad. `kick_implicated_scenes()` archives md to `drafts/ch{NN}/archive/{scene_id}_rev{K:02d}.md`, resets `SceneStateRecord -> PENDING` via pure `transition()` helper, emits ONE `role='scene_kick'` Event. `ChapterDagOrchestrator._step1_canon` routes chapter-critic FAIL through the kicker when issues cite scene refs; `CHAPTER_FAIL_SCENE_KICKED` substate distinguishes surgical-kick from terminal CHAPTER_FAIL.
- **Threat mitigations verified:** T-05-02-01 (regex injection blocked by int-cast + numeric-only match space), T-05-02-02 (spend-cap >0 via Pydantic), T-05-02-03 (atomic tmp+rename; archive-before-reset), T-05-02-04 (oscillation guard rail prevents trivial axis flutter from blowing Mode-B budget), T-05-02-06 (exactly 1 trigger per mode_escalation Event; order-of-check documented).

## Task Commits

Each task strict TDD RED -> GREEN:

1. **Task 1: Oscillation detector + mode_thresholds config extension**
   - RED: `63316e7` (`test(05-02): RED — failing tests for oscillation detector`)
   - GREEN: `5b7e48c` (`feat(05-02): GREEN — oscillation detector + regen config extension (REGEN-02 + REGEN-04)`)

2. **Task 2: Surgical scene-kick + DAG CHAPTER_FAIL routing**
   - RED: `aef15dd` (`test(05-02): RED — failing tests for surgical scene-kick + DAG routing`)
   - GREEN: `32a0de6` (`feat(05-02): GREEN — surgical scene-kick routing (LOOP-04 + SC4 deferral closure)`)

3. **Task 3: cli/draft.py scene-loop extension (4 escalation branches)**
   - RED: `b16a941` (`test(05-02): RED — failing tests for scene-loop escalation + spend-cap`)
   - GREEN: `f940192` (`feat(05-02): GREEN — scene-loop extension (preflag + oscillation + spend-cap + Mode-B escalation)`)

**Plan metadata commit:** pending (SUMMARY.md + STATE.md + ROADMAP.md commit follows).

## Files Created/Modified

### Kernel modules
- `src/book_pipeline/regenerator/oscillation.py` — `detect_oscillation()` pure function + `_extract_axis_severity_set()` helper.
- `src/book_pipeline/chapter_assembler/scene_kick.py` — `extract_implicated_scene_ids()` + `kick_implicated_scenes()` + `_next_archive_rev()` + `_emit_scene_kick_event()`.
- `src/book_pipeline/cli/draft.py` — added `_emit_mode_escalation`, `_scene_events`, `_compute_scene_spent_usd`, `_critic_events_for_scene`, `_synth_critic_events_from_severities`, `_run_mode_b_attempt`, and extended `run_draft_loop` with 4-branch escalation wiring + `attempt_severities` local tracking.
- `src/book_pipeline/chapter_assembler/dag.py` — `_step1_canon` routes chapter-critic FAIL through `scene_kick` when implicated scenes exist; `run()` treats `CHAPTER_FAIL_SCENE_KICKED` as step-1 terminal.
- `src/book_pipeline/interfaces/types.py` — additive `ChapterState.CHAPTER_FAIL_SCENE_KICKED = "chapter_fail_scene_kicked"`.
- `src/book_pipeline/config/mode_thresholds.py` — `RegenConfig` model + `regen: RegenConfig` field on `ModeThresholdsConfig` (default_factory).

### Config YAML
- `config/mode_thresholds.yaml` — new `regen:` block with `r_cap_mode_a: 3` + `spend_cap_usd_per_scene: 0.75`.

### Tests
- `tests/regenerator/test_oscillation.py` — 8 tests (history_below_min, two_identical_fires, low_severity_ignored, different_axes, three_back_not_one_back, multiple_common, empty_list, two_events_no_three_back).
- `tests/chapter_assembler/test_scene_kick.py` — 8 tests (single ref, multiple refs, non-specific, evidence fallback, zero-pad canonicalization, reset to PENDING, archive markdown, single scene_kick event).
- `tests/chapter_assembler/test_dag.py` — +2 routing tests (test_I scene-kick substate; test_J non-specific terminal preserved).
- `tests/interfaces/test_chapter_state_machine.py` — enum-count bumped 10 -> 11 (CHAPTER_FAIL_SCENE_KICKED).
- `tests/cli/test_draft_escalation.py` — 5 tests (preflag routes, r_cap_exhaust, oscillation, mode_b_exhaustion, event shape).
- `tests/cli/test_draft_spend_cap.py` — 4 tests (fires_at_threshold, below_threshold, respects_config, counts_across_roles).
- `tests/integration/test_scene_loop_escalation.py` — 4 parametrized branches (preflag / r_cap_exhausted / oscillation / spend_cap_exceeded) verifying terminal state + single mode_escalation Event shape end-to-end.

## Decisions Made

Every locked user decision D-05..D-10 has a corresponding shipped artifact:

- **D-05** -> `config/mode_thresholds.yaml` `regen.r_cap_mode_a: 3` via `RegenConfig(r_cap_mode_a: int = Field(default=3, gt=0))`; `run_draft_loop(max_regen=3)` default unchanged.
- **D-06** -> `config/mode_thresholds.yaml` `regen.spend_cap_usd_per_scene: 0.75`; `_compute_scene_spent_usd()` + comparison against `spend_cap_usd_per_scene` in run_draft_loop.
- **D-07** -> `detect_oscillation()` pure function in `regenerator/oscillation.py` — N vs N-2 comparison, mid/high gate, `_extract_axis_severity_set` defensive over malformed events.
- **D-08** -> `_emit_mode_escalation(event_logger, scene_id, from_mode, to_mode, trigger, issue_ids)` helper; exactly 4 call sites in `cli/draft.py` (one per trigger).
- **D-09** -> `run_draft_loop` composition: preflag pre-loop -> (for attempts 1..R+1) -> critic FAIL -> spend_cap check -> oscillation check -> r_cap_exhausted check. Order documented in code comments.
- **D-10** -> `extract_implicated_scene_ids()` + `kick_implicated_scenes()` + `ChapterDagOrchestrator._step1_canon` routing; `CHAPTER_FAIL_SCENE_KICKED` substate for traceability.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Oscillation detector couldn't read critic events from test fakes**

- **Found during:** Task 3 (test_oscillation_escalates_before_r_exhausted)
- **Issue:** Initial implementation of `run_draft_loop` read critic events from `event_logger.events`. Production `SceneCritic` emits OBS-01 Events with `extra.severities`; unit tests use `_FakeCritic` that returns `CriticResponse` directly without emitting. The detector received an empty list and never fired.
- **Fix:** Added `attempt_severities: list[dict[str, str]]` local tracking in `run_draft_loop` — on each critic FAIL, record the worst severity per axis (via _SEV_RANK) from `critic_resp.issues`. Added `_synth_critic_events_from_severities(scene_id, attempt_severities)` helper that synthesizes minimal `role='critic'` Events for the detector. This decouples the oscillation signal from the event-logger implementation.
- **Files modified:** `src/book_pipeline/cli/draft.py`
- **Verification:** test_oscillation_escalates_before_r_exhausted passes; integration parametrized branch [oscillation] passes; production path also works because the same synthesized events feed the same detector.
- **Committed in:** `f940192` (Task 3 GREEN commit)

**2. [Rule 1 - Bug] Hardcoded `mode: "A"` in scene frontmatter**

- **Found during:** Task 3 implementation (Mode-B commit path)
- **Issue:** `_commit_scene` hardcoded `"mode": "A"` in the scene frontmatter dict. Mode-B COMMITTED scenes would then incorrectly claim mode="A", breaking Phase 4 assembly audit + future digest analysis.
- **Fix:** Replaced with `"mode": getattr(draft, "mode", "A")` — uses `DraftResponse.mode` from whichever drafter produced the scene, defaulting to "A" for legacy compat.
- **Files modified:** `src/book_pipeline/cli/draft.py`
- **Committed in:** `f940192` (Task 3 GREEN commit)

**3. [Rule 1 - Bug] Test-written issues triggered oscillation in r_cap_exhaust test**

- **Found during:** Task 3 (test_r_cap_exhaust_escalates_to_mode_b)
- **Issue:** Initial test seeded the same `mid_issue` for all 4 attempts. Oscillation correctly fired at attempt 3 (N and N-2 match historical:mid), escalating to Mode-B before R-cap exhaustion — so the test couldn't observe a clean r_cap_exhausted trigger.
- **Fix:** Rotated 4 unique (axis, severity) tuples — historical:mid, arc:high, metaphysics:mid, donts:high — so oscillation never fires and R-cap is the sole trigger. Same fix applied to integration parametrized branch [r_cap_exhausted].
- **Files modified:** `tests/cli/test_draft_escalation.py`, `tests/integration/test_scene_loop_escalation.py`
- **Committed in:** `f940192` (Task 3 GREEN commit)

**4. [Rule 1 - Bug] Ruff unused-variable + import-order cleanups**

- **Found during:** Tasks 2 + 3 lint gate
- **Issue:** (a) `dag.py` unpacked `non_specific` unused; (b) `tests/cli/test_draft_escalation.py` imports unsorted by ruff.
- **Fix:** Prefixed `_non_specific`; ran `ruff check --fix` for import sort.
- **Files modified:** `src/book_pipeline/chapter_assembler/dag.py`, `tests/cli/test_draft_escalation.py`.
- **Committed in:** Task 2/3 GREEN commits (inline).

---

**Total deviations:** 4 auto-fixed (2 bugs, 1 blocking, 1 lint).
**Impact on plan:** All auto-fixes preserve intended behavior + semantics. No scope creep; no functional requirements added beyond the plan's must_haves.

## Issues Encountered

- None beyond the 4 deviations above. The composition-root getattr pattern kept Phase 3 tests green without modification (no brittleness).

## Known Stubs

- `cli/draft.py` has 3 `# TODO(05-03): alerter.send_alert(...)` comment markers at spend_cap_exceeded, mode_b_exhausted, and mode_b_critic_fail branches. Plan 05-03 lands the `TelegramAlerter` + wires these call sites. Scene-loop correctness is NOT blocked on the alerter — HARD_BLOCKED states + mode_escalation Events already carry full forensic trail.

## Operator Follow-ups (None)

- No operator actions required. All kernel changes ship with default-safe values (`regen.r_cap_mode_a=3`, `regen.spend_cap_usd_per_scene=0.75`).

## Next Phase Readiness

**Plan 05-03 can now consume:**
- Escalation event taxonomy (4 trigger values on `role='mode_escalation'` Events).
- HARD_BLOCKED blocker tags: `spend_cap_exceeded`, `mode_b_exhausted`, `mode_b_critic_fail`.
- 3 `# TODO(05-03)` comment sites enumerating where Telegram alert calls go.

**No blockers for Plan 05-03.** No new PyPI dependencies added.

## Self-Check: PASSED

**Files created:**
- FOUND: src/book_pipeline/regenerator/oscillation.py
- FOUND: src/book_pipeline/chapter_assembler/scene_kick.py
- FOUND: tests/regenerator/test_oscillation.py
- FOUND: tests/chapter_assembler/test_scene_kick.py
- FOUND: tests/cli/test_draft_escalation.py
- FOUND: tests/cli/test_draft_spend_cap.py
- FOUND: tests/integration/test_scene_loop_escalation.py

**Commits:**
- FOUND: 63316e7 (test 05-02 RED oscillation)
- FOUND: 5b7e48c (feat 05-02 GREEN oscillation + config)
- FOUND: aef15dd (test 05-02 RED scene-kick)
- FOUND: 32a0de6 (feat 05-02 GREEN scene-kick)
- FOUND: b16a941 (test 05-02 RED escalation + spend-cap)
- FOUND: f940192 (feat 05-02 GREEN scene-loop extension)

**Test suite:** 573 non-slow tests passing (baseline 542 + 31 new, zero regressions).

**Lint gate:** `bash scripts/lint_imports.sh` green (import-linter 2/2 + ruff + scoped mypy).

**Config smoke:**
  - `ModeThresholdsConfig().regen.r_cap_mode_a == 3`
  - `ModeThresholdsConfig().regen.spend_cap_usd_per_scene == 0.75`
  - `ChapterState.CHAPTER_FAIL_SCENE_KICKED.value == "chapter_fail_scene_kicked"`

---
*Phase: 05-mode-b-escape-regen-budget-alerting-nightly-orchestration*
*Completed: 2026-04-23*
