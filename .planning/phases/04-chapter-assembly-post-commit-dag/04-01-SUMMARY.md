---
phase: 04-chapter-assembly-post-commit-dag
plan: 01
subsystem: kernel-skeleton-+-chapter-state-machine
tags: [kernel-skeleton, import-linter, chapter-state-machine, phase-4-foundation, loop-02, loop-03]
requirements_completed: []  # LOOP-02 + LOOP-03 are multi-plan; Plan 04-01 lands only kernel skeletons + state machine shape. Concrete impls land in 04-02 (ConcatAssembler), 04-03 (Opus extractor + retrospective), 04-04 (orchestrator + ablation harness).
dependency_graph:
  requires:
    - "03-01 (4-kernel-package extension precedent — Plan 04-01 applies the exact same atomic landing pattern for chapter_assembler/entity_extractor/retrospective/ablation)"
    - "01-02 (interfaces.types Phase 1 freeze — ChapterState + ChapterStateRecord are additive, not modifications)"
    - "01-06 (import-linter contract extension policy — Plan 04-01 appends 4 more packages under the same policy)"
    - "02-01 (scripts/lint_imports.sh mypy-scope extension pattern — Plan 04-01 extends with 4 more kernel package dirs)"
  provides:
    - "src/book_pipeline/chapter_assembler/__init__.py — empty kernel package marker (Plan 04-02 fills with ConcatAssembler)"
    - "src/book_pipeline/entity_extractor/__init__.py — empty kernel package marker (Plan 04-03 fills with OpusEntityExtractor)"
    - "src/book_pipeline/retrospective/__init__.py — empty kernel package marker (Plan 04-03 fills with OpusRetrospectiveWriter)"
    - "src/book_pipeline/ablation/__init__.py — empty kernel package marker (Plan 04-04 fills with AblationRun harness)"
    - "src/book_pipeline/interfaces/chapter_state_machine.py — ChapterState + ChapterStateRecord re-export + pure transition() helper parallel to scene_state_machine.py"
    - "src/book_pipeline/interfaces/types.py — ChapterState StrEnum (10 values) + ChapterStateRecord Pydantic (chapter_num, state, scene_ids, chapter_sha, dag_step, history, blockers)"
    - "pyproject.toml import-linter contracts 1 + 2 — extended with 4 Phase 4 kernel packages"
    - "scripts/lint_imports.sh — mypy scope extended by 4 packages"
    - "tests/chapter_assembler/__init__.py, tests/entity_extractor/__init__.py, tests/retrospective/__init__.py, tests/ablation/__init__.py — test package markers so pytest walks them (concrete tests land in Plans 04-02..04-04)"
    - "tests/interfaces/test_chapter_state_machine.py — 6 tests covering the 10-state Enum, str-subclass shape, happy-path 7-transition history, pure-function guarantee, failure branches, JSON roundtrip"
    - "tests/test_import_contracts.py — 3 new Phase 4 structural assertions (importable, listed-in-both-contracts, listed-in-mypy-scope)"
  affects:
    - "Plan 04-02 (ConcatAssembler) — lands inside chapter_assembler/ without touching pyproject.toml or lint_imports.sh"
    - "Plan 04-03 (OpusEntityExtractor + OpusRetrospectiveWriter) — lands inside entity_extractor/ + retrospective/ without touching pyproject.toml or lint_imports.sh"
    - "Plan 04-04 (chapter orchestrator + AblationRun harness) — lands inside ablation/ and imports ChapterStateMachine.transition() through the 4-step post-commit DAG without further contract churn"
    - "Plans 04-05..04-06 — continue filling the 4 kernel packages with additional files (schemas, templates, CLI subcommands) under the same zero-contract-churn pattern established here"
