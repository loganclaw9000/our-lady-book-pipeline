---
phase: 04-chapter-assembly-post-commit-dag
verified: 2026-04-23T18:42:38Z
status: passed_with_deferrals
score: 11/13 must-haves verified (+2 deferred to Phase 5)
must_haves_verified: 11
must_haves_total: 13
requirements_traced: 6/6
overrides_applied: 1
overrides:
  - name: "lint gate regression"
    action: "fixed inline via typing.cast(Retrospective, result) in dag.py _call_retrospective_writer; lint green on 120 source files; commit 86aa13b"
deferrals:
  - gap: "Bundler stale-card flag (SC6 read side)"
    target_phase: 5
    rationale: "Write-side complete (source_chapter_sha stamped on every EntityCard); read-side bundler threading needs entity_state retriever metadata extension + regression test. Shares detect-staleness + route-response shape with SC4 scene-kick routing. Not load-bearing for first-draft smoke since stale cards only matter for chapter 2+. Rescoped in REQUIREMENTS.md CORPUS-02."
  - gap: "Surgical scene-kick routing (SC4 read side)"
    target_phase: 5
    rationale: "Terminal CHAPTER_FAIL + blocker tag complete; CriticIssue->scene_id mapping + per-scene state reset natural home is REGEN-03 Mode-B escape work in Phase 5. Rescoped in REQUIREMENTS.md LOOP-04."
gaps:
  - truth: "bash scripts/lint_imports.sh exits 0 (aggregate lint + type gate green)"
    status: failed
    reason: "mypy step fails with 2 no-any-return errors in chapter_assembler/dag.py, introduced by the WR-04 shim `_call_retrospective_writer` (commit a3f2221). Writer is typed `Any`, so `return writer.write(...)` has inferred type `Any`, which mypy rejects against the declared `-> Retrospective` return. REVIEW-FIX.md claimed all 10 fixes verified against lint but only pytest was rerun; mypy regression slipped through."
    artifacts:
      - path: "src/book_pipeline/chapter_assembler/dag.py"
        issue: "Lines 313, 320: `return writer.write(...)` returns `Any` from a function declared `-> Retrospective`"
    missing:
      - "Cast the return value to Retrospective via `typing.cast(Retrospective, writer.write(...))` OR change the helper's declared return type to `Retrospective | Any` OR add a runtime isinstance assertion narrowing the type"
      - "Re-run `bash scripts/lint_imports.sh` to confirm mypy green on 120 source files"
  - truth: "Bundler flags stale cards at retrieval time — success criterion 6 second half (roadmap SC6: 'the bundler flags any card whose source SHA no longer matches the current canon file')"
    status: partial
    reason: "`source_chapter_sha` is correctly stamped on every EntityCard by OpusEntityExtractor (defense-in-depth override; Plan 04-03 test B verified). However, no code path in `src/book_pipeline/rag/bundler.py` (or any rag retriever) READS `source_chapter_sha` and compares it against the current canon chapter file's sha to flag stale cards. CONTEXT.md line 122 specifies this regression test explicitly ('mutate canon/chapter_01.md by one byte without bumping source_chapter_sha; bundler flags stale card at next retrieval') but no such bundler logic or test exists."
    artifacts:
      - path: "src/book_pipeline/rag/bundler.py"
        issue: "No source_chapter_sha comparison logic; EntityCard.source_chapter_sha is written but never read at retrieval time"
      - path: "src/book_pipeline/interfaces/types.py"
        issue: "EntityCard.source_chapter_sha is mandatory + stamped correctly (write side complete)"
    missing:
      - "Add stale-card detection to ContextPackBundlerImpl or to the entity_state retriever: on each EntityCard hit, compare card.source_chapter_sha against the current `git rev-list -1 HEAD -- canon/chapter_{NN:02d}.md` sha for the card's last_seen_chapter; emit a warning event + optionally filter the card"
      - "Add regression test per CONTEXT.md line 122: mutate canon/chapter_01.md by one byte, assert bundler flags stale card"
  - truth: "On chapter-critic FAIL, surgical scene-kick is the default routing; full-chapter redraft triggered only by explicit severity signal — roadmap SC4"
    status: partial
    reason: "Phase 4 correctly transitions to CHAPTER_FAIL terminal state with blocker tag 'chapter_critic_axis_fail' (test B in test_dag.py + critic-fail variant in integration test). However, there is NO routing logic that returns specific implicated scenes to regen vs triggering full-chapter redraft. CONTEXT.md <deferred> line 130 explicitly defers 'Mode-B redraft on CHAPTER_FAIL (REGEN-03/DRAFT-03) — Phase 5', but the SURGICAL SCENE-KICK side (roadmap SC4's default) is not specified as deferred anywhere. No CriticIssue→scene_id mapping, no per-scene-kick subroutine, no severity-signal inspection of the chapter critic response."
    artifacts:
      - path: "src/book_pipeline/chapter_assembler/dag.py"
        issue: "CHAPTER_FAIL terminal state is the full response; no implicated-scene extraction or routing logic"
      - path: ".planning/phases/04-chapter-assembly-post-commit-dag/04-CONTEXT.md"
        issue: "Deferred note only covers Mode-B redraft (full-chapter); surgical scene-kick default is not explicitly re-scoped"
    missing:
      - "Either: (a) implement a minimal CriticIssue→scene_id mapper that re-opens implicated scenes' state records to PENDING + records a mode_tag='scene_kick' event + returns those scene_ids as a new CHAPTER_FAIL substate, OR (b) explicitly reclassify this roadmap SC4 as Phase 5 scope and update REQUIREMENTS.md + LOOP-04 spec to reflect the deferral"
      - "Add regression test: chapter-critic fail with 1 high-severity issue citing ch99_sc02 → only sc02 state returns to PENDING; sc01 + sc03 stay COMMITTED"
