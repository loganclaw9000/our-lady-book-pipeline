# Phase 4: Chapter Assembly + Post-Commit DAG - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning
**Mode:** Auto-generated via `gsd-discuss-phase --auto` (full-auto; user pre-answered locked decisions)

<domain>
## Phase Boundary

When all scenes for a chapter are COMMITTED in `drafts/ch{NN}/`, the pipeline atomically assembles them into `canon/chapter_{NN}.md`, runs an independent chapter-level critic against a **fresh** ContextPack (not the scene-level packs — breaks C-4 collusion), commits canon on pass, and fires a strict post-commit DAG (EntityExtractor → RAG reindex → RetrospectiveWriter) that must complete before the next chapter's drafting unblocks. A new `ChapterStateMachine` governs chapter transitions; the Phase 1 `SceneStateMachine` is frozen and untouched. All Phase 4 LLM calls route through the Phase 3 gap-closure `ClaudeCodeMessagesClient` — subscription-covered, no per-call billing.

**In scope (REQs):** CORPUS-02, CRIT-02, LOOP-02, LOOP-03, LOOP-04, TEST-01.

**Out of scope:**
- Mode-B escalation on chapter-critic fail (DRAFT-03, REGEN-03), Telegram alerts (ALERT-01), nightly openclaw cron (ORCH-01) — Phase 5. Phase 4 leaves chapter-fail scenes in `CHAPTER_FAIL` as handoff terminal state.
- Cross-family critic audit (CRIT-03), actual ablation runs, thesis matcher, digest generator, metrics ledger ingester — Phase 6. Phase 4 stands up only the **harness** for TEST-01 (config dataclass + CLI stub + `runs/ablations/` layout) so Phase 6 doesn't retrofit.
- Outline-auto-generated SceneRequests beyond the expected-scene-count gate — Phase 5 cron.

</domain>

<decisions>
## Implementation Decisions

### Chapter assembly trigger (LOOP-02, LOOP-03)
- `book-pipeline chapter <chapter_num>` CLI is the single entry point. Gate: all expected scenes (count from outline.md arc-position parser) present in `drafts/ch{NN}/` with `state=COMMITTED` in `drafts/scene_buffer/ch{NN}/<sid>.state.json`. Missing scenes → exit 2 with absent-ID list; partial chapters never touch `canon/`.
- Atomic rule: either all scenes assemble + chapter-critic passes + canon commits + DAG fires, OR nothing commits to `canon/`. Scene buffer is staging; only the chapter-commit step mutates canon.

### Assembly format (LOOP-02, grey-area a)
- `book_pipeline.chapter_assembler.ConcatAssembler` satisfies the frozen `ChapterAssembler` Protocol. Deterministic: scenes concatenated in `scene_index` order with `\n\n---\n\n` section-break markers. Re-running on identical inputs produces byte-identical output (success criterion 1).
- Per-scene YAML frontmatter discarded; each scene boundary preserved as HTML comment `<!-- scene: ch{NN}_sc{NN} -->` for Phase 6 traceability. Chapter frontmatter aggregates: `{chapter_num, assembled_from_scenes: [sid], chapter_critic_pass, voice_fidelity_aggregate: mean, word_count, thesis_events: [], voice_pin_shas: [sha]}` (size >1 indicates a mid-chapter pin upgrade — flagged in retrospective).