tech-stack:
  added: []  # No new runtime deps; pydantic + datetime + enum are all already-used stdlib-or-existing.
  patterns:
    - "Kernel-package atomic extension: 4 new packages + 4 test markers + pyproject contract 1+2 appends + lint_imports.sh mypy scope append, all in ONE plan's single feat commit. Downstream plans land concrete files INSIDE these directories with zero pyproject.toml / lint-script churn. Precedent: Phase 3 Plan 01 (drafter/critic/regenerator/voice_fidelity). Pattern: pay the import-linter + mypy-scope tax ONCE per phase-wave of new packages."
    - "ChapterStateMachine parallel-to-SceneStateMachine: NEW module (not a Phase 1 addition). SceneStateMachine stays frozen; Phase 4 introduces a SEPARATE ChapterStateMachine because chapter-grain states (assembling, chapter_critiquing, post_commit_dag, dag_complete, dag_blocked) do not map onto scene states. transition() signature is a byte-for-byte structural clone of scene_state_machine.transition() — same model_copy pattern, same history entry shape ({from, to, ts_iso, note}), same pure-function guarantee. One persistence contract, two state-machine namespaces."
    - "Phase 1 additive-only freeze: ChapterState Enum + ChapterStateRecord Pydantic model added to interfaces/types.py __all__ alphabetically; zero existing fields/types renamed or removed. test_types regression suite (pre-existing) + git diff --stat (65 insertions / 0 deletions) both confirm the additive-only shape. Downstream freeze-aware tests (test_types Test 4: SceneState has exactly 9 members) continue to pass."
    - "Kernel/book-domain static substring guard extended: test_kernel_does_not_import_book_specifics kernel_dirs list gains 4 Phase 4 dirs. Empty __init__.py files contain no `book_specifics` substring, so the scan is additive-safe. Belt-and-suspenders next to import-linter contract 1."
    - "Ruff noqa-in-comment gotcha: ruff scans code-adjacent comments for `UP042` tokens and emits a warning when the phrase appears in a docstring-adjacent comment block (not a real noqa directive). Avoid verbatim-quoting noqa codes in prose comments — paraphrase (`suppress the UP042 StrEnum suggestion via a noqa on the class line`) instead. Same class-level `# noqa: UP042` decorator is valid and required; only the explanatory comment needed rewording."
key-files:
  created:
    - "src/book_pipeline/chapter_assembler/__init__.py (~13 lines; docstring citing Plan 04-02 ConcatAssembler)"
    - "src/book_pipeline/entity_extractor/__init__.py (~13 lines; docstring citing Plan 04-03 OpusEntityExtractor)"
    - "src/book_pipeline/retrospective/__init__.py (~13 lines; docstring citing Plan 04-03 OpusRetrospectiveWriter)"
    - "src/book_pipeline/ablation/__init__.py (~13 lines; docstring citing Plan 04-04 AblationRun harness)"
    - "src/book_pipeline/interfaces/chapter_state_machine.py (~52 lines; re-exports ChapterState/ChapterStateRecord + transition() pure helper parallel to scene_state_machine.transition())"
    - "tests/chapter_assembler/__init__.py (empty test package marker)"
    - "tests/entity_extractor/__init__.py (empty test package marker)"
    - "tests/retrospective/__init__.py (empty test package marker)"
    - "tests/ablation/__init__.py (empty test package marker)"
    - "tests/interfaces/__init__.py (empty test package marker — pytest collection seed)"
    - "tests/interfaces/test_chapter_state_machine.py (~170 lines; 6 behavior tests)"
    - ".planning/phases/04-chapter-assembly-post-commit-dag/04-01-SUMMARY.md — this file"
  modified:
    - "src/book_pipeline/interfaces/types.py (additive: ChapterState Enum + ChapterStateRecord Pydantic + __all__ updates; 65 insertions, 0 deletions)"
    - "pyproject.toml (import-linter contract 1 source_modules += 4; contract 2 forbidden_modules += 4; Phase 4 plan 01 provenance comments added)"
    - "scripts/lint_imports.sh (mypy scope +4 kernel package dirs: chapter_assembler, entity_extractor, retrospective, ablation)"
    - "tests/test_import_contracts.py (kernel_dirs scan += 4 Phase 4 dirs; 3 new structural tests: test_phase_4_kernel_packages_importable, test_phase_4_packages_listed_in_both_contracts, test_phase_4_packages_in_lint_imports_mypy_scope)"
