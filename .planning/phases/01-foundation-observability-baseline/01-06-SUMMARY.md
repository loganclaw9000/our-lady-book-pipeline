---
phase: 01-foundation-observability-baseline
plan: 06
subsystem: module-boundary-lint
tags: [import-linter, module-boundaries, kernel-extraction, adr-004, found-05, book-specifics, pre-commit, mypy-scoping]
requirements_completed: [FOUND-05]
dependency_graph:
  requires:
    - "01-01 (uv venv + pyproject.toml + import-linter>=2.0 in dev deps + pre-commit framework installed)"
    - "01-02 (book_pipeline.interfaces package — source_modules target)"
    - "01-02 (book_pipeline.stubs package — source_modules target)"
    - "01-05 (book_pipeline.observability package — source_modules target AND the site of the proof test's injected probe)"
  provides:
    - "Two import-linter forbidden contracts in pyproject.toml enforcing ADR-004 kernel-extraction hygiene"
    - "src/book_pipeline/book_specifics/ — the canonical home for Our Lady of Champion-specific code (CORPUS_ROOT, bible paths, Nahuatl canonicalization table)"
    - "scripts/lint_imports.sh — single-command CI/dev gate: import-linter + ruff + SCOPED mypy on Phase 1 packages"
    - "pre-push pre-commit hook wiring lint_imports.sh (heavier checks once per push, not per commit)"
    - "tests/test_import_contracts.py — 4 happy-path tests including the shape guard that keeps mypy scoped (not whole-tree)"
    - "tests/test_lint_rule_catches_violation.py — proof test that the FOUND-05 rule actually bites (fixture injects a real kernel->book_specifics import, asserts lint-imports exits non-zero with matching diagnostic, cleans up in finally)"
    - "Extension policy documented in pyproject.toml AND scripts/lint_imports.sh: each Phase 2+ PR appends its new kernel packages to both lists in the same PR"
  affects:
    - "Phase 2 RAG-01: will append `book_pipeline.rag` to BOTH contract source_modules lists AND to scripts/lint_imports.sh mypy targets in the same PR"
    - "Phase 3 DRAFT-01: will append `book_pipeline.drafter` and `book_pipeline.regenerator` similarly"
    - "Phase 4 CRITIC-01: will append `book_pipeline.critic` similarly"
    - "Phase 5 ORCH-01: will append `book_pipeline.orchestration` similarly"
    - "Every Phase 2+ PR's CI: a single `bash scripts/lint_imports.sh` is the aggregate boundary + lint gate"
tech_stack:
  added:
    - "import-linter 2.11 (already in pyproject via plan 01-01) — `[tool.importlinter]` configuration in pyproject.toml"
  patterns:
    - "Append-as-you-add boundary enforcement: contract source_modules + mypy targets both extend in the same PR that creates a new kernel package. Contrast with the rejected 'pre-list future modules' approach — import-linter 2.x errors on missing modules, which would brick the gate until the package lands."
    - "Scoped mypy (NOT whole-tree) in the aggregate gate: parity with each per-plan mypy gate, so the aggregate never fails on something no per-plan gate saw."
    - "Proof-test pattern for lint rules: a fixture writes a real violation, asserts the tool exits non-zero, asserts the output mentions the right thing, cleans up. Without it, rule enforcement is theater."
    - "pre-push stage (not pre-commit) for heavier checks: full lint_imports.sh runs once per `git push`, not per `git commit`."
key_files:
  created:
    - "src/book_pipeline/book_specifics/__init__.py"
    - "src/book_pipeline/book_specifics/corpus_paths.py"
    - "src/book_pipeline/book_specifics/nahuatl_entities.py"
    - "scripts/lint_imports.sh"
    - "tests/test_import_contracts.py"
    - "tests/test_lint_rule_catches_violation.py"
  modified:
    - "pyproject.toml"
    - ".pre-commit-config.yaml"
    - "src/book_pipeline/cli/main.py"
    - "src/book_pipeline/cli/openclaw_cmd.py"
    - "tests/test_cli_skeleton.py"
