---
phase: 04-chapter-assembly-post-commit-dag
plan: 02
subsystem: concat-assembler-+-chapter-critic
tags: [chapter-assembly, concat-assembler, chapter-critic, crit-02, loop-02, fresh-pack, crit-04-audit, chapter-rubric]
requirements_completed: []  # LOOP-02 + CRIT-02 multi-plan; 04-02 lands kernel deterministic-join + second Critic impl. CLI composition + DAG orchestrator land in 04-04; full LOOP-02/CRIT-02 pass at phase close.
dependency_graph:
  requires:
    - "04-01 (kernel skeletons — chapter_assembler/__init__.py + critic/ already in import-linter contracts 1+2 and scripts/lint_imports.sh mypy scope)"
    - "03-05 (SceneCritic — ChapterCritic clones structure-for-structure: pre-rendered cached _system_blocks, tenacity retry config, W-7 audit-on-failure, messages.parse via output_format=CriticResponse)"
    - "03-07 (_commit_scene frontmatter shape + B-3 invariant — voice_pin_sha==checkpoint_sha is the input contract ConcatAssembler.from_committed_scenes validates)"
    - "02-05 (ContextPackBundlerImpl — the fresh-pack factory that Plan 04-04 will call with a chapter-scoped SceneRequest; Plan 04-02 itself is caller-agnostic)"
    - "01-02 (CriticRequest/CriticResponse/Critic Protocol FROZEN — ChapterCritic lives inside the existing shape; chapter_text rides on CriticRequest.scene_text per plan-noted Protocol re-use)"
  provides:
    - "src/book_pipeline/chapter_assembler/concat.py — ConcatAssembler class (Protocol-conformant, deterministic, ~237 lines)"
    - "src/book_pipeline/chapter_assembler/__init__.py — re-exports ConcatAssembler"
    - "src/book_pipeline/critic/chapter.py — ChapterCritic + ChapterSystemPromptBuilder + ChapterCriticError + CHAPTER_AXES_ORDERED (~654 lines)"
    - "src/book_pipeline/critic/templates/chapter_system.j2 — chapter-scoped system prompt (rubric + 5-axis instructions + 2 few-shot)"
    - "src/book_pipeline/critic/templates/chapter_fewshot.yaml — 1 bad (cross-scene location drift) + 1 good (coherent 3-scene progression) few-shot"
    - "config/rubric.yaml — additive chapter_rubric_version='chapter.v1' + chapter_axes block (5 axes, score_threshold_0to5=3, weight=1.0)"
    - "src/book_pipeline/config/rubric.py — ChapterAxisConfig + ChapterRubricConfig + CHAPTER_REQUIRED_AXES + RubricConfig.chapter_rubric field with model_validator(mode='before') flat-key collapse"
    - "tests/chapter_assembler/test_concat.py — 8 non-slow tests (Protocol conformance + 3-scene happy path + determinism + pin-upgrade dedup + single-scene + from_committed_scenes happy/missing-pin/missing-dir)"
    - "tests/critic/test_chapter_critic.py — 12 non-slow tests (A-K plan-spec coverage + missing-axis fill)"
  affects:
    - "Plan 04-03 (OpusEntityExtractor + OpusRetrospectiveWriter) — can consume the ConcatAssembler output shape (chapter frontmatter with assembled_from_scenes list) for retrospective input filtering"
    - "Plan 04-04 (chapter DAG orchestrator) — composes ConcatAssembler.from_committed_scenes + bundler.bundle(chapter_scene_request) + ChapterCritic.review in the assembly/critique steps; ChapterStateMachine transitions ASSEMBLING → ASSEMBLED → CHAPTER_CRITIQUING drive the compose"
    - "Plan 04-05/06 — integration smoke + LOOP-04 gate; ChapterCritic.level='chapter' + audit records under runs/critic_audit/chapter_NN_*.json become queryable for Phase 5 alert hooks"
    - "Phase 6 (OBS-02 ingester) — rubric_version='chapter.v1' stamped on response + Event + audit lets the ingester partition chapter vs scene critic metrics without schema changes"