key-decisions:
  - "(04-01) ChapterStateRecord.chapter_sha is Optional (str | None = None) and dag_step is int with default 0 rather than an Enum. Rationale: chapter_sha is naturally absent before COMMITTING_CANON completes (null-until-commit semantics), and dag_step is a monotonic counter (0=not-started, 1=canon, 2=entity, 3=rag, 4=retro) that maps cleanly to integer comparison for the LOOP-04 next-chapter gate (`dag_step == 4 and state == DAG_COMPLETE`). An Enum would force 5 named values for what's naturally progress counting; the plan spec embraces this shape explicitly (`dag_step: int = 0`)."
  - "(04-01) transition() does NOT enforce legal state transitions (e.g. won't reject PENDING_SCENES → DAG_COMPLETE). Rationale: matches SceneStateMachine.transition() precedent — caller-side orchestration (Phase 4 Plan 04-04) owns the state-graph policy. Enforcing it here would split the validation between the kernel helper and the orchestrator and create drift risk. The pure helper's single responsibility is 'append history + bump state', the caller controls WHAT bumps are allowed. Test_transition_fail_branches asserts blockers[] appending works AFTER transition() returns — the orchestrator stitches the decoration."
  - "(04-01) tests/interfaces/__init__.py was missing pre-Plan 04-01 (no prior plan placed tests directly under tests/interfaces/). Created as an empty marker so pytest collects tests/interfaces/test_chapter_state_machine.py; no other test_*.py files live there yet. Future Phase 4 plans that test other kernel-interfaces modules (if any) reuse this package."
  - "(04-01) ChapterState value strings are lowercase snake_case (`pending_scenes`, `post_commit_dag`) matching SceneState's convention (`pending`, `critic_fail`). Downstream persistence (drafts/chapter_buffer/ch{NN:02d}.state.json) stores these values verbatim. Case-changing the values later would break already-persisted state records — the values are part of the on-disk schema contract."
  - "(04-01) ruff noqa warning on a prose comment containing the literal `UP042` token required a comment reword (not a real lint failure — the warning said `expected code to consist of uppercase letters followed by digits only`, meaning ruff almost matched the pattern as a noqa directive in a non-noqa context). Reworded the comment to paraphrase `noqa: UP042` rather than quote it verbatim. Rule 1 (bug-fix) deviation — the warning was mine, introduced by Task 2 GREEN, caught inside the same verification pass and folded in before commit. Zero semantic change."
  - "(04-01) Plan spec's <behavior> for Task 2 called for `test_transition_fail_branches` to cover CHAPTER_CRITIQUING → CHAPTER_FAIL AND POST_COMMIT_DAG → DAG_BLOCKED — implemented as TWO sub-branches in one test. Each branch asserts the state transition happened AND that the caller-side `record.model_copy(update={'blockers': [..., new_tag]})` pattern produces a record with blockers set. This proves the kernel-helper + caller-orchestration split works end-to-end without giving transition() a blockers parameter it doesn't need."
  - "(04-01) Chose to leave `book_pipeline.interfaces.__init__.py` UNTOUCHED. It already re-exports SceneState/SceneStateRecord/transition from scene_state_machine; mirroring that pattern for ChapterStateMachine would introduce a name collision on `transition` (two different functions, same name). Callers import the chapter variant via `from book_pipeline.interfaces.chapter_state_machine import transition` — explicit module path, no ambiguity. Test imports use this explicit pattern."
metrics:
  duration_minutes: 18
  completed_date: 2026-04-21
  tasks_completed: 2
  files_created: 12
  files_modified: 4
  tests_added: 9  # 3 import-contract structural + 6 chapter_state_machine behavior
  tests_passing: 440  # was 431 baseline; +9 new non-slow tests
  tests_baseline: 431
  slow_tests_added: 0
  scoped_mypy_source_files_after: 106  # was 105 pre-Plan; +1 (chapter_state_machine.py; 4 kernel __init__.py markers contribute to mypy scope but are ~13-line docstring-only modules)
