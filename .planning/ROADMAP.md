# Roadmap: our-lady-book-pipeline

**Created:** 2026-04-21
**Granularity:** standard (6 phases)
**Parallelization:** enabled (cross-phase hints included where safe)
**Core value:** Autonomous first-draft production of *Our Lady of Champion* (27 chapters, ~81k words) with voice-faithful prose (FT local checkpoint), internally consistent narrative (5-axis typed RAG + critic), and transferable experiment telemetry for future writing pipelines.

---

## Phases

- [x] **Phase 1: Foundation + Observability Baseline** - uv scaffolding, Pydantic config, Protocol contracts, EventLogger, voice-pin + SHA canary, openclaw workspace, module-boundary lint, Telegram plumbing. (completed 2026-04-22)
- [x] **Phase 2: Corpus Ingestion + Typed RAG** - 5 LanceDB indexes, ContextPackBundler with 40KB cap + conflict reconciliation, arc-position beat parser, golden-query CI gate. (completed 2026-04-22)
- [x] **Phase 3: Mode-A Drafter + Scene Critic + Basic Regen** - vLLM-served voice checkpoint, scene Critic with 5-axis rubric, scene-local Regenerator (R=1), voice-fidelity anchor set, SceneStateMachine end-to-end. (completed 2026-04-22)
- [~] **Phase 4: Chapter Assembly + Post-Commit DAG** - ChapterAssembler, chapter-level Critic (fresh RAG pack), atomic canon commit, EntityExtractor with SHA-linked cards, RetrospectiveWriter with lint. (3/6 — 04-01 kernel skeletons + ChapterStateMachine; 04-02 ConcatAssembler + ChapterCritic; 04-03 OpusEntityExtractor + OpusRetrospectiveWriter)
- [ ] **Phase 5: Mode-B Escape + Regen Budget + Alerting + Nightly Orchestration** - Mode-B Drafter (Opus), full R-cap regen with cost gate, oscillation detector, Mode-B preflags, hard-block Telegram alerts, nightly openclaw cron.
- [ ] **Phase 6: Testbed Plane + Production Hardening + First Draft** - Thesis registry + matcher, ablation harness, cross-family critic, weekly digest, metrics ledger ingester, 27-chapter production run with >=3 closed theses.
- [x] **Phase 7: Narrative Physics Engine** - Codified storytelling atomics + 13-axis critic + drafter pre-flight gates + canon-bible continuity layer (CB-01 6th retriever) + scene-buffer dedup + ch15+ forward-only enforcement. (5/5 plans + gsd-verifier PASS after 2026-04-26 gap closure)

---

## Phase Details

### Phase 1: Foundation + Observability Baseline

**Goal**: A runnable package skeleton with EventLogger live and voice-pin SHA verification wired, such that every subsequent LLM call automatically produces a structured event. No prose is drafted in this phase, but the observability plane that watches drafting is already operational.

**Depends on**: Nothing (first phase)

**Requirements**: FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, OBS-01

**Success Criteria** (what must be TRUE):
  1. Running `uv sync` from a clean clone produces a working venv; `uv run book-pipeline --version` prints a version string and exits 0.
  2. All four YAML configs (`voice_pin.yaml`, `rubric.yaml`, `rag_retrievers.yaml`, `mode_thresholds.yaml`) load into typed Pydantic Settings models, and startup fails with a clear error if any field is missing or malformed.
  3. `openclaw.json` at repo root is recognized by the gateway, the `workspaces/drafter/` workspace has AGENTS/SOUL/BOOT markdown, and `openclaw cron add` succeeds (even if the cron body is a no-op placeholder).
  4. The 13 Protocol interfaces are importable from `book_pipeline.interfaces` with docstring contracts; stub implementations raise NotImplementedError but satisfy `isinstance(...)` for Protocol checks.
  5. A smoke invocation of the EventLogger writes a well-formed JSONL line to `runs/events.jsonl` with all OBS-01 fields (ts, role, model, prompt_hash, token counts, latency, temp, top_p, caller, output_hash, mode_tag) — this line is the first demonstration that OBS-01 is live from day one.
  6. Module-boundary lint (ruff rule or custom check) flags book-specific imports inside generic-kernel-candidate modules and passes CI.

**Plans**: 6 plans in 4 waves (Wave 1: 01 skeleton → Wave 2 parallel: 02 Protocols + 03 configs + 04 openclaw → Wave 3: 05 EventLogger → Wave 4: 06 import-linter)
- [x] 01-01-PLAN.md — Package skeleton (pyproject, uv.lock, CLI subcommand dispatcher, dev tooling) [FOUND-01]
- [x] 01-02-PLAN.md — 13 Protocol interfaces + Pydantic type contracts + stubs [FOUND-04]
- [x] 01-03-PLAN.md — 4 YAML configs + Pydantic-Settings models + validate-config CLI [FOUND-02]
- [x] 01-04-PLAN.md — openclaw.json + drafter workspace + bootstrap/register-cron CLI [FOUND-03]
- [x] 01-05-PLAN.md — JsonlEventLogger concrete + xxhash helpers + smoke-event CLI [OBS-01]
- [x] 01-06-PLAN.md — import-linter module boundary contracts + violation-proof test [FOUND-05]
**UI hint**: no