decisions:
  - "import-linter 2.x is STRICT about missing source_modules — emits `Module 'book_pipeline.drafter' does not exist.` and exits non-zero. The plan's guidance assumed graceful handling of missing modules; it wasn't accurate for v2.11. Fix: contracts only list modules that exist TODAY (`interfaces`, `observability`, `stubs`). Phase 2+ PRs append their new kernel packages to both contract lists as they land — this matches the SAME extension policy already established for the mypy-target list in scripts/lint_imports.sh. Extension-point comments landed in pyproject.toml in-line so Phase 2+ authors see the instruction at the point of edit."
  - "pre-push (not pre-commit) stage for the local lint-imports hook: running mypy + ruff + import-linter on every commit would add multi-second latency to every `git commit`; running them once per `git push` preserves correctness (nothing hits the remote without the gate) without the per-commit tax."
  - "Static grep fallback `test_kernel_does_not_import_book_specifics` added as a belt-and-suspenders guard: even if import-linter is misconfigured, a kernel source file containing the literal string 'book_specifics' fails this test. Cheap to run, catches the class of regression where someone comments out a contract."
  - "Proof-test fixture uses `tests/observability/_lint_violation_probe.py` (prefixed with `_`) as the injection site — clearly non-importable, clearly temporary; a `finally` block unlinks regardless of test outcome; a separate guard test asserts the file doesn't exist in a clean tree so uncleaned state fails fast rather than corrupting subsequent runs."
metrics:
  duration_minutes: 4
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 6
  files_modified: 5
  tests_added: 7
  tests_passing: 111
commits:
  - hash: d338942
    type: feat
    summary: import-linter contracts + book_specifics module + lint_imports.sh (+ 3 Rule-3 auto-fixes)
  - hash: 1a9f3c2
    type: test
    summary: proof test that import-linter catches FOUND-05 violation
---

# Phase 1 Plan 6: Module-Boundary Lint (FOUND-05) Summary

**One-liner:** FOUND-05 IS LIVE — import-linter v2.11 enforces ADR-004 kernel-extraction hygiene via two forbidden contracts in pyproject.toml (`kernel packages MUST NOT import from book_specifics`, `interfaces MUST NOT import from concrete kernel impls`), `src/book_pipeline/book_specifics/` is the explicit home for Our Lady of Champion-coupled code (CORPUS_ROOT + Nahuatl canonicalization table), `scripts/lint_imports.sh` runs import-linter + ruff + SCOPED mypy (NOT whole-tree) as a single aggregate gate wired to the pre-push pre-commit stage, and a fixture-driven proof test actively INJECTS a real kernel->book_specifics import on every CI run to confirm the rule still bites.

## What Shipped

A working module-boundary enforcement layer that Phase 2+ relies on from day one:

- **`pyproject.toml [tool.importlinter]`** — root_packages + 2 forbidden contracts. Contracts only reference modules that exist today (interfaces, observability, stubs); Phase 2+ PRs append new kernel packages to the source_modules lists (pattern documented in-line).
- **`src/book_pipeline/book_specifics/`** — the canonical home for book-coupled code:
    - `corpus_paths.py`: `CORPUS_ROOT = Path("~/Source/our-lady-of-champion").expanduser()` + 6 bible-file constants (BRIEF, ENGINEERING, PANTHEON, SECONDARY_CHARACTERS, OUTLINE, KNOWN_LIBERTIES). Phase 2 ingestion + Phase 4 entity extraction will read from here.
    - `nahuatl_entities.py`: `NAHUATL_CANONICAL_NAMES` dict with 6 Mesoamerican-name canonicalization entries (Quetzalcoatl, Tenochtitlan, Malintzin, Cempoala, Tlaxcalteca, Motecuhzoma) + their orthography variants. Phase 4 EntityExtractor canonicalizes against this table.