commits:
  - hash: 29a345e
    type: test
    summary: "Task 1 RED — failing tests for Phase 4 kernel packages + lint-imports extension"
  - hash: ad009c8
    type: feat
    summary: "Task 1 GREEN — 4 Phase 4 kernel package skeletons + import-linter extension"
  - hash: 6c5ee05
    type: test
    summary: "Task 2 RED — failing tests for ChapterStateMachine"
  - hash: e497497
    type: feat
    summary: "Task 2 GREEN — ChapterStateMachine module + ChapterState/ChapterStateRecord types"
---

# Phase 4 Plan 01: Kernel Skeletons + ChapterStateMachine Summary

**One-liner:** Phase 4's foundation landed — 4 empty kernel packages (`chapter_assembler/`, `entity_extractor/`, `retrospective/`, `ablation/`) wired into both import-linter contracts and `scripts/lint_imports.sh` mypy scope under the Phase 3 Plan 01 extension-policy precedent; `book_pipeline.interfaces.chapter_state_machine` ships the NEW Phase 4 chapter-grain state machine (10-value `ChapterState` StrEnum, 7-field `ChapterStateRecord` Pydantic with `chapter_num`/`state`/`scene_ids`/`chapter_sha`/`dag_step`/`history`/`blockers`, pure `transition()` helper parallel to the frozen `scene_state_machine.transition()`) with the SceneStateMachine module bytes-identical (empty diff) as required by the Phase 1 freeze. Plans 04-02..04-06 can now land concrete implementations inside already-linted directories without further pyproject.toml / lint-script churn.

## ChapterStateMachine Shape (for Plans 04-02..04-04)

| Field | Type | Default | Purpose |
|---|---|---|---|
| chapter_num | int | required | 1-indexed chapter number (matches outline.md) |
| state | ChapterState | required | Current state (one of 10 values) |
| scene_ids | list[str] | [] | Scene ids assembled for this chapter (["ch01_sc01", ...]) |
| chapter_sha | str \| None | None | git HEAD sha after canon commit — gates DAG steps; null-until-commit |
| dag_step | int | 0 | Monotonic counter: 0=not-started, 1=canon, 2=entity, 3=rag, 4=retro |
| history | list[dict[str, object]] | [] | Ordered transition entries ({from, to, ts_iso, note}) |
| blockers | list[str] | [] | Caller-appended blocker tags |

### State values (ChapterState Enum, 10 values)

| Value | Phase | Role in flow |
|---|---|---|
| `pending_scenes` | pre-assembly | Waiting for all expected scene drafts to reach COMMITTED |
| `assembling` | assembly | ConcatAssembler running |
| `assembled` | assembly | Assembly complete, chapter text ready for critic |
| `chapter_critiquing` | critic | ChapterCritic building fresh ContextPack + running 5-axis rubric |
| `chapter_fail` | critic-fail | Any axis <3 or severity=high → Phase 5 handoff (Mode-B redraft) |
| `chapter_pass` | critic-pass | All 5 axes ≥3, ready for canon commit |
| `committing_canon` | canon | `git commit -m "canon(chNN): commit <title>"` in flight |
| `post_commit_dag` | dag | 4-step DAG running (canon → entity → rag → retro) |
| `dag_complete` | dag-ok | dag_step == 4, next chapter unblocked (LOOP-04) |
| `dag_blocked` | dag-fail | Step 1/2/3 persistent failure — alert hook; next chapter gated closed |

### Happy-path transition sequence (7 transitions)

```
PENDING_SCENES
  → ASSEMBLING           (note: "start concat")
  → ASSEMBLED            (note: "concat ok")
  → CHAPTER_CRITIQUING   (note: "fresh pack")
  → CHAPTER_PASS         (note: "5/5 axes >=3")
  → COMMITTING_CANON     (note: "git commit")
  → POST_COMMIT_DAG      (note: "entity extraction")
  → DAG_COMPLETE         (note: "retro written")
```

Seven transitions, seven history entries. Each entry: `{"from": <prior_value>, "to": <new_value>, "ts_iso": <UTC ISO-8601>, "note": <caller-supplied>}`.

### Failure branches

```
CHAPTER_CRITIQUING → CHAPTER_FAIL    (note: "axis=arc severity=high")
  + caller: blockers.append("chapter_critic_axis_fail")

POST_COMMIT_DAG → DAG_BLOCKED        (note: "entity_extractor_3x_retry_exhaust")
  + caller: blockers.append("entity_extractor_unavailable")
  + dag_step and chapter_sha carry through for resume semantics
```

