---
phase: 04-chapter-assembly-post-commit-dag
plan: 06
subsystem: e2e-integration-regression-test
tags: [e2e-integration, loop-02, loop-03, loop-04, crit-02, corpus-02, test-01, phase-4-gate, regression-test, mocked-llm]
requirements_completed: [LOOP-02, LOOP-03, LOOP-04, CRIT-02, CORPUS-02, TEST-01]
dependency_graph:
  requires:
    - "04-01 (kernel skeletons + ChapterStateMachine — the integration test imports ChapterState/ChapterStateRecord for state-record assertions)"
    - "04-02 (ConcatAssembler + ChapterCritic — happy-path test invokes both indirectly through `book-pipeline chapter 99`; asserts deterministic assembled canon + lint-passing chapter critic flow)"
    - "04-03 (OpusEntityExtractor + OpusRetrospectiveWriter — test invokes both via the DAG orchestrator; asserts entity-state JSON validates through EntityExtractionResponse + retrospective md passes `lint_retrospective`)"
    - "04-04 (ChapterDagOrchestrator — the test's orchestration target; asserts 4-commit DAG + pipeline_state.json LOOP-04 gate)"
    - "04-05 (cli/chapter.py composition root — the test invokes `_run(argparse.Namespace(chapter_num=99, expected_scene_count=3, no_archive=False))` directly; the composition root wires all 11 kernel deps + book-domain seams)"
  provides:
    - "tests/integration/__init__.py — package marker (empty)"
    - "tests/integration/conftest.py — 5 pytest fixtures (tmp_repo, mock_llm_client, mock_retrievers_factory, mock_embedder_and_reranker, bundler_fingerprint_spy) + MockLLMClient + BundlerSpy + module-level DEFAULT_VOICE_PIN_SHA / ALT_VOICE_PIN_SHA constants + install_llm_client_monkeypatch helper"
    - "tests/integration/test_chapter_dag_end_to_end.py — 3 non-slow tests (happy path + mid-chapter-pin-upgrade + chapter-critic-fail-no-canon-commit) regression-guarding every Phase 4 success criterion"
    - "tests/integration/fixtures/ch99_sc0{1,2,3}.md — 3 realistic-prose scene fixtures with valid Plan 03-07 B-3 frontmatter (voice_pin_sha == checkpoint_sha + 5-axis critic scores + pov/date_iso/location + 70-word Cortes-era narrative body per scene)"
  affects:
    - "Phase 5 (ORCH-01 nightly cron) — regression-guards the `book-pipeline chapter <N>` invariant: Phase 5 cron can reuse `_run(args)` directly to drive the per-chapter DAG, and this test guarantees the exit-code contract (0/2/3/4) stays stable."
    - "Phase 6 (TEST-03 ablation execution) — relies on the Phase 4 DAG being idempotent + atomic; Plan 04-06 test is the single point that catches regressions in the 4-commit sequence or the pipeline_state.json gate format Phase 6 will read."
    - "Phase 6 (OBS-02 ingester) — the test's events.jsonl-shape assertion (`role ∈ {chapter_critic, entity_extractor, retrospective_writer}` + `caller_context.chapter_num == 99`) locks in the OBS-02 partition contract end-to-end."
    - "All future Phase 4 bug-fixes or refactors — this is the ONE test that proves Phase 4 works end-to-end; if a Plan 04-0X refactor breaks composition, this test is the failure alarm."
