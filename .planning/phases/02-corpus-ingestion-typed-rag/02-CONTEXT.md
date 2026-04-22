# Phase 2: Corpus Ingestion + Typed RAG - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning
**Mode:** Auto-generated via `gsd-discuss-phase --auto` (full-auto, recommended defaults accepted)

<domain>
## Phase Boundary

Given a `SceneRequest({POV, date, location, beat_function, chapter_num})`, the pipeline assembles a single `ContextPack` ≤40KB from 5 typed retrievers with full per-hit provenance and surfaced cross-axis conflicts. Retrieval quality is gated by a golden-query CI job before any drafter ever reads a pack.

**In scope (REQs):** CORPUS-01, RAG-01, RAG-02, RAG-03, RAG-04.

**Out of scope:**
- EntityExtractor itself (Phase 4 / CORPUS-02) — Phase 2's `entity_state` retriever reads whatever `entity-state/**/*.md` cards already exist and MUST tolerate the zero-cards case.
- Scene drafting / critic / regen (Phase 3+).
- Mode-B drafter (Phase 5).
- Chapter-level assembly, post-commit DAG, retrospectives (Phase 4).

</domain>

<decisions>
## Implementation Decisions

### Corpus Ingestion (CORPUS-01)
- Source is `~/Source/our-lady-of-champion/` — READ-ONLY. Pipeline never writes. Ingestion copies bytes into LanceDB tables under `indexes/`; it does not mutate the corpus repo.
- Trigger: openclaw cron nightly — compares corpus file mtimes, triggers full re-ingest if any source file changed. No inotify, no manual trigger, no incremental chunking (corpus is ~250KB; full reingest < 2 min).
- Each ingestion logs one `event_type="ingestion_run"` event to `runs/events.jsonl` with `{source_files[], chunk_counts_per_axis, embed_model_version, db_version, ingestion_run_id}` — reproducibility trail and input to golden-query CI baseline.

### Chunking & Embedding
- Chunk by markdown heading + sentence-window merge; target 512 tokens / 64-token overlap. Lore bibles are already heading-structured, so heading-respect eliminates random-boundary risk (PITFALLS R-4 "wrong-fact retrieval").
- Each chunk carries metadata: `{source_file, heading_path, rule_type, ingestion_run_id, chunk_id}`. `rule_type` (rule / example / hypothetical / cross-reference) is a PITFALLS R-4 mitigation for the metaphysics retriever.
- Embeddings: BAAI/bge-m3 (dense, 1024d, one shared local instance) — pinned per STACK.md. Revision SHA pinned in `config/rag_retrievers.yaml` at ingest time; dim change forces re-index.
- Re-ranking: BGE reranker-v2-m3 cross-encoder, top-k=50 → top-8 per axis. Dense-only retrieval is known to miss metaphysics-jargon specifics.

### 5 Typed Retrievers (RAG-01, RAG-02)
- One LanceDB table per axis: `historical`, `metaphysics`, `entity_state`, `arc_position`, `negative_constraint`. Names exactly match `config/rag_retrievers.yaml` and `RetrievalResult.retriever_name` (underscores, not hyphens).
- Chunk→axis routing: prefix-based type labels written into LanceDB metadata at ingest time (one table per axis), plus heading-regex classifier for ambiguous sections. Rejected alternative: keyword-clustering (over-engineered for 250KB corpus).
- `arc_position` retriever parses `~/Source/our-lady-of-champion/outline.md` into beat-function-granularity chunks (27 chapters × blocks × beats) with stable beat IDs that survive re-ingestion — beat ID schema is `ch{NN}_b{block}_beat{NN}` and lives in the chunk metadata, not just the text.
- `entity_state` retriever: primary source is `pantheon.md` + `secondary-characters.md`; `auto_update_from: entity-state/` is wired but MUST return a valid empty-hits `RetrievalResult` when `entity-state/` is empty (Phase 4 fills this).
- `negative_constraint` retriever always returns top-K regardless of tag match — bundler filters at assembly (PITFALLS R-5 silent-miss mitigation).

### ContextPackBundler (RAG-03)
- Hard 40KB ceiling; per-axis soft caps (historical 12KB, metaphysics 8KB, entity 8KB, arc-position 6KB, negative 6KB). Bundler trims lowest-score hits within each axis to stay under cap.
- `ContextPack.retrievals` carries full per-hit provenance (already on the frozen Phase 1 schema: `RetrievalHit.source_path` + `chunk_id` + `score` + `metadata`). Phase 2 adds OPTIONAL `ContextPack.conflicts: list[ConflictFlag]` and `ContextPack.ingestion_run_id: str | None` — allowed under the Phase 1 freeze (optional additions only).
- Cross-retriever reconciliation step: extract structured claims per retriever (location / date / possessions / entity states), diff, emit a `ConflictFlag` for each contradiction instead of silently concatenating (PITFALLS R-1). A copy is written to `drafts/retrieval_conflicts/<scene_id>.json`.

### Observability
- Every `Retriever.retrieve()` call and every `ContextPackBundler.bundle()` call emits an OBS-01 `Event`. Per the Phase 1 `Retriever` Protocol docstring (`event emission orchestrated by the bundler`), the BUNDLER is the event-emission site for all 5 retriever events in a single bundle — retrievers themselves stay side-effect-free. `caller_context` carries `{scene_id, chapter_num, pov, beat_function, retriever_name, index_fingerprint}`.
- Ingestion runs emit their own `event_type="ingestion_run"` events; golden-query CI reads these to assert index freshness.

