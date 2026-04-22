# Phase 3: Mode-A Drafter + Scene Critic + Basic Regen - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning
**Mode:** Auto-generated via `gsd-discuss-phase --auto` (full-auto; user pre-answered locked decisions)

<domain>
## Phase Boundary

A single scene (ch01_sc01) is drafted by the pinned voice-FT checkpoint served via vLLM, critiqued by Opus against the 5-axis rubric, regenerated once on mid+-severity failure, and left on disk in a well-defined `SceneState` — with voice-fidelity measured against a curated anchor centroid from the very first commit. Every drafter/critic/regen call emits an OBS-01 `Event`; critic rubric version + raw response are persisted as an audit record.

**In scope (REQs):** DRAFT-01, DRAFT-02, CRIT-01, CRIT-04, REGEN-01, OBS-03.

**Out of scope:**
- Mode-B drafter (DRAFT-03), structural preflag routing (DRAFT-04), auto-escalation on R-exhaustion (REGEN-03), per-scene cost cap (REGEN-02), oscillation detector (REGEN-04), Telegram alerts (ALERT-01), nightly openclaw cron (ORCH-01) — all Phase 5. Phase 3 leaves R-exhausted scenes in `HARD_BLOCKED("failed_critic_after_R_attempts")` as a handoff terminal state; Phase 5 wires that edge to Mode-B.
- ChapterAssembler, chapter-level critic (CRIT-02), post-commit DAG, EntityExtractor, RetrospectiveWriter — Phase 4.
- Scenes beyond ch01_sc01 smoke; outline→SceneRequest auto-generation — Phase 4. Phase 3 runs on-demand via `book-pipeline draft <scene_id>` CLI.

</domain>

<decisions>
## Implementation Decisions

### Voice pin = V6, not projected V9/V10 (DRAFT-01)
- paul-thinkpiece-pipeline is still iterating (V6 is newest as of 2026-04-21); V9/V10 did not materialize. Phase 3 pins V6 LoRA adapter at `/home/admin/finetuning/output/paul-v6-qwen3-32b-lora/`, base `Qwen/Qwen3-32B`. `voice_pin.yaml` is updated: `ft_run_id: v6_qwen3_32b`, `checkpoint_path` = adapter dir, `checkpoint_sha` = SHA256 over `adapter_model.safetensors` + `adapter_config.json`, recomputed + compared on every boot (PITFALLS V-3).
- Pin upgrade is a deliberate PR: bump `voice_pin.yaml`, restart vLLM unit, invalidate ContextPack/Draft caches. No `latest/` symlink anywhere.

### vLLM serve (DRAFT-01)
- systemd --user unit `vllm-paul-voice.service` on port 8002 (does not collide with `vllm-qwen122` on 8000). Flags: `--enable-lora --lora-modules paul-voice=<adapter_path>`, base `Qwen/Qwen3-32B`, `--dtype bfloat16 --max-model-len 8192 --tensor-parallel-size 1 --gpu-memory-utilization 0.85`. User memory rule "stop qwen122 before training" does NOT apply to concurrent serving on separate slices.
- `book-pipeline vllm-bootstrap` CLI writes the unit + enables it. Boot handshake: GET `/v1/models` asserts `paul-voice` loaded, adapter SHA recomputed + compared to `voice_pin.yaml`; mismatch → `HARD_BLOCKED("checkpoint_sha_mismatch")`, no auto-serve.

### Mode-A drafter (DRAFT-01, DRAFT-02)
- `book_pipeline.drafter.mode_a.ModeADrafter` satisfies the frozen Drafter Protocol with `mode="A"`. `httpx` client against vLLM's OpenAI-compatible endpoint + `tenacity` (3x exponential backoff per ARCHITECTURE.md §3.4 retry boundary 2). Persistent failure → `HARD_BLOCKED("mode_a_unavailable")`; does NOT silently escalate on infra failure.
- Per-scene sampling from `mode_thresholds.yaml` `sampling_profiles:` block, keyed by outline `scene_type` tag: `prose` → `temp=0.85, top_p=0.92`; `dialogue_heavy` → `temp=0.7, top_p=0.90`; `structural_complex` → `temp=0.6, top_p=0.88`. `repetition_penalty=1.05` across profiles.
- Prompt template `src/book_pipeline/drafter/templates/mode_a.j2` (Jinja2): system = voice description + rubric-awareness + `ContextPack.retrievals` corpus snippets; user = scene spec (chapter, POV, beat, date, location, ~1000w target) + prior_scenes summary.
- Memorization gate (PITFALLS V-2): 12-gram overlap scan against `paul-thinkpiece-pipeline/v3_data/train_filtered.jsonl`. Any hit → `HARD_BLOCKED("training_bleed")`. Runs in drafter pre-return.