- **`scripts/lint_imports.sh`** — executable (`chmod +x`), `set -euo pipefail`, `cd` to repo root, runs three steps:
    1. `uv run lint-imports`
    2. `uv run ruff check src tests`
    3. `uv run mypy` on the 7 Phase 1 packages (SCOPED, matching each plan's per-plan mypy gate)
- **`.pre-commit-config.yaml`** — appended a local `lint-imports` hook at `stages: [pre-push]`.
- **`tests/test_import_contracts.py`** — 4 happy-path tests: lint-imports exits 0, book_specifics importable, static grep fallback, and — critically — `test_lint_imports_mypy_scope_matches_phase_1_packages` which **guards the scoping** (asserts `uv run mypy src` as a whole-tree call NEVER lands in lint_imports.sh, AND asserts the 6 scoped targets are present).
- **`tests/test_lint_rule_catches_violation.py`** — 3-test proof suite; the load-bearing test injects `src/book_pipeline/observability/_lint_violation_probe.py` with `from book_pipeline.book_specifics import corpus_paths`, runs `uv run lint-imports`, asserts exit code != 0 AND that stdout/stderr mentions "book_specifics" or "kernel packages", then unlinks the probe in a `finally` block.
- **7 new tests** — all green. Full suite: 108 passing before task 2, 111 passing after.

## The FOUND-05 Exact Contracts (for Phase 2+ reference)

Copy this verbatim when a new kernel package (e.g. `book_pipeline.rag` in Phase 2) lands — append the new module to both source_modules lists in the SAME PR that creates the package, so the gate starts enforcing immediately:

```toml
[tool.importlinter]
root_packages = ["book_pipeline"]

[[tool.importlinter.contracts]]
# Contract extension policy (matches scripts/lint_imports.sh mypy-targets policy):
#   When Phase 2+ adds a new kernel package, that plan's PR appends the new
#   module to this source_modules list in the same PR. import-linter 2.x is
#   strict about missing modules ("Module 'X' does not exist"), so we only
#   list modules that exist TODAY. Future kernel modules pre-listed here
#   would break lint-imports until they land.
# Phase 2 will add: "book_pipeline.rag"
# Phase 3 will add: "book_pipeline.drafter", "book_pipeline.regenerator"
# Phase 4 will add: "book_pipeline.critic"
# Phase 5 will add: "book_pipeline.orchestration"
name = "Kernel packages MUST NOT import from book_specifics"
type = "forbidden"
source_modules = [
    "book_pipeline.interfaces",
    "book_pipeline.observability",
    "book_pipeline.stubs",
]
forbidden_modules = [
    "book_pipeline.book_specifics",
]
ignore_imports = []

[[tool.importlinter.contracts]]
# Same extension policy — append concrete kernel packages as they land.
name = "Interfaces MUST NOT import from concrete kernel implementations"
type = "forbidden"
source_modules = [
    "book_pipeline.interfaces",
]
forbidden_modules = [
    "book_pipeline.observability",
    "book_pipeline.stubs",
]
ignore_imports = []
```

**Deviation from the original plan:** The plan's `<interfaces>` block pre-listed future kernel packages (`rag`, `drafter`, `critic`, `regenerator`, `orchestration`) in source_modules. import-linter 2.11 errors on missing modules (`Module 'book_pipeline.drafter' does not exist.`), which bricks the gate. The documented extension policy is the fix — each phase adds its own modules as they land, which is strictly better anyway: the gate starts enforcing on each new kernel package from commit #1 rather than waiting for all phases to be present.

## The SCOPED mypy Target List (for Phase 2+ reference)

scripts/lint_imports.sh step 3 — Phase 2+ appends its new packages in the SAME PR that creates them:

```bash
uv run mypy \
  src/book_pipeline/interfaces \
  src/book_pipeline/stubs \
  src/book_pipeline/observability \
  src/book_pipeline/config \
  src/book_pipeline/openclaw \
  src/book_pipeline/cli \
  src/book_pipeline/book_specifics
# Phase 2 will add: src/book_pipeline/rag
# Phase 3 will add: src/book_pipeline/drafter src/book_pipeline/regenerator
# Phase 4 will add: src/book_pipeline/critic
# Phase 5 will add: src/book_pipeline/orchestration
```

`test_lint_imports_mypy_scope_matches_phase_1_packages` guards against a whole-tree `uv run mypy src` regression AND asserts the 6 Phase 1 targets are present — so if a future PR accidentally drops a target or switches to whole-tree, the test catches it.

## Why the Proof Test Matters

Without `test_lint_rule_catches_violation.py`, someone could silently neuter FOUND-05 and nothing would notice:

- Delete a `source_module` from a contract? The contract still loads; it just doesn't check that package anymore.
- Comment out a contract? The other contracts still pass; pytest still green.
- Switch `forbidden_modules` to an empty list? The contract technically still "passes."

The proof test actively injects a real kernel->book_specifics import on every CI run, so any regression of the above form — or any refactor that moves book_specifics out from under the contract — **fails the test with a clear message**. It's the difference between "we have a rule" and "we have a rule that bites."

The fixture writes `src/book_pipeline/observability/_lint_violation_probe.py` containing `from book_pipeline.book_specifics import corpus_paths`, runs `uv run lint-imports`, asserts exit code != 0 AND that the output mentions `book_specifics` or `kernel packages`, then unlinks the probe in a `finally` block. A separate guard test (`test_violation_file_does_not_exist_in_clean_tree`) fails fast if a previous test run didn't clean up.

## Verification Evidence

Plan `<success_criteria>` + task `<acceptance_criteria>` full table:

| Criterion                                                                                                          | Status | Evidence                                                                                      |
| ------------------------------------------------------------------------------------------------------------------ | ------ | --------------------------------------------------------------------------------------------- |
| `pyproject.toml` contains `[tool.importlinter]` section                                                            | PASS   | grep confirmed                                                                                |
| `pyproject.toml` contains 2 `[[tool.importlinter.contracts]]` blocks                                               | PASS   | grep -c = 2                                                                                   |
| source_modules includes `book_pipeline.interfaces`, `book_pipeline.observability`, `book_pipeline.stubs`           | PASS   | grep confirmed all 3                                                                          |
| forbidden_modules includes `book_pipeline.book_specifics`                                                          | PASS   | grep confirmed                                                                                |
| book_specifics/__init__.py, corpus_paths.py, nahuatl_entities.py all exist                                         | PASS   | all 3 files created                                                                           |
| CORPUS_ROOT constant in corpus_paths.py                                                                            | PASS   | grep confirmed                                                                                |
| NAHUATL_CANONICAL_NAMES dict in nahuatl_entities.py                                                                | PASS   | grep confirmed                                                                                |
| scripts/lint_imports.sh is executable (`test -x`)                                                                  | PASS   | `-rwxrwxr-x` mode                                                                             |
| scripts/lint_imports.sh mypy step scoped: no `uv run mypy src`; has all 6 scoped targets                            | PASS   | `test_lint_imports_mypy_scope_matches_phase_1_packages` green                                 |
| `uv run lint-imports` exits 0 against committed tree                                                               | PASS   | "Contracts: 2 kept, 0 broken."                                                                |
| `bash scripts/lint_imports.sh` exits 0 (all 3 steps)                                                               | PASS   | "OK — module boundaries, ruff, and scoped mypy all pass."                                     |
| `uv run pytest tests/test_import_contracts.py -x` all 4 tests pass                                                 | PASS   | `4 passed in 0.53s`                                                                           |
| .pre-commit-config.yaml contains local lint-imports hook with `entry: bash scripts/lint_imports.sh`                | PASS   | confirmed in the appended block                                                               |
| tests/test_lint_rule_catches_violation.py exists with 3 tests                                                      | PASS   | 3 test functions                                                                              |
| `uv run pytest tests/test_lint_rule_catches_violation.py -x -v` passes all 3 tests                                 | PASS   | `3 passed in 1.05s`                                                                           |
| After test run, `src/book_pipeline/observability/_lint_violation_probe.py` does NOT exist                           | PASS   | `test ! -f ...` succeeded post-run                                                            |
| Violation test asserts stdout/stderr mentions `book_specifics` OR `kernel packages`                                | PASS   | loose-match assertion green                                                                   |
| `test_lint_imports_passes_again_after_cleanup` confirms idempotency                                                | PASS   | green                                                                                         |
| `uv run lint-imports` manually after pytest returns 0                                                              | PASS   | "Contracts: 2 kept, 0 broken." post-run                                                       |
| Full regression suite (pytest tests/)                                                                              | PASS   | `111 passed in 3.10s`                                                                         |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] import-linter contract source_modules pre-listed future kernel packages — lint-imports errored on missing modules**

