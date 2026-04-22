# our-lady-book-pipeline

## What This Is

An autonomous book-drafting pipeline that produces the historical-fiction novel *Our Lady of Champion* by orchestrating a fine-tuned local voice model (from `paul-thinkpiece-pipeline`) with a frontier-model critic, enforcing factual consistency via 5-axis typed RAG against a lore-bible corpus (`our-lady-of-champion`). The pipeline simultaneously serves as the deliberate testbed for a family of writing pipelines (blog, thinkpiece, short-story) — every architectural choice emits structured observations that inform future pipelines and feed back into voice-FT training decisions.

Audience: Paul Logan (sole reader, minimal hands-on involvement once running). Digest-level review weekly, hard-block alerts only.

## Core Value

The pipeline autonomously produces first-draft novel chapters that are both **voice-faithful** (recognizable as Paul's prose) and **internally consistent** (against historical timeline, metaphysics rules, named-entity continuity, arc beats, thematic constraints) — while capturing enough experiment telemetry that learnings transfer to every future writing pipeline Paul builds.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] **FOUNDATION-01**: Repository scaffolded with Python packaging, dev venv, and `openclaw` workspace wired as orchestration layer.
- [ ] **CORPUS-01**: `our-lady-of-champion/` lore bibles ingested (read-only) into 5 typed indexes (historical, metaphysics, entity-state, arc-position, negative-constraint).
- [ ] **CORPUS-02**: Entity-state auto-extraction agent runs post-commit and writes structured per-chapter entity cards into `entity-state/`.
- [ ] **RAG-01**: Typed RAG retrievers return structured context packs (~30-40KB cap) keyed by scene request (POV + date + location + beat function).
- [ ] **RAG-02**: Chapter outline (outline.md, 27 chapters) parsed into arc-position retriever with beat-function-level granularity.
- [ ] **DRAFTER-01**: Mode-A drafter loads a pinned voice-FT checkpoint from `paul-thinkpiece-pipeline` via vLLM (or equivalent local inference), with temperature/top_p configurable per scene type.
- [ ] **DRAFTER-02**: Mode-B (frontier) drafter uses Anthropic API (Opus or Sonnet) with voice samples in-context, opt-in per-scene.
- [ ] **CRITIC-01**: Critic scores each drafted scene on 5 axes (historical, metaphysics, entity, arc, don'ts) with structured JSON issue lists and per-axis severities.
- [ ] **CRITIC-02**: Chapter-level critic runs after scene assembly to catch arc coherence + voice consistency issues spanning scenes.
- [ ] **REGEN-01**: Regenerator takes critic issue list as input and rewrites only the affected passages (scene-local regen), with a configurable max-iteration budget R.
- [ ] **REGEN-02**: After R Mode-A regen failures on a single scene, controller escalates that scene to Mode B automatically.
- [ ] **LOOP-01**: Full scene-to-commit loop runs autonomously: RAG → Mode A drafter → critic → regen/escalate → commit scene to buffer → assemble chapter → chapter critic → commit to canon → re-index → run entity extractor → run retrospective writer.
- [ ] **OBS-01**: Every LLM call (drafter, critic, regen, extractor, retrospective) emits a structured JSONL event with prompt hash, model, temp, token counts, latency, caller context, output hash.
- [ ] **OBS-02**: Per-axis critic scores, regen counts, mode tags persist per committed unit in a metric ledger suitable for weekly aggregation.
- [ ] **RETRO-01**: Retrospective writer runs post-chapter-commit (Opus) and produces a markdown note on what worked, what didn't, what patterns emerged.
- [ ] **THESIS-01**: Thesis registry (open/closed) captures experiments with hypothesis + test design + success metric; thesis matcher closes theses when evidence threshold is met.
- [ ] **DIGEST-01**: Weekly digest generator (Python + Opus) produces a markdown summary of production (chapters, voice fidelity, drift), experiments (closed theses, new candidates), cost, and blockers.
- [ ] **ORCH-01**: Nightly cron via openclaw drives scene-generation loop; gateway running and persistent workspace state is durable across reboots.
- [ ] **ALERT-01**: Hard-block conditions (stuck regen loop, rubric conflict, budget blown, voice-drift beyond threshold) page Paul via Telegram (using existing channel).
- [ ] **TESTBED-01**: Ablation harness can run N scenes under variant-A vs variant-B configs with everything else held fixed; results land in `runs/ablations/` with structured deltas.
- [ ] **FIRST-DRAFT**: Pipeline produces a complete first draft of *Our Lady of Champion* (27 chapters, ~81k words) committed to `canon/` with a closed thesis yield of ≥ 3 resolved hypotheses.

### Out of Scope

- **Line-edit polish for publication** — pipeline produces drafts, not publication-ready manuscripts; final editing is manual/human.
- **Cover art / marketing / pitch letters / query letters** — out of scope for any writing pipeline in this family.
- **Real-time collaborative editing with Paul** — async digest review is the surface. No live editor.
- **Model training** — that's `paul-thinkpiece-pipeline`'s job. Book pipeline **consumes** checkpoints, never produces them.
- **Generic writing-pipeline kernel** (standalone repo) — deferred until pipeline #2 (blog) exists, per ADR-004. Book pipeline maintains clean internal boundaries but ships in one repo for v1.
- **Modifying the corpus** — `our-lady-of-champion/` is read-only source-of-truth. Lore updates happen there, not via pipeline.
- **UI / web dashboard for digest review** — markdown digests are the v1 interface. Browser-based dashboard deferred until digest-reading friction is proven.
- **Frontier-primary drafting architecture** — Mode A (voice-FT local) is the default. Mode B is an escape hatch, not a fallback strategy. If Mode-B rate climbs past threshold, that's a signal to invest in a book-voice FT branch, not to flip the default.
- **OAuth / multi-user auth** — pipeline is single-user (Paul); no auth surface required.

## Context

- **Sibling: `paul-thinkpiece-pipeline`** — active FT project (weeks of ongoing work, v3→v6 iteration, cu130 + packing 25× speedup infra). Produces voice-FT checkpoints consumed here. One-way dependency: book pipeline pins a checkpoint; thinkpiece pipeline does not depend on book pipeline.
- **Corpus: `~/Source/our-lady-of-champion/`** — 10 markdown lore bibles (brief, outline, engineering, pantheon, relics, secondary-characters, maps, glossary, known-liberties, handoff), ~250KB total, already dense and structured. Outline is decomposed to 27 chapters × ~3000 words with POV + date + location + historical event + beat function per chapter.
- **Orchestration: `openclaw`** — local agentic framework already installed (npm-installed at `~/.npm-global/lib/node_modules/openclaw`, systemd-managed gateway, used successfully for `wipe-haus-state/` persona workspaces). Runs cron + persistent workspaces. Role: bulk drafting + orchestration (free tokens).
- **Critic: Anthropic API (Opus primary, Sonnet fallback)** — used where reasoning quality matters most: critic, entity extractor, retrospective writer, digest synthesis.
- **Runtime: DGX Spark GB10** — same machine as `paul-thinkpiece-pipeline`. `venv_cu130` + `cu130_env.sh` available for local-inference concerns.
- **Testbed framing** (ADR-003): this is pipeline #1 of a family. Observability is first-class, not a polish item. Every shortcut here is a learning lost for pipelines #2-N.

## Constraints

- **Tech stack**: Python (matches sibling paul-thinkpiece-pipeline), local inference via vLLM (or equivalent) for voice FT model, Anthropic SDK for critic calls. Vector store: pgvector or lancedb (final pick in phase 1 research).
- **Voice model**: must be a pinned checkpoint from paul-thinkpiece-pipeline (specific version recorded in `config/voice_pin.yaml`). Upgrading a pin is deliberate and logged.
- **Corpus immutability**: `our-lady-of-champion/` is read-only. Pipeline may re-ingest but may not modify.
- **Human involvement**: minimal. Weekly digest review + Telegram hard-block alerts. Anything that demands more attention than that is a pipeline defect to fix.
- **Budget**: Anthropic token spend tracked per-week. Mode-B escape rate is a cost lever (frontier drafting is expensive). No hard budget cap set yet but weekly digest must include spend.
- **Observability cost**: accept 2-3× engineering cost over a one-shot pipeline to afford structured event log + thesis registry + ablation harness. This is non-negotiable per ADR-003.
- **Kernel extraction**: deferred (ADR-004). Internal module boundaries should be clean enough to extract when pipeline #2 arrives, but no separate repo until then.
- **Compatibility**: openclaw gateway (systemd --user) must remain the orchestration layer. Don't reinvent cron or workspace state.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Mode dial (voice default, frontier escape) over promotion ladder | No non-frontier model 1-shots >1000w cleanly; ladder conflated capability with track record and would've forced voice loss on promotion | — Pending (ADR-001) |
| Scene-level generation, chapter-level commit | Scene (~1000w) fits voice model + matches RAG targeting; chapter (~3000w) matches outline grain and is canonical review unit | — Pending (ADR-002) |
| Testbed framing — over-instrument on purpose | Pipeline is #1 of a family; shortcuts here lose learnings for pipelines #2-N | — Pending (ADR-003) |
| Book-first, extract kernel when pipeline #2 arrives | Don't abstract until written twice; premature abstraction encodes book-specific assumptions as "universal" | — Pending (ADR-004) |
| Typed RAG (5 retrievers) over monolith RAG | Critic needs structured axis-specific findings to grade against rubric; one blob retrieval won't produce that signal | — Pending (thesis 005 tests) |
| Entity-state auto-extraction post-commit | Continuity errors across 81k words are hard to catch via unstructured RAG; structured entity cards give critic something to pattern-match | — Pending (thesis 003 tests) |
| openclaw (local) for orchestration + bulk drafting, Anthropic API for critic + reasoning | Asymmetric deployment: free tokens for volume, frontier quality where failure is most expensive | — Pending |
| Pre-flag structurally complex beats (Cholula stir, two-thirds reveal, siege climax) as Mode B from the start | Known to exceed voice model's structural reach; better to budget frontier cost explicitly than fight regen loops | — Pending |
| Voice pin target = V9 or V10 (by the time Phase 3 lands) | paul-thinkpiece-pipeline is actively iterating; V6 is current but will be superseded. Phase 3 `voice_pin.yaml` pins whichever is latest-stable at that time | — Pending |
| Remote = private GitHub (`loganclaw9000/our-lady-book-pipeline`) | Novel content + experimental code, push on every commit | ✓ Good |
| Corpus updates propagate via cron re-ingest | If `~/Source/our-lady-of-champion/` changes mid-drafting, a cron job re-runs ingestion; no file-watch, no manual trigger | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-21 after initialization*