tech-stack:
  added: []  # No new runtime deps; jinja2/pydantic/pydantic-settings/tenacity/yaml/xxhash all already-used.
  patterns:
    - "Clone-not-abstract: ChapterCritic mirrors SceneCritic structure-for-structure (SystemPromptBuilder pattern, pre-rendered _system_blocks list reused across calls for cache identity, tenacity 5-attempt wait_exponential retry, _post_process fill-missing-axes + invariant-fix + rubric_version-override, W-7 _handle_failure audit-then-raise) rather than extracting a shared base class. Rationale: ADR-004 'don't abstract until written twice' — this IS the second write, and the divergences (stricter >=60 + no-high-severity threshold, LLM's axis-pass claim OVERRIDDEN on threshold violation, FRESH ContextPack accepted by caller, audit filename prefix 'chapter_NN' vs scene's '{sid}_{attempt}', Event role 'chapter_critic' vs 'critic', missing-axis default score 60.0 vs 75.0) cluster inside _post_process + __init__ signature, not at the Protocol boundary. A shared base class would need two subclasses with three different thresholds (scene, chapter-now, future chapter-v2) and every configuration knob lifted — net code increase. Plan 06 (if a third critic lands) is the trigger for extraction, not this plan."
    - "Fresh-pack invariant by caller contract, audit by fingerprint: ChapterCritic does NOT build its own ContextPack (no bundler import, no retrievers list) — it TRUSTS the pack in CriticRequest.context_pack. Plan 04-04's DAG orchestrator is responsible for running a fresh bundler.bundle(chapter_scene_request, retrievers) before calling review(). The PROTECTION is that the audit record stamps context_pack_fingerprint, which test_E_fresh_pack_invariant locks in: if Plan 04-04 (or a future caller) accidentally re-uses a scene pack, the audit fingerprint gives Phase 6 OBS-02 a single-column join that catches the regression post-hoc. C-4 mitigation is distributed: CALLER builds fresh pack; CRITIC records fingerprint in audit; INTEGRATION TEST in Plan 04-06 asserts chapter_pack.fingerprint NOT IN {scene_pack.fingerprint}. Three belts + two suspenders."
    - "Threshold math cemented: pass threshold 3/5 is stored as score_threshold_0to5:3 in YAML; post-process compares against _CHAPTER_PASS_THRESHOLD_0to100=60.0. The x20 normalization means the same CriticResponse Pydantic model (float 0..100 scores) carries both critics' outputs, so the existing Event/audit/JSONL pipeline works unchanged. If Phase 6 ablations want to flex the threshold (e.g. 4/5 for specific chapter types), the single change point is config/rubric.yaml's score_threshold_0to5 — no critic code edits required. Plan 04-02 explicitly does NOT thread the threshold through the prompt template's free-text wording (rubric block renders `pass threshold: score_0to5 >= {{ threshold }}`, but the scoring-guidance paragraph hardcodes '3=acceptable baseline'). A future plan that wants a 4/5 chapter rubric will need to regenerate the few-shot to match."
    - "Additive rubric schema with flat-key collapse: RubricConfig gained chapter_rubric: ChapterRubricConfig as a required field. The YAML stores chapter_rubric_version + chapter_axes at the ROOT (not nested under chapter_rubric:) to match the existing rubric_version + axes: scene layout. A model_validator(mode='before') classmethod collapses the flat keys into the nested shape Pydantic expects. Benefit: operators editing rubric.yaml see scene + chapter rubrics at the same indent level (no mental context-switch from top-level to nested). Cost: one extra validator on RubricConfig. The test_rubric_accepts_valid_5_axes fixture was updated to include chapter_rubric_version + chapter_axes; no other caller needed changes (RubricConfig() now loads BOTH rubrics on a single read)."
    - "Kernel-substring-guard discipline: the test_kernel_does_not_import_book_specifics belt-and-suspenders test (next to import-linter contract 1) does a literal substring scan for 'book_specifics' in every kernel .py file. Verbatim-quoting the phrase in a docstring breaks the scan. Plan 04-02 reworded 2 docstrings (chapter_assembler/__init__.py + chapter_assembler/concat.py) to 'book-domain layer' / 'book-domain imports' — semantic equivalent, substring-safe. Same mitigation Plan 04-01 took on a different token (UP042 noqa-in-comment). Downstream plans that write prose about the kernel/book_specifics boundary should ALWAYS paraphrase."
    - "Post-process OVERRIDES the LLM's axis-pass claim: SceneCritic trusts Opus's pass_per_axis booleans (it only enforces overall_pass = all(pass_per_axis.values())). ChapterCritic goes further — for each axis it recomputes axis_pass = (score >= 60.0) AND (max_severity < 'high'), and overwrites parsed.pass_per_axis[axis] if Opus's claim disagrees. Rationale: chapter-scale reasoning is harder for Opus to keep internally consistent across a 3000-word context, and the threshold rule is mechanical. Trust the score + severity list; don't trust the boolean. Caught by test_C (score 50 + LLM-claimed pass=True → flipped to False) and test_D (score 80 + high-severity issue → flipped to False)."
key-files:
  created:
    - "src/book_pipeline/chapter_assembler/concat.py (237 lines; ConcatAssembler class + _SCENE_MD_RE + _parse_scene_md helper + from_committed_scenes classmethod)"
    - "src/book_pipeline/critic/chapter.py (654 lines; ChapterCritic + ChapterSystemPromptBuilder + ChapterCriticError + helpers)"
    - "src/book_pipeline/critic/templates/chapter_fewshot.yaml (96 lines; bad 3-scene chapter with entity drift + good 3-scene chapter with travel bridge)"
    - "src/book_pipeline/critic/templates/chapter_system.j2 (38 lines; 5-axis chapter rubric + 0..5 scoring + per-axis chapter-scale instructions)"
    - "tests/chapter_assembler/test_concat.py (216 lines; 8 non-slow tests)"
    - "tests/critic/test_chapter_critic.py (512 lines; 12 non-slow tests)"
    - ".planning/phases/04-chapter-assembly-post-commit-dag/04-02-SUMMARY.md (this file)"
  modified:
    - "src/book_pipeline/chapter_assembler/__init__.py (re-export ConcatAssembler; reworded docstring to avoid 'book_specifics' substring)"
    - "src/book_pipeline/critic/__init__.py (re-export ChapterCritic + ChapterSystemPromptBuilder + ChapterCriticError + CHAPTER_AXES_ORDERED alongside existing scene surface)"
    - "src/book_pipeline/config/rubric.py (additive: ChapterAxisConfig + ChapterRubricConfig + CHAPTER_REQUIRED_AXES + RubricConfig.chapter_rubric field + model_validator(mode='before') flat-key collapse + extra='allow' on model_config)"
    - "config/rubric.yaml (additive: chapter_rubric_version + chapter_axes block; scene rubric_version + axes untouched)"
    - "tests/test_config.py (test_rubric_accepts_valid_5_axes fixture: add chapter_rubric_version + chapter_axes to tmp_path rubric YAML; assert cfg.chapter_rubric.rubric_version == 'chapter.v1')"