- **Found during:** Task 1 verify step (first `uv run lint-imports` after writing pyproject.toml)
- **Issue:** The plan's `<interfaces>` block wrote source_modules containing `book_pipeline.rag`, `book_pipeline.drafter`, `book_pipeline.critic`, `book_pipeline.regenerator`, `book_pipeline.orchestration`. The plan's `<context>` comment claimed: "import-linter handles missing source_modules by simply finding nothing to check — this is fine." This was not true for import-linter 2.11 (installed via plan 01-01). v2.11 emits `Module 'book_pipeline.drafter' does not exist.` and exits non-zero, which would fail FOUND-05's own success criterion (`uv run lint-imports` exits 0).
- **Fix:** Reduced source_modules to the 3 kernel modules that exist today (`interfaces`, `observability`, `stubs`) in contract 1, and to `[interfaces, observability, stubs]` in contract 2's forbidden_modules. Added extension-policy comments in-line in pyproject.toml so Phase 2+ authors see the instruction at the point of edit: each phase appends its new kernel packages to these lists in the SAME PR that creates the packages. This matches the identical policy already documented for the mypy-target list in scripts/lint_imports.sh (one policy, two lists).
- **Rationale:** The append-as-you-add policy is strictly better than the pre-list approach even independent of the version issue: Phase 2+ packages get enforcement from commit #1 rather than waiting for all phases to land. Phase 2+ PRs touch pyproject.toml and scripts/lint_imports.sh in lockstep, which is a trivially small change and mirrors how mypy scoping is already extended.
- **Files modified:** `pyproject.toml`
- **Commit:** `d338942`