### Golden-Query CI Gate (RAG-04)
- Seed set: 12 queries curated from `outline.md` beats, ≥2 per axis (covers all 5). Each query has an `expected_chunks` allowlist (by `source_file` + `heading_path`) AND a `forbidden_chunks` denylist (no leaks from wrong axis into an axis-specific retriever).
- CI passes iff ≥90% of golden queries return all expected chunks in the top-8 AND 0 forbidden-chunk leaks appear in any retriever. Fails on index drift — the baseline is pinned against a specific `ingestion_run_id`.
- CI workflow shape itself still deferred per Phase 1 CONTEXT (pre-commit framework adequate for this phase, full GitHub Actions defined when Phase 2 merges).

### Kernel Discipline (ADR-004)
- `book_pipeline.rag/` and `book_pipeline.corpus_ingest/` are kernel-shaped modules — no references to `our-lady-of-champion` paths inside them.
- Book-specific corpus paths (`CORPUS_ROOT`, bible filenames, Nahuatl name canonicalization) stay in `book_pipeline.book_specifics/`. Per Phase 1's append-as-you-add policy (`01-06-SUMMARY.md`), this phase's PRs add `book_pipeline.rag` and `book_pipeline.corpus_ingest` to BOTH `pyproject.toml` import-linter contract lists AND `scripts/lint_imports.sh` mypy targets in the same PR.

### Claude's Discretion
- Specific file layout within `rag/` and `corpus_ingest/` modules; test harness internals; exact chunker/reranker library wrapper choices within the pinned BGE-M3 + BGE reranker-v2-m3 models; internal shape of `ConflictFlag` Pydantic model (as long as it surfaces both sides + source chunk_ids); precise `heading_regex` classifier patterns.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1)
- `book_pipeline.interfaces.retriever.Retriever` + `context_pack_bundler.ContextPackBundler` — Protocols FROZEN. `retrieve()` / `reindex()` / `index_fingerprint()` and `bundle(request, retrievers)` signatures are definitive.
- `book_pipeline.interfaces.types`: `SceneRequest`, `RetrievalHit`, `RetrievalResult`, `ContextPack` — Phase 2 implementations target these exact shapes.
- `book_pipeline.observability.JsonlEventLogger` — live since Phase 1; every retriever/bundler/ingestion event writes through it. Schema v1.0 is frozen; Phase 2 additions land in `Event.extra` or new optional top-level fields (no renames, no removals).
- `book_pipeline.book_specifics.corpus_paths.CORPUS_ROOT` — canonical path anchor for the read-only corpus.
- `scripts/lint_imports.sh` + `[tool.importlinter]` — kernel-boundary gate; Phase 2 extends both lists.

### Established Patterns
- Stub impls live in `book_pipeline.stubs`; real impls in their target kernel package. Phase 2's concrete `LanceDBRetriever`, `RoundRobinContextPackBundler`, `CorpusIngester` land in `book_pipeline.rag` / `book_pipeline.corpus_ingest`.
- Event schema v1.0 permits OPTIONAL additions — so `ContextPack.conflicts` and `ContextPack.ingestion_run_id` are safe additions. NEVER rename existing fields.

### Integration Points
- `~/Source/our-lady-of-champion/` — 10 markdown bibles (`brief`, `engineering`, `glossary`, `handoff`, `known-liberties`, `maps`, `outline`, `pantheon`, `relics`, `secondary-characters`). Confirmed present; read-only.
- openclaw cron — added via `openclaw cron add` (Phase 1 ORCH plumbing). Phase 2 registers the nightly ingest job.
- vLLM / Anthropic SDK — NOT called from this phase. Embedding is local (BGE-M3 via sentence-transformers). No frontier LLM in the retrieval loop.

</code_context>

<specifics>
## Specific Ideas

- Pin `model_revision` of `BAAI/bge-m3` in `config/rag_retrievers.yaml` at ingest time and record it in the ingestion_run event — dim mismatch on re-load MUST fail closed, not degrade silently.
- `retrieval_conflicts/<scene_id>.json` is an artifact directory that drafter (Phase 3) and critic (Phase 3) will both want to read — Phase 2 establishes the path and schema, downstream phases consume.
- Golden-query seed set belongs at `tests/rag/golden_queries.jsonl` (kernel test location, not book_specifics) with a sibling `tests/rag/fixtures/expected_chunks.jsonl` — the fixture is book-specific content but lives under tests/, which is exempt from the import-linter kernel contract.
- The bundler's per-axis soft cap + global 40KB hard cap is the hedge against PITFALLS I-2 "prompt bloat spiral" — a rising average `ContextPack.total_bytes` across runs is itself a health signal for the weekly digest (Phase 6).

</specifics>

<deferred>
## Deferred Ideas

- Incremental ingest (only re-chunk changed files): corpus is 250KB; full reingest is cheap; revisit only if ingest exceeds 5 min.
- Hybrid sparse + dense retrieval (BGE-M3 can emit sparse + ColBERT tokens from one forward pass per STACK.md): dense-only is the Phase 2 baseline; hybrid becomes the first RAG ablation (thesis 005) in Phase 6, not a Phase 2 feature.
- `jina-embeddings-v3` comparison: STACK.md flags this as a candidate if BGE-M3 underperforms on Nahuatl + metaphysics corpus. Measure in Phase 6's thesis registry; do not swap preemptively.
- Web dashboard for conflict review — REVIEW-01 is v2; markdown + JSON artifacts are sufficient for v1.
- Full GitHub Actions CI workflow: still deferred per Phase 1 CONTEXT. RAG-04 gate runs via `pytest tests/rag/test_golden_queries.py` invoked by the same pre-push hook as Phase 1's lint gate until the CI workflow lands.

</deferred>