`transition()` itself does not mutate `blockers` — the caller decorates via `record.model_copy(update={"blockers": [...new_tag]})` after the state bump. Matches SceneStateMachine's kernel-helper + caller-orchestration split.

### Resume semantics (for Plan 04-04 orchestrator)

`dag_step` and `chapter_sha` are preserved across DAG_BLOCKED transitions — the orchestrator reads the persisted ChapterStateRecord on re-invocation and resumes at `dag_step + 1` without re-invoking the chapter critic. Chapter commit (step 1) stays committed even if step 2/3/4 block; partial completion is a valid on-disk state. `ChapterStateRecord.model_validate_json(path.read_text())` is the resume read, and `transition(record, new_state, note)` + atomic tmp+rename is the resume write.

## Plans 04-02..04-06 Kernel-Package Add Pattern (no pyproject.toml churn)

Plans 04-02 (ConcatAssembler), 04-03 (OpusEntityExtractor + OpusRetrospectiveWriter), 04-04 (chapter orchestrator + ablation harness), 04-05 (chapter_critic + CLI), 04-06 (LOOP-04 gate + integration smoke):

- **DO** add files inside the 4 empty kernel packages created here.
- **DO NOT** touch pyproject.toml's import-linter contracts. All 4 Phase 4 kernel package names are already listed (contract 1 source_modules + contract 2 forbidden_modules). import-linter enforces the boundary automatically on every commit via scripts/lint_imports.sh.
- **DO NOT** touch scripts/lint_imports.sh. mypy scope is already extended to the 4 packages.
- **DO** add tests under `tests/<package>/`. Test discovery works transparently — the 4 `tests/<pkg>/__init__.py` markers are already on disk.

This is the Phase 3 Plan 01 precedent verbatim — every kernel package pays its import-linter + mypy-scope tax ONCE, on the plan that creates the package.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ruff false-positive noqa warning on prose comment containing `UP042` token.**

- **Found during:** Task 2 GREEN verify (`bash scripts/lint_imports.sh`).
- **Issue:** `src/book_pipeline/interfaces/types.py:219` contained a comment `# Match SceneState's \`class X(str, Enum): # noqa: UP042\` convention so the` — the verbatim-quoted `noqa: UP042` token inside the prose comment triggered ruff's warning `Invalid \`# noqa\` directive on src/book_pipeline/interfaces/types.py:219: expected code to consist of uppercase letters followed by digits only`. Ruff's heuristic almost matched the pattern as a real noqa directive. Not a hard lint failure (`All checks passed!` still printed) but noise I didn't want to carry forward.
- **Fix:** Reworded the explanatory comment to paraphrase the noqa reference: `# Match SceneState's \`class X(str, Enum)\` convention (suppress the UP042 StrEnum suggestion via a noqa on the class line) so the visible MRO matches downstream code expectations.` Zero semantic change; the actual class-level `# noqa: UP042` is still present and valid on line 221.
- **Files modified:** `src/book_pipeline/interfaces/types.py`.
- **Commit:** `e497497` (Task 2 GREEN, folded in before commit).
- **Scope:** Caused by Plan 04-01 (my comment authoring). Rule 1 applies — ruff false-positive warning was a correctness issue (noise polluting the aggregate gate output even though the gate technically passed).

---

**Total deviations:** 1 auto-fixed (Rule 1 bug — ruff false-positive noqa-in-comment caught inside the same verification pass; reworded before commit).

**Impact on plan:** Plan shape unchanged. The ChapterStateMachine structure, the 4 kernel packages, and the import-linter extension all land exactly as specified in 04-01-PLAN.md. No additional scope.

## Authentication Gates

**None.** Plan 04-01 does not touch Anthropic API, Claude Code CLI, openclaw gateway, vLLM serve, or any network/auth boundary. Only local filesystem + local git commits + pure-Python pytest runs.

## Deferred Issues