tech-stack:
  added: []  # No new runtime deps. pytest + yaml + subprocess + stdlib json all already-used. Mock seams are pure Python dataclasses / monkeypatch.
  patterns:
    - "E2E integration test with tmp_path `git init` + real git subprocess + fully-mocked LLM: the test is unit-grain (<8s wall-clock) but covers the full composition root + DAG + disk side-effects + git log. Every LLM surface is swapped via monkeypatch.setattr on cli.chapter module attributes (build_llm_client, build_retrievers_from_config, BgeM3Embedder, BgeReranker, ContextPackBundlerImpl.bundle). Real git subprocess runs inside tmp_path with a fresh `git init -q --initial-branch=main` + local `user.name`/`user.email` config + pre-commit hooks disabled (rm on every .git/hooks/* file). Zero dependency on the real repo's git state; zero dependency on the real Anthropic/vLLM network."
    - "Symlink-not-copy for template assets: the tmp_repo fixture does `(tmp_path / 'src').symlink_to(REPO_ROOT / 'src')` so the `DEFAULT_{CHAPTER,EXTRACTOR,RETROSPECTIVE}_TEMPLATE_PATH = Path('src/book_pipeline/.../templates/*.j2')` relative paths (unchanged from Plans 04-02 + 04-03) resolve transparently after monkeypatch.chdir(tmp_path). Alternative (shutil.copytree of the whole src/ tree) would have been slower + fragile. Alternative (monkeypatch the DEFAULT_*_TEMPLATE_PATH constants to absolute paths) would have coupled the test to production module internals. Symlink is the cheapest path that preserves behavior."
    - "MockLLMClient as a dataclass facade: messages.parse dispatches on `output_format.__name__` ('CriticResponse' → pass-by-default CriticResponse; 'EntityExtractionResponse' → a single Cortes EntityCard). messages.create returns a fixed lint-passing markdown. All returns flow through the real ParseResponse/CreateResponse dataclasses from `llm_clients.claude_code` so the callers' `.parsed_output` / `.content[0].text` access paths exercise the real SDK-compat shim. Tests override per-call by mutating `mock_llm_client.messages.critic_overall_pass = False` before invoking `_run`."
    - "BundlerSpy via class-method monkeypatch: `monkeypatch.setattr(ContextPackBundlerImpl, 'bundle', _spy_bundle)` replaces the method on the class itself rather than the instance — this catches every bundler constructed downstream, including the one cli/chapter.py builds at `_build_dag_orchestrator` time. The spy records (SceneRequest, fingerprint) pairs for later assertion + returns a minimal ContextPack that skips the real conflict detector + budget enforcer (those need real RetrievalResults our fakes don't produce). Fresh-pack-invariant assertion: find at least 1 call with `scene_request.scene_index == 0 AND beat_function == 'chapter_overview'`, then assert its fingerprint is not in any other call's fingerprint set. Future-proof for Plan 05+ variants where scene-level packs might also flow through the spy."
    - "Hooks-disabled tmp_repo idiom: after `git init`, the fixture does `for hook in .git/hooks/*: hook.unlink()`. Git hook samples that are *.sample (not executable) don't fire anyway, but real git installations sometimes carry an active `pre-commit` hook that the `git init` template copied in. Preemptively nuking them means the test's `commit_paths` calls can never hit an unexpected hook failure. CLAUDE.md's NEVER --no-verify rule remains respected because `commit_paths` still invokes git commit without the --no-verify flag — there's just nothing for git to invoke hook-side."
    - "Environment-var sanitation belt-and-suspenders: `monkeypatch.setenv('ANTHROPIC_API_KEY', '')` inside `tmp_repo` ensures that even if a mock seam accidentally falls through to the real `anthropic.Anthropic()` SDK, no credential is available to make a network call. Paired with the ANTHROPIC_API_KEY=='' check in the MockLLMClient path, this is double-insurance against accidental live-API traffic in the test suite — satisfies the plan prompt's NO real Anthropic API call hard constraint."
    - "Parametrize variants as SIBLING tests (not @pytest.mark.parametrize): 3 tests live as separate top-level functions — `test_end_to_end_3_scene_stub_chapter_dag` (happy path), `test_end_to_end_mid_chapter_pin_upgrade` (sc02 pin rewrite), `test_chapter_critic_fail_no_canon_commit` (critic fail). Rationale: each variant has a different set of assertions (the happy path has 9 assertion groups; the mid-upgrade test focuses on voice_pin_shas size == 2; the fail test focuses on no-commit + state=CHAPTER_FAIL). A single parametrized function would need conditional-assertion branches that hide WHAT each variant guards. 3 focused tests produce 3 focused failure messages, which is the whole reason this plan exists (any regression points at a specific criterion)."
    - "Absolute-path directory anchors for the orchestrator (Rule 1 deviation, Task 2 GREEN): cli/chapter.py's `_build_dag_orchestrator` now passes `repo_root / 'canon'` (etc.) rather than `Path('canon')` — the orchestrator's `canon_path.relative_to(repo_root)` requires absolute args. Plan 04-05's bare-relative shape worked when cwd==repo_root (which was always the case in unit tests), but the integration test's `monkeypatch.chdir(tmp_path)` + `repo_root=Path.cwd()=tmp_path` combo exposed the broken invariant when `Path('canon/chapter_99.md').relative_to(tmp_path_absolute)` raised ValueError. The fix preserves behavior when caller cwd == repo_root + makes the orchestrator-to-git path resolution robust to chdir."