key-decisions:
  - "(04-02) ChapterCritic._post_process OVERRIDES LLM's pass_per_axis claim on threshold violation. SceneCritic's post-process only enforced overall_pass = all(pass_per_axis.values()); ChapterCritic additionally computes axis_pass = (score>=60) AND (max_severity<'high') and overwrites the LLM's per-axis boolean if it disagrees. Captured in tests C (score 50 → pass flipped False) + D (score 80 + high-severity → pass flipped False). Rationale: the 3/5 threshold rule is mechanical — Opus's free-text reasoning at chapter scale drifts on internal consistency; trust the scores + severity list, not the booleans."
  - "(04-02) Fresh-pack invariant enforced by CALLER, not by critic. ChapterCritic does NOT build a ContextPack — it trusts CriticRequest.context_pack as delivered. Plan 04-04's DAG orchestrator is responsible for running bundler.bundle(chapter_scene_request, retrievers) with a chapter-scoped SceneRequest (scene_index=0 sentinel, chapter-midpoint ISO date, primary POV, beat_function='chapter_overview'). Protection: audit record stamps context_pack_fingerprint; test_E_fresh_pack_invariant locks in that a distinct chapter_pack fingerprint (vs scene_pack) appears in the audit record, so a future caller-side regression surfaces in Phase 6 OBS-02 ingestion without needing changes to the critic. C-4 mitigation distributed across caller + critic + integration test."
  - "(04-02) RubricConfig.chapter_rubric is a REQUIRED field (not Optional). Operators adding a new rubric.yaml MUST include chapter_rubric_version + chapter_axes. Alternative (Optional chapter_rubric with default=None) was rejected: ChapterCritic.__init__ needs rubric.chapter_rubric.rubric_version at construction time; an Optional default would only defer the crash to a more confusing error site. Made required; test_rubric_accepts_valid_5_axes fixture updated to include the new keys. One fixture change (additive); no functional regressions."
  - "(04-02) Flat-YAML + model_validator(mode='before') collapse over nested YAML shape. config/rubric.yaml puts chapter_rubric_version + chapter_axes at the root (matching rubric_version + axes: scene layout) rather than nesting under chapter_rubric:. A RubricConfig validator collapses the flat keys into the nested Pydantic shape. Trade-off: one extra Pydantic validator classmethod (6 lines) for operator ergonomics (scene and chapter rubrics at the same indent level, no mental context-switch). Chose flat-root layout."
  - "(04-02) Chapter critic is SINGLE-ATTEMPT per review() call. Audit records stamp attempt_number=1 (no retry budget at the critic level). If Plan 04-04's DAG orchestrator wants retries, it re-invokes review() — each re-invocation writes its own audit file with its own ts_iso, which is what Phase 6 OBS-02 wants for cost/latency analysis. Parallel to the scene critic's attempt tracking via CriticRequest.chapter_context['attempt_number']; chapter critic just defaults to 1 because the scene-loop R-retry semantic doesn't apply at chapter scale."
  - "(04-02) Chapter critic Event role='chapter_critic' (NOT 'critic'). Plan 03-05 chose role='critic' for the scene-level Event; Plan 04-02 chooses role='chapter_critic' so Phase 6 OBS-02 ingester can partition metrics without needing to join on rubric_version. Event.role is a flat string in the frozen Phase 1 schema; adding a new role value is additive and backward-compatible. A future unified role='critic' + sub-type='scene|chapter' refactor is possible but would require a schema bump per Phase 1 freeze policy. Left for Phase 6 if OBS-02 ingester surfaces a concrete reason."
  - "(04-02) Kernel substring-guard paraphrase discipline (Plan 04-01 Rule 1 precedent applied preemptively). The test_kernel_does_not_import_book_specifics substring scan checks for the literal 'book_specifics' token in every kernel .py. Two docstrings authored at Plan 04-02 time carried the phrase 'MUST NOT import from book_specifics'; both reworded to 'MUST NOT import from the book-domain layer' / 'no book-domain imports'. Zero semantic change; substring scan stays belt-and-suspenders green. Same class of mitigation Plan 04-01 took on a ruff UP042-noqa-in-comment false-positive."
  - "(04-02) ConcatAssembler.from_committed_scenes zeroes telemetry fields (tokens_in=0, tokens_out=0, latency_ms=0, output_sha='') on re-read DraftResponse instances. These are re-read artifacts, not fresh drafter invocations — the original values are archived in runs/events.jsonl under role='drafter'. Alternative (preserving the values in the scene md frontmatter so re-read round-trips verbatim) was rejected: frontmatter is user-facing metadata (critic_scores_per_axis, voice_fidelity_score, voice_pin_sha); tokens/latency are post-hoc observability telemetry that Phase 6 OBS-02 joins from the event log. Kept frontmatter lean."
metrics:
  duration_minutes: 22
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 6  # concat.py, chapter.py, chapter_fewshot.yaml, chapter_system.j2, test_concat.py, test_chapter_critic.py
  files_modified: 5  # chapter_assembler/__init__.py, critic/__init__.py, config/rubric.py, config/rubric.yaml, tests/test_config.py
  tests_added: 20  # 8 ConcatAssembler + 12 ChapterCritic
  tests_passing: 460  # was 440 baseline; +20 new non-slow tests
  tests_baseline: 440
  slow_tests_added: 0
  scoped_mypy_source_files_after: 108  # was 107 after Plan 04-02 Task 1; +1 (chapter.py). Task 1 didn't add new mypy source count — concat.py went into the already-scoped chapter_assembler dir.
