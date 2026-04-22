---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-04-22T06:32:01Z"
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 12
  completed_plans: 7
  percent: 58
---

# STATE: our-lady-book-pipeline

**Last updated:** 2026-04-22 after Plan 02-01 (RAG kernel foundation)
**Status:** Executing Phase 02

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

Phase 2: Corpus Ingestion + Typed RAG. Build the 5-axis LanceDB retrieval plane on top of the Phase 1 observability baseline. Plan 02-01 shipped the kernel RAG foundation (chunker + BGE-M3 embedder + LanceDB schema) — Plans 02-02 through 02-06 build ingester, retrievers, bundler, and golden-query CI gate on this foundation. No LLM calls until Phase 3 — embeddings are local (BGE-M3 via sentence-transformers).

---

## Current Position

Phase: 02 (Corpus Ingestion + Typed RAG) — EXECUTING
Plan: 2 of 6 (next: 02-02 corpus ingester)

- **Phase:** 2
- **Plan:** 02-01 COMPLETE; 02-02 next
- **Status:** In progress
- **Plans complete:** 1 / 6 (Phase 2); 7 / 12 total (Phase 1: 6; Phase 2: 1)
- **Progress:** [██████░░░░] 58%

### Roadmap progress

- [x] **Phase 1:** Foundation + Observability Baseline (6/6 plans)
- [ ] **Phase 2:** Corpus Ingestion + Typed RAG (1/6 plans — 02-01 shipped RAG kernel foundation)
- [ ] **Phase 3:** Mode-A Drafter + Scene Critic + Basic Regen
- [ ] **Phase 4:** Chapter Assembly + Post-Commit DAG
- [ ] **Phase 5:** Mode-B Escape + Regen Budget + Alerting + Nightly Orchestration
- [ ] **Phase 6:** Testbed Plane + Production Hardening + First Draft

---

## Performance Metrics

No prose-generation metrics yet — pipeline has not produced artifacts. First real metrics land in Phase 3 (first Mode-A scene scored against anchor set) and Phase 5 (first full nightly loop run).

### Plan execution metrics

| Plan  | Duration (min) | Tasks | Files created | Files modified | Tests added | Tests passing | Completed   |
| ----- | -------------- | ----- | ------------- | -------------- | ----------- | ------------- | ----------- |
| 02-01 | 45             | 1     | 11            | 3              | 20          | 131           | 2026-04-22  |

### Target metrics (will populate once pipeline runs)

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
- **(02-01) chapter column on CHUNK_SCHEMA at chunk time (W-5 revision).** Over `heading_path LIKE 'Chapter N %'` at retrieval time. LIKE would false-match `Chapter 10/11/...` under a `Chapter 1` prefix; int-column exact equality sidesteps the whole class. Plan 04 arc_position retriever consumes this.
- **(02-01) pin-once revision_sha for BGE-M3.** Explicit `revision=<sha>` at construction is returned verbatim and respected; `revision=None` opts into HfApi HEAD resolution on first access (bootstrap path — Plan 02 uses this on its first ingest to fill `model_revision: TBD-phase2` in config/rag_retrievers.yaml).
- **(02-01) Import-linter contract-2 extension semantics.** Contract 2's source_modules is frozen at `[interfaces]`; new kernel concretes land in `forbidden_modules` instead (deviated from plan's literal "source_modules in BOTH" instruction; plan-author conflated growth points). Intent preserved (each new kernel is in both contracts). Future plans extending kernel packages (drafter, critic, orchestration) will follow this clarified pattern.

### Open todos

- Plan 02-02: corpus ingester — wire chunk_markdown + BgeM3Embedder + open_or_create_table, route chunks to 5 axes, fill `model_revision` in config/rag_retrievers.yaml, emit `event_type=ingestion_run` event.
- Plan 02-02 must ALSO reconcile `book_specifics/corpus_paths.py` (stale filenames: `brief.md` vs actual `our-lady-of-champion-brief.md`).
- Before Phase 3 starts: curate the 20-30 voice-fidelity anchor passages from paul-thinkpiece-pipeline training corpus (blocker for the anchor-set pin, not a line item in a plan).
- Watch: `lancedb.table_names()` deprecation — migrate to `list_tables().tables` when old API is actually removed (lance_schema.py has a self-contained call site, one-line change).

### Blockers

None.

### Research flags per phase

- **Phase 2 (RAG):** BGE-M3 vs jina-embeddings-v3 on domain corpus; LlamaIndex ingestion utilities vs custom chunking for rule-card boundaries. Decide before retriever implementations begin.
- **Phase 3 (Core loop):** Critic rubric prompt architecture (per-axis prompts vs single-schema output); Opus 4.7 token budget per scene; voice-fidelity cosine threshold calibration.
- **Phase 5 (Mode-B):** Anthropic workspace-scoped cache behavior with openclaw per-agent workspace model (changed 2026-02-05); Sonnet 4.6 viability as Mode-B fallback for non-structurally-complex beats.

---

## Session Continuity

### Last session

- **Date:** 2026-04-22
- **Action:** Executed Plan 02-01 — book_pipeline.rag kernel foundation (chunker + BGE-M3 embedder + LanceDB schema + import-linter / mypy extensions).
- **Outcome:** 6 primitives exported from book_pipeline.rag (Chunk, chunk_markdown, EMBEDDING_DIM, BgeM3Embedder, CHUNK_SCHEMA, open_or_create_table). 20 new tests green (9 chunker + 6 embedder + 5 schema); full suite 131 passed. Aggregate gate `bash scripts/lint_imports.sh` green. Two per-task commits: 8cd8169 (RED tests) + be38615 (GREEN impl). Plan 02-01 CLOSED.
- **Stopped at:** Completed 02-01-PLAN.md — ready for Plan 02-02 (corpus ingester).

### Next session

- **Expected action:** `/gsd-execute-phase 2` continuation (or explicit `gsd-execute-plan 02-02`) — decompose and execute Plan 02-02 (corpus ingester). Consumes Plan 02-01's primitives.
- **Key continuation note:** Plan 02-02 must reconcile `book_specifics/corpus_paths.py` stale filenames (e.g., `brief.md` → `our-lady-of-champion-brief.md`) per the plan's `<corpus_notes>` block. Plan 02-01 explicitly did NOT touch corpus_paths.py (kernel vs book_specifics separation); 02-02 is where that lives.

### Session continuity invariants

- All mutable project state lives on disk under `.planning/` and the artifact directories (`canon/`, `drafts/`, `runs/`, `indexes/`, `entity-state/`, `theses/`, `retrospectives/`, `digests/`).
- No in-memory state is assumed to survive between sessions. The event log (`runs/events.jsonl`, not yet live) is append-only truth; every derived view is rebuildable from it.

---

*State file is updated after each plan completion, phase transition, and milestone boundary.*