### Scene critic (CRIT-01, CRIT-04)
- `book_pipeline.critic.scene.SceneCritic` with `level="scene"`. `anthropic>=0.96.0`, model `claude-opus-4-7`, `client.messages.parse(response_format=CriticResponse)` for Pydantic-backed structured output. `cache_control={"type": "ephemeral", "ttl": "1h"}` on the system prompt (rubric + few-shots) — identical prefix across all scene-critic calls in a run.
- System prompt loads `rubric.yaml` verbatim + 5-axis instructions + 1 bad + 1 good few-shot example curated at `src/book_pipeline/critic/templates/scene_fewshot.yaml`. User prompt = drafted scene + same `ContextPack` the drafter saw (fingerprint passed for tracing).
- `rubric_version` (`v1` from rubric.yaml) stamped on `CriticResponse.rubric_version` + on the `Event`. Rubric edits bump version; observability filters by version for cross-contamination-free longitudinal compare (success criterion 4).
- **CRIT-04 audit log:** every critic call writes `{rubric_version, raw_anthropic_response, parsed_CriticResponse, prompt_hash, scene_id, attempt_number}` to `runs/critic_audit/{scene_id}_{attempt}_{timestamp}.json`. Events carry summaries; audit carries raw payloads. Both keyed by `event_id`.

### Regenerator (REGEN-01)
- `book_pipeline.regenerator.scene_local.SceneLocalRegenerator` satisfies the Regenerator Protocol. Input: prior `DraftResponse` + `CriticIssue` list + same `ContextPack`. Output: new `DraftResponse` with `attempt_number = prior + 1`.
- Scene-local rewrite only (NOT full regen). Prompt shape: "Rewrite passages [ranges]. Fix issues [bullets grouped by severity]. Preserve exactly [unaffected passages quoted]." Word count stays within ±10% of original (success criterion 5).
- `max R = 3` from `mode_thresholds.yaml` `mode_a.regen_budget_R`. Only issues with severity ≥ `mid` trigger regen; severity `low` is recorded, not actioned. After R attempts still failing → `HARD_BLOCKED("failed_critic_after_R_attempts")`. Phase 5 REGEN-03 will re-route that state to Mode-B.

### SceneStateMachine integration
- Phase 3 introduces the orchestrator that calls `interfaces.scene_state_machine.transition()`. Happy path: `PENDING → RAG_READY → DRAFTED_A → CRITIC_PASS → COMMITTED`. Failure path: `DRAFTED_A → CRITIC_FAIL → REGENERATING → DRAFTED_A(attempt=2) → ...` up to R, then `HARD_BLOCKED`. `ESCALATED_B` exists in the enum (Phase 1) but is unused in Phase 3.
- State persisted to `drafts/scene_buffer/ch{NN}/{scene_id}.state.json` via atomic tmp+rename. No in-memory state across orchestrator ticks (ARCHITECTURE.md §4).

### Voice-fidelity anchor set (OBS-03)
- **Anchor curation runs BEFORE first production draft** (success criterion 6 — retroactive baselines prevented by construction). 20-30 passages, 150-400 words each, from (a) paul-thinkpiece-pipeline `v3_data/train_filtered.jsonl` high-quality pairs, (b) held-out blog posts not in training. Tagged sub-genre (≥6 essay, ≥6 analytic, ≥4 narrative) per PITFALLS V-1 two-tier pattern.
- Anchors committed at `config/voice_anchors/anchor_set_v1.yaml` (YAML: `{id, text, sub_genre, source, provenance_sha}`); full-set SHA pinned in `mode_thresholds.yaml` under `voice_fidelity.anchor_set_sha`. Embeddings via BGE-M3 (reused from Phase 2 `book_pipeline.rag.embedder`), cached at `indexes/voice_anchors/embeddings.parquet`; centroid = mean vector (also per-sub-genre centroids).
- Per-scene: cosine vs centroid. Thresholds in `mode_thresholds.yaml`: pass ≥0.78, flag 0.75-0.78, fail <0.75. **>0.95 is ALSO a flag** (PITFALLS V-2 memorization). Score attached to drafter Event via `caller_context.voice_fidelity_score`.

### Observability (OBS-03)
- Every drafter/critic/regenerator call emits an `Event` (Phase 1 schema, additive only). `caller_context`: `{scene_id, chapter, beat_function, pov, mode: "A", attempt_number, rubric_version (critic), voice_pin_sha (drafter), voice_fidelity_score (drafter), anchor_set_sha}`. Top-level `checkpoint_sha` populated for every drafter event (Phase 1 frozen field, V-3 mitigation).

### CLI surface (Phase 3)
- `book-pipeline vllm-bootstrap` — write + start systemd unit, verify handshake.
- `book-pipeline curate-anchors` — one-time: (re)build `anchor_set_v1.yaml` + recompute embeddings + print SHA for pinning. **Must run before first production draft.**
- `book-pipeline draft <scene_id>` — on-demand full Phase 3 loop: load `scenes/{chapter}/{scene_id}.yaml` stub → RAG → draft → critic → regen/commit-or-hardblock.