commits:
  - hash: 3303a00
    type: test
    summary: "Task 1 RED — failing tests for ConcatAssembler"
  - hash: 32f1ba1
    type: feat
    summary: "Task 1 GREEN — ConcatAssembler kernel (LOOP-02)"
  - hash: 6a04048
    type: test
    summary: "Task 2 RED — failing tests for ChapterCritic (CRIT-02)"
  - hash: d97f697
    type: feat
    summary: "Task 2 GREEN — ChapterCritic kernel (CRIT-02)"
---

# Phase 4 Plan 02: ConcatAssembler + ChapterCritic Summary

**One-liner:** Two Phase 4 kernel concretes landed — `ConcatAssembler` (deterministic scene-join producing a single chapter markdown with aggregated frontmatter + HTML `<!-- scene: ch{NN}_sc{II} -->` traceability markers, satisfies the frozen `ChapterAssembler` Protocol) and `ChapterCritic` (second `Critic` Protocol impl: Opus 4.7 chapter-level reviewer with stricter ≥3/5 per-axis threshold that the LLM cannot override, FRESH `ContextPack` accepted by caller contract for C-4 collusion prevention, CRIT-04 audit-on-every-invocation under `runs/critic_audit/chapter_{NN:02d}_01_*.json` with W-7 failure-path preservation, rubric_version='chapter.v1' stamped on response + Event + audit, and a single role='chapter_critic' OBS-01 Event per call). The `RubricConfig` Pydantic loader was extended additively (Phase 1 freeze-respecting) to carry a required `chapter_rubric: ChapterRubricConfig` field built by `model_validator(mode='before')` collapse from the flat `chapter_rubric_version` + `chapter_axes` YAML keys; existing scene rubric fields byte-identical. 20 new non-slow tests land (8 ConcatAssembler + 12 ChapterCritic covering plan-spec A-K + missing-axis fill); full suite 460 passed from 440 baseline, zero regression.

## ConcatAssembler — deterministic scene-join (LOOP-02)

**File:** `src/book_pipeline/chapter_assembler/concat.py` (237 lines).

**Contract:**

- `assemble(scene_drafts: list[DraftResponse], chapter_num: int) -> str` — pure join; matches frozen `ChapterAssembler` Protocol.
- `@classmethod from_committed_scenes(chapter_num, commit_dir) -> tuple[list[DraftResponse], str]` — sibling disk-reader; regex-validates filenames (`ch(\d+)_sc(\d+)\.md`) to block path-traversal per T-04-02-01; enforces B-3 invariant by raising `RuntimeError` if any scene md is missing the `voice_pin_sha` frontmatter key (T-04-02-01 mitigation).

**Output shape:**

```
---
chapter_num: 1
assembled_from_scenes: [ch01_sc01, ch01_sc02, ch01_sc03]
chapter_critic_pass: null     # filled by Plan 04-04 DAG orchestrator
voice_fidelity_aggregate: 0.85  # mean of per-scene voice_fidelity_score, null if any missing
word_count: 9
thesis_events: []             # filled by Plan 04-03 retrospective writer
voice_pin_shas: [sha1, sha2]  # dedup preserving order; size>1 signals mid-chapter pin upgrade
---

<!-- scene: ch01_sc01 -->
scene one body

---

<!-- scene: ch01_sc02 -->
scene two body
...
```

**Deterministic:** two `.assemble(drafts, chapter_num)` calls on identical inputs produce byte-identical strings. No timestamps in the output; `yaml.safe_dump(sort_keys=False)` freezes key ordering. Test 3 (`test_concat_is_deterministic`) asserts `out1 == out2`.

**Tests landed (8 non-slow):**

1. Protocol conformance (`isinstance(ConcatAssembler(), ChapterAssembler) is True`).
2. 3-scene happy path — chapter frontmatter + 3 HTML markers + 2 section separators.
3. Deterministic re-run — byte-identical output.
4. Mid-chapter pin upgrade — `voice_pin_shas` dedup preserving order.
5. Single-scene edge case — 1 HTML marker, 0 separators, valid frontmatter.
6. `from_committed_scenes` happy path — reads 2 scene md files (written out-of-order to verify regex-driven sort), returns `(drafts, chapter_text)`.
7. `from_committed_scenes` B-3 enforcement — scene md missing `voice_pin_sha` → `RuntimeError`.
8. `from_committed_scenes` fail-fast — missing `drafts/ch{NN}/` dir → `FileNotFoundError`.

## ChapterCritic — Opus 4.7 chapter-level reviewer (CRIT-02)

**File:** `src/book_pipeline/critic/chapter.py` (654 lines).

**Contract:** satisfies the frozen `Critic` Protocol at runtime (`isinstance(c, Critic) is True`, `c.level == "chapter"`).

**Pass threshold math (scoring conversion):**

- Chapter rubric stores `score_threshold_0to5: 3` per axis.
- LLM is instructed to score 0..5; the structured-output schema carries 0..100 floats (×20 normalization so the same `CriticResponse` Pydantic model covers scene + chapter).
- `_post_process` enforces per axis: `axis_pass = (score >= 60.0) AND (max_severity_on_axis != 'high')`. LLM's `pass_per_axis[axis]` boolean is OVERWRITTEN if it disagrees (warning-logged).
- `overall_pass = all(pass_per_axis.values())` — mismatched `overall_pass` is silently corrected (logged via `Event.extra['invariant_fixed']=True`).
- Missing axes filled with `pass=True, score=60.0` so a filled axis default-passes rather than default-fails (60.0 == exactly the 3/5 threshold; filled axes land in `Event.extra['filled_axes']`).