key-files:
  created:
    - "tests/integration/__init__.py (empty package marker)"
    - "tests/integration/conftest.py (521 lines; 5 fixtures + MockLLMClient + BundlerSpy + install_llm_client_monkeypatch helper)"
    - "tests/integration/test_chapter_dag_end_to_end.py (424 lines; 3 non-slow tests covering happy path + mid-chapter-pin-upgrade + chapter-critic-fail)"
    - "tests/integration/fixtures/ch99_sc01.md (20 lines; realistic 70-word Cortes-era narrative body + B-3 frontmatter)"
    - "tests/integration/fixtures/ch99_sc02.md (20 lines; same frontmatter shape; Cempoala gift-exchange body)"
    - "tests/integration/fixtures/ch99_sc03.md (20 lines; same frontmatter shape; Tlaxcala-bound departure body)"
    - ".planning/phases/04-chapter-assembly-post-commit-dag/04-06-SUMMARY.md (this file)"
  modified:
    - "src/book_pipeline/cli/chapter.py (Task 2 GREEN: `_build_dag_orchestrator` now passes absolute directory anchors — `repo_root / 'canon'` instead of bare `Path('canon')` — so `.relative_to(repo_root)` works inside the orchestrator regardless of cwd. 15 insertions + 9 deletions; no behavior change when cwd==repo_root. Rule 1 bug-fix deviation from Plan 04-05.)"
key-decisions:
  - "(04-06) Monkeypatch at the `book_pipeline.cli.chapter` module namespace, NOT at the source modules. cli/chapter.py does `from book_pipeline.llm_clients import build_llm_client` at module load — so the `build_llm_client` name resolved inside `_build_dag_orchestrator` is the one in `chapter`'s namespace, not the one in `llm_clients.factory`. Same for `BgeM3Embedder`, `BgeReranker`, `build_retrievers_from_config`. Monkeypatch.setattr on the `cli.chapter` module attributes reaches the call-site binding. Alternative (mock.patch.object with explicit dotted path) would work but bloats each test; the chosen idiom matches the Plan 04-05 `test_chapter_cli.py` precedent exactly."
  - "(04-06) `ContextPackBundlerImpl.bundle` is monkey-patched on the CLASS (not the instance) so the real `ContextPackBundlerImpl.__init__` still runs normally. The wrapped method returns a synthetic ContextPack with `fingerprint=f'chapter_pack_fp_{request.scene_index}_{request.beat_function}'` — deterministic + easy to inspect in the spy's `calls` list. The real bundler's conflict detector + budget enforcer are bypassed because our fake retrievers return empty hits; exercising the real code paths would require a full LanceDB setup (out of scope for this test)."
  - "(04-06) Test asserts `voice_pin_shas == [DEFAULT_VOICE_PIN_SHA]` in the happy-path variant. All three scene fixtures share the same pin; ConcatAssembler dedupes preserving order — so the list has exactly one entry. The `test_end_to_end_mid_chapter_pin_upgrade` variant rewrites sc02's pin to a different sha before `_run` — asserting `voice_pin_shas == [DEFAULT, ALT]` size 2 (order preserved). This regression-guards both the dedup AND the order-preservation properties of ConcatAssembler's `voice_pin_shas` aggregation."
  - "(04-06) The three tests split by failure-mode granularity rather than `@pytest.mark.parametrize`. Each test's failure message points at a specific Phase 4 success criterion — so if sc02-rewrite breaks in isolation, the test title tells the operator exactly which feature regressed. Parametrization would force shared assertions + conditional branches + a single failure surface. Scaling cost: 3x boilerplate for the `_install_common_monkeypatches` + `args = Namespace(...)` setup — acceptable for ONE E2E test file in the whole Phase."
  - "(04-06) The test bypasses `subprocess.run(['uv', 'run', 'book-pipeline', 'chapter', '99'])` and instead calls `chapter_mod._run(argparse.Namespace(chapter_num=99, ...))` directly. Rationale: injecting the fake LLM client + fake retrievers + embedder/reranker through a subprocess boundary would require env-var + entry-point hacks (or a monkey-patched `sys.modules['book_pipeline.cli.chapter']`). Direct `_run` invocation sits one layer above the argparse parser but still exercises the full composition root — the assertions we care about (4 git commits + on-disk artifacts + pipeline_state + events.jsonl + fresh-pack invariant + lint-pass) all land regardless of whether argparse or a Namespace handed us the args."
  - "(04-06) Task 2 GREEN landed a Rule 1 bug-fix in cli/chapter.py (relative → absolute directory anchors) rather than working around the bug inside the test. The bug was pre-existing (Plan 04-05 missed it because all 04-05 unit tests mock `_build_dag_orchestrator` entirely and never exercise the real composition path + real ChapterDagOrchestrator + real disk paths together). The plan-4 E2E test is the FIRST caller that exercises the composition root against real disk. Fixing the cli/chapter.py path bug preserves the invariant for Phase 5 cron + every future integration test + every real user invocation of `book-pipeline chapter <N>`. The alternative (test-only workaround via a `Path.cwd()` monkeypatch) would have papered over a real latent bug."
  - "(04-06) tmp_repo fixture deletes all `.git/hooks/*` files post `git init`. Rationale: the developer's global git install may carry a globally-configured pre-commit hook (via `git config --global core.hooksPath`) that gets copied into the fresh repo's hooks dir by `git init`'s template mechanism. Any real hook firing during the test's `git commit` calls would risk spurious failures unrelated to what the test is checking. Nuking all hooks at fixture-setup time is the cheapest guarantee. CLAUDE.md's NEVER --no-verify rule stays respected — `commit_paths` doesn't pass --no-verify; there's just no hook to invoke."
  - "(04-06) MockLLMClient's messages.parse consumes 2 different output_format types (`CriticResponse` + `EntityExtractionResponse`) without maintaining separate per-type call tracking. The parse_calls list stores `(output_format.__name__, messages)` tuples — tests assert on the count of each name via `parse_calls.count('CriticResponse') == 1` etc. This gives us partition-level traceability without a separate registry. A fifth Opus caller in Phase 6 (digest generator) would extend trivially."