### Chapter-level critic independence (CRIT-02)
- `book_pipeline.critic.chapter.ChapterCritic` — second `Critic` Protocol impl with `level="chapter"`, `rubric_id="chapter.v1"`. Builds its OWN `ContextPack` from the assembled chapter text via a chapter-level `SceneRequest`-shaped query (beat_function = chapter's dominant arc beat, POV = primary POV, date = chapter midpoint ISO). Re-runs the Phase 2 bundler; does NOT receive scene-level packs. Prevents C-4 drafter/critic collusion (success criterion 2).
- Prompt template `src/book_pipeline/critic/templates/chapter_system.j2`: same 5-axis rubric, chapter-scoped rewording + arc-coherence + voice-consistency guidance. Backend via `build_llm_client(critic_backend_cfg)`. CRIT-04 audit log writes under `runs/critic_audit/chapter_{NN:02d}_{timestamp}.json`.
- **Pass threshold** (grey-area b): all 5 axes must score ≥3/5 (stricter than scene's ≥2/5). Any axis <3 or severity=`high` → FAIL. Fail handling (grey-area e): scenes stay in scene_buffer; chapter enters `CHAPTER_FAIL` — Phase 5 routing decides surgical scene-kick vs full-chapter Mode-B redraft.

### Post-commit DAG order (LOOP-02, LOOP-03, grey-area f)
Strict sequence, each step an atomic git commit (enables per-step rollback):
1. **Chapter commit:** `git commit -m "canon(ch{NN}): commit <title>"` writes `canon/chapter_{NN}.md`. `chapter_sha = git rev-parse HEAD` stamped into DAG artifacts for stale-card detection (success criterion 6).
2. **EntityExtractor commit:** produces `entity-state/chapter_{NN:02d}_entities.json`; message `chore(entity-state): ch{NN} extraction`.
3. **RAG reindex commit:** `entity_state` LanceDB table rebuilt from `entity-state/*.json`; `arc_position` retriever calls existing `ArcPositionRetriever.reindex()` (Protocol-conformant no-arg, Plan 02-04). Message `chore(rag): reindex after ch{NN}`.
4. **Retrospective commit:** produces `retrospectives/chapter_{NN:02d}.md`; message `docs(retro): ch{NN}`.

Total 4 commits per chapter. Next chapter drafting is GATED on commit 4 (LOOP-04).

### EntityExtractor (CORPUS-02, grey-area c)
- `book_pipeline.entity_extractor.opus.OpusEntityExtractor` satisfies the frozen Protocol. Backend = `ClaudeCodeMessagesClient`. Structured output via `claude -p --json-schema`.
- Schema: `EntityExtractionResponse(entities: list[EntityCard], chapter_num: int, extraction_timestamp: str)` at `book_pipeline/entity_extractor/schema.py`. `EntityCard.state` dict carries `{aliases: [str], entity_type: person|place|object|event, first_mentioned_chapter, current_state: str, relationships: [{to, kind}], confidence_score}`. `source_chapter_sha` mandatory (V-3).
- **Incremental:** loads all `entity-state/chapter_*.json`, passes consolidated prior-cards view as context, emits NEW or UPDATED cards only. Write path = single `entity-state/chapter_{NN:02d}_entities.json` per chapter (one file per chapter, simpler diff). Failure: tenacity 3× retry on transient; persistent fail → `DAG_BLOCKED` with alert hook (Phase 5 wires Telegram).

### RAG reindex (grey-area d)
- `entity_state` table: regenerate FULLY from `entity-state/chapter_*.json` (idempotent, cheap at ≤500 rows). BGE-M3 revision pinned in `rag_retrievers.yaml` — never change without bumping ingestion_run_id.
- `arc_position` table: existing `ArcPositionRetriever.reindex()` — reflects freshly-committed canon.
- Other 3 retrievers (historical, metaphysics, negative_constraint) are corpus-static; NOT re-indexed per chapter.

### RetrospectiveWriter (RETRO-01 via TEST-01, grey-area e)
- `book_pipeline.retrospective.opus.OpusRetrospectiveWriter` satisfies the frozen Protocol. Backend = `ClaudeCodeMessagesClient`.
- Input: `canon/chapter_{NN}.md` + slice of `runs/events.jsonl` filtered by `caller_context.chapter` + scene critic reports + voice-fidelity scores + per-scene `attempt_count`. Output: markdown with sections "What Worked", "What Drifted", "Emerging Patterns", "Open Questions for Next Chapter"; `candidate_theses` in YAML frontmatter.
- **Lint rule** (success criterion 5): must reference ≥1 specific scene ID (regex `ch\d+_sc\d+`) AND ≥1 critic-issue artifact (chunk_id / axis name / issue evidence quote). Lint fail → re-invoke once with "cite {sid}/{axis}" nudge; second fail logs warning, commits anyway (soft signal).
- Ungated: failure → log + skip; next chapter unblocks.

### LOOP-04 (next-chapter gate)
- State persisted at `.planning/pipeline_state.json` (derived view; git log is truth). Fields: `{last_committed_chapter, last_committed_dag_step: 1|2|3|4, dag_complete: bool, last_hard_block: str | null}`.
- Phase 5 cron reads this before spawning ch{NN+1} drafts. Phase 4 writes it atomically per DAG step; provides `book-pipeline chapter-status` CLI.

### TEST-01 (ablation harness foundation)
- Stands up `runs/ablations/` layout + `AblationRun` pydantic dataclass (`{run_id, variant_a_config_sha, variant_b_config_sha, n_scenes, corpus_sha, voice_pin_sha, created_at}`) + `book-pipeline ablate` CLI stub that validates two variant configs, creates `runs/ablations/{ts}/{a,b}/` skeletons, prints "Phase 6 will drive execution."
- No actual execution in Phase 4 — Phase 6 wires the loop. Gives Phase 6 on-disk shape to build against.

### ChapterStateMachine (grey-area g)
- NEW module `book_pipeline.interfaces.chapter_state_machine` alongside frozen `scene_state_machine`. NOT a Phase 1 addition — `SceneStateMachine` is frozen, `ChapterStateMachine` is new. Parallel structure: Pydantic `ChapterStateRecord` + `ChapterState` StrEnum + pure-Python `transition()` helper.
- States: `PENDING_SCENES → ASSEMBLING → ASSEMBLED → CHAPTER_CRITIQUING → (CHAPTER_FAIL | CHAPTER_PASS) → COMMITTING_CANON → POST_COMMIT_DAG → (DAG_COMPLETE | DAG_BLOCKED)`. Strict; no skipping. Persisted at `drafts/chapter_buffer/ch{NN}.state.json` via atomic tmp+rename.

### Scene buffer archival
- On successful DAG completion, `drafts/scene_buffer/ch{NN}/*` moves to `drafts/scene_buffer/archive/ch{NN}/` (git mv — preserves history for Phase 6 retrospective diffing). `drafts/ch{NN}/*.md` cleared post-DAG.

### CLI surface (Phase 4)
- `book-pipeline chapter <chapter_num>` — full loop: gate-check → assemble → chapter-critic → commit canon → DAG. Idempotent per state-machine record (resumes at last DAG step on re-run).
- `book-pipeline chapter-status [<chapter_num>]` — prints `.planning/pipeline_state.json` view.
- `book-pipeline ablate --variant-a <cfg> --variant-b <cfg> --n <N>` — TEST-01 stub.

### Claude's Discretion
Exact file layout within `chapter_assembler/`, `entity_extractor/`, `retrospective/`, `ablation/` modules; prompt template body details; test fixture chapter size (suggest 3 scenes × ~300 words for the integration test); Pydantic field ordering within `EntityExtractionResponse`; atomic-commit tooling (GitPython vs subprocess `git`).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1, 2, 3, 3.1)
- `book_pipeline.interfaces.{chapter_assembler, critic, entity_extractor, retrospective_writer}` — Protocols FROZEN. Phase 4 concrete impls satisfy signatures exactly; no Protocol refactor.
- `book_pipeline.interfaces.types` — `EntityCard` (with `source_chapter_sha`), `Retrospective`, `CriticRequest/Response/Issue` FROZEN; `Event` additive-only.
- `book_pipeline.critic.scene.SceneCritic` (Plan 03-05) — template + `anthropic_client: Any` pattern directly cloned for `ChapterCritic`. CRIT-04 audit pattern reused.
- `book_pipeline.llm_clients.{build_llm_client, ClaudeCodeMessagesClient}` (Plan 03-09) — default backend for all Phase 4 LLM calls. No `ANTHROPIC_API_KEY` required.
- `book_pipeline.rag.{ContextPackBundlerImpl, build_retrievers_from_config}` — re-used by `ChapterCritic` for its independent pack.
- `book_pipeline.rag.retrievers.arc_position.ArcPositionRetriever.reindex()` (Plan 02-04) — Protocol-conformant no-arg reindex, called in DAG step 3.
- `book_pipeline.cli.draft.{CompositionRoot, _build_composition_root}` (Plan 03-07) — pattern mirrored for `cli/chapter.py` (bundler, retrievers, chapter_critic, entity_extractor, retrospective_writer, state machine).
- `book_pipeline.observability.JsonlEventLogger` — Phase 4 LLM events stamp `caller_context.chapter` + role ∈ `{chapter_critic, entity_extractor, retrospective_writer}`.

### Established Patterns
- Kernel vs book_specifics (ADR-004): `chapter_assembler/`, `entity_extractor/`, `retrospective/`, `ablation/` are kernel-shaped. The `canon/` path anchor + outline-derived expected-scene-count lookup → `book_specifics/`. `pyproject.toml` import-linter list extended in the same PR.
- Short-lived batch CLI (ARCHITECTURE.md §5): `chapter <N>` is one tick; state on disk; state-machine-on-disk is the error handler.
- Backend-swappable LLM client (Plan 03-09 pattern): one `critic_backend:` block in `mode_thresholds.yaml` serves critic + extractor + retrospective.
- CRIT-04 audit pattern: `runs/critic_audit/<prefix>_<ts>.json` with `{raw_response, parsed, prompt_hash, chapter_num, rubric_version}`.
- Atomic persistence: tmp+rename for state JSON; `git commit` for canon/entity-state/retrospectives.

### Integration Points
- Phase 3 committed scenes at `drafts/ch{NN}/{sid}.md` with B-3 invariant (`voice_pin_sha == checkpoint_sha`). `ChapterAssembler` parses frontmatter for aggregation.
- `runs/events.jsonl` — RetrospectiveWriter's event source, filtered by `caller_context.chapter`.
- `indexes/resolved_model_revision.json` (Phase 2) carries ingestion_run_id — DAG reindex step updates after RAG rebuild.
- Claude Code CLI at `/home/admin/.local/bin/claude` — same OAuth session Phase 3 gap-closure verified (2026-04-22). No new auth surface.

</code_context>

<specifics>
## Specific Ideas

- **Fresh ContextPack for ChapterCritic is load-bearing** — if it inherits scene-pack fingerprints, CRIT-02 collapses to inline validation. Test assertion: `chapter_critic_pack.fingerprint NOT IN {scene.pack.fingerprint for scene in chapter}`.
- Commit chain resumability: if DAG step 2 fails AFTER step 1, `canon/chapter_{NN}.md` stays committed — partial completion valid. `ChapterStateRecord.state` holds resume point; re-running `book-pipeline chapter <N>` picks up at failed step without re-invoking chapter critic.
- Integration-test shape (success criterion 3 proof): 3-scene stub chapter (pre-seed `drafts/ch99/` with 3 synthetic `.md` + COMMITTED state records), run `book-pipeline chapter 99`, assert 4 git commits + `entity-state/chapter_99_entities.json` + `retrospectives/chapter_99.md` on disk + lint passes. Mock Claude Code CLI subprocess per Plan 03-09 E2E test pattern.
- `LOOP-04` gate file is a derived view, not truth — regression test: delete `.planning/pipeline_state.json`, re-derive from `git log --grep "canon(ch" --grep "docs(retro: ch"`; confirm reconstruction.
- Success criterion 6 regression: mutate `canon/chapter_01.md` by one byte without bumping `source_chapter_sha`; bundler flags stale card at next retrieval.
- PITFALLS C-4 (scene drafter + critic share pack) mitigation lives specifically in the ChapterCritic's fresh-bundle rule; test harness asserts the invariant.

</specifics>

<deferred>
## Deferred Ideas

- Mode-B redraft on `CHAPTER_FAIL` (REGEN-03/DRAFT-03) — Phase 5. Phase 4 terminal state is the handoff.
- Telegram alerts on `DAG_BLOCKED` or entity-extractor HARD_BLOCK — Phase 5 (ALERT-01).
- Oscillation detector for chapter-critic churn — Phase 5.
- Nightly openclaw cron reading `.planning/pipeline_state.json` to drive ch{NN+1} drafting — Phase 5 (ORCH-01).
- Actual ablation execution (variant-A vs variant-B N-scene runs with SHA-frozen snapshots) — Phase 6 (TEST-03). Phase 4 ships only the harness skeleton.
- Thesis matcher consumption of `candidate_theses` from retrospectives — Phase 6 (TEST-02).
- Cross-family critic audit (≥10% chapters, non-Anthropic judge) — Phase 6 (CRIT-03).
- Weekly digest surfacing chapter-critic fail rate / DAG block rate — Phase 6 (DIGEST-01).
- Metrics ledger ingester (events.jsonl → metrics.sqlite) — Phase 6 (OBS-02).
- Observability panel for voice-pin drift across chapter boundaries — Phase 6.

</deferred>