**Distilled threshold: `score_0to5 × 20 ≥ 60 ⇔ normalized_0to100 ≥ 60`.**

**CRIT-04 audit log shape:** `runs/critic_audit/chapter_{NN:02d}_01_{ts}.json` written on EVERY invocation (success AND tenacity-exhaustion failure per W-7). Record carries: `event_id`, `scene_id=chapter_{NN:02d}`, `chapter_num`, `assembly_commit_sha`, `attempt_number=1`, `timestamp_iso`, `rubric_version=chapter.v1`, `model_id`, `opus_model_id_response`, `caching_cache_control_applied=True`, `cached_input_tokens`, `system_prompt_sha`, `user_prompt_sha`, `context_pack_fingerprint`, `raw_anthropic_response` (full SDK dump on success; `{error, error_type, attempts_made=5}` on failure), `parsed_critic_response` (`CriticResponse.model_dump()` on success; `None` on failure).

**Fresh-pack invariant (C-4 mitigation, distributed enforcement):**

- `ChapterCritic` accepts `CriticRequest.context_pack` as pre-built — NO bundler import, NO retrievers list.
- Plan 04-04's DAG orchestrator will run `bundler.bundle(chapter_scene_request, retrievers)` with a chapter-scoped `SceneRequest(scene_index=0, chapter_midpoint_iso, primary_POV, beat_function='chapter_overview')` BEFORE calling `review()`.
- Audit record stamps `context_pack_fingerprint`; `test_E_fresh_pack_invariant` asserts that a distinct chapter-pack fingerprint (`CHAPTER_FP_XYZ`) appears in the audit record, provably != any scene-pack fingerprint (`SCENE_FP_ABC`).
- Future regression (caller reusing a scene pack) surfaces in Phase 6 OBS-02 ingester post-hoc via fingerprint join; Plan 04-06 integration test will assert `chapter_pack.fingerprint NOT IN {scene_pack.fingerprint}` end-to-end.

**Tenacity config (identical to SceneCritic):** 5 attempts, `wait_exponential(multiplier=2, min=2, max=30)`, `retry_if_exception_type((APIConnectionError, APIStatusError))`, `reraise=True`. Worst-case wall time ~92s per call (T-04-02-04 DoS mitigation).

**Tenacity timing proof (Test K):** `monkeypatch.setattr(ChapterCritic._call_opus_inner.retry, 'wait', tenacity.wait_fixed(0))` drops exhaustion wall time from ~60s to <2s. Test K asserts `elapsed < 2.0s` AND the failure audit record is still written. Same idiom as Plan 03-05 SceneCritic's `_patch_tenacity_wait_fast`.

**Tests landed (12 non-slow):**

| Test | Behavior |
|---|---|
| A | Protocol conformance (`isinstance(c, Critic)`, `c.level == 'chapter'`) |
| B | Happy path → `overall_pass=True`, 1 role='chapter_critic' Event, `Event.rubric_version == 'chapter.v1'` |
| C | Axis score 50 below 60 threshold → `pass=False` + `overall_pass=False` (post-process invariant fix) |
| D | Axis score 80 BUT 1 high-severity issue → `pass=False` (severity overrides score) |
| E | Fresh-pack invariant — audit records `CHAPTER_FP_XYZ`, distinct from `SCENE_FP_ABC` |
| F | Audit written on success with `scene_id=chapter_01`, `chapter_num=1`, `rubric_version=chapter.v1` |
| G | W-7 — tenacity exhaustion writes failure audit with `parsed_critic_response=None` + `raw_anthropic_response.error_type='APIConnectionError'` + `attempts_made=5` |
| H | Exactly 1 chapter_critic Event per review() call |
| I | `rubric_version` stamped on response + Event + audit (all three sites) |
| J | `_system_blocks` object-identity stable across review() calls (Anthropic cache identity) |
| K | Tenacity exhaustion fast (<2s with wait patch) + failure audit written |
| supplementary | Missing-axis fill (score=60.0 matches 3/5 threshold) + `Event.extra['filled_axes']==['metaphysics']` |

## `config/rubric.yaml` — chapter rubric block

Additive under Phase 1 freeze — scene `rubric_version: "v1"` + `axes:` mapping untouched byte-for-byte. New keys at YAML root:

```yaml
chapter_rubric_version: "chapter.v1"
chapter_axes:
  historical:
    description: "Cross-scene historical coherence; no contradictions between scenes in dates, places, or events."
    score_threshold_0to5: 3
    weight: 1.0
  metaphysics:
    description: "Cross-scene rule-card consistency; no mid-chapter engine-tier drift..."
    score_threshold_0to5: 3
    weight: 1.0
  entity:
    description: "Entity continuity across scenes; character states advance coherently chapter-wide."
    score_threshold_0to5: 3
    weight: 1.0
  arc:
    description: "Chapter hits its outline arc position; beat pacing balanced; no dead scenes."
    score_threshold_0to5: 3
    weight: 1.0
  donts:
    description: "No Things-to-Avoid violations detectable at chapter scale (thematic creep, cumulative drift)."
    score_threshold_0to5: 3
    weight: 1.0
```

## Deltas vs Plan 03-05 SceneCritic