metrics:
  duration_minutes: 38
  completed_date: 2026-04-23
  tasks_completed: 2
  files_created: 6  # __init__.py, conftest.py, test_chapter_dag_end_to_end.py, 3 scene fixtures
  files_modified: 1  # src/book_pipeline/cli/chapter.py (absolute-path anchors)
  tests_added: 3  # 1 happy-path + 2 parametrize variants (mid-pin-upgrade + critic-fail)
  tests_passing: 511  # was 508 baseline; +3 new integration tests
  tests_baseline: 508
  slow_tests_added: 0
  integration_test_runtime_s: 7.5  # ~7.47s wall-clock for all 3 tests combined; well under the 30s plan target
  scoped_mypy_source_files_after: 120  # unchanged (Plan 04-05 added 4 CLI source files; Plan 04-06 landed only tests + 1 cli edit)
commits:
  - hash: e558989
    type: test
    summary: "Task 1 — integration conftest + 3 scene fixtures"
  - hash: 27ef6be
    type: test
    summary: "Task 2 RED — failing E2E integration test for Phase 4 DAG"
  - hash: bde9f07
    type: feat
    summary: "Task 2 GREEN — cli/chapter.py absolute directory anchors"
---

# Phase 4 Plan 06: End-to-End Integration Test Summary

**One-liner:** Phase 4 ships its regression guardrail — a single end-to-end integration test (`tests/integration/test_chapter_dag_end_to_end.py`, 3 non-slow sibling tests, 424 LOC) that exercises Plans 04-01..04-05 composed together against a fully-mocked LLM backend in a `git init`-ed `tmp_path` repo. The happy-path test asserts all 9 Phase 4 success criteria in one run: 4 atomic git commits in strict order (`canon(ch99)` → `chore(entity-state)` → `chore(rag)` → `docs(retro)`), deterministic `canon/chapter_99.md` with B-3-preserved `voice_pin_shas: [single_sha]` frontmatter + 3 HTML scene markers + 2 section separators, `entity-state/chapter_99_entities.json` validating through `EntityExtractionResponse` with every `source_chapter_sha == captured canon commit sha`, `retrospectives/chapter_99.md` passing `lint_retrospective` cleanly, `.planning/pipeline_state.json` carrying `dag_complete=True` + `last_committed_chapter=99` for LOOP-04 gate readiness, fresh-pack invariant enforced through a `ContextPackBundlerImpl.bundle` class-method spy (chapter pack's fingerprint is disjoint from any other bundle call's fingerprint), and events.jsonl carrying all 3 Phase 4 Opus roles (`chapter_critic` + `entity_extractor` + `retrospective_writer`) stamped with `caller_context.chapter_num=99`. Two parametrize-variant sibling tests regression-guard additional edge cases: `test_end_to_end_mid_chapter_pin_upgrade` (sc02 rewritten with a different voice_pin_sha → chapter frontmatter shows `voice_pin_shas: [default, alt]` size 2), and `test_chapter_critic_fail_no_canon_commit` (critic forces `overall_pass=False` → exit 3, zero new commits, state=CHAPTER_FAIL). One Rule 1 bug-fix deviation landed in Task 2 GREEN: `cli/chapter.py._build_dag_orchestrator` now passes ABSOLUTE directory anchors (`repo_root / 'canon'`) to the orchestrator instead of bare-relative `Path('canon')` so the DAG's `.relative_to(repo_root)` calls succeed when tests chdir to tmp_path. Full suite: 511 passed (+3 vs 508 baseline); integration runtime 7.47s wall-clock (well under the 30s plan budget); zero vLLM boot, zero real Anthropic/Claude-Code calls, zero real git push per the plan's hard constraint.

## Phase 4 Success Criteria — E2E Coverage Matrix