**2. [Rule 3 - Blocking] ruff SIM105 pre-existing error in src/book_pipeline/cli/main.py blocked aggregate gate**

- **Found during:** Task 1 verify step (running `bash scripts/lint_imports.sh` after writing it)
- **Issue:** Plan 01-01's `main.py` used `try/except ImportError/pass`, which ruff's SIM105 flags. Plan 01-05's SUMMARY explicitly out-of-scope-flagged this for the orchestrator. This plan's aggregate gate now surfaces it — the gate cannot exit 0 on the committed tree without the fix.
- **Fix:** Replaced with `with contextlib.suppress(ImportError): importlib.import_module(dotted)`. Added `import contextlib` to the imports. Semantics unchanged.
- **Files modified:** `src/book_pipeline/cli/main.py`
- **Rationale for crossing the scope-boundary:** The plan's own success criterion requires `bash scripts/lint_imports.sh` to exit 0 on the committed tree. Leaving pre-existing ruff errors in place would make this plan's own deliverable fail its own gate — a contradiction. The fix is a 3-line trivial refactor with zero behavior change.
- **Commit:** `d338942`

**3. [Rule 3 - Blocking] ruff F841 pre-existing error in tests/test_cli_skeleton.py blocked aggregate gate**

- **Found during:** Task 1 verify step
- **Issue:** `rc = main(["--help"]) if False else None` — dead assignment; `if False` branch never taken; variable never used.
- **Fix:** Removed the line; kept the explanatory comment about argparse raising SystemExit.
- **Files modified:** `tests/test_cli_skeleton.py`
- **Rationale:** same as above — aggregate gate can't exit 0 without fixing pre-existing ruff errors in ruff's `src tests` scope.
- **Commit:** `d338942`

**4. [Rule 3 - Blocking] mypy func-returns-value pre-existing error in src/book_pipeline/cli/openclaw_cmd.py blocked aggregate gate**

