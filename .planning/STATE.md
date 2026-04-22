---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 02-04-PLAN.md (entity_state + arc_position retrievers + outline_parser; RAG-01/RAG-02 closed)
last_updated: "2026-04-22T07:45:00.000Z"
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 12
  completed_plans: 10
  percent: 83
---

# STATE: our-lady-book-pipeline

**Last updated:** 2026-04-22 after Plan 02-04 (entity_state + arc_position retrievers + outline_parser; RAG-01/RAG-02 closed; all 5 typed retrievers operational)
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
Plan: 5 of 6 (next: 02-05 ContextPackBundler + negative_constraint assembly-time filter)

- **Phase:** 2
- **Plan:** 02-04 COMPLETE; 02-05 next
- **Status:** In progress
- **Plans complete:** 4 / 6 (Phase 2); 10 / 12 total (Phase 1: 6; Phase 2: 4)
- **Progress:** [████████░░] 83%

### Roadmap progress

- [x] **Phase 1:** Foundation + Observability Baseline (6/6 plans)
- [ ] **Phase 2:** Corpus Ingestion + Typed RAG (4/6 plans — 02-01 RAG kernel + 02-02 corpus ingester + 02-03 3-of-5 retrievers + 02-04 entity_state/arc_position + outline_parser)
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
| 02-03 | 14             | 2     | 11            | 0              | 25          | 192           | 2026-04-22  |
| 02-04 | 12             | 2     | 7             | 0              | 17          | 209           | 2026-04-22  |

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
- **(02-03) B-1 sole ownership of `retrievers/__init__.py` — Plan 03 owns, Plan 04 never modifies.** All 5 retriever symbols pre-declared; Plan 02-04's `entity_state` + `arc_position` loaded via `importlib.import_module` inside `contextlib.suppress(ImportError)` (dynamic import needed to bypass mypy's import-untyped static complaint on modules-not-yet-on-disk). Pre-Plan-04: attributes are `None`. Post-Plan-04: attributes are the real classes.
- **(02-03) B-2 frozen Protocol `reindex(self) -> None` on every concrete retriever.** Axis-specific reindex state (Plan 02-04's ArcPositionRetriever outline_path, embedder, ingestion_run_id) is stored on `self` at `__init__` and read during `reindex()`. Runtime-checkable `isinstance(r, Retriever)` passes — verified by dedicated test in each retriever test file + `inspect.signature(r.reindex).parameters` emptiness check.
- **(02-03) W-2 explicit-kwargs retriever __init__ template.** `def __init__(self, *, db_path, embedder, reranker, **kw) -> None: super().__init__(name="axis", db_path=db_path, embedder=embedder, reranker=reranker, **kw)`. No positional-splat forwarding. Plan 02-04's two retrievers MUST follow this template.
- **(02-03) candidate_k=50 -> final_k=8 pipeline cemented on LanceDBRetrieverBase.** Plan 02-05 bundler's 40KB ContextPack cap math assumes 8 hits per axis × 5 axes = up to 40 hits. `final_k` is an `__init__` kwarg for future tuning without API break.
- **(02-03) MetaphysicsRetriever `[a-z_]+` regex injection guard on `include_rule_types`.** Defense in depth; today's callers are all trusted (Plan 02-05 bundler reads from `config/rag_retrievers.yaml`) but the guard prevents a future regression from leaking unsanitized input into the where clause. Raises `ValueError` on any non-conformant value.
- **(02-03) NegativeConstraintRetriever `_where_clause` is UNCONDITIONALLY `None` (PITFALLS R-5).** Tag-based filtering lives in Plan 02-05 bundler, NEVER in this retriever. Prevents the silent-miss failure where a scene's tag set doesn't match and the constraint never surfaces.
- **(02-03) RetrievalHit.metadata carries 5 keys (added `vector_distance` beyond the plan's literal 4).** `{rule_type, heading_path, ingestion_run_id, chapter, vector_distance}` — zero-cost additive signal for Plan 02-05 bundler + Plan 02-06 CI baseline introspection.
- **(02-04) outline_parser has two modes: STRICT (synthetic `# Chapter N:` / `## Block X:` / `### Beat N:`) + LENIENT FALLBACK (real OLoC `# ACT N —` / `## BLOCK N —` / `### Chapter N —`).** Strict regexes are CASE-SENSITIVE so ALL-CAPS fallback headings don't get shadowed as orphaned strict matches. Each `### Chapter N` in fallback mode becomes one beat (beat=1) under its enclosing `## BLOCK N`. Real outline parses to 27 beats; canary threshold is `len >= 20` so minor future edits don't fail CI.
- **(02-04) Beat ID schema `ch{chapter:02d}_b{block_id}_beat{beat:02d}` is load-bearing for RAG-02 stability.** Determined ENTIRELY by chapter/block/beat numbering — body-text edits don't shift IDs. Zero-padded so lex order matches numeric (ch01 < ch10 < ch27). block_id is letter-lowercase in strict mode (a/b/c...), digit-string in fallback mode (1..9).
- **(02-04) W-5 chapter filter shipped: `_where_clause` returns `f"chapter = {int(request.chapter)}"`.** int() cast is defense-in-depth despite Pydantic's `chapter: int` typing. Exact-equality on the int column eliminates the prefix-match class of bug ("Chapter 1" vs "Chapter 10..19"). Tests 2+3 prove: chapter=1 returns only chapter-1 hits, chapter=99 returns empty. Plan 02-06 golden queries can pin on this semantic.
- **(02-04) ArcPositionRetriever uses state-in-__init__ + zero-arg reindex.** `outline_path` + `ingestion_run_id` stored at construction; `reindex(self) -> None` matches frozen Protocol exactly. No classmethod workaround, no method-level args. CorpusIngester (Plan 02-02) ingests outline.md generically; ArcPositionRetriever.reindex() overwrites arc_position table with beat-ID-stable rows (`tbl.delete("true")` + `tbl.add(rows)`). Plan 06 CLI composes: construct retriever + call reindex().
- **(02-04) B-1 honored: Plan 02-04 did NOT modify `retrievers/__init__.py`.** `git log --oneline --all -- src/book_pipeline/rag/retrievers/__init__.py` shows only Plan 02-03 commits (`4ea3dac`, `e7acc52`). Plan 02-03's `importlib.import_module(...)` + `contextlib.suppress(ImportError)` guards now resolve to real classes (verified: `from book_pipeline.rag.retrievers import EntityStateRetriever, ArcPositionRetriever` returns non-None classes).
- **(02-04) All 5 concrete retrievers satisfy runtime-checkable `isinstance(r, Retriever)` + `inspect.signature(r.reindex).parameters == {}`.** B-2 complete across the retriever surface. Plan 02-05 bundler can safely accept `list[Retriever]` without further validation.

### Open todos
- Plan 02-05: ContextPackBundler + negative_constraint assembly-time tag filter. Consumes the 5 Retriever instances; emits exactly one `role="bundler"` Event per `bundle()` call carrying per-axis RetrievalResult + conflict flags. 40KB cap math assumes 8 hits/axis × 5 axes = up to 40 hits.
- Before Phase 3 starts: curate the 20-30 voice-fidelity anchor passages from paul-thinkpiece-pipeline training corpus (blocker for the anchor-set pin, not a line item in a plan).
- Plan 02-06: run the first REAL `book-pipeline ingest --force` on a machine with GPU + HF access; capture `chunk_counts_per_axis` + `indexes/resolved_model_revision.json` as the golden-query CI baseline. Also the first real BGE reranker-v2-m3 load.
- Watch: `lancedb.table_names()` deprecation — migrate to `list_tables().tables` when old API is actually removed (3 call sites now: `rag/lance_schema.py`, `corpus_ingest/ingester.py`, and test_lance_schema.py). `rag/retrievers/base.py` goes through `open_or_create_table` so it benefits from a single-site migration.
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
- **Action:** Executed Plan 02-03 — 3 of 5 typed retrievers (historical, metaphysics with PITFALLS R-4 filter + injection guard, negative_constraint with PITFALLS R-5 deliberate-no-filter) on top of a shared `LanceDBRetrieverBase` (candidate_k=50 -> final_k=8 pipeline with empty-table tolerance + B-2 frozen `reindex(self) -> None` + `empty` sentinel on index_fingerprint for empty tables) and a lazy `BgeReranker` cross-encoder wrapper. B-1: Plan 03 sole-owns `retrievers/__init__.py` with all 5 imports pre-declared (Plan 04's entity_state + arc_position loaded via `importlib.import_module` inside `contextlib.suppress(ImportError)`).
- **Outcome:** New module tree `src/book_pipeline/rag/retrievers/` (5 source files — base + 3 concrete retrievers + __init__.py) and `src/book_pipeline/rag/reranker.py`. 25 new tests green (4 reranker + 8 retriever_base + 4 historical + 5 metaphysics + 4 negative_constraint); full suite 192 passed (was 167). Aggregate gate `bash scripts/lint_imports.sh` green (2 contracts kept, ruff clean, mypy 68 files clean — added retrievers subpackage under existing `src/book_pipeline/rag` mypy scope). 4 per-task commits: 2b2dab1 + e7acc52 (Task 1 RED/GREEN) + 0de228b + 4ea3dac (Task 2 RED/GREEN). RAG-01 progresses from 0% to 60% complete (3 of 5 retrievers).
- **Stopped at:** Completed 02-03-PLAN.md (3 of 5 typed retrievers + shared base + BGE reranker)

### Next session

- **Expected action:** `/gsd-execute-phase 2` continuation (or explicit `gsd-execute-plan 02-04`) — Plan 02-04: entity_state + arc_position retrievers. Creates 2 new retriever source files; does NOT modify `__init__.py` (B-1 contract). ArcPositionRetriever parses `~/Source/our-lady-of-champion/our-lady-of-champion-outline.md` into beat-function granularity chunks (27 chapters × blocks × beats) with stable `ch{NN}_b{block}_beat{NN}` IDs, overriding `reindex()` body (NOT signature — B-2). EntityStateRetriever reads `entity-state/` cards, tolerating the zero-cards case (empty-table path already in the base).
- **Key continuation note:** Plan 02-04 MUST follow the W-2 explicit-kwargs `__init__` template (no `*args` forwarding) and MUST preserve the B-2 zero-arg `reindex(self) -> None` signature. Dedicated test in each new retriever test file: `assert isinstance(r, Retriever)` (runtime_checkable Protocol) AND `assert len(inspect.signature(r.reindex).parameters) == 0`.
- **Key precedent:** Plan 02-03 established the retriever-subclass template: override `_build_query_text(request) -> str` (required) and optionally `_where_clause(request) -> str | None` (default `None`). Any axis-specific state for a non-trivial `reindex()` override is stored on `self` at `__init__` time. Never emit observability events from retrievers (grep-guarded to 0 matches — the bundler in Plan 02-05 is the sole emission site).

### Session continuity invariants

- All mutable project state lives on disk under `.planning/` and the artifact directories (`canon/`, `drafts/`, `runs/`, `indexes/`, `entity-state/`, `theses/`, `retrospectives/`, `digests/`).
- No in-memory state is assumed to survive between sessions. The event log (`runs/events.jsonl`, not yet live) is append-only truth; every derived view is rebuildable from it.

---

*State file is updated after each plan completion, phase transition, and milestone boundary.*