| # | Criterion | Where asserted | Assertion primitive |
|---|---|---|---|
| 1 | Deterministic assembly | happy-path test, group B | `chapter_fm['assembled_from_scenes'] == ['ch99_sc01','ch99_sc02','ch99_sc03']` + 3 HTML markers + 2 section separators in body |
| 2 | Fresh RAG pack for chapter critic | happy-path test, group G | `bundler_fingerprint_spy` records calls; chapter-scoped call's fingerprint not in any other call's fingerprint set |
| 3 | Atomic canon commit + 4-step DAG | happy-path test, group A | `git log --pretty=%s` shows 4 new commits in strict order (canon, entity-state, rag, retro); regex patterns lock each message shape |
| 4 | CHAPTER_FAIL routing (no canon commit) | critic-fail sibling test | Zero new commits post-run; `canon/chapter_99.md` does not exist; state=CHAPTER_FAIL + blocker tag "chapter_critic_axis_fail" |
| 5 | Retrospective lint pass | happy-path test, group D | `lint_retrospective(retro) == (True, [])` on the committed `retrospectives/chapter_99.md` |
| 6 | source_chapter_sha stamped + matches canon sha | happy-path test, group C | every `entity_resp.entities[*].source_chapter_sha == post_hashes[len(pre_hashes)]` (the canon commit sha) |
| 7 | B-3 invariant continuity (size 1 + size 2) | happy-path group B + mid-pin-upgrade sibling | `voice_pin_shas == [DEFAULT]` for happy path; `voice_pin_shas == [DEFAULT, ALT]` after sc02 rewrite |
| 8 | LOOP-04 gate readiness | happy-path test, group E | `.planning/pipeline_state.json` has `last_committed_chapter==99, last_committed_dag_step==4, dag_complete==True, last_hard_block==None` |
| 9 | Event log partition shape | happy-path test, group H | `runs/events.jsonl` carries roles `{chapter_critic, entity_extractor, retrospective_writer}` + `caller_context.chapter_num==99` stamps |

## Integration Test Shape (happy path)

```
tmp_path/                            # monkeypatch.chdir() target
├── .git/                            # real git init + user.name/user.email set
├── src -> REPO_ROOT/src             # symlink so DEFAULT_*_TEMPLATE_PATH resolves
├── config/
│   ├── voice_pin.yaml               # copied from real repo
│   ├── rubric.yaml                  # copied from real repo
│   ├── rag_retrievers.yaml          # copied from real repo
│   └── mode_thresholds.yaml         # copied from real repo
├── drafts/
│   ├── ch99/
│   │   ├── ch99_sc01.md             # from tests/integration/fixtures/
│   │   ├── ch99_sc02.md
│   │   └── ch99_sc03.md
│   ├── scene_buffer/ch99/
│   │   ├── ch99_sc01.state.json     # state=COMMITTED (pre-seeded)
│   │   ├── ch99_sc02.state.json
│   │   └── ch99_sc03.state.json
│   └── chapter_buffer/              # DAG writes ch99.state.json here
├── canon/                           # DAG writes chapter_99.md here
├── entity-state/                    # DAG writes chapter_99_entities.json here
├── retrospectives/                  # DAG writes chapter_99.md here
├── indexes/
│   └── resolved_model_revision.json # ingestion_run_id=ing_test_20260422
├── runs/events.jsonl                # empty touch; DAG appends
└── .planning/pipeline_state.json    # DAG writes this after each step
```

After `_run(args)` returns 0, the above tree has 5 commits total (1 seed + 4 DAG commits) AND every assertion group passes.

## Mock Seams (5 monkeypatch points)

| Seam | Where | What it replaces |
|------|-------|------------------|
| `chapter_mod.build_llm_client` | `install_llm_client_monkeypatch` | Returns the shared `MockLLMClient` instance for all 3 Phase 4 Opus callers (chapter critic + entity extractor + retrospective writer) |
| `chapter_mod.build_retrievers_from_config` | `mock_retrievers_factory` fixture | Returns dict of 5 `_FakeRetriever` instances (historical, metaphysics, entity_state, arc_position, negative_constraint); each has `.retrieve / .reindex / .index_fingerprint` stubs |
| `chapter_mod.BgeM3Embedder` | `mock_embedder_and_reranker` fixture | No-op __init__ (skips 2GB model download); `.encode(text) -> [0.0]*1024` |
| `chapter_mod.BgeReranker` | `mock_embedder_and_reranker` fixture | No-op __init__ (skips the reranker model); `.rerank -> []` |
| `ContextPackBundlerImpl.bundle` | `bundler_fingerprint_spy` fixture | Class-method monkeypatch; records `(SceneRequest, fingerprint)` into the spy list; returns a minimal ContextPack with `fingerprint=f'chapter_pack_fp_{request.scene_index}_{request.beat_function}'` |

## Runtime Measurement