- **Found during:** Task 1 verify step (mypy step of scripts/lint_imports.sh)
- **Issue:** Plan 01-04's `openclaw_cmd.py:52` used `lambda _a: (p.print_help(), 0)[1]` — a tuple-index hack to make a lambda return 0. mypy --strict flags this because `p.print_help()` is typed `-> None` and mypy's error checker emits `"print_help" of "ArgumentParser" does not return a value`. Plan 01-05's SUMMARY flagged this for the orchestrator.
- **Fix:** Rewrote as a proper `def _show_help(_a: argparse.Namespace) -> int: p.print_help(); return 0` nested function, used `p.set_defaults(_handler=_show_help)`. Same semantics, mypy-strict clean.
- **Files modified:** `src/book_pipeline/cli/openclaw_cmd.py`
- **Rationale:** same as #2 — aggregate gate cannot exit 0 without this.
- **Commit:** `d338942`

---

**Total deviations:** 4 auto-fixed (1 Rule 1 plan-inaccuracy fix, 3 Rule 3 pre-existing-error fixes).
**Impact on plan:** All 4 deviations were necessary for the plan's own success criteria to pass. No scope creep: every fix was minimal, explicitly documented, and behavior-preserving. The 3 Rule 3 fixes were pre-existing issues that plan 01-05's SUMMARY already flagged for the orchestrator — this plan's aggregate gate was the natural forcing function.

## Issues Encountered

None beyond the deviations above. The proof-test fixture teardown works reliably on both pass AND fail paths (confirmed via `test ! -f _lint_violation_probe.py` after test run); the plan's built-in guard test (`test_violation_file_does_not_exist_in_clean_tree`) provides a fail-fast check on the next run if teardown ever regresses.

## Authentication Gates

None. This plan is entirely local (no network, no LLM calls, no secrets). FOUND-05 is a static-analysis layer.

## Deferred Issues

None for this plan's scope. Every acceptance criterion has an automated check; every verify-block command runs green on the current main branch.

**Future work already named by plan 01-05 that this plan helped clean up (not fully resolved):**

- Plan 01-05 flagged ruff warnings in `src/book_pipeline/cli/version.py`. Those did NOT resurface in my ruff `src tests` run — plan 01-05 must have been looking at an older ruff version or a different invocation. If any re-surface in a later phase, they'll land as a new Rule 3 fix then.
- Plan 01-05's other flagged ruff warnings in `src/book_pipeline/openclaw/bootstrap.py` and `tests/test_openclaw.py` also did NOT re-surface. Same reasoning.

## Known Stubs

None. Every artifact shipped by this plan is fully functional:

- `CORPUS_ROOT` is a real `Path` pointing at `~/Source/our-lady-of-champion` (the read-only corpus sibling repo).
- `NAHUATL_CANONICAL_NAMES` is populated with 6 real canonicalization entries.
- `scripts/lint_imports.sh` runs real `uv run lint-imports` + `uv run ruff check` + `uv run mypy`; exits non-zero on any failure.
- The proof test actively writes + reads + deletes a real probe file on every invocation.