human_verification: []
---

# Phase 4: Chapter Assembly + Post-Commit DAG Verification Report

**Phase Goal:** When all scenes for a chapter are in the buffer, they atomically assemble into `canon/chapter_NN.md`, pass an independent chapter-level critic (fresh RAG pack, not the scene pack), commit to git, and trigger the post-commit DAG (EntityExtractor → RAG reindex → RetrospectiveWriter) to completion before the next chapter's drafting begins.

**Verified:** 2026-04-23T18:42:38Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (13 total from ROADMAP SCs + plan must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ChapterAssembler deterministically stitches scenes; re-running on identical inputs produces identical output (roadmap SC1) | ✓ VERIFIED | `ConcatAssembler.assemble` no timestamps; `yaml.safe_dump(sort_keys=False)`; test_concat.py::test_concat_is_deterministic asserts byte-identical output; end-to-end integration test asserts chapter frontmatter + 3 HTML markers + 2 section separators. |
| 2 | Chapter Critic issues its OWN RAG query (fresh pack); breaks C-4 collusion (roadmap SC2) | ✓ VERIFIED | `ChapterCritic` has NO bundler import (grep returns empty); accepts `CriticRequest.context_pack` as pre-built; `ChapterDagOrchestrator._step1_canon` constructs fresh SceneRequest with `scene_index=0, beat_function='chapter_overview'`; test_E_fresh_pack_assertion + integration test's `bundler_fingerprint_spy` verify the chapter pack's fingerprint is distinct from any other bundle call's fingerprint. |
| 3 | On chapter-critic PASS, atomic git commit lands canon, post-commit DAG fires 3 more commits, next chapter's drafting BLOCKED until DAG completes (roadmap SC3) | ✓ VERIFIED | ChapterDagOrchestrator 4-step strict-order DAG; test_A_happy_path_4_commits asserts exact commit sequence `canon(ch99) → chore(entity-state) → chore(rag) → docs(retro)`; integration test's `git log --pretty=%s` regex-matches all 4 messages; `.planning/pipeline_state.json` with `dag_complete=True + last_committed_dag_step=4` is the Phase 5 cron gate. |
| 4 | On chapter-critic FAIL, surgical scene-kick is the default; full-chapter redraft on explicit severity signal (roadmap SC4) | ✗ PARTIAL | CHAPTER_FAIL terminal state + blocker tag verified (test_B + integration critic-fail variant). But NO scene-kick routing: no CriticIssue→scene_id mapping, no implicated-scene filter, no per-scene state-reset logic. CONTEXT.md <deferred> only covers Mode-B redraft (Phase 5); surgical scene-kick routing unaddressed. See gaps. |
| 5 | RetrospectiveWriter output passes a lint rule rejecting generic boilerplate (roadmap SC5) | ✓ VERIFIED | `lint_retrospective(retro) -> tuple[bool, list[str]]`: requires ≥1 `ch\d+_sc\d+` match AND ≥1 critic-artifact match (axis word OR chunk_id OR 20+ char quote). Invoked on every write() output; retry-once on fail; log+commit on second fail (ungated per CONTEXT.md). Integration test asserts `lint_retrospective(retro) == (True, [])` on committed retrospective. |
| 6 | EntityCards carry `source_chapter_sha`; bundler flags stale cards (roadmap SC6) | ✗ PARTIAL | WRITE side complete: EntityCard.source_chapter_sha mandatory field; OpusEntityExtractor force-overrides on every card (defense-in-depth, test_B). READ/FLAG side missing: `src/book_pipeline/rag/bundler.py` contains zero references to `source_chapter_sha` or stale-card detection. CONTEXT.md line 122 specifies the regression test but it doesn't exist. See gaps. |
| 7 | 4 new kernel packages (chapter_assembler, entity_extractor, retrospective, ablation) importable + lint-clean (Plan 01) | ✓ VERIFIED | All 4 packages exist with __init__.py; `uv run python -c "import book_pipeline.chapter_assembler, ..."` exits 0; import-linter contracts 1 + 2 both list the 4 packages; `grep -E "book_pipeline\.(chapter_assembler\|entity_extractor\|retrospective\|ablation)" pyproject.toml` returns 8 matches (4 in each contract). |
| 8 | ChapterStateMachine with 10-value StrEnum + Pydantic record + pure transition() helper (Plan 01) | ✓ VERIFIED | `ChapterState` has 10 values (len(list(ChapterState)) == 10 via smoke test); ChapterStateRecord has 7 fields {chapter_num, state, scene_ids, chapter_sha, dag_step, history, blockers}; `transition()` is pure (model_copy); 6 tests in test_chapter_state_machine.py; JSON roundtrip verified. |
| 9 | ConcatAssembler + ChapterCritic satisfy frozen Protocols; ≥3/5 threshold enforced (Plan 02) | ✓ VERIFIED | Smoke test: `isinstance(ConcatAssembler(), ChapterAssembler) is True`, `ChapterCritic.level == "chapter"`; _post_process enforces `axis_pass = (score >= 60.0) AND (max_severity != 'high')` and OVERRIDES LLM's pass_per_axis claim (test_C + test_D); CRIT-04 audit log under `runs/critic_audit/chapter_NN_01_*.json` per invocation (success + tenacity-exhaustion failure). |
| 10 | OpusEntityExtractor incremental diff + source_chapter_sha override; OpusRetrospectiveWriter lint-on-output + single nudge retry + ungated stub on failure (Plan 03) | ✓ VERIFIED | 10 test_opus.py tests cover: Protocol conformance, sha-stamp defense, filter-unchanged, flag-updated, 1-event-per-call, empty-chapter fast-fail, tenacity-3x-fast, prior-cards prompt injection. 10 retrospective tests cover: protocol, lint-pass first-try, lint-fail-then-pass-on-retry, lint-fail-twice-logs-and-commits, markdown parse shape, ungated generation failure returning stub. |
| 11 | ChapterDagOrchestrator wires 4-step strict DAG with resumability (dag_step counter); scene buffer archival on DAG_COMPLETE; AblationRun harness skeleton lands (Plan 04) | ✓ VERIFIED | 8 test_dag.py tests cover: happy 4-commit, critic-fail-no-commit, resumability from dag_step=1 (Concat/Critic call_count=0), entity-extractor DAG_BLOCKED, fresh-pack invariant, ungated stub retro, scene-count gate, pipeline_state atomic write. 5 test_harness.py tests cover AblationRun Pydantic + idempotent skeleton helper. `rag/reindex.py` additive kernel extension landed per Plan 04 Task 1. |
| 12 | `book-pipeline chapter / chapter-status / ablate` CLI subcommands registered + discoverable (Plan 05) | ✓ VERIFIED | `uv run book-pipeline --help` lists all 3 subcommands with usage text; `book-pipeline chapter --help` shows `chapter_num`, `--expected-scene-count`, `--no-archive`; `ablate --help` shows `--variant-a/--variant-b/--n/--run-id`; 2 pyproject.toml import-linter exemptions added for cli.chapter → outline_scene_counts + corpus_paths; cli/chapter.py listed in documented_exemptions. EXPECTED_SCENE_COUNTS dict has 28 entries (chapters 1-27 + 99). |
| 13 | E2E integration test regression-guards every Phase 4 success criterion in a mocked tmp_path repo (Plan 06) | ✓ VERIFIED | `tests/integration/test_chapter_dag_end_to_end.py` (424 lines) has 3 passing tests: happy path (9 assertion groups covering all 6 roadmap SCs + LOOP-04 gate + events.jsonl shape + fresh-pack invariant), mid-chapter-pin-upgrade (voice_pin_shas size == 2), chapter-critic-fail (exit 3, no canon commit, state=CHAPTER_FAIL). Runtime 7.47s wall-clock. Fully mocked LLM, fully mocked retrievers/bundler/embedder, real git subprocess in tmp_path, ANTHROPIC_API_KEY sanitized. |

**Score:** 10/13 truths verified (SC4 + SC6 partial; aggregate lint gate failed on mypy regression)

### Required Artifacts (top-level)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/book_pipeline/chapter_assembler/concat.py` | ConcatAssembler Protocol conformant | ✓ VERIFIED | 249 lines; isinstance(ConcatAssembler(), ChapterAssembler) is True; WR-02 chapter-scoped regex fix landed; WR-07 voice_fidelity_score as proper Pydantic field |
| `src/book_pipeline/chapter_assembler/dag.py` | ChapterDagOrchestrator 4-step DAG | ⚠️ STUB (mypy) | 1135 lines; all 8 unit tests + 3 integration tests pass; WR-04/05/06 fixes landed; BUT 2 mypy no-any-return errors block lint gate |
| `src/book_pipeline/chapter_assembler/git_commit.py` | Atomic git commit helpers | ✓ VERIFIED | 136 lines; commit_paths + check_worktree_dirty + GitCommitError; 4 tests with real `git init` in tmp_path |
| `src/book_pipeline/critic/chapter.py` | ChapterCritic level='chapter' | ✓ VERIFIED | 678 lines; 12 tests pass including WR-05 checkpoint_sha stamping; Protocol-conformant |
| `src/book_pipeline/critic/templates/chapter_system.j2` | Chapter-scoped 5-axis rubric prompt | ✓ VERIFIED | On disk; loaded by ChapterSystemPromptBuilder at __init__ |
| `src/book_pipeline/critic/templates/chapter_fewshot.yaml` | 1 bad + 1 good chapter example | ✓ VERIFIED | On disk; 96 lines; validates through CriticResponse.model_validate |
| `src/book_pipeline/entity_extractor/opus.py` | OpusEntityExtractor CORPUS-02 | ✓ VERIFIED | 423 lines; 8 tests pass including source_chapter_sha defense-in-depth override |
| `src/book_pipeline/entity_extractor/schema.py` | EntityExtractionResponse schema | ✓ VERIFIED | 37 lines; 2 schema tests pass |
| `src/book_pipeline/retrospective/opus.py` | OpusRetrospectiveWriter TEST-01 | ✓ VERIFIED | 604 lines; 6 tests pass including ungated stub-on-failure; WR-04 chapter_num kwarg added |
| `src/book_pipeline/retrospective/lint.py` | lint_retrospective pure function | ✓ VERIFIED | 55 lines; 4 lint tests pass; invoked by writer.write() before return |
| `src/book_pipeline/ablation/harness.py` | AblationRun + skeleton helper | ✓ VERIFIED | 90 lines; 5 tests pass; CR-01 containment check added via resolve()/relative_to |
| `src/book_pipeline/interfaces/chapter_state_machine.py` | ChapterStateMachine module | ✓ VERIFIED | 10-value Enum + 7-field Record + pure transition(); 6 tests pass |
| `src/book_pipeline/rag/reindex.py` | Entity-state reindex helper | ✓ VERIFIED | 139 lines; CR-02 per-row fallback landed; raises on fallback failure (no silent duplicates) |
| `src/book_pipeline/cli/chapter.py` | Chapter CLI composition root | ✓ VERIFIED | 388 lines; 7 tests pass; WR-08 `_discover_repo_root` landed; absolute-path anchors fix from Plan 04-06 |
| `src/book_pipeline/cli/chapter_status.py` | Status viewer CLI | ✓ VERIFIED | 125 lines; 4 tests pass |
| `src/book_pipeline/cli/ablate.py` | Ablate stub CLI | ✓ VERIFIED | 293 lines; 5 tests pass; CR-01 _validate_run_id landed (rejects ., .., dot-sequences) |
| `src/book_pipeline/book_specifics/outline_scene_counts.py` | EXPECTED_SCENE_COUNTS table | ✓ VERIFIED | 28-entry dict; chapters 1-27 + 99 |
| `tests/integration/test_chapter_dag_end_to_end.py` | E2E regression test | ✓ VERIFIED | 424 lines; 3 tests; 7.47s runtime; all 6 roadmap SCs asserted in happy path |
| `pyproject.toml` | Import-linter contracts 1+2 extended | ✓ VERIFIED | 4 Phase 4 kernel packages in each contract (8 matches); 2 new cli.chapter exemptions |
| `scripts/lint_imports.sh` | mypy scope extended | ⚠️ REGRESSED | mypy target list includes all 4 Phase 4 packages; gate itself exits NON-ZERO due to 2 dag.py errors |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `chapter_assembler/concat.py` | `interfaces/chapter_assembler.py` | Protocol conformance | ✓ WIRED | `isinstance(a, ChapterAssembler) is True` verified |
| `critic/chapter.py` | `interfaces/critic.py` | Critic Protocol level='chapter' | ✓ WIRED | `isinstance(c, Critic)` + `c.level == 'chapter'` |
| `chapter_assembler/dag.py` | `interfaces/chapter_state_machine.transition` | state transitions through pure helper | ✓ WIRED | grep shows 10+ transition(record, ...) call sites |
| `chapter_assembler/dag.py` | `chapter_assembler/concat.py` | from_committed_scenes | ✓ WIRED | _invoke_assembler calls getattr-based dispatch |
| `chapter_assembler/dag.py` | `critic/chapter.py` | critic.review(CriticRequest) | ✓ WIRED | _step1_canon builds fresh pack + calls review |
| `chapter_assembler/dag.py` | `entity_extractor/opus.py` | entity_extractor.extract | ✓ WIRED | _step2_entity calls extract(chapter_text, N, chapter_sha, prior_cards) |
| `chapter_assembler/dag.py` | `retrospective/opus.py` | retrospective_writer.write (via WR-04 shim) | ✓ WIRED | _call_retrospective_writer shim passes chapter_num kwarg |
| `chapter_assembler/dag.py` | `rag/reindex.py` | reindex_entity_state_from_jsons | ✓ WIRED | _step3_rag calls the helper |
| `cli/chapter.py` | `chapter_assembler/dag.ChapterDagOrchestrator` | composition root | ✓ WIRED | _build_dag_orchestrator wires 11+ deps |
| `cli/chapter.py` | `book_specifics/outline_scene_counts.EXPECTED_SCENE_COUNTS` | gate-check source | ✓ WIRED | import-linter exemption present; function-body import |
| `EntityCard.source_chapter_sha` | bundler/retriever stale-card flag | read-time comparison | ✗ NOT_WIRED | Write side complete; read side absent — SC6 partial |
| `ChapterCritic fail event` | surgical scene-kick routing | CriticIssue→scene_id mapper | ✗ NOT_WIRED | Fail terminal state only; routing deferred but not explicitly to later phase |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `canon/chapter_{NN}.md` | chapter markdown | ConcatAssembler.assemble(drafts) | Yes (real scene text + aggregated frontmatter) | ✓ FLOWING |
| `entity-state/chapter_{NN}_entities.json` | EntityExtractionResponse | OpusEntityExtractor.extract output | Yes (real Opus structured parse; source_chapter_sha force-overridden) | ✓ FLOWING |
| `retrospectives/chapter_{NN}.md` | Retrospective rendered md | OpusRetrospectiveWriter.write output | Yes (lint-gated 4-section output; ungated stub on gen failure) | ✓ FLOWING |
| `.planning/pipeline_state.json` | `{last_committed_chapter, dag_step, dag_complete, last_hard_block}` | DAG orchestrator atomic writes after each step | Yes (real values from commit_paths + state record) | ✓ FLOWING |
| `drafts/chapter_buffer/ch{NN}.state.json` | ChapterStateRecord | transition(record, new_state, note) through DAG | Yes (real state/history/dag_step values) | ✓ FLOWING |
| `runs/events.jsonl` chapter_critic role | Event | ChapterCritic.review emits one per invocation | Yes (real caller_context + rubric_version + checkpoint_sha since WR-05) | ✓ FLOWING |
| entity_state LanceDB table rows | EntityCard rows | rag/reindex.py wipe-and-insert from JSON | Yes (real embedder.encode + CR-02 per-row fallback protects from duplicates) | ✓ FLOWING |
| `AblationRun.ablation_config.json` | Pydantic model dump | create_ablation_run_skeleton atomic write | Yes (real SHAs + timestamps) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CLI subcommands discoverable | `uv run book-pipeline --help \| grep -E "chapter\|ablate"` | 3 subcommands listed | ✓ PASS |
| chapter --help exits 0 | `uv run book-pipeline chapter --help` | usage shown with chapter_num positional | ✓ PASS |
| ablate --help exits 0 | `uv run book-pipeline ablate --help` | usage shown with --variant-a/--variant-b/--n | ✓ PASS |
| Protocol conformance | `uv run python -c "from book_pipeline.chapter_assembler import ConcatAssembler; ..."` | All isinstance checks True | ✓ PASS |
| ChapterState 10 values + ChapterStateRecord 7 fields | Smoke test | `len(list(ChapterState)) == 10`; fields match spec | ✓ PASS |
| EXPECTED_SCENE_COUNTS size 28 + 99 present | Smoke test | 28 entries, 99 in dict | ✓ PASS |
| import-linter contracts green | `bash scripts/lint_imports.sh` step 1 | "Contracts: 2 kept, 0 broken" | ✓ PASS |
| ruff clean | `bash scripts/lint_imports.sh` step 2 | "All checks passed!" | ✓ PASS |
| **mypy clean on kernel + book_specifics** | `bash scripts/lint_imports.sh` step 3 | **Found 2 errors in 1 file (dag.py:313, 320)** | ✗ **FAIL** |
| Full non-slow suite | `uv run pytest -m "not slow"` | 516 passed, 4 deselected | ✓ PASS |
| Test collection | `uv run pytest --co -q` | 520 tests collected | ✓ PASS |
| Phase 4 test subset | `uv run pytest tests/{integration,chapter_assembler,critic/test_chapter_critic.py,entity_extractor,retrospective,ablation,interfaces/test_chapter_state_machine.py,cli/test_chapter*_cli.py,cli/test_ablate_cli.py}` | 82 passed | ✓ PASS |
| Import-contract regressions | `uv run pytest tests/test_import_contracts.py` | 10 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| CORPUS-02 | 04-03, 04-06 | Entity-state auto-extraction agent runs post-commit, writes entity cards, re-indexes entity_state LanceDB | ✓ SATISFIED | OpusEntityExtractor lands; entity-state/chapter_NN_entities.json written in DAG step 2; rag/reindex.py wipes-and-inserts in step 3; 10 tests green |
| CRIT-02 | 04-02, 04-06 | Chapter-level critic runs after assembly with arc-coherence + voice-consistency axes on 5-axis rubric | ✓ SATISFIED | ChapterCritic level='chapter', rubric_version='chapter.v1', ≥3/5 threshold with LLM-override, 5-axis per-axis enforcement, fresh-pack invariant; 12 tests green |
| LOOP-02 | 04-01, 04-02, 04-04, 04-06 | Chapter assembler stitches buffered scenes, runs chapter-level critic, on PASS atomically commits canon + re-indexes | ✓ SATISFIED | ConcatAssembler + ChapterCritic + DAG steps 1 (canon commit) + 3 (RAG reindex) all wired; integration test asserts 4 commits in strict order |
| LOOP-03 | 04-01, 04-04, 04-05, 04-06 | Post-chapter DAG runs to completion before next chapter's scenes begin: extractor → reindex → retrospective | ✓ SATISFIED | DAG steps 2/3/4 in strict order; resumability via dag_step counter; pipeline_state.json gate; `book-pipeline chapter` CLI registered |
| LOOP-04 | 04-05, 04-06 | Rollback on chapter-level critic FAIL: surgical scene-kick by default, full-chapter redraft on explicit severity signal | ✗ PARTIAL | CHAPTER_FAIL terminal state + exit code 3 + blocker tag verified, BUT surgical scene-kick routing NOT implemented (no CriticIssue→scene_id mapping, no severity-signal inspection). Roadmap SC4 requires this; CONTEXT.md defers Mode-B redraft (full-chapter side) to Phase 5 but not the scene-kick side. Gap. |
| TEST-01 | 04-03, 04-04, 04-05, 04-06 | Retrospective writer (Opus) runs post-chapter-commit, produces md with lint rule rejecting generic output | ✓ SATISFIED | OpusRetrospectiveWriter.write() + lint_retrospective + single-nudge-retry + ungated-stub-on-failure; DAG step 4 writes retrospectives/chapter_NN.md; AblationRun harness skeleton on-disk shape locked |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/book_pipeline/chapter_assembler/dag.py | 313, 320 | `return writer.write(...)` returns `Any` (writer: Any parameter) | 🛑 Blocker | Blocks aggregate lint gate; mypy step fails with 2 errors; prevents CI-like hygiene |
| (none) | — | No TODO/FIXME/PLACEHOLDER comments in Phase 4 source files | ℹ️ Info | clean |
| (none) | — | No empty returns/empty handlers in Phase 4 source files | ℹ️ Info | clean |
| (none) | — | Summary stubs (`what_worked='(generation failed)'`) are documented ungated-path sentinels, NOT anti-patterns | ℹ️ Info | per CONTEXT.md grey-area e |

### Human Verification Required

None. All Phase 4 checks are programmatically verifiable (no UI, no real LLM calls, no external service smoke). The 2 gaps flagged (mypy regression + SC6 bundler-flag missing + SC4 scene-kick routing missing) are all programmatically reproducible.

### Gaps Summary

**3 gaps blocking full goal achievement (2 partial + 1 failed):**

1. **Lint gate regression (FAILED)** — `bash scripts/lint_imports.sh` exits non-zero because mypy reports 2 `no-any-return` errors in `chapter_assembler/dag.py` (introduced by WR-04 shim, not caught by REVIEW-FIX verification). The test suite (516 passed) disguises this because tests use Any-typed fakes. Blocks the aggregate gate that every plan summary claims green.

2. **Stale-card detection bundler side missing (PARTIAL / roadmap SC6)** — `EntityCard.source_chapter_sha` is stamped correctly on every card (defense-in-depth override verified by test_B), but NO rag/bundler.py or retriever code reads `source_chapter_sha` and compares against the current canon sha. Roadmap SC6 requires "bundler flags any card whose source SHA no longer matches the current canon file". CONTEXT.md line 122 specifies the exact regression test (mutate canon, re-query, assert flag) — no such test + no flagging logic.

3. **Surgical scene-kick routing missing (PARTIAL / roadmap SC4)** — Phase 4 correctly lands CHAPTER_FAIL terminal state with `chapter_critic_axis_fail` blocker (tests verified). But SC4 requires "surgical scene-kick is the default (only the implicated scene(s) return to regen)". No CriticIssue→scene_id mapping, no per-scene state reset to PENDING, no severity-signal inspection. CONTEXT.md defers only the full-chapter redraft half to Phase 5; the scene-kick default side is not explicitly re-scoped.

**Not blockers but noteworthy:** Phase 4 SUMMARY files all claim `bash scripts/lint_imports.sh green` after each plan, including post-REVIEW-FIX. The mypy regression was introduced by commit `a3f2221` (WR-04 fix) and never re-verified against the full lint gate before REVIEW-FIX closure. The REVIEW-FIX report says "All fixes verified via syntax check (ast.parse) plus the full non-slow pytest suite (516 passed, 4 deselected)" — notably omits lint_imports.sh from post-fix verification. This is a process gap worth surfacing in the follow-up.

---

_Verified: 2026-04-23T18:42:38Z_
_Verifier: Claude (gsd-verifier)_