| Test | Wall clock |
|------|------------|
| `test_end_to_end_3_scene_stub_chapter_dag` | ~3.5s (happy path; full DAG + 9 assertion groups) |
| `test_end_to_end_mid_chapter_pin_upgrade` | ~2.5s (happy DAG + voice_pin_shas inspection) |
| `test_chapter_critic_fail_no_canon_commit` | ~1.5s (no DAG progression past step 1 critic; early-exit) |
| **Total (3 tests)** | **7.47s** |

Well under the plan's 30s wall-clock target. Full non-slow suite runs in 84s (was 82s pre-plan).

## Phase 4 Test-Count Delta

| Plan | Tests added | Cumulative |
|------|-------------|------------|
| pre-Phase-4 baseline | — | 431 |
| 04-01 (kernel skeletons + ChapterStateMachine) | +9 | 440 |
| 04-02 (ConcatAssembler + ChapterCritic) | +20 | 460 |
| 04-03 (OpusEntityExtractor + OpusRetrospectiveWriter) | +17 | 477 |
| 04-04 (ChapterDagOrchestrator + AblationRun) | +20* | 497 |
| 04-05 (chapter + chapter-status + ablate CLIs) | +11* | 508 |
| **04-06 (E2E integration test)** | **+3** | **511** |

Phase 4 net delta: **+80 non-slow tests** over the 431-test baseline. (`*` — the individual plan summaries stated tests_added of +17 and +16 respectively; the actual full-suite count delta recorded here nets those numbers against deselected/pre-existing rows).

## Deltas vs Plan 04-05 CLI tests

| Facet | test_chapter_cli.py (04-05) | test_chapter_dag_end_to_end.py (04-06) |
|---|---|---|
| Scope | Unit — argparse, exit-code mapping, composition wiring | E2E — full DAG from CLI entry point through 4 git commits + 3 on-disk artifacts |
| Orchestrator used | Fake `_FakeOrch` returning pre-baked records | REAL `ChapterDagOrchestrator` executing all 4 DAG steps |
| Git subprocess | Not invoked | Real `git init` + 4 real `git commit` calls in tmp_path |
| LLM mock | Per-test (ad-hoc) | Centralized `MockLLMClient` (dispatches on output_format.__name__) |
| Bundler + retrievers | Per-test fakes | Centralized via conftest fixtures |
| Runtime | ~1s for 7 tests | 7.47s for 3 tests (full stack exercise) |
| Regression target | Exit codes, arg parsing, composition wiring | Every Phase 4 success criterion in one shot |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `cli/chapter.py._build_dag_orchestrator` passed bare-relative directory anchors to `ChapterDagOrchestrator`.**

- **Found during:** Task 2 RED → running `test_end_to_end_3_scene_stub_chapter_dag` against the un-fixed cli/chapter.py yielded a `ValueError: 'canon/chapter_99.md' is not in the subpath of '/tmp/.../tmp_path'` at the orchestrator's `canon_path.relative_to(self.repo_root)` call in `dag.py:552`.
- **Issue:** Plan 04-05 shipped cli/chapter.py with `canon_dir=Path("canon")` (relative), `retros_dir=Path("retrospectives")` (relative), etc. — but `repo_root=Path.cwd()` is absolute. The orchestrator's `.relative_to(repo_root)` assumes its dir arguments are absolute. This path worked accidentally in all Plan 04-05 unit tests because those tests never exercised the real composition root + real orchestrator together (every 04-05 test mocks `_build_dag_orchestrator` entirely).
- **Fix:** `_build_dag_orchestrator` now passes `repo_root / 'canon'` (absolute) + adds a provenance comment citing Plan 04-06. Behavior unchanged when caller cwd == repo_root (the intended invocation shape); chdir-to-tmp_path tests + any future cron wrappers that call `_run` from a non-repo-root cwd now work correctly.
- **Files modified:** `src/book_pipeline/cli/chapter.py` (15 insertions, 9 deletions).
- **Commit:** `bde9f07` (Task 2 GREEN, landed after Task 2 RED commit `27ef6be` proved the failure).
- **Scope:** Rule 1 — latent Plan 04-05 bug exposed by Plan 04-06 E2E test; fixed at the source rather than worked around in the test.

**2. [Rule 1 - Bug] Ruff SIM105 on `try-except-pass` inside the tmp_repo fixture.**

- **Found during:** Task 2 GREEN `bash scripts/lint_imports.sh`.
- **Issue:** `tests/integration/conftest.py` had `try: hook.unlink() except OSError: pass` inside the hook-cleanup loop.
- **Fix:** `with contextlib.suppress(OSError): hook.unlink()`. Semantically identical; SIM105 hard-fail cleared.
- **Files modified:** `tests/integration/conftest.py` (added `import contextlib`).
- **Commit:** folded into `27ef6be` (Task 2 RED, before the RED-GREEN split commit was authored).
- **Scope:** Ruff hard-fail caught during Task 2 authoring. Rule 1.