The `source_modules` list being shorter than the plan's original draft is NOT a stub — it's the documented extension policy. Phase 2+ packages are enforced starting the same PR that creates them, not later.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`:

- **T-06-01 (Tampering — developer edits pyproject.toml to remove a source_module) — MITIGATED:** `test_lint_rule_catches_violation.py` actively injects a real violation on every CI run; tampering that disables the rule will cause that test to go green when it should fail, which the test's own assertion catches (the test ASSERTS the rule bites — if it doesn't, pytest fails). Additionally, the `test_kernel_does_not_import_book_specifics` static grep fallback catches the common regression class of a commented-out contract.
- **T-06-02 (Repudiation — violation slips through by skipping pre-commit) — MITIGATED:** `scripts/lint_imports.sh` is designed to be the CI entry point (Phase 2 will add GitHub Actions per CONTEXT.md deferred ideas). The pre-push hook catches at push time as a belt-and-suspenders defense.
- **T-06-03 (DoS — import-linter hangs on circular imports) — ACCEPTED:** Module graph is small (53 files, 96 dependencies per lint-imports output); import-linter has built-in timeout.

No new threat flags surfaced during execution.

## Self-Check: PASSED

Artifact verification (files on disk):

- FOUND: `src/book_pipeline/book_specifics/__init__.py`
- FOUND: `src/book_pipeline/book_specifics/corpus_paths.py` (contains `CORPUS_ROOT`)
- FOUND: `src/book_pipeline/book_specifics/nahuatl_entities.py` (contains `NAHUATL_CANONICAL_NAMES`)
- FOUND: `scripts/lint_imports.sh` (executable, `-rwxrwxr-x`)
- FOUND: `tests/test_import_contracts.py` (4 tests, all green)
- FOUND: `tests/test_lint_rule_catches_violation.py` (3 tests, all green)
- FOUND: `pyproject.toml` contains `[tool.importlinter]` section + 2 `[[tool.importlinter.contracts]]` blocks
- FOUND: `.pre-commit-config.yaml` contains local `lint-imports` hook at `stages: [pre-push]`
- NOT FOUND (as expected): `src/book_pipeline/observability/_lint_violation_probe.py` (fixture cleanup confirmed)

Commit verification on `main` branch of `/home/admin/Source/our-lady-book-pipeline/`:

- FOUND: `d338942 feat(01-06): add import-linter contracts + book_specifics module + lint_imports.sh`
- FOUND: `1a9f3c2 test(01-06): add proof test that import-linter catches FOUND-05 violation`

Both per-task commits landed on `main` branch. FOUND-05 is LIVE.

## Phase 1 Acceptance Checklist — ALL 6 REQ-IDs COVERED

Phase 1 exit criteria per CONTEXT.md:

| Plan  | REQ-ID    | Status | Evidence                                                                                            |
| ----- | --------- | ------ | --------------------------------------------------------------------------------------------------- |
| 01-01 | FOUND-01  | DONE   | `uv run book-pipeline --version` exits 0 with `book-pipeline 0.1.0`; CLI dispatcher with `register_subcommand` API shipped |
| 01-02 | FOUND-04  | DONE   | 13 Protocols in `book_pipeline.interfaces`; stub implementations pass `isinstance(stub, Protocol)` |
| 01-03 | FOUND-02  | DONE   | Pydantic-Settings 2 + PyYAML; 4 config files validated at startup; `validate-config` CLI            |
| 01-04 | FOUND-03  | DONE   | `openclaw.json` at repo root; drafter workspace skeleton; `openclaw bootstrap` CLI                  |
| 01-05 | OBS-01    | DONE   | Concrete `JsonlEventLogger` + `hash_text`/`event_id` helpers + `smoke-event` CLI (smoke_test + drafter roles) |
| 01-06 | FOUND-05  | **DONE (this plan)** | import-linter contracts enforcing kernel<->book_specifics boundary + book_specifics module + aggregate gate + proof test |

**Phase 1 is COMPLETE.** The observability plane that watches drafting is operational, every required interface has a Protocol and a stub, config is typed and validated, openclaw is bootstrapped, and module boundaries are machine-enforced.

## Next Phase Readiness

- **Phase 2 (RAG-01) extension points:**
    - Append `"book_pipeline.rag"` to `source_modules` in BOTH `[[tool.importlinter.contracts]]` blocks in pyproject.toml.
    - Append `src/book_pipeline/rag` to the mypy-target list in `scripts/lint_imports.sh`.
    - Both edits in the SAME PR that creates `src/book_pipeline/rag/`.
- **Phase 2 CI readiness:** `scripts/lint_imports.sh` is the ready-to-go aggregate gate — GitHub Actions (or whatever Phase 2 picks) just needs one step: `bash scripts/lint_imports.sh`.
- **No blockers.** Phase 1 fully closes.

---
*Phase: 01-foundation-observability-baseline*
*Plan: 06*
*Completed: 2026-04-22*