1. **`lancedb table_names()` deprecation warning** (~150 instances in the non-slow suite). Inherited from Phase 2 Plans 02-01/02/03/04/05/06 + Phase 3. No functional impact. Migration is a one-line change across 3 call sites when lancedb removes the old API. Not a Plan 04-01 concern; tracked in `.planning/deferred-items.md` (if present).

2. **Plan spec's `# noqa: UP042` visible-MRO explanation.** The plan said "match SceneState's `# noqa: UP042` pattern for visible-MRO parity" — modern Python StrEnum (`class ChapterState(StrEnum)`) would also satisfy `isinstance(member, str) is True` and arguably be cleaner, but would change `ChapterState.__mro__` visibly (StrEnum → str → Enum → object, vs the current str → Enum → object). Downstream code that introspects MRO (currently zero callers in this codebase; but test_chapter_state_is_str_enum covers the isinstance check) would see a different shape. Staying with `class X(str, Enum)` is the path of least surprise; a future refactor that migrates BOTH SceneState and ChapterState to StrEnum in one atomic plan is safe, but out of scope for Plan 04-01.

3. **transition() does not enforce legal transitions.** Matches SceneStateMachine precedent (callers own state-graph policy). Phase 4 Plan 04-04's orchestrator is where illegal transitions would raise; the kernel helper intentionally stays policy-free. If a future plan wants kernel-level enforcement, it would need to land a `LEGAL_TRANSITIONS: dict[ChapterState, set[ChapterState]]` table + validation in both scene and chapter transition() helpers symmetrically, OR a separate `validated_transition()` helper. Not a Plan 04-01 concern.

## Known Stubs

**1. `book_pipeline.chapter_assembler/__init__.py`, `book_pipeline.entity_extractor/__init__.py`, `book_pipeline.retrospective/__init__.py`, `book_pipeline.ablation/__init__.py`** are 13-line empty-package markers (docstring + `__all__: list[str] = []`). Plans 04-02 (ConcatAssembler), 04-03 (OpusEntityExtractor + OpusRetrospectiveWriter), 04-04 (AblationRun harness) fill them. The empty state is intentional — import-linter contracts 1+2 reference these packages, so they MUST exist before the first plan that adds concrete impl. Plan 04-01 is the one-time wire-up plan per the Phase 3 Plan 01 precedent.

**2. `tests/chapter_assembler/__init__.py`, `tests/entity_extractor/__init__.py`, `tests/retrospective/__init__.py`, `tests/ablation/__init__.py`** are 0-byte empty files. Plans 04-02..04-04 land concrete `test_*.py` files in these directories. Pytest collection walks them on every run; `0` collected tests for now is expected.

No unintended stubs — no hardcoded empty values flowing to UI, no "coming soon" placeholders, no TODOs.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 4 threats in the register are covered as planned:

- **T-04-01-01** (Tampering: pyproject.toml contract extension): MITIGATED. `test_phase_4_packages_listed_in_both_contracts` asserts each of the 4 new packages appears `>=2` times in pyproject.toml (contract 1 source + contract 2 forbidden). `test_phase_4_packages_in_lint_imports_mypy_scope` asserts each `src/book_pipeline/<pkg>` line is in `scripts/lint_imports.sh`. Tampering that removes a package from either contract breaks both lint-imports AND the regression tests.
- **T-04-01-02** (Tampering: interfaces/types.py Phase 1 freeze): MITIGATED. Additive-only change verified: `git diff --stat src/book_pipeline/interfaces/types.py` shows `65 insertions(+), 0 deletions(-)`. Phase 1 Event schema + all 16 existing types untouched. Pre-existing `tests/test_types.py` (6 tests including "SceneState Enum has exactly 9 members") passes unchanged.
- **T-04-01-03** (EoP: kernel → book_specifics leak): MITIGATED. 4 new kernel dirs appended to `kernel_dirs` list in `test_kernel_does_not_import_book_specifics`; each `__init__.py` contains no `book_specifics` substring. Import-linter contract 1 is the primary enforcement; the substring scan is the belt-and-suspenders guard.
- **T-04-01-04** (Repudiation: ChapterStateMachine history append): ACCEPTED as per plan. `transition()` writes `datetime.now(UTC).isoformat()` to every history entry. Clock drift is out-of-scope for a single-user pipeline; same stance as SceneStateMachine.