**3. [Rule 1 - Bug] Ruff I001 import-order on `test_chapter_dag_end_to_end.py`.**

- **Found during:** Task 2 GREEN `bash scripts/lint_imports.sh`.
- **Issue:** The import block mixed book_pipeline + tests.integration.conftest imports without the proper blank-line separator.
- **Fix:** `uv run ruff check tests/integration --fix` auto-sorted the blocks.
- **Files modified:** `tests/integration/test_chapter_dag_end_to_end.py`.
- **Commit:** folded into `27ef6be` (Task 2 RED).
- **Scope:** Rule 1 — ruff hard-fail.

**Total deviations:** 3 auto-fixed (2 Rule 1 ruff false-positives + 1 Rule 1 pre-existing latent bug in cli/chapter.py). **Zero Rule 2/3/4 escalations.** Plan shape unchanged — the integration test + conftest + 3 scene fixtures all land exactly as specified in 04-06-PLAN.md; happy path + mid-chapter-pin-upgrade + critic-fail variants + all 9 Phase 4 success-criterion assertion groups match plan spec verbatim.

## Authentication Gates

**None.** Plan 04-06 does not touch the real Anthropic API, the real Claude Code CLI, the openclaw gateway, or vLLM. All LLM surfaces are mocked via `MockLLMClient`. Git is LOCAL — the test's `git init` happens inside `tmp_path` with no remote. No `git push`/`fetch`/`clone`/`remote` interaction. No network traffic of any kind. Hard constraint from the plan prompt respected verbatim.

Belt-and-suspenders: the `tmp_repo` fixture sets `monkeypatch.setenv("ANTHROPIC_API_KEY", "")` so even if a mock seam accidentally fell through, no credential would be available.

## Deferred Issues

1. **`lancedb.table_names()` deprecation warning** (~230 instances in the non-slow suite). Inherited from Phase 2 + Phase 3 + Plans 04-03/04. No functional impact. Not a Plan 04-06 concern.
2. **`tests/rag/test_golden_queries.py::test_golden_queries_pass_on_baseline_ingest`** — 1 PRE-EXISTING Phase 2 RAG baseline drift. Deselected in this plan's full-suite run. Unrelated to Plan 04-06. Tracked for Phase 6 OBS-02 digest-panel surfacing.
3. **Integration test's `src` symlink depends on repo-layout stability.** The `tmp_repo` fixture does `(tmp_path / 'src').symlink_to(REPO_ROOT / 'src')`. If the `src/book_pipeline/.../templates/` path ever moves, this fixture breaks. Alternative (monkeypatch the DEFAULT_*_TEMPLATE_PATH constants) is a reasonable future refactor, but would couple the test to production module internals; symlink is currently simpler.
4. **`_FakeRetriever` + spy bundler bypass the real retriever/budget pipeline.** The test doesn't exercise the real `ContextPackBundlerImpl.bundle` body (budget enforcement, conflict detection, round-robin assembly). That's Plan 02-05's test domain — Plan 04-06 scope is the composition + DAG + disk side-effects. A hypothetical Plan 05-0X "live-RAG integration test" could exercise the real bundler path against a tiny pre-seeded LanceDB; deferred for now.
5. **Test asserts 4 new commits BUT tolerates variations in commit message wording inside the regex.** E.g. `canon(ch99): commit chapter 99` matches the pattern `^canon\(ch99\):`. If a future plan changes the canonical commit message shape, the regex needs updating. Not a fragility concern — the git-commit message shape is a load-bearing contract across Plans 04-04 + 04-05 + 04-06 + Phase 5 cron.

## Known Stubs

**None.** Every file shipped carries either:
- Concrete implementation (cli/chapter.py fix with absolute path anchors).
- Concrete test coverage (3 passing tests across 3 Phase 4 sub-flows).
- Concrete fixtures (3 scene md files with realistic Cortes-era prose + valid B-3 frontmatter).

No hardcoded empty values flowing to UI. No "coming soon" placeholders. No TODOs. MockLLMClient's scripted responses are SUFFICIENT for the E2E integration test; they are deliberately minimal (1 axis-pass for each axis, 1 EntityCard, 1 lint-passing retro) — this matches the plan's stated mock-simplicity posture. Additional per-call variation (e.g. critic-pass-then-fail mid-run) would be Phase 5 routing tests' territory.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 4 threats in the register are covered as planned:

