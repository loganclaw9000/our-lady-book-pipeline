---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 02-02-PLAN.md (corpus ingester + mtime idempotency + CLI)
last_updated: "2026-04-22T06:56:01.437Z"
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 12
  completed_plans: 8
  percent: 67
---

# STATE: our-lady-book-pipeline

**Last updated:** 2026-04-22 after Plan 02-02 (corpus ingester + mtime idempotency + CLI)
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

Phase 2: Corpus Ingestion + Typed RAG. Build the 5-axis LanceDB retrieval plane on top of the Phase 1 observability baseline. Plan 02-01 shipped the kernel RAG foundation (chunker + BGE-M3 embedder + LanceDB schema); Plan 02-02 shipped the CorpusIngester + mtime idempotency + `book-pipeline ingest` CLI with W-3 (explicit heading classifier allowlist) / W-4 (resolved_model_revision.json replaces YAML write-back) / W-5 (chapter column) implemented. Plans 02-03 through 02-06 build retrievers, bundler, and golden-query CI gate on this foundation. No LLM calls until Phase 3 — embeddings are local (BGE-M3 via sentence-transformers).

---

## Current Position

Phase: 02 (Corpus Ingestion + Typed RAG) — EXECUTING
Plan: 3 of 6 (next: 02-03 historical + metaphysics retrievers)

- **Phase:** 2
- **Plan:** 02-02 COMPLETE; 02-03 next
- **Status:** In progress
- **Plans complete:** 2 / 6 (Phase 2); 8 / 12 total (Phase 1: 6; Phase 2: 2)
- **Progress:** [███████░░░] 67%

### Roadmap progress

- [x] **Phase 1:** Foundation + Observability Baseline (6/6 plans)
- [ ] **Phase 2:** Corpus Ingestion + Typed RAG (2/6 plans — 02-01 RAG kernel + 02-02 corpus ingester)
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
| 02-02 | 16             | 2     | 14            | 6              | 36          | 167           | 2026-04-22  |

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
- **(02-02) CLI-composition exemption is the only sanctioned bridge across the kernel/book_specifics line.** Documented in 3 places: pyproject.toml `ignore_imports`, `tests/test_import_contracts.py` `documented_exemptions` set, and the CLI module docstring. Reusable pattern for Phase 3+ drafter/critic/regenerator CLI seams (e.g., loading `voice_pin.yaml`).
- **(02-02) `indexes/resolved_model_revision.json` (gitignored) replaces the planned YAML write-back (W-4).** `{sha, model, resolved_at_iso}` shape; written only after successful ingest; `config/rag_retrievers.yaml` is READ-ONLY to the ingester. Regression-guarded by `test_w4_yaml_config_is_not_modified` (asserts byte-identical yaml pre/post ingest).
- **(02-02) `BRIEF_HEADING_AXIS_MAP` is an explicit 12-entry allowlist (W-3).** Hand-authored from the real `brief.md` H2 headings (4 metaphysics + 8 historical). Regex-absence is asserted by `test_heading_classifier_module_has_no_regex`. Unmapped headings default to the file's primary axis (`historical`). `classify_brief_heading` accepts either the full breadcrumb OR the trailing segment.
- **(02-02) `ingestion_run_id` mixes microsecond timestamp + mtime-snapshot hash to stay unique across rapid rebuilds.** Plan's literal digest input (sorted paths + revision_sha) would have collided on back-to-back `--force` runs; the extra entropy closes the hole. Plan 05 bundler stamps `ContextPack.ingestion_run_id` with this format.

### Open todos

- Plan 02-03: historical + metaphysics retrievers — LanceDB query wrappers against the 5 tables populated by 02-02; metaphysics retriever filters on `rule_type='rule'` by default (PITFALLS R-4).
- Before Phase 3 starts: curate the 20-30 voice-fidelity anchor passages from paul-thinkpiece-pipeline training corpus (blocker for the anchor-set pin, not a line item in a plan).
- Plan 02-06: run the first REAL `book-pipeline ingest --force` on a machine with GPU + HF access; capture `chunk_counts_per_axis` + `indexes/resolved_model_revision.json` as the golden-query CI baseline.
- Watch: `lancedb.table_names()` deprecation — migrate to `list_tables().tables` when old API is actually removed (3 call sites now: `rag/lance_schema.py`, `corpus_ingest/ingester.py`, and test_lance_schema.py).
- Optional: T-02-02-04 harden — wrap 5-table rebuild in try/except that restores prior mtime_index.json on failure. Current ordering (write mtime last) is equivalent in practice but the explicit safety net is deferred.

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
- **Action:** Executed Plan 02-02 — CorpusIngester + mtime idempotency + `book-pipeline ingest` CLI, with W-3 (explicit heading classifier allowlist) / W-4 (resolved_model_revision.json replaces YAML write-back) / W-5 (chapter column round-trip) revisions implemented.
- **Outcome:** New kernel package `book_pipeline.corpus_ingest` (router + mtime_index + ingester). New CLI composition seam `book_pipeline.cli.ingest`. Reconciled `book_specifics/corpus_paths.py` filenames to `our-lady-of-champion-*.md` and added CORPUS_FILES 5-axis mapping. New `book_specifics/heading_classifier.py` with 12-entry BRIEF_HEADING_AXIS_MAP. 36 new tests green (6 corpus_paths + 5 heading_classifier + 7 router + 7 mtime_index + 11 ingester); full suite 167 passed (was 131). Aggregate gate `bash scripts/lint_imports.sh` green (2 contracts kept, ruff clean, mypy 62 files clean). 4 per-task commits: fa1adfc + 9d31263 (Task 1 RED/GREEN) + e2af2a8 + 6d7d981 (Task 2 RED/GREEN). `book-pipeline ingest --help` and `--dry-run` both verified end-to-end. CORPUS-01 complete.
- **Stopped at:** Completed 02-02-PLAN.md (corpus ingester + mtime idempotency + CLI)

### Next session

- **Expected action:** `/gsd-execute-phase 2` continuation (or explicit `gsd-execute-plan 02-03`) — decompose and execute Plan 02-03 (historical + metaphysics typed retrievers). Consumes Plan 02-02's populated LanceDB tables.
- **Key continuation note:** Plan 02-03 should NOT run a real BGE-M3 ingest to test retrievers — use the same `_FakeEmbedder` pattern from `tests/corpus_ingest/test_ingester.py` (deterministic `(n, 1024)` float32 via hash-seeded rng). The real first ingest is deferred to Plan 02-06 where it serves as the golden-query CI baseline.
- **Key precedent:** The CLI-composition exemption pattern (pyproject ignore_imports + grep-fallback documented_exemptions + module docstring) is now the sanctioned way to bridge book_specifics into kernel-level CLI commands. Plan 03/04/05 should follow the same 3-site pattern when they add their own CLI subcommands.

### Session continuity invariants

- All mutable project state lives on disk under `.planning/` and the artifact directories (`canon/`, `drafts/`, `runs/`, `indexes/`, `entity-state/`, `theses/`, `retrospectives/`, `digests/`).
- No in-memory state is assumed to survive between sessions. The event log (`runs/events.jsonl`, not yet live) is append-only truth; every derived view is rebuildable from it.

---

*State file is updated after each plan completion, phase transition, and milestone boundary.*