## Verification Evidence

Plan `<success_criteria>` + task `<done>` coverage:

| Criterion | Status | Evidence |
|---|---|---|
| All tasks in 04-01-PLAN.md executed + committed atomically | PASS | 4 per-task commits (2 × RED/GREEN pairs): `29a345e`, `ad009c8`, `6c5ee05`, `e497497`. |
| SUMMARY.md at .planning/phases/04-chapter-assembly-post-commit-dag/04-01-SUMMARY.md | PASS | This file. |
| 4 new kernel packages exist with __init__.py | PASS | `ls src/book_pipeline/{chapter_assembler,entity_extractor,retrospective,ablation}/__init__.py` all exist. |
| ChapterStateMachine implemented with strict transitions (10 states) | PASS | `ChapterState` Enum has 10 values; `transition()` purely appends history entries; 6 tests (including 10-value check, happy-path roundtrip, failure branches, JSON roundtrip) all pass. |
| pyproject.toml import-linter source_modules extended with 4 new packages | PASS | `grep -c 'book_pipeline.chapter_assembler' pyproject.toml` = 2 (contract 1 source + contract 2 forbidden). Same for the other 3 packages. |
| scripts/lint_imports.sh mypy targets extended | PASS | `grep -c 'src/book_pipeline/chapter_assembler' scripts/lint_imports.sh` = 1 for each of 4. |
| `bash scripts/lint_imports.sh` green | PASS | 2 contracts kept, ruff clean, mypy clean on 106 source files. |
| Full test suite pass count increases from 431 baseline | PASS | 440 passed (was 431; +9 new Plan 04-01 tests: 3 import-contract structural + 6 chapter_state_machine behavior). |
| `uv run python -c 'import book_pipeline.{chapter_assembler,...}'` exits 0 | PASS | Confirmed; `ok` printed. |
| `git diff src/book_pipeline/interfaces/scene_state_machine.py` is empty | PASS | `git diff` returns empty. SceneStateMachine bytes-identical. |
| `git diff src/book_pipeline/interfaces/types.py` additive-only | PASS | 65 insertions / 0 deletions. No existing fields or types renamed or removed. |
| ChapterStateRecord matches SceneStateRecord structural template | PASS | Same pure-function pattern in transition(); same history entry shape; same model_copy-based immutability; same Pydantic `model_validate_json` roundtrip. |

## Self-Check: PASSED

Artifact verification (files on disk at `/home/admin/Source/our-lady-book-pipeline/`):

- FOUND: `src/book_pipeline/chapter_assembler/__init__.py`
- FOUND: `src/book_pipeline/entity_extractor/__init__.py`
- FOUND: `src/book_pipeline/retrospective/__init__.py`
- FOUND: `src/book_pipeline/ablation/__init__.py`
- FOUND: `src/book_pipeline/interfaces/chapter_state_machine.py`
- FOUND: `tests/chapter_assembler/__init__.py`
- FOUND: `tests/entity_extractor/__init__.py`
- FOUND: `tests/retrospective/__init__.py`
- FOUND: `tests/ablation/__init__.py`
- FOUND: `tests/interfaces/__init__.py`
- FOUND: `tests/interfaces/test_chapter_state_machine.py`

Commit verification on `main` branch (git log --oneline):

- FOUND: `29a345e test(04-01): RED — failing tests for Phase 4 kernel packages + lint-imports extension`
- FOUND: `ad009c8 feat(04-01): GREEN — 4 Phase 4 kernel package skeletons + import-linter extension`
- FOUND: `6c5ee05 test(04-01): RED — failing tests for ChapterStateMachine`
- FOUND: `e497497 feat(04-01): GREEN — ChapterStateMachine module + ChapterState/ChapterStateRecord types`

All 4 per-task commits landed on `main`. Aggregate gate green. Full non-slow test suite 440 passed (was 431 baseline; +9 new).

---

*Phase: 04-chapter-assembly-post-commit-dag*
*Plan: 01*
*Completed: 2026-04-21*