- **T-04-06-01** (Tampering: test mutates real repo canon/): MITIGATED. `monkeypatch.chdir(tmp_path)` at fixture-setup time. Every write path resolves through the new cwd. The symlink `tmp_path/src -> REPO_ROOT/src` is READ-ONLY from the test's perspective (only jinja template reads + module imports traverse it). No writes land outside tmp_path.
- **T-04-06-02** (EoP: Mock LLM client leaks API key or subprocess side effect): MITIGATED. MockLLMClient is a pure Python dataclass — NO subprocess, NO network. `monkeypatch.setenv("ANTHROPIC_API_KEY", "")` in fixture provides double-insurance. `ps aux` during the test shows no `vllm` or `claude -p` process.
- **T-04-06-03** (Repudiation: Integration test failure masks which Plan regressed): MITIGATED. Happy-path assertions are grouped A-I with inline comments citing each Phase 4 success criterion; the 3 sibling tests have descriptive names (`_3_scene_stub_chapter_dag`, `_mid_chapter_pin_upgrade`, `_chapter_critic_fail_no_canon_commit`) so the failure's target plan is unambiguous.
- **T-04-06-04** (DoS: Test downloads 2GB BGE-M3 model): MITIGATED. `mock_embedder_and_reranker` fixture patches `BgeM3Embedder.__init__` + `BgeReranker.__init__` to no-ops. Test runs without GPU; wall-clock is 7.47s for all 3 tests combined.

## Verification Evidence

Plan `<success_criteria>` + task `<done>` coverage:

| Criterion | Status | Evidence |
|---|---|---|
| All tasks in 04-06-PLAN.md executed per TDD cadence | PASS | 3 commits: `e558989` (Task 1), `27ef6be` (Task 2 RED), `bde9f07` (Task 2 GREEN). |
| Each task committed atomically | PASS | Task 1 in one commit; Task 2 split into RED + GREEN sub-commits per TDD cadence. |
| SUMMARY.md at `.planning/phases/04-chapter-assembly-post-commit-dag/04-06-SUMMARY.md` | PASS | This file. |
| 3-scene stub chapter DAG E2E test exists and passes | PASS | `tests/integration/test_chapter_dag_end_to_end.py::test_end_to_end_3_scene_stub_chapter_dag` passes in ~3.5s. |
| Mid-chapter pin upgrade test exists and passes | PASS | `test_end_to_end_mid_chapter_pin_upgrade` passes; asserts `voice_pin_shas` size == 2. |
| Chapter-critic-fail test exists and passes | PASS | `test_chapter_critic_fail_no_canon_commit` passes; asserts exit 3 + no canon commit + state=CHAPTER_FAIL. |
| All 9 Phase 4 success criteria covered in assertion groups | PASS | See Coverage Matrix above. |
| `bash scripts/lint_imports.sh` green | PASS | 2 import-linter contracts kept, ruff clean, mypy clean on 120 source files. |
| Full non-slow test suite passes from 508 baseline | PASS | 511 passed (+3 new integration tests). 2 deselected (slow + pre-existing golden-query fail). |
| Integration test runtime under 30s wall-clock | PASS | ~7.47s total for all 3 tests combined. |
| NO vLLM boot, NO real Anthropic API call, NO real git push | PASS | All LLM surfaces mocked via `MockLLMClient`; git is LOCAL (`git init` inside tmp_path; no `git remote`). Hard constraint respected. |

## Self-Check: PASSED

Artifact verification (files on disk at `/home/admin/Source/our-lady-book-pipeline/`):

- FOUND: `tests/integration/__init__.py`
- FOUND: `tests/integration/conftest.py` (521 lines)
- FOUND: `tests/integration/test_chapter_dag_end_to_end.py` (424 lines, 3 tests)
- FOUND: `tests/integration/fixtures/ch99_sc01.md`
- FOUND: `tests/integration/fixtures/ch99_sc02.md`
- FOUND: `tests/integration/fixtures/ch99_sc03.md`
- FOUND: `src/book_pipeline/cli/chapter.py` (Task 2 GREEN edit applied)

Commit verification on `main` branch (`git log --oneline`):

- FOUND: `e558989 test(04-06): Task 1 — integration conftest + 3 scene fixtures`
- FOUND: `27ef6be test(04-06): Task 2 RED — failing E2E integration test for Phase 4 DAG`
- FOUND: `bde9f07 feat(04-06): Task 2 GREEN — cli/chapter.py absolute directory anchors`

All 3 per-task commits landed on `main`. Aggregate gate green on 120 source files. Full non-slow test suite 511 passed (+3 new vs 508 baseline). Integration runtime 7.47s — well under the 30s plan target. Phase 4 green end-to-end; ready for STATE.md + ROADMAP.md roll-forward.

---

*Phase: 04-chapter-assembly-post-commit-dag*
*Plan: 06*
*Completed: 2026-04-23*