| Facet | SceneCritic (03-05) | ChapterCritic (04-02) |
|---|---|---|
| Protocol `level` | `"scene"` | `"chapter"` |
| Pass threshold | `score >= 70.0 AND no-high-severity` | `score >= 60.0 AND no-high-severity` |
| LLM's pass_per_axis claim | Trusted (only overall_pass invariant enforced) | OVERRIDDEN by post-process on threshold violation |
| Rubric version | `"v1"` from `rubric.rubric_version` | `"chapter.v1"` from `rubric.chapter_rubric.rubric_version` |
| Missing-axis fill score | 75.0 | 60.0 (matches 3/5 threshold so filled default-passes) |
| Audit filename prefix | `{scene_id}_{attempt:02d}_{ts}.json` (e.g. `ch01_sc01_01_*.json`) | `chapter_{NN:02d}_01_{ts}.json` (e.g. `chapter_01_01_*.json`) |
| `attempt_number` in audit | From `request.chapter_context['attempt_number']` (R-tracked) | Always 1 (single-attempt; DAG orchestrator re-invokes on retry) |
| Event role | `"critic"` | `"chapter_critic"` |
| Context pack source | Trusted from `CriticRequest.context_pack` (bundler runs upstream) | Trusted from `CriticRequest.context_pack` (FRESH pack, caller-guaranteed; audit fingerprint locks invariant) |
| Tenacity config | 5 × `wait_exponential(2,2,30)` | 5 × `wait_exponential(2,2,30)` (identical) |
| Cache identity | Pre-rendered `_system_blocks` reused by reference | Same idiom, pre-rendered `_system_blocks` reused (Test J) |
| W-7 audit-on-failure | Yes | Yes (same `_handle_failure` shape; raises `ChapterCriticError` after audit + error Event) |
| `REQUIRED_AXES` | Scene 5-axis set | `CHAPTER_REQUIRED_AXES` — same 5 axes (named separately for future decoupling) |

**What stayed the same:** Protocol shape, `messages.parse(output_format=CriticResponse)` API, `SystemPromptBuilder` pattern with pre-rendered cached system prompt + `cache_control={'type':'ephemeral','ttl':'1h'}`, tenacity retry config, W-7 audit-then-raise failure handling, `_post_process` fill-missing-axes structure, rubric_version stamped 3-ways (response + Event + audit), single Event per invocation.

**What differs (beyond the table):** ChapterCritic's `_post_process` inspects `parsed.issues` to compute per-axis max severity and OVERRIDES the LLM's pass_per_axis booleans — SceneCritic trusts them. Audit record carries 2 additional fields (`chapter_num`, `assembly_commit_sha`). Event `caller_context` carries chapter-flavored fields (`chapter_num`, `assembly_commit_sha`) instead of scene-flavored (`scene_id`, `attempt_number`); `Event.extra` adds `chapter_word_count`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RUF002 × multiplication-sign in test docstrings.**

- **Found during:** Task 1 and Task 2 GREEN verify (`bash scripts/lint_imports.sh` ruff step).
- **Issue:** Two test-file docstrings and one code comment (`tests/chapter_assembler/test_concat.py`, `tests/critic/test_chapter_critic.py`) contained the literal `×` MULTIPLICATION SIGN (U+00D7). Ruff RUF002 flags it as ambiguous vs Latin small letter `x`. Hard-fails ruff; the lint-gate would have blocked the GREEN commit.
- **Fix:** Replaced all `×` with ASCII `x` in comments/docstrings. Math semantics unchanged (`"0..5 × 20"` → `"0..5 x 20"` stays unambiguous in prose context).
- **Files modified:** `tests/chapter_assembler/test_concat.py`, `tests/critic/test_chapter_critic.py`.
- **Commits:** folded into `32f1ba1` (Task 1 GREEN) and `d97f697` (Task 2 GREEN) before commit.
- **Scope:** Caused by this plan's test authoring. Rule 1 applies — ruff hard-fail.

**2. [Rule 1 - Bug] Kernel substring guard caught `"book_specifics"` token in docstrings.**

- **Found during:** Task 1 GREEN verify (`uv run pytest tests/test_import_contracts.py`).
- **Issue:** `src/book_pipeline/chapter_assembler/__init__.py` and `src/book_pipeline/chapter_assembler/concat.py` each had docstring phrases like `"MUST NOT import from book_specifics"`. The belt-and-suspenders test `test_kernel_does_not_import_book_specifics` does a literal substring scan for `"book_specifics"` in every kernel .py — caught the phrase in docstrings and hard-failed.
- **Fix:** Reworded to `"MUST NOT import from the book-domain layer"` / `"no book-domain imports"`. Zero semantic change; substring-scan stays green. Import-linter contract 1 remains the REAL enforcement; the substring scan is the secondary guard.
- **Files modified:** `src/book_pipeline/chapter_assembler/__init__.py`, `src/book_pipeline/chapter_assembler/concat.py`.
- **Commit:** folded into `32f1ba1` (Task 1 GREEN) before commit.
- **Scope:** Caused by Plan 04-02 Task 1 authoring. Same class of mitigation as Plan 04-01 Rule 1 (noqa UP042-in-comment false positive). Downstream plans writing prose about the kernel/book_specifics boundary should ALWAYS paraphrase.

**3. [Rule 2 - Missing critical functionality] Test-fixture update for extended RubricConfig schema.**