**Parallelization**: Plans 02 + 03 + 04 run in parallel in Wave 2 after Plan 01's skeleton lands (zero file-overlap — plans 03/04 append to main.py's SUBCOMMAND_IMPORTS via strictly-additive one-line edits). Plan 05 (Wave 3) depends on Plan 02's Event model + EventLogger Protocol. Plan 06 (Wave 4) must be last so it lints real committed modules.

---

### Phase 2: Corpus Ingestion + Typed RAG

**Goal**: Given a `{POV, date, location, beat_function, chapter_num}` scene request, the pipeline produces a single ContextPack <=40KB assembled from 5 typed retrievers with provenance and surfaced conflicts. Retrieval quality is testable in isolation (golden-query CI) before any drafter pressure is applied.

**Depends on**: Phase 1 (Protocol contracts; EventLogger; config loading)

**Requirements**: CORPUS-01, RAG-01, RAG-02, RAG-03, RAG-04

**Success Criteria** (what must be TRUE):
  1. Ingesting `~/Source/our-lady-of-champion/` populates 5 LanceDB tables (`historical`, `metaphysics`, `entity_state`, `arc_position`, `negative_constraint`) read-only against the source; re-running ingestion is idempotent and incremental.
  2. Calling `retrieve(SceneRequest)` on each of the 5 Retriever implementations returns a RetrievalResult with source-file + chunk-id provenance on every hit, never a bare text blob.
  3. `outline.md` is parsed into the arc-position retriever at beat-function granularity (27 chapters x blocks x beats) with stable beat IDs that survive re-ingestion.
  4. ContextPackBundler enforces a hard 40KB ceiling, runs a cross-retriever reconciliation step, and emits `retrieval_conflicts.json` when retrievers contradict (never silently concatenates).
  5. A golden-query CI job with >=5 queries per retriever passes on a fresh clone; any index drift that moves expected chunks breaks the job.

**Plans**: 6 plans in 5 waves (Wave 1: 01 rag foundation → Wave 2: 02 CorpusIngester → Wave 3 parallel: 03 text retrievers + 04 entity_state + arc_position → Wave 4: 05 ContextPackBundler → Wave 5: 06 golden-query CI + openclaw cron)
- [x] 02-01-PLAN.md — rag kernel module: chunker + BGE-M3 embedder + LanceDB schema + import-linter extension [CORPUS-01]
- [x] 02-02-PLAN.md — CorpusIngester + router + mtime idempotency + `book-pipeline ingest` CLI + 5 LanceDB tables populated [CORPUS-01]
- [x] 02-03-PLAN.md — LanceDBRetrieverBase + BgeReranker + 3 retrievers (historical, metaphysics rule_type-filtered, negative_constraint always-top-K) [RAG-01]
- [x] 02-04-PLAN.md — outline_parser with stable beat IDs + entity_state (zero-cards-tolerant) + arc_position retriever [RAG-01, RAG-02]
- [x] 02-05-PLAN.md — ContextPackBundler: 40KB hard cap + per-axis soft caps + cross-retriever conflict detection + 6-event emission [RAG-03]
- [x] 02-06-PLAN.md — golden-query CI gate (13 queries, 0 forbidden leaks) + openclaw nightly-ingest cron + baseline ingest pinned at ing_20260422T082448725590Z_2264c687 [RAG-04, CORPUS-01]
**UI hint**: no