### Claude's Discretion
Exact file layout within `drafter/`, `critic/`, `regenerator/` modules; test harness structure; anchor-set source selection within the 20-30 range; vLLM LoRA flags beyond the pinned adapter+base pairing.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1 + 2)
- `book_pipeline.interfaces.{drafter, critic, regenerator, scene_state_machine}` — Protocols + `transition()` helper, FROZEN. Phase 3 concrete impls satisfy signatures exactly.
- `book_pipeline.interfaces.types` — `DraftRequest/Response`, `CriticRequest/Response/Issue`, `RegenRequest`, `SceneState`, `SceneStateRecord`, `Event`. All FROZEN; additions are OPTIONAL fields only.
- `book_pipeline.observability.JsonlEventLogger` (Phase 1) — write path for every Phase 3 LLM call.
- `book_pipeline.rag.ContextPackBundler` + 5 retrievers (Phase 2) — produce `ContextPack` consumed by drafter + critic. `ContextPack.fingerprint` is the cache key.
- `book_pipeline.rag.embedder` (BGE-M3, Phase 2) — reused verbatim for voice-anchor embeddings.
- `book_pipeline.book_specifics.corpus_paths` — read-only path anchor; Phase 3 adds `VOICE_ANCHOR_ROOT`.

### Established Patterns
- Kernel vs book_specifics (ADR-004): `drafter/`, `critic/`, `regenerator/`, `observability/` are kernel-shaped. vLLM endpoint URL, anchor filenames, training-bleed corpus path → `book_specifics/`. import-linter contract extended in the same PR as the code (Phase 1 / Phase 2 convention).
- Event schema additive policy (Phase 1 freeze): Phase 3 uses only existing Event fields; per-phase extras go in `caller_context` or `extra`.
- Short-lived batch orchestrator (ARCHITECTURE.md §5): `draft <scene_id>` CLI is one tick; state-on-disk between invocations is load-bearing.

### Integration Points
- vLLM systemd --user shares machine with `vllm-qwen122` (port 8000, different slice); concurrent serving is fine.
- Anthropic — `ANTHROPIC_API_KEY` via pydantic-settings `.env`; same SDK openclaw gateway is configured for.
- paul-thinkpiece-pipeline V6 LoRA at `/home/admin/finetuning/output/paul-v6-qwen3-32b-lora/` — read-only consumer; Phase 3 computes SHA but never modifies.

</code_context>

<specifics>
## Specific Ideas

- **Anchor curation is P0** — if it slips, every downstream voice-fidelity number is retroactive and therefore meaningless. Plan 1 should be `curate-anchors` + commit `anchor_set_v1.yaml` + pin its SHA; vLLM serve + drafter come online only after.
- `scenes/ch01/ch01_sc01.yaml` stub is hand-authored for the smoke run (Phase 4 auto-generates from outline). Minimum fields: `{chapter, scene_index, beat_function, pov, date_iso, location, word_target: 1000, scene_type: prose|dialogue_heavy|structural_complex}`. `scene_type` drives sampling profile lookup.
- Scene commit on `COMMITTED`: text → `drafts/ch{NN}/{scene_id}.md` with YAML frontmatter `{voice_pin_sha, critic_scores_per_axis, attempt_count, ingestion_run_id, draft_timestamp, voice_fidelity_score, mode: "A"}`. Phase 4's ChapterAssembler reads these.
- Success criterion 4 regression test: emit events under `rubric_version=v1`, bump to `v2`, confirm digest-style filter returns v1 events without cross-contamination.
- PITFALLS C-1 self-preference (Opus-on-Opus) is Phase 5's concern (Mode-B not live). Phase 3 baseline is Mode-A-only, so CRIT-03 cross-family judge (Phase 6) can re-score this phase's scenes without mode confound.

</specifics>

<deferred>
## Deferred Ideas

- Mode-B escape + auto-escalation (REGEN-03) on `HARD_BLOCKED("failed_critic_after_R_attempts")` — Phase 5. Phase 3 leaves the edge un-wired; the terminal state is the handoff.
- Per-scene cost cap + mid-run abort (REGEN-02) — Phase 5. Phase 3's implicit bound: R=3 × one critic call per attempt.
- Oscillation detector (REGEN-04) — Phase 5.
- Structural preflag (DRAFT-04) → Mode-B routing — Phase 5. Phase 3 honors `scene_type: structural_complex` only for sampling profile, not mode routing.
- Chapter assembly + chapter-level critic (CRIT-02, LOOP-02) + post-commit DAG (CORPUS-02, TEST-01) — Phase 4.
- Nightly openclaw cron (ORCH-01) + Telegram alerts (ALERT-01) — Phase 5. Phase 3 CLI is on-demand only.
- Cross-family critic audit (CRIT-03) on ≥10% of scenes — Phase 6.
- n-gram memorization scanner (PITFALLS V-2) evolves from in-drafter blocker to observability-ingester panel — Phase 6 gets the panel; Phase 3 ships the blocker.

</deferred>