- **Found during:** Task 2 GREEN verify (full pytest run).
- **Issue:** `tests/test_config.py::test_rubric_accepts_valid_5_axes` wrote a minimal rubric YAML at `tmp_path/config/rubric.yaml` without the new `chapter_rubric_version` + `chapter_axes` keys. `RubricConfig()` now raises `ValidationError: chapter_rubric Field required`.
- **Fix:** Extended the fixture to include the chapter keys + asserted `cfg.chapter_rubric.rubric_version == "chapter.v1"`. Matches the extended RubricConfig shape. Alternative (making `chapter_rubric` Optional with default=None) was rejected — `ChapterCritic.__init__` reads `rubric.chapter_rubric.rubric_version` at construction time; an Optional default would only defer the crash to a confusing error site. Rule 2 applies — the test fixture needed to match the new schema contract.
- **Files modified:** `tests/test_config.py`.
- **Commit:** folded into `d97f697` (Task 2 GREEN) before commit.
- **Scope:** Caused by this plan's RubricConfig schema extension. Additive field; 1 fixture touched; 0 production regressions.

---

**Total deviations:** 3 auto-fixed (2 Rule 1 — ruff + substring-guard false-positive; 1 Rule 2 — test fixture schema update). **Zero Rule 4 architectural escalations.** Plan shape unchanged — ConcatAssembler + ChapterCritic land exactly as specified; threshold math, fresh-pack contract, audit filename prefix, Event role, and tenacity semantics all match plan spec verbatim.

## Authentication Gates

**None.** Plan 04-02 does not touch Anthropic API (tests mock via `FakeAnthropicClient`), Claude Code CLI, openclaw gateway, vLLM serve, or any network/auth boundary. Only local filesystem + local git commits + pure-Python pytest runs. The REAL Anthropic path exercises only through Plan 03-08 (scene critic smoke) and future Plan 04-05 (chapter critic smoke) — Plan 04-02 lands the kernel shape, not the live-infra call.

## Deferred Issues

1. **`lancedb.table_names()` deprecation warning** (~150 instances in the non-slow suite). Inherited from Phase 2 + Phase 3 plans. No functional impact. Not a Plan 04-02 concern; tracked in Plan 04-01 deferred list.
2. **Chapter critic prompt-template threshold hardcoding.** `chapter_system.j2` renders `pass threshold: score_0to5 >= {{ threshold }}` from the rubric config, BUT the scoring-guidance paragraph hardcodes `"3=acceptable baseline"`. A future plan that wants a 4/5 chapter rubric will need to regenerate the prose guidance + few-shot examples to match. Single change point is the template body, not the code.
3. **Event.role='chapter_critic' vs unified role='critic'+sub_type.** Phase 1 Event schema has no `sub_type` field. Plan 04-02 chose role='chapter_critic' to partition metrics in Phase 6 OBS-02 ingester without a schema bump. A future unified role='critic' + new sub_type field would require a Phase 1 Event schema version bump. Left for Phase 6 if OBS-02 ingester surfaces a concrete need.
4. **ConcatAssembler.from_committed_scenes telemetry loss.** Re-read DraftResponse instances have `tokens_in=0, tokens_out=0, latency_ms=0, output_sha=''`. The original values are archived in `runs/events.jsonl` under `role='drafter'`; Phase 6 OBS-02 ingester joins via `scene_id`. No regression; explicit design choice to keep frontmatter lean.

## Known Stubs

**None.** Every file shipped carries either:
- Concrete implementation (concat.py, chapter.py, chapter_system.j2, chapter_fewshot.yaml, rubric.py additions, rubric.yaml additions).
- Concrete test coverage (test_concat.py with 8 tests, test_chapter_critic.py with 12 tests, test_config.py fixture update).

No hardcoded empty values flowing to UI. No "coming soon" placeholders. No TODOs.

`DraftResponse` objects built by `ConcatAssembler.from_committed_scenes` have zeroed telemetry fields (`tokens_in=0`, etc.), but this is DOCUMENTED design (re-read artifacts; originals archived in the event log). Not a stub.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 7 threats in the register are covered as planned:

- **T-04-02-01** (Tampering: ConcatAssembler frontmatter): MITIGATED. `from_committed_scenes` REQUIRES `voice_pin_sha` in every scene's frontmatter (raises `RuntimeError` otherwise; test_from_committed_scenes_missing_voice_pin_sha_raises locks it in). Regex-validated filename pattern `ch(\d+)_sc(\d+)\.md` blocks path traversal.
- **T-04-02-02** (Tampering: ChapterCritic pass-threshold bypass): MITIGATED. `_post_process` enforces `pass_per_axis[axis] = (score >= 60.0) AND (no high-severity issue)` and OVERRIDES the LLM's per-axis boolean when it disagrees. Test_C + test_D lock both halves of the rule (threshold violation + high-severity override).
- **T-04-02-03** (Info disclosure: audit records contain raw chapter text): ACCEPTED. `runs/critic_audit/` is gitignored (existing rule from Plan 03-05). Same posture as T-03-05-07.
- **T-04-02-04** (DoS: unbounded tenacity + unbounded subprocess timeout): MITIGATED. 5 attempts × `wait_exponential(2,2,30)` ≈ 92s ceiling per call. Claude subprocess hard-cap lives in the Plan 03-09 `claude_code_cli` backend; ChapterCritic inherits via `anthropic_client` injection (tested implicitly by FakeAnthropicClient).
- **T-04-02-05** (Repudiation: chapter critic failure without trace): MITIGATED. W-7 pattern: audit record + error Event written BEFORE raise on tenacity exhaustion (test_G + test_K).
- **T-04-02-06** (EoP: ChapterCritic imports book_specifics): MITIGATED. Kernel substring-guard + import-linter contract 1 both green. `grep -c "book_specifics" src/book_pipeline/critic/chapter.py` returns 0.
- **T-04-02-07** (Tampering: fresh-pack invariant bypassed by caller): MITIGATED at audit grain. `test_E_fresh_pack_invariant` locks in that the audit record carries the chapter_pack fingerprint (distinct from scene_pack fingerprint in the test setup). End-to-end enforcement arrives in Plan 04-06 integration test (`chapter_pack.fingerprint NOT IN {scene_pack.fingerprint}`). Distributed C-4 mitigation: caller builds fresh pack; critic records fingerprint; integration test asserts distinctness.

