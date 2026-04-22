---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
last_updated: "2026-04-22T03:37:14.791Z"
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 6
  completed_plans: 6
  percent: 100
---

# STATE: our-lady-book-pipeline

**Last updated:** 2026-04-21 at roadmap creation
**Status:** Ready to plan

---

## Project Reference

- **Project doc:** `.planning/PROJECT.md`
- **Requirements:** `.planning/REQUIREMENTS.md` (41 v1 REQ-IDs)
- **Roadmap:** `.planning/ROADMAP.md` (6 phases)
- **Research synthesis:** `.planning/research/SUMMARY.md`
- **Architecture:** `docs/ARCHITECTURE.md`
- **Locked decisions:** `docs/ADRs/001-004`

### Core value (one line)

Autonomously produce first-draft novel chapters that are both voice-faithful (Paul's prose via pinned FT local checkpoint) and internally consistent (5-axis critic enforced pre-commit), while capturing enough experiment telemetry that learnings transfer to every future writing pipeline.

### Current focus

Phase 1: Foundation + Observability Baseline. Scaffold the uv-managed Python package, wire Pydantic Settings configs, define the 13 Protocol interfaces, stand up the EventLogger (OBS-01 live from day one), wire the openclaw workspace, and establish the module-boundary lint rule. No LLM calls yet — this phase exists so that when LLM calls start in Phase 3, every one of them is already observed.

---

## Current Position

Phase: 1 (Foundation + Observability Baseline) — EXECUTING
Plan: 1 of 6

- **Phase:** 2
- **Plan:** Not started
- **Status:** Pending
- **Plans complete:** 0 / TBD
- **Progress:** `[                    ]` 0%

### Roadmap progress

- [ ] **Phase 1:** Foundation + Observability Baseline
- [ ] **Phase 2:** Corpus Ingestion + Typed RAG
- [ ] **Phase 3:** Mode-A Drafter + Scene Critic + Basic Regen
- [ ] **Phase 4:** Chapter Assembly + Post-Commit DAG
- [ ] **Phase 5:** Mode-B Escape + Regen Budget + Alerting + Nightly Orchestration
- [ ] **Phase 6:** Testbed Plane + Production Hardening + First Draft

---

## Performance Metrics

No metrics yet — pipeline has not produced artifacts. First real metrics land in Phase 3 (first Mode-A scene scored against anchor set) and Phase 5 (first full nightly loop run).

Target metrics (will populate once pipeline runs):

- Mode-B escape rate (target: 20-30% for Act 1, per research)
- Voice-fidelity cosine vs anchor set (target band: 0.60-0.88 — too-high indicates memorization)
- Per-axis critic pass rate (scene + chapter)
- Regen iteration distribution
- Anthropic spend per chapter
- Thesis closure rate (target: >=3 closed by FIRST-01)

---

## Accumulated Context

### Decisions logged

- **Granularity: standard, 6 phases.** Requirements (41) clustered into 6 coherent delivery boundaries per research SUMMARY.md recommendation; dependencies (EventLogger before LLM calls, RAG before Drafter, scene flow before chapter flow, core loop before testbed) forced this ordering.
- **Observability is Phase 1, not Phase 6.** Per ADR-003 + pitfall V-3 + V-1/V-2, EventLogger + voice-pin SHA canary + anchor-set curation protocol all land before any prose commits. Retroactive observability baselines are impossible.
- **Mode-B is Phase 5, not earlier.** Mode-B is an escape from Mode-A failure; Mode-A (Phase 3) must exist and be characterized before Mode-B's escalation logic is meaningful. Moving Mode-B earlier would invert the testbed question ("is voice-FT reach sufficient?") into "how cheap is Mode-B?" — wrong question.
- **Testbed plane (theses, digest, ablations) is Phase 6.** Requires >=3 committed chapters before evidence is meaningful. Retrospective writer (TEST-01) is in Phase 4 so the first retrospective proves the template + lint before Phase 6 depends on it.
- **No UI phase.** Markdown is the v1 interface (PROJECT.md out-of-scope for dashboard); every phase carries `UI hint: no`.
- **Parallelization hints encoded per phase.** Config is `parallel=true`. Each phase's detail section notes which plans are safely parallelizable (e.g., the 5 retrievers in Phase 2, Drafter + Critic in Phase 3 once schemas pin).

### Open todos

- Kick off Phase 1 planning via `/gsd-plan-phase 1`.
- Before Phase 3 starts: curate the 20-30 voice-fidelity anchor passages from paul-thinkpiece-pipeline training corpus (this is a blocker for the anchor-set pin, not a line item in a plan).
- Before Phase 2 starts: confirm whether BGE-M3 or jina-embeddings-v3 wins on the Nahuatl + metaphysics rule-card corpus (flagged in STACK.md as an open research item).

### Blockers

None.

### Research flags per phase

- **Phase 2 (RAG):** BGE-M3 vs jina-embeddings-v3 on domain corpus; LlamaIndex ingestion utilities vs custom chunking for rule-card boundaries. Decide before retriever implementations begin.
- **Phase 3 (Core loop):** Critic rubric prompt architecture (per-axis prompts vs single-schema output); Opus 4.7 token budget per scene; voice-fidelity cosine threshold calibration.
- **Phase 5 (Mode-B):** Anthropic workspace-scoped cache behavior with openclaw per-agent workspace model (changed 2026-02-05); Sonnet 4.6 viability as Mode-B fallback for non-structurally-complex beats.

---

## Session Continuity

### Last session

- **Date:** 2026-04-21
- **Action:** Initialized GSD project (PROJECT.md + REQUIREMENTS.md + research plane); created ROADMAP.md + STATE.md; populated REQUIREMENTS.md traceability table.
- **Outcome:** 6-phase roadmap covering all 41 v1 requirements; ready for Phase 1 planning.

### Next session

- **Expected action:** `/gsd-plan-phase 1` — decompose Phase 1 (Foundation + Observability Baseline) into 3-5 executable plans.
- **Expected duration:** Phase 1 is small in scope (pure scaffolding; no LLM calls) but load-bearing. Plan-phase output should identify the parallel work (config loader, EventLogger, Protocol definitions, openclaw workspace, lint rule) and the one sequential gate (the package skeleton itself must exist before anything else can be added to it).

### Session continuity invariants

- All mutable project state lives on disk under `.planning/` and the artifact directories (`canon/`, `drafts/`, `runs/`, `indexes/`, `entity-state/`, `theses/`, `retrospectives/`, `digests/`).
- No in-memory state is assumed to survive between sessions. The event log (`runs/events.jsonl`, not yet live) is append-only truth; every derived view is rebuildable from it.

---

*State file is updated after each plan completion, phase transition, and milestone boundary.*