**Parallelization**: Plans 03 and 04 run in parallel in Wave 3 (exclusive file ownership — 03 owns base.py + historical/metaphysics/negative_constraint retriever files + reranker; 04 owns entity_state + arc_position retriever files + outline_parser; both edit retrievers/__init__.py but that's additive). Plans 05 and 06 serialize in Waves 4 and 5 because Plan 05 extends rag/__init__.py (to export ContextPackBundlerImpl) and Plan 06 edits the same file. Bundler + reconciliation step depends on all 5 retrievers existing (Plans 03 + 04).

---

### Phase 3: Mode-A Drafter + Scene Critic + Basic Regen

**Goal**: A single scene (ch01_sc01) can be drafted by the pinned voice-FT checkpoint, critiqued by Opus against the 5-axis rubric, regenerated once on failure, and left on disk in a well-defined SceneStateMachine state — with voice-fidelity measured from the very first commit (anchor set curated before any prose lands).

**Depends on**: Phase 1 (EventLogger, voice-pin config, Protocol contracts), Phase 2 (ContextPackBundler produces a ContextPack for a scene request)

**Requirements**: DRAFT-01, DRAFT-02, CRIT-01, CRIT-04, REGEN-01, OBS-03

**Success Criteria** (what must be TRUE):
  1. vLLM serves the pinned voice checkpoint on port 8002 under a systemd --user unit; book pipeline Drafter boots refuse to operate if the checkpoint SHA recorded in `voice_pin.yaml` does not match the loaded weights.
  2. A single scene drafted via Mode-A produces a DraftResponse whose per-scene-type sampling parameters (temperature, top_p, repetition_penalty) were sourced from config and whose event log entry records `mode="A"`, `checkpoint_sha=<sha>`, and a voice-fidelity cosine against the 20-30 anchor passages.
  3. The Critic returns a CriticResponse parsed via `client.messages.parse()` with Pydantic validation, per-axis `{score, severity, issues:[{location, claim, evidence}]}` populated for all 5 axes (historical, metaphysics, entity, arc, don'ts).
  4. Rubric versions (`rubric.yaml` v1, v2, ...) are stamped on every critic event; a later digest can filter scene scores by rubric version without cross-contamination.
  5. On a critic FAIL with severity >= mid, the Regenerator takes the structured issue list and rewrites only affected passages within +/-10% word count; the regenerated draft is scored again and its event log entry records `attempt_number=2`.
  6. The voice-fidelity anchor set (20-30 curated passages) is committed to the repo before any production Mode-A scene commits, and its SHA is pinned in config — retroactive baselines are prevented by construction.

**Plans**: 8 plans in 7 waves (Wave 1: 01 kernel-skeleton+voice-pin-V6 → Wave 2: 02 anchor-curation+voice_fidelity → Wave 3 parallel: 03 vLLM systemd+client + 05 Scene critic → Wave 4: 04 Mode-A drafter → Wave 5: 06 Regenerator kernel-only → Wave 6: 07 CLI composition+SceneStateMachine+stub+mocked integration → Wave 7: 08 human-verify real-world smoke)

Plans:
- [x] 03-01-PLAN.md — Kernel package skeletons (drafter/critic/regenerator/voice_fidelity) + V6 SHA pin + pin-voice CLI [DRAFT-01]
- [x] 03-02-PLAN.md — OBS-03 anchor curation (20-30 passages) + voice_fidelity module (centroid + scorer) + mode_thresholds voice_fidelity block [OBS-03]
- [x] 03-03-PLAN.md — vLLM systemd unit + httpx/tenacity VllmClient + boot_handshake SHA gate [DRAFT-01]
- [x] 03-04-PLAN.md — Mode-A drafter: Jinja2 template + sampling profiles + memorization gate + voice-fidelity Event [DRAFT-01, DRAFT-02, OBS-03]
- [x] 03-05-PLAN.md — Scene critic: Anthropic Opus 4.7 messages.parse + ephemeral 1h cache + CRIT-04 audit log + rubric_version stamp [CRIT-01, CRIT-04]
- [x] 03-06-PLAN.md — SceneLocalRegenerator kernel module: Jinja2 regen template + tenacity + ±10% word-count guard + Event emission (mocked Anthropic tests only) [REGEN-01]
- [x] 03-07-PLAN.md — book-pipeline draft CLI composition + SceneStateMachine wiring + ch01_sc01 stub + build_retrievers_from_config factory + mocked integration tests [REGEN-01]
- [x] 03-08-PLAN.md — Human-verify real-world smoke on ch01_sc01 (REAL vLLM + REAL Anthropic Opus + REAL RAG) [REGEN-01]
**UI hint**: no

**Parallelization**: Plan 01 lands kernel skeletons + pyproject.toml import-linter extension + V6 SHA pin FIRST (Wave 1) so later plans can land concrete code inside drafter/critic/regenerator/voice_fidelity without pyproject churn. Plan 02 consumes 01 scaffolding to curate anchors + fill the voice_fidelity scorer. Wave 3 plans 03 + 05 run in parallel (03 owns drafter/vllm_client + drafter/systemd_unit + cli/vllm_bootstrap; 05 owns critic/scene + critic/audit + critic/templates; zero file overlap). Wave 4 Plan 04 composes the Mode-A drafter on top of voice_fidelity (02) + vLLM client (03). Wave 5 Plan 06 ships SceneLocalRegenerator kernel-only (no CLI composition) — depends on 01 + 05 for VOICE_DESCRIPTION + tenacity pattern reuse. Wave 6 Plan 07 is the CLI composition + state machine + ch01_sc01 stub + build_retrievers_from_config factory (W-1) + mocked integration tests — depends on 01..06 for full kernel availability. Wave 7 Plan 08 is the human-verify real-world smoke with operator pre-flight checklist — depends on 07 for the CLI to exist. The 03-06→03-07→03-08 split was introduced via planner-checker revision pass B-1 closure to keep each plan within executor-quality budget (~50% context / 2-3 tasks).

---

### Phase 4: Chapter Assembly + Post-Commit DAG

**Goal**: When all scenes for a chapter are in the buffer, they atomically assemble into `canon/chapter_NN.md`, pass an independent chapter-level critic (fresh RAG pack, not the scene pack), commit to git, and trigger the post-commit DAG (EntityExtractor -> RAG reindex -> RetrospectiveWriter) to completion before the next chapter's drafting begins.

**Depends on**: Phase 3 (scenes exist and commit to buffer), Phase 2 (RAG bundler re-queryable for chapter-critic independence)

**Requirements**: CORPUS-02, CRIT-02, LOOP-02, LOOP-03, LOOP-04, TEST-01

**Success Criteria** (what must be TRUE):
  1. ChapterAssembler deterministically stitches buffered scenes into `canon/chapter_NN.md`; re-running on identical inputs produces identical output (diff is empty).
  2. The chapter-level Critic issues its OWN RAG query (not the scene packs) and scores the assembled chapter on arc-coherence, pacing, voice-consistency, and interior-change axes — breaking the C-4 collusion where scene drafter and scene critic share a pack.
  3. On chapter-critic PASS, an atomic git commit lands the chapter in `canon/`, the post-commit DAG fires (EntityExtractor writes SHA-linked cards to `entity-state/chapter_NN/`, RAG reindex runs against the new entity cards, RetrospectiveWriter produces `retrospectives/chapter_NN.md`), and the next chapter's drafting is BLOCKED until the DAG completes.
  4. On chapter-critic FAIL, surgical scene-kick is the default (only the implicated scene(s) return to regen); a full-chapter redraft is triggered only by an explicit severity signal recorded in the event log.
  5. The RetrospectiveWriter output passes a lint rule that rejects generic boilerplate (e.g., must cite specific scene IDs, must reference at least one critic-issue artifact) — the first retrospective proves the testing machinery before Phase 5 depends on it.
  6. EntityCards carry a `source_chapter_sha` field; the bundler flags any card whose source SHA no longer matches the current canon file (stale-card detection from day one).

**Plans**: 6 plans in 5 waves (Wave 1: 01 kernel skeletons + ChapterStateMachine → Wave 2 parallel: 02 ConcatAssembler + ChapterCritic && 03 EntityExtractor + RetrospectiveWriter → Wave 3: 04 Post-commit DAG orchestrator + AblationRun harness → Wave 4: 05 book-pipeline chapter + chapter-status + ablate CLIs → Wave 5: 06 end-to-end mocked integration test)

Plans:
- [x] 04-01-PLAN.md — Kernel package skeletons (chapter_assembler/entity_extractor/retrospective/ablation) + ChapterStateMachine + import-linter extension [LOOP-02, LOOP-03]
- [x] 04-02-PLAN.md — ConcatAssembler deterministic scene-join + ChapterCritic (≥3/5 threshold, fresh ContextPack, CRIT-04 audit log) [LOOP-02, CRIT-02]
- [x] 04-03-PLAN.md — OpusEntityExtractor (incremental update, source_chapter_sha stamping) + OpusRetrospectiveWriter (lint-enforced output) [CORPUS-02, TEST-01]
- [x] 04-04-PLAN.md — ChapterDagOrchestrator (4-commit strict-order DAG + resumability + scene buffer archival) + AblationRun harness skeleton [LOOP-02, LOOP-03, TEST-01]
- [x] 04-05-PLAN.md — book-pipeline chapter <N> + chapter-status + ablate CLIs + EXPECTED_SCENE_COUNTS book-specifics table [LOOP-03, LOOP-04, TEST-01]
- [x] 04-06-PLAN.md — End-to-end mocked integration test (3-scene stub chapter → 4 commits + 3 artifacts + fresh-pack invariant + lint-pass retrospective) [LOOP-02, LOOP-03, LOOP-04, CRIT-02, CORPUS-02, TEST-01]
**UI hint**: no

**Parallelization**: ChapterAssembler, EntityExtractor, and RetrospectiveWriter can be scaffolded in parallel once their Protocols are pinned. The post-commit DAG ordering (extractor -> reindex -> retrospective -> ready_for_next) is strict and must be sequenced; building the DAG orchestrator is one plan, building the three agents is three plans.

---

### Phase 5: Mode-B Escape + Regen Budget + Alerting + Nightly Orchestration

**Goal**: Every failure path terminates in either a successful commit (Mode-A, Mode-B escalation, or regen success) or a deduplicated Telegram alert — never a silent wedge. The nightly openclaw cron drives the full loop unattended, budget caps prevent Mode-B cost blowouts, and pre-flagged structurally complex beats (Cholula, two-thirds reveal, siege) route to Mode-B from the start.

**Depends on**: Phase 4 (chapters commit end-to-end; retrospectives exist), Phase 3 (scene loop operates), Phase 1 (Telegram alert plumbing stub exists)

**Requirements**: DRAFT-03, DRAFT-04, REGEN-02, REGEN-03, REGEN-04, LOOP-01, ORCH-01, ALERT-01, ALERT-02

**Success Criteria** (what must be TRUE):
  1. When Mode-A regens exhaust the configurable R budget on a scene, the controller auto-escalates to Mode-B Drafter (Anthropic Opus 4.7 with voice samples in-context, `ttl="1h"` ephemeral prompt cache), and the scene's event log records `mode="B"` with triggering issue IDs.
  2. Pre-flagged beats from `config/mode_preflags.yaml` (Cholula stir, two-thirds revelation, siege climax) route to Mode-B directly without burning Mode-A regen budget; demotion to Mode-A requires an explicit config change and is logged.
  3. A per-scene cost cap is enforced as a HARD abort with mid-run Telegram alert (not end-of-week surprise); the oscillation detector flags scenes alternating between two failure axes across regen iterations and escalates to Mode-B without spending the remaining R.
  4. The scene loop runs end-to-end autonomously (request -> RAG -> Drafter -> Critic -> [PASS=buffer | FAIL=regen | EXHAUST=Mode-B | BLOCK=alert]) with <=1 human-touch per nominal scene; a forced-failure test drives a scene through every branch.
  5. Nightly `openclaw cron add` at 02:00 kicks the loop; the gateway survives a reboot and the cron entry in `~/.openclaw/cron/jobs.json` persists; a stale-cron detector alerts if no run has completed in >36h.
  6. Hard-block conditions (stuck regen, rubric conflict, budget blown, voice-drift beyond threshold, checkpoint SHA mismatch, vLLM health failure) emit deduplicated Telegram alerts with a 1-hour cool-down before re-alerting on the same condition.

**Plans**: 4 plans in 3 waves (Wave 1: 05-01 Mode-B kernel + preflag + pricing + voice-samples curator → Wave 2 parallel: 05-02 regen-budget + oscillation + scene-kick routing && 05-03 alerts kernel + TelegramAlerter + bundler stale-card flag → Wave 3: 05-04 nightly orchestrator + openclaw cron + stale-cron detector + OBS-02 SQLite ledger)

Plans:
- [x] 05-01-PLAN.md — Mode-B Drafter (Opus 4.7 + cache_control 1h) + preflag reader + pricing table + curate-voice-samples CLI [DRAFT-03, DRAFT-04]
- [x] 05-02-PLAN.md — Regen-budget wrapper + oscillation detector + spend-cap enforcement + surgical scene-kick routing (SC4 closure) [REGEN-02, REGEN-03, REGEN-04, LOOP-04]
- [x] 05-03-PLAN.md — alerts/ kernel package + TelegramAlerter + cooldown persistence + bundler stale-card flag (SC6 closure) [ALERT-01, ALERT-02, CORPUS-02]
- [x] 05-04-PLAN.md — Nightly orchestrator CLI + openclaw cron registration + stale-cron detector + OBS-02 SQLite ledger ingester [ORCH-01, LOOP-01]
**UI hint**: no

**Parallelization**: Mode-B Drafter (DRAFT-03/04) and the regen-upgrade work (REGEN-02/03/04) are largely independent; alerting (ALERT-01/02) depends on hard-block taxonomy being defined but can be built in parallel against stubbed triggers. ORCH-01 comes last in this phase because it needs every failure path to terminate cleanly.

---

### Phase 6: Testbed Plane + Production Hardening + First Draft

**Goal**: The pipeline earns its testbed designation. Theses close with transferable artifacts, the weekly digest becomes the single human-facing interface, ablations produce structured deltas on held-fixed configs, cross-family critic spot-checks flag judge bias, and the pipeline drives to the terminal milestone: 27 chapters committed with >=3 closed theses yielding transferable artifacts for pipeline #2 (blog).

**Depends on**: Phase 5 (nightly autonomous loop runs; Mode-B commits exist), Phase 4 (retrospectives accumulate), Phase 3 (per-axis scores persist), Phase 1 (EventLogger schema is frozen)

**Requirements**: OBS-02, OBS-04, CRIT-03, TEST-02, TEST-03, TEST-04, ORCH-02, FIRST-01, FIRST-02

**Success Criteria** (what must be TRUE):
  1. The ObservabilityIngester rebuilds `runs/metrics.sqlite` idempotently from `runs/events.jsonl` on every run, includes an integrity line (row counts + checksum) that the weekly digest displays, and the schema is versioned so longitudinal queries survive rubric/prompt migrations.
  2. The weekly DigestGenerator (07:00 cron, Opus-authored markdown in `digests/week_YYYY-WW.md`) surfaces Mode-B rate, per-axis score trends by rubric version, regen count distribution, critic false-positive-rate proxies, cost-per-chapter, stale-card panel, thesis-aging panel (flagging any thesis open >30 days without evidence), and blockers.
  3. The thesis registry under `theses/open/` and `theses/closed/` passes the schema linter (frontmatter requires `metric` + `test_design` + `deadline`); the ThesisMatcher (Opus reads retrospectives + events) proposes closures with transferable-artifact blocks and Paul confirms or overrides weekly.
  4. The ablation harness runs N scenes under variant-A vs variant-B with SHA-frozen snapshot of config + corpus + checkpoint, writes structured deltas to `runs/ablations/<ts>/`, and can be invoked for any open thesis requiring paired evidence.
  5. A cross-family critic audit (non-Anthropic judge: Gemini 2.5 Pro or GPT-5) runs on >=10% of scenes; when per-axis disagreement exceeds the configured threshold, the digest flags a human-review candidate.
  6. FIRST-01 acceptance: 27 chapters committed to `canon/` with the final-milestone digest including production summary (word count, chapter pacing, mode-A/mode-B distribution, regen distribution, total Anthropic spend), testbed summary (>=3 closed theses with their transferable artifacts), and transfer-ready notes for pipeline #2 (blog).

**Plans**: TBD
**UI hint**: no

**Parallelization**: Testbed infrastructure (thesis registry, ablation harness, metrics ingester, digest generator) is largely independent and parallelizable once Phase 5 produces real signal. Cross-family critic (CRIT-03) depends on scene-critic output format but not on other Phase 6 work. FIRST-01 is gated by everything else landing; its "plan" is largely operational: run the pipeline, watch the digest, close theses.

---

### Phase 7: Narrative Physics Engine — codified storytelling atomics + 13-axis critic + canon-bible continuity layer + scene-buffer dedup + ch15+ forward-only enforcement

**Goal:** Build the Narrative Physics Engine — a metadata + rules + enforcement layer that codifies storytelling atomics so the pipeline can draft + validate scenes against narrative invariants (POV, motivation, treatment, content ownership, named-quantity continuity, stub-leak, repetition-loop, scene-buffer similarity) the way Unreal Engine validates physical motion against physics invariants. **Forward-only (D-21):** builds for ch15-27 + ch09 retry; ch01-14 historical artifacts NOT retrofit; ch01-04 read-only sanity baseline.

**Requirements**: PHYSICS-01, PHYSICS-02, PHYSICS-03, PHYSICS-04, PHYSICS-05, PHYSICS-06, PHYSICS-07, PHYSICS-08, PHYSICS-09, PHYSICS-10, PHYSICS-11, PHYSICS-12, PHYSICS-13

**Depends on:** Phase 5 (alerts kernel-package precedent + scene-kick recovery loop both reused); Phase 4 (chapter_assembler/concat.py extended for D-18 quote normalizer); Phase 3 (scene critic 5-axis extended to 13); Phase 2 (RAG 6th retriever via existing LanceDB additive nullable contract). Does NOT block on Phase 6 — Phase 7 can ship in parallel with Phase 6 testbed work.

**Success Criteria** (what must be TRUE):
  1. `book_pipeline.physics` kernel package landed with strict Pydantic SceneMetadata schema (D-03/D-13/D-04 fields), 5 pre-flight gates (pov_lock, motivation, ownership, treatment, quantity), 2 deterministic pre-LLM detectors (stub_leak, repetition_loop), SceneEmbeddingCache + cosine helpers; import-linter contract extended to enforce kernel boundary.
  2. CB-01 6th RAG axis lands as a new VALUE for the existing rule_type column ('canonical_quantity') — no new LanceDB column, no new table — with the 5 manuscript canaries (Andres age, La Nina height, Santiago del Paso scale, Cholula date, Cempoala arrival) hand-seeded per OQ-05 (c). Bundler emits 7 events per call (was 6).
  3. Drafter pre-flight runs the 5 gates BEFORE any vLLM call (D-24); each emission produces one role='physics_gate' Event per OBS-01. Drafter prompt header injects D-23 verbatim canonical-quantity stamp + D-13 fenced ownership/beat block.
  4. Critic 5-axis rubric extends to 13 axes (rubric.yaml v2). Pre-LLM short-circuits (stub_leak, repetition_loop) fire BEFORE the Anthropic call; on hit, return synthetic CriticResponse without LLM spend. motivation_fidelity FAIL is hard-stop (overall_pass=False unconditionally — D-02 load-bearing).
  5. Scene-buffer dedup: BGE-M3 cosine ≥0.80 vs prior committed scenes' embeddings forces scene_buffer_similarity=False + scene-kick (D-28). Embedding cache lives at `.planning/intel/scene_embeddings.sqlite` with PRIMARY KEY (scene_id, bge_m3_revision_sha) so model upgrades naturally invalidate.
  6. ch15+ first-flight smoke: ch15 sc02 resume passes all 13 axes (or scene-kicks recover deterministically). ch01-04 read-only smoke: engine flags zero false positives on the 4 frozen-baseline chapters across 13 axes. PovLock activates at ch15+ for Itzcoatl (1st_person); ch09 retry NOT gated per OQ-01 (a).

**Plans**: 5 plans in 4 waves (Wave 1: 07-01 schema + locks + import-linter + REQUIREMENTS.md → Wave 2: 07-02 CB-01 retriever + canonical_quantity ingest + 7-event bundler invariant → Wave 3 parallel: 07-03 pre-flight gates + canon_bible + drafter prompt extension && 07-04 critic 13-axis + stub_leak + repetition_loop + motivation hard-stop → Wave 4: 07-05 scene-buffer cosine + quote normalizer + CLI composition + ch15 / ch01-04 integration smokes)

Plans:
- [x] 07-01-PLAN.md — physics package skeleton + SceneMetadata Pydantic schema + PovLock storage + config/pov_locks.yaml + import-linter contract + REQUIREMENTS.md PHYSICS-01..13 [PHYSICS-01, PHYSICS-02, PHYSICS-03]
- [x] 07-02-PLAN.md — ContinuityBibleRetriever (6th axis) + canonical_quantities corpus_ingest + config/canonical_quantities_seed.yaml hand-seeded canaries + bundler 7-event invariant [PHYSICS-04]
- [x] 07-03-PLAN.md — physics/canon_bible.py + 5 pre-flight gate files + run_pre_flight composer + drafter ModeA pre-flight wiring + Jinja2 canonical-stamp + fenced beat directive [PHYSICS-05, PHYSICS-06]
- [x] 07-04-PLAN.md — physics/stub_leak.py + physics/repetition_loop.py + critic 5→13 axis extension + rubric.yaml v2 + motivation hard-stop in _post_process [PHYSICS-07, PHYSICS-08, PHYSICS-09, PHYSICS-13]
- [x] 07-05-PLAN.md — physics/scene_buffer.py SceneEmbeddingCache + cosine helpers + chapter_assembler/concat.py quote normalizer + critic pre-LLM short-circuit hooks + CLI composition + ch15 sc02 smoke + ch01-04 zero-FP smoke [PHYSICS-10, PHYSICS-11, PHYSICS-12]
**UI hint**: no

**Parallelization**: Wave 1 (07-01 schema) is foundational — every later plan imports from physics.schema/locks/gates.base. Wave 2 (07-02 CB-01) is independent of Wave 3 plans. Wave 3 splits into two parallel plans: 07-03 (drafter-side: gates + prompt extension; depends on 07-01 schema + 07-02 CB-01 for the canon_bible reader) and 07-04 (critic-side: 13-axis schema + stub_leak/repetition_loop pre-LLM detectors + motivation hard-stop; depends only on 07-01 schema). Wave 4 (07-05) is the integration point — depends on everything; lands the scene-buffer cosine + CLI composition root + the phase-acceptance integration smokes.

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation + Observability Baseline | 6/6 | Complete    | 2026-04-22 |
| 2. Corpus Ingestion + Typed RAG | 6/6 | Complete    | 2026-04-22 |
| 3. Mode-A Drafter + Scene Critic + Basic Regen | 8/8 | Complete    | 2026-04-22 |
| 4. Chapter Assembly + Post-Commit DAG | 0/6 | Planned    | - |
| 5. Mode-B Escape + Regen Budget + Alerting + Nightly Orchestration | 0/TBD | Not started | - |
| 6. Testbed Plane + Production Hardening + First Draft | 0/TBD | Not started | - |
| 7. Narrative Physics Engine | 5/5 | Complete (verifier PASS after 2026-04-26 gap closure) | 2026-04-26 |

---

## Coverage

- **v1 requirements total:** 41 (+ 13 PHYSICS-NN scoped to Phase 7 = 54 total)
- **Mapped to phases:** 41 + 13 = 54
- **Unmapped:** 0
- **Coverage:** 100% (every REQ-ID assigned to exactly one phase)

### Phase-to-requirements index

| Phase | Requirements | Count |
|-------|--------------|-------|
| 1 | FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, OBS-01 | 6 |
| 2 | CORPUS-01, RAG-01, RAG-02, RAG-03, RAG-04 | 5 |
| 3 | DRAFT-01, DRAFT-02, CRIT-01, CRIT-04, REGEN-01, OBS-03 | 6 |
| 4 | CORPUS-02, CRIT-02, LOOP-02, LOOP-03, LOOP-04, TEST-01 | 6 |
| 5 | DRAFT-03, DRAFT-04, REGEN-02, REGEN-03, REGEN-04, LOOP-01, ORCH-01, ALERT-01, ALERT-02 | 9 |
| 6 | OBS-02, OBS-04, CRIT-03, TEST-02, TEST-03, TEST-04, ORCH-02, FIRST-01, FIRST-02 | 9 |
| 7 | PHYSICS-01, PHYSICS-02, PHYSICS-03, PHYSICS-04, PHYSICS-05, PHYSICS-06, PHYSICS-07, PHYSICS-08, PHYSICS-09, PHYSICS-10, PHYSICS-11, PHYSICS-12, PHYSICS-13 | 13 |
| **Total** | | **54** |

---

## Dependencies between phases

```
Phase 1 (Foundation + Observability) ─┐
                                      ├──► Phase 2 (Corpus + Typed RAG)
                                      │         │
                                      │         ▼
                                      └──► Phase 3 (Mode-A + Scene Critic + Regen)
                                                │
                                                ▼
                                          Phase 4 (Chapter Assembly + DAG)
                                                │
                                                ▼
                                          Phase 5 (Mode-B + Budget + Alerting + Cron)
                                                │
                                                ├──► Phase 6 (Testbed + Hardening + FIRST-01)
                                                │
                                                └──► Phase 7 (Narrative Physics Engine)
                                                        — runs in parallel with Phase 6;
                                                          extends Phase 2 (CB-01 6th axis),
                                                          Phase 3 (5→13 axis critic),
                                                          Phase 4 (concat.py quote normalizer),
                                                          Phase 5 (alerts kernel-package precedent).
```

**Notes on the dependency graph:**

- Phase 1 is the foundation every phase reads from (EventLogger, Protocols, config loader, voice-pin schema). Nothing else starts until Phase 1 lands.
- Phase 2 can start plans in parallel with Phase 1's Protocol definitions (FOUND-04) once the 5 retriever signatures are pinned, but cannot complete until Phase 1's EventLogger exists (retrievers emit events).
- Phase 3 depends on Phase 1 (voice-pin SHA check + EventLogger) and Phase 2 (ContextPack input to drafter + critic). The Critic prompt-architecture plan within Phase 3 can be developed against a stubbed ContextPack while Phase 2 lands its reconciliation step.
- Phase 4 depends on Phase 3 (scenes in the buffer) and re-uses Phase 2's bundler for the chapter-critic's independent re-query.
- Phase 5 depends on Phase 4 (chapter-level DAG). Mode-B escape is meaningful only when Mode-A has been characterized (Phase 3) and chapter commits atomically (Phase 4).
- Phase 6 reads from every prior phase's event log. Its content is gated by having >=3 committed chapters (Phase 5's nightly loop must have run productively) before thesis closures and ablations produce meaningful evidence.
- Phase 7 (Narrative Physics Engine) is a kernel-package addition + RAG-axis extension + critic-prompt extension; it does NOT block on Phase 6. Phase 7 reuses the alerts kernel-package precedent from Plan 05-03, the scene-kick recovery loop from Plan 05-02, the additive-nullable LanceDB column policy from Plan 05-03, and the Anthropic structured-output discipline from Plans 03-04/04-02. Forward-only scope (D-21): Phase 7 enforces narrative physics for ch15-27 + ch09 retry; ch01-14 are historical artifacts and are NOT retrofit. ch01-04 read-only baseline (zero-FP smoke) is the canary.

---

## UI surface

No phase exposes a web/GUI surface. The pipeline's human interface is:

- Markdown digests (`digests/week_YYYY-WW.md`) — Paul reads weekly.
- Markdown retrospectives (`retrospectives/chapter_NN.md`) — feed digest + thesis matcher.
- Markdown entity cards (`entity-state/chapter_NN/*.md`) — machine + human readable.
- Canon markdown in `canon/chapter_NN.md` — the book itself.
- Telegram alerts — hard-block conditions only, deduplicated.

A browser dashboard is explicitly deferred to v2 (REVIEW-01) per PROJECT.md out-of-scope. Every phase in this roadmap carries `UI hint: no`.

---

*Last updated: 2026-04-25 — Phase 7 planned (5 plans / 4 waves, 13 PHYSICS-NN REQ-IDs).*