## Verification Evidence

Plan `<success_criteria>` + task `<done>` coverage:

| Criterion | Status | Evidence |
|---|---|---|
| All tasks in 04-02-PLAN.md executed per TDD cadence | PASS | 2 × (RED + GREEN) = 4 commits: `3303a00`, `32f1ba1`, `6a04048`, `d97f697`. |
| Each task committed atomically | PASS | Separate RED and GREEN commits per task; each GREEN commit runs verify + lint before landing. |
| SUMMARY.md at .planning/phases/04-chapter-assembly-post-commit-dag/04-02-SUMMARY.md | PASS | This file. |
| ConcatAssembler satisfies ChapterAssembler Protocol | PASS | `test_concat_satisfies_protocol` asserts `isinstance(ConcatAssembler(), ChapterAssembler) is True`. |
| ConcatAssembler deterministic (byte-identical on re-run) | PASS | `test_concat_is_deterministic` asserts `out1 == out2`. |
| ChapterCritic satisfies Critic Protocol + level='chapter' | PASS | `test_A_protocol_conformance`. |
| ChapterCritic rubric_version='chapter.v1' stamped 3-ways | PASS | `test_I_rubric_version_stamped_everywhere`. |
| ≥3/5 threshold enforced (score >= 60 AND no-high-severity) | PASS | `test_C_below_threshold_fails` (score 50 → flipped) + `test_D_high_severity_fails_axis` (score 80 + high-sev → flipped). |
| CRIT-04 audit-on-every-invocation (success + failure) | PASS | `test_F_audit_record_on_success` + `test_G_audit_record_on_failure_W7`. |
| Fresh-pack invariant testable via audit fingerprint | PASS | `test_E_fresh_pack_invariant` asserts audit records `CHAPTER_FP_XYZ`, distinct from `SCENE_FP_ABC`. |
| Exactly 1 Event per chapter critic invocation | PASS | `test_H_one_event_per_invocation`. |
| Cached system_blocks object-identity stable | PASS | `test_J_cached_system_blocks_identity`. |
| Tenacity exhaustion fast with wait patch | PASS | `test_K_tenacity_exhaustion_fast` asserts <2s elapsed + audit written. |
| `config/rubric.yaml` has chapter_rubric_version + chapter_axes | PASS | `uv run python -c "import yaml; d=yaml.safe_load(open('config/rubric.yaml')); assert d['chapter_rubric_version']=='chapter.v1'; assert set(d['chapter_axes'].keys())=={'historical','metaphysics','entity','arc','donts'}"` prints `rubric ok`. |
| `bash scripts/lint_imports.sh` green | PASS | 2 contracts kept; ruff clean; mypy clean on 108 source files. |
| Full non-slow test suite passes from 440 baseline | PASS | 460 passed (+20 new non-slow: 8 ConcatAssembler + 12 ChapterCritic). 4 deselected (slow); 0 regression. |
| `uv run python -c "..."` smoke assert | PASS | Prints `assembler ok` + `critic level: chapter`. |

## Self-Check: PASSED

Artifact verification (files on disk at `/home/admin/Source/our-lady-book-pipeline/`):

- FOUND: `src/book_pipeline/chapter_assembler/concat.py` (237 lines)
- FOUND: `src/book_pipeline/chapter_assembler/__init__.py` (updated)
- FOUND: `src/book_pipeline/critic/chapter.py` (654 lines)
- FOUND: `src/book_pipeline/critic/__init__.py` (updated)
- FOUND: `src/book_pipeline/critic/templates/chapter_fewshot.yaml` (96 lines)
- FOUND: `src/book_pipeline/critic/templates/chapter_system.j2` (38 lines)
- FOUND: `src/book_pipeline/config/rubric.py` (updated additively)
- FOUND: `config/rubric.yaml` (updated additively)
- FOUND: `tests/chapter_assembler/test_concat.py` (216 lines, 8 tests)
- FOUND: `tests/critic/test_chapter_critic.py` (512 lines, 12 tests)
- FOUND: `tests/test_config.py` (fixture updated)

Commit verification on `main` branch (git log --oneline):

- FOUND: `3303a00 test(04-02): RED — failing tests for ConcatAssembler`
- FOUND: `32f1ba1 feat(04-02): GREEN — ConcatAssembler kernel (LOOP-02)`
- FOUND: `6a04048 test(04-02): RED — failing tests for ChapterCritic (CRIT-02)`
- FOUND: `d97f697 feat(04-02): GREEN — ChapterCritic kernel (CRIT-02)`

All 4 per-task commits landed on `main`. Aggregate gate green. Full non-slow test suite 460 passed (was 440 baseline; +20 new).

---

*Phase: 04-chapter-assembly-post-commit-dag*
*Plan: 02*
*Completed: 2026-04-22*
