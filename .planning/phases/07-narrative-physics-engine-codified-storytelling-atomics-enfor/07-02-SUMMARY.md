---
phase: 07-narrative-physics-engine-codified-storytelling-atomics-enfor
plan: 02
subsystem: rag
tags: [retriever, continuity-bible, canonical-quantities, lance-additive, bundler-7-events]
dependency-graph:
  requires:
    - book_pipeline.rag.retrievers.base.LanceDBRetrieverBase
    - book_pipeline.rag.lance_schema.CHUNK_SCHEMA + open_or_create_table
    - book_pipeline.rag.embedding.BgeM3Embedder
    - book_pipeline.config.rag_retrievers.RagRetrieversConfig
    - book_pipeline.corpus_ingest.CorpusIngester (for CLI integration site)
  provides:
    - book_pipeline.rag.retrievers.continuity_bible.ContinuityBibleRetriever (6th RAG axis / CB-01)
    - book_pipeline.corpus_ingest.canonical_quantities (CanonicalQuantity, load_canonical_quantities_seed, ingest_canonical_quantities)
    - config/canonical_quantities_seed.yaml (5 D-15 manuscript canaries — operator truth per OQ-05 (c) RESOLVED)
    - bundler emit-7-events invariant (was 6 events with 5 retrievers)
  affects:
    - src/book_pipeline/cli/ingest.py — every non-skipped `book-pipeline ingest` writes canonical quantities
    - src/book_pipeline/config/rag_retrievers.py — OPTIONAL_RETRIEVERS frozenset; BundlerConfig.per_axis_byte_caps
    - tests/cli/test_ingest_arc_reindex.py + tests/test_config.py — fakes/assertions extended for the new 6th axis
tech-stack:
  added: []
  patterns:
    - LanceDBRetrieverBase subclass for the 6th axis (mirror of NegativeConstraintRetriever; rule_type filter precedent from MetaphysicsRetriever)
    - rule_type column gains a NEW VALUE 'canonical_quantity' (D-22 — additive non-column extension; no new schema column)
    - Pydantic v2 strict (extra="forbid") + Field(pattern=...) + defense-in-depth field_validator on CanonicalQuantity.id (T-07-03 mitigation visible in code)
    - yaml.safe_load only for seed YAML loading (T-07-10)
    - Deterministic chunk_id `f"canonical:{q.id}"` provably safe due to `^[a-z0-9_]+$` regex (T-07-03 round-trip property)
    - Idempotent re-ingest via delete-before-insert + deterministic chunk_id
    - Replaced bare `try: ... except Exception: pass` with typed `except (RuntimeError, ValueError)` (no silent error swallowing per checker fix)
    - `OPTIONAL_RETRIEVERS` superset pattern in typed config validator — Phase-1 freeze + 6th-axis additive
key-files:
  created:
    - src/book_pipeline/rag/retrievers/continuity_bible.py (74 LOC)
    - src/book_pipeline/corpus_ingest/canonical_quantities.py (203 LOC)
    - config/canonical_quantities_seed.yaml (59 LOC; 5 hand-seeded canaries)
    - tests/rag/test_continuity_bible_retriever.py (331 LOC; 8 tests — 5 fast + 3 slow)
    - tests/rag/test_bundler_seven_events.py (168 LOC; 2 tests)
    - tests/corpus_ingest/test_canonical_quantities.py (290 LOC; 26 tests incl. 11 adversarial T-07-03 + 9 round-trip)
  modified:
    - src/book_pipeline/rag/retrievers/__init__.py (import-guarded ContinuityBibleRetriever registration)
    - src/book_pipeline/corpus_ingest/__init__.py (re-export CanonicalQuantity + ingest fns)
    - src/book_pipeline/cli/ingest.py (post-ingest canonical_quantities hook + log line)
    - src/book_pipeline/rag/bundler.py (docstrings updated 6→7 events; module + bundle())
    - src/book_pipeline/config/rag_retrievers.py (OPTIONAL_RETRIEVERS frozenset; BundlerConfig.per_axis_byte_caps)
    - config/rag_retrievers.yaml (continuity_bible retriever entry + bundler.per_axis_byte_caps.continuity_bible=8192)
    - tests/cli/test_ingest_arc_reindex.py (FakeEmbedder.embed_texts no-op)
    - tests/test_config.py (asserts required ⊆ keys, allows the optional 6th)
    - .planning/phases/07-.../deferred-items.md (Plan 07-01 latent DraftRequest model_rebuild documented)
decisions:
  - Dedicated 'continuity_bible' LanceDB table (NOT shared with metaphysics) for clean axis purity matching the existing 5-retrievers-5-tables paradigm. The rule_type='canonical_quantity' filter is defense in depth even though the dedicated table holds only CB-01 rows in v1 (D-22 contract).
  - CanonicalQuantity.id regex-validated to ^[a-z0-9_]+$ via BOTH `Field(pattern=...)` AND a `field_validator` with explicit error message (T-07-03 mitigation visible to readers + stable against future Field-level regression). All 11 adversarial id strings (incl. SQL-injection candidate `"x'; DROP TABLE scene_embeddings; --"`) raise ValidationError at the schema layer.
  - Replaced bare `try: ... except Exception: pass` with typed `except (RuntimeError, ValueError)` per checker fix; LanceDB does NOT export a `LanceError` class (verified `dir(lancedb.exceptions)`); RuntimeError covers most LanceDB error paths and ValueError covers the empty-table delete pre-add no-op. Real errors (other exception classes) propagate.
  - OPTIONAL_RETRIEVERS frozenset extension to RagRetrieversConfig._check_required_retrievers — keeps the 5 frozen names enforced (Plan 02 contract), allows continuity_bible as an optional 6th axis, rejects unknown keys. Phase-1 freeze policy honored (additive only).
  - BundlerConfig.per_axis_byte_caps additive section (Phase-1 freeze policy mirrors RerankerConfig precedent) — `continuity_bible: 8192` (8KB cap per Assumption A5 — keeps CB-01 hits from crowding the 40KB total budget while leaving room for canonical-stamp injection per D-23).
  - tests/cli/test_ingest_arc_reindex.py FakeEmbedder gains a no-op `embed_texts` returning `np.zeros((len(texts), 1024))` — the CLI's new canonical_quantities hook calls embedder.embed_texts; the test was already fully mocked elsewhere, so adding a 5-line no-op is the cleanest fix.
  - tests/test_config.py::test_rag_retrievers_has_5_required_names asserts `required <= keys` rather than equality — the 5 frozen names MUST be present (Plan 02 contract); the 6th is optional and config-controlled.
metrics:
  duration: "24m 17s"
  completed: "2026-04-26T07:11:08Z"
  tasks_completed: 3
  tests_added: 36 (5 retriever fast + 3 retriever slow + 2 bundler 7-event + 26 canonical_quantities)
  files_created: 6
  files_modified: 9
  loc_added_src: 277 (74 retriever + 203 ingest)
  loc_added_tests: 789
---

# Phase 7 Plan 2: ContinuityBibleRetriever (CB-01 / 6th RAG Axis) Summary

**One-liner:** 6th RAG axis (`continuity_bible` / CB-01) — dedicated LanceDB table holding 5 hand-seeded canonical quantities (Andrés age=23, La Niña=55ft, Santiago del Paso=210ft, Cholula=1519-10-18, Cempoala=1519-06-02), retriever subclasses LanceDBRetrieverBase with `rule_type='canonical_quantity'` defense-in-depth filter, CanonicalQuantity.id Pydantic-regex-validated (T-07-03 SQL-injection-unrepresentable), bundler 7-event invariant landed.

## What Landed

### ContinuityBibleRetriever (Task 1)

`src/book_pipeline/rag/retrievers/continuity_bible.py` — 74 LOC subclass of `LanceDBRetrieverBase`:

```python
class ContinuityBibleRetriever(LanceDBRetrieverBase):
    def __init__(self, *, db_path, embedder, reranker, **kw):
        super().__init__(name="continuity_bible", ...)
    def _build_query_text(self, request) -> str:
        # POV + location + date + beat + chapter
    def _where_clause(self, request) -> str | None:
        return "rule_type = 'canonical_quantity'"
```

Mirrors the `NegativeConstraintRetriever` analog exactly (W-2 keyword-only ctor; `**kw` passthrough; B-2 inherited zero-arg `reindex()`). The `rule_type` filter is defense in depth — the dedicated `'continuity_bible'` LanceDB table holds only canonical-quantity rows in v1, but the WHERE clause guarantees that any cross-axis schema accident (e.g., a mistakenly-shared table during ingest) cannot leak non-canonical rows.

Registered in `book_pipeline.rag.retrievers.__init__` via the existing import-guarded fallback pattern (mirrors `EntityStateRetriever` / `ArcPositionRetriever`).

### Canonical-quantity row shape (consumed by Plans 07-03/07-04)

Each LanceDB row in `'continuity_bible'` table:

| Field | Value |
|-------|-------|
| `chunk_id` | `f"canonical:{q.id}"` (e.g., `canonical:andres_age`) |
| `text` | Structured: `"<Name>: <value> (<chapter scope>). <Drift evidence sentence>"` |
| `source_file` | `config/canonical_quantities_seed.yaml` |
| `heading_path` | `f"Canonical Quantity: {q.id}"` |
| `rule_type` | `"canonical_quantity"` |
| `ingestion_run_id` | matches CorpusIngester run id |
| `chapter` | `None` (canonical quantities are scope-aware via text, not column) |
| `source_chapter_sha` | `None` (Plan 05-03 column; only entity_state writes a real SHA) |
| `embedding` | BGE-M3 1024-dim float32 |

The 5 seeded rows (text payloads — substring-extractable for D-23 prompt-header injection):

| chunk_id | Canonical value | Chapter scope |
|----------|-----------------|---------------|
| `canonical:andres_age` | Age **23** | ch01-ch14 |
| `canonical:la_nina_height` | **55** ft apex deck | ch01-ch14 |
| `canonical:santiago_del_paso_scale` | **210** ft apex deterrent | ch01-ch14 |
| `canonical:cholula_date` | **October 18, 1519** | ch04-ch07 (Cholula stir arc) |
| `canonical:cempoala_arrival` | **June 2, 1519** | ch03 (sole arrival; ch04 is post-arrival) |

### Canonical-quantity ingest (Task 2)

`src/book_pipeline/corpus_ingest/canonical_quantities.py` — 203 LOC. Three public symbols:

- `CanonicalQuantity` (Pydantic v2 model, `extra="forbid"`, `frozen=True`)
- `load_canonical_quantities_seed(yaml_path) -> list[CanonicalQuantity]` — `yaml.safe_load` only (T-07-10)
- `ingest_canonical_quantities(*, db_path, seed_yaml_path, embedder, ingestion_run_id) -> int`

Re-exported from `book_pipeline.corpus_ingest.__init__`.

CLI integration in `book_pipeline.cli.ingest`: every non-skipped `book-pipeline ingest` invokes `ingest_canonical_quantities()` after the regular 5-axis ingest + arc reindex; emits log line `ingested 5 canonical quantities from config/canonical_quantities_seed.yaml`.

### `config/canonical_quantities_seed.yaml`

Hand-seeded with the 5 D-15 manuscript canaries per OQ-05 (c) RESOLVED 2026-04-25. Inline header forbids ad-hoc value-tuning — value changes flow through the separate `canon update` workflow (re-ingest + drift alert), NOT through future-plan side effects.

### Bundler 7-event invariant

`src/book_pipeline/rag/bundler.py` docstrings updated `emit 6 events` → `emit 7 events`. The bundle() body did NOT change — it loops over whatever retriever list it receives. The invariant is "1 event per retriever + 1 bundler event"; pre-Plan-07-02 5-retriever calls still emit 6 events, post-Plan-07-02 6-retriever calls emit 7. New test file `tests/rag/test_bundler_seven_events.py` exercises the 6-retriever path (2 tests).

## Threat Model Verification

| Threat ID | Mitigation Status | Evidence |
|-----------|-------------------|----------|
| T-07-03 (Tampering, LanceDB delete WHERE chunk_id IN (...) f-string interpolation) | mitigated | `CanonicalQuantity.id` regex-validated to `^[a-z0-9_]+$` via BOTH `Field(pattern=...)` AND a defense-in-depth `field_validator`. 11 parametrized adversarial inputs (incl. `"x'; DROP TABLE scene_embeddings; --"`, `"X"`, `"x.y"`, `"x;y"`, `"x y"`, `"x-y"`, `"andres age"`, `""`, `"AndresAge"`, newlines, single-quote) each raise `ValidationError`. Round-trip property test: 9 clean ids interpolate into `f"canonical:{q.id}"` and the payload after the `canonical:` prefix matches `^[a-z0-9_]+$`. Bare `try/except Exception/pass` replaced with typed `except (RuntimeError, ValueError)`. |
| T-07-04 (boundary integrity / EoP) | mitigated | continuity_bible.py imports only from `book_pipeline.rag.{embedding, reranker, retrievers.base}` + `book_pipeline.interfaces.types.SceneRequest` — all kernel modules. canonical_quantities.py imports only kernel + lancedb + yaml + pydantic. `bash scripts/lint_imports.sh` exits 0 (2 contracts kept). |
| T-07-05 (Tampering, LanceDB schema migration) | mitigated | D-22 contract upheld: NO new column, only a new VALUE for the existing `rule_type` string column. `open_or_create_table` enforces `CHUNK_SCHEMA` invariants on reopen (RuntimeError on mismatch); end-to-end ingest verified writes 5 rows with correct schema; idempotent re-ingest verified `count_rows() == 5` after second run. |
| T-07-06 (BGE-M3 cache poisoning) | mitigated | CB-01 reuses the existing shared `BgeM3Embedder` instance; revision_sha unchanged from Phase 2; no new cache surface introduced. |
| T-07-10 (YAML deserialization) | mitigated | `load_canonical_quantities_seed` uses `yaml.safe_load` ONLY. `CanonicalQuantity` model uses `extra="forbid"` (defense in depth) — verified by `test_canonical_quantity_extra_forbid_rejects_unknown_fields`. |

## CLI Ingest Output (Task 3 verification)

```
$ uv run book-pipeline ingest --force
[OK] CorpusIngester.ingest
  ingestion_run_id:     ing_20260426T070415843241Z_56041839
  embed_model_revision: 5617a9f61b028005a4858fdac845db406aefb181
  db_version:           lancedb>=0.30.2
  wall_time_ms:         31772
  source_files:         9
    arc_position           42 chunks
    entity_state           54 chunks
    historical             45 chunks
    metaphysics            51 chunks
    negative_constraint    45 chunks
  resolved_model_revision: indexes/resolved_model_revision.json
  arc_position reindex: beat-ID-stable rows written
  ingested 5 canonical quantities from config/canonical_quantities_seed.yaml
```

LanceDB row count verified:

```
$ python -c "import lancedb; db = lancedb.connect('indexes'); t = db.open_table('continuity_bible'); print(t.count_rows())"
5
```

All 5 canonical chunk_ids landed:
- `canonical:andres_age`
- `canonical:la_nina_height`
- `canonical:santiago_del_paso_scale`
- `canonical:cholula_date`
- `canonical:cempoala_arrival`

## Test Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `tests/rag/test_continuity_bible_retriever.py` | 8 (5 fast + 3 slow) | name + _where_clause filter (verbatim) + empty-table tolerance + top-K with rule_type='canonical_quantity' + Retriever Protocol; slow integration: real BGE-M3 + reranker + indexes/ — Cempoala / Cholula / Andrés queries surface canonical-value rows |
| `tests/rag/test_bundler_seven_events.py` | 2 | 6 fake retrievers → 7 events emitted (6 retriever + 1 bundler); bundle() docstring documents `emit 7 events` |
| `tests/corpus_ingest/test_canonical_quantities.py` | 26 | 5 happy-path tests (load YAML; text fields contain canonical values; ingest writes 5 rows; idempotent re-ingest; deterministic chunk_id prefix); 11 T-07-03 adversarial id rejections; 9 T-07-03 round-trip clean-id safety; extra="forbid" rejection |
| **Total** | **36** | **All Wave 0 tests for Plan 07-02** |

Plan 07-02 acceptance gate (`uv run pytest tests/rag/test_continuity_bible_retriever.py tests/rag/test_bundler_seven_events.py tests/corpus_ingest/test_canonical_quantities.py -m "not slow" -x`): **33 passed, 3 deselected, 0 failed**.

Slow integration gate (`uv run pytest tests/rag/test_continuity_bible_retriever.py tests/corpus_ingest/test_canonical_quantities.py -m slow -x`): **3 passed, 31 deselected, 0 failed** (~104s wall-time on real BGE-M3 + LanceDB).

## Bundler 7-event invariant (Plan 07-03 wiring note)

Plan 07-03 will compose the CLI scene-loop site (`cli/draft.py`) to pass 6 retrievers (the existing 5 + ContinuityBibleRetriever). After that wiring, every `book-pipeline draft` invocation will emit 7 events per scene context-pack assembly (was 6). Tests covering the bundler 7-event invariant: `tests/rag/test_bundler_seven_events.py::test_bundle_emits_exactly_seven_events_with_six_retrievers`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] LanceDB has no `LanceError` class**
- **Found during:** Task 2 GREEN — writing the typed except clause.
- **Issue:** Plan instructed `except (lancedb.LanceError, ValueError)` but `dir(lancedb)` shows no `LanceError` class; `lancedb.exceptions` exposes only `MissingColumnError` (subclasses KeyError) and `MissingValueError` (subclasses ValueError). LanceDB's other errors surface as `RuntimeError` / `ValueError`.
- **Fix:** Used `except (RuntimeError, ValueError)` instead. RuntimeError covers most LanceDB error paths; ValueError covers the empty-table delete pre-add no-op + `MissingValueError`. Real errors (any other exception class) propagate — no silent swallowing. Inline comment explains the exception-class choice.
- **Files modified:** `src/book_pipeline/corpus_ingest/canonical_quantities.py`.
- **Commit:** `cd530e8`.

**2. [Rule 3 - Blocking] `RagRetrieversConfig` rejected the 6th retriever**
- **Found during:** Task 1 GREEN — config load post-YAML edit.
- **Issue:** `RagRetrieversConfig._check_5_retrievers` validator required `set(keys) == REQUIRED_RETRIEVERS` (the 5 frozen names). Adding `continuity_bible:` to YAML caused `ValidationError`. Also `BundlerConfig` had no `per_axis_byte_caps` field.
- **Fix:** Added `OPTIONAL_RETRIEVERS = frozenset({"continuity_bible"})`; renamed validator to `_check_required_retrievers` and changed the contract to "required ⊆ keys ⊆ required ∪ optional" (preserves Plan 02 invariant + allows the 6th additive axis); added `per_axis_byte_caps: dict[str, int] = Field(default_factory=dict)` to `BundlerConfig` (additive section, Phase-1 freeze policy mirrors RerankerConfig precedent).
- **Files modified:** `src/book_pipeline/config/rag_retrievers.py`.
- **Commit:** `e00b45d`.

**3. [Rule 1 - Bug fix] `tests/cli/test_ingest_arc_reindex.py` FakeEmbedder lacked embed_texts**
- **Found during:** Task 2 GREEN — full-suite regression check.
- **Issue:** Plan 07-02 CLI ingest hook calls `embedder.embed_texts(...)` for canonical_quantities ingest. The pre-existing test's FakeEmbedder is monkeypatched in place of `BgeM3Embedder` and lacked `embed_texts`. Direct regression caused by Plan 07-02 changes.
- **Fix:** Added 5-line no-op `embed_texts` returning `np.zeros((len(texts), 1024), dtype=np.float32)` to the test's FakeEmbedder. Test continues to assert what it cares about (arc reindex wiring); canonical_quantities ingest completes silently in the test path.
- **Files modified:** `tests/cli/test_ingest_arc_reindex.py`.
- **Commit:** `cd530e8`.

**4. [Rule 1 - Bug fix] `tests/test_config.py::test_rag_retrievers_has_5_required_names` over-strict**
- **Found during:** Task 2 GREEN.
- **Issue:** Test asserted `set(cfg.retrievers.keys()) == {5 names}` — Plan 07-02 deliberately adds an optional 6th retriever (continuity_bible) so the equality assertion broke.
- **Fix:** Changed to `required <= set(cfg.retrievers.keys())` with explanatory comment; preserves the Plan 02 contract (5 required names MUST be present) while allowing the optional 6th.
- **Files modified:** `tests/test_config.py`.
- **Commit:** `cd530e8`.

### Out-of-Scope (logged, NOT fixed)

**Pre-existing `DraftRequest.model_rebuild()` not auto-triggered when only `interfaces.types` is imported (Plan 07-01 latent).** Verified at `git checkout HEAD~3` (Plan 07-01 head); failures pre-date Plan 07-02. Affects ~16 tests across `tests/drafter/`, `tests/cli/test_draft_loop.py`, `tests/cli/test_draft_spend_cap.py`, `tests/chapter_assembler/test_dag.py`, `tests/integration/test_chapter_dag_end_to_end.py`, `tests/integration/test_scene_loop_escalation.py`. Logged to `.planning/phases/07-.../deferred-items.md` with three fix candidates for Plan 07-03 to pick from. Per `<deviation_rules>` SCOPE BOUNDARY rule — only auto-fix issues directly caused by current task changes; pre-existing failures in unrelated files are out of scope.

**Pre-existing ruff failures in `src/book_pipeline/cli/draft.py`** (already logged to deferred-items.md by Plan 07-01).

## Authentication Gates

None. Plan 07-02 was fully autonomous, NO LLM calls (Anthropic / vLLM untouched), one BGE-M3 ingest call to populate `indexes/continuity_bible/` for the slow integration test. V7C training was not running during execution — GPU clear (verified `nvidia-smi` before ingest).

## Decisions Made

1. **Dedicated `continuity_bible` LanceDB table** (not shared with `metaphysics`) for clean axis purity — matches the existing 5-retrievers-5-tables paradigm and keeps the bundler's per-axis byte cap accounting clean. The `rule_type='canonical_quantity'` filter is defense in depth.
2. **CanonicalQuantity.id regex via BOTH Field(pattern=...) AND field_validator.** Field(pattern=...) alone is sufficient runtime; the field_validator makes the T-07-03 mitigation visible to readers AND hardens against future Field-level regression (e.g., if someone widens the regex thinking it's "just" the pattern argument).
3. **Replace bare `try: ... except Exception: pass` with `except (RuntimeError, ValueError)`** per checker fix — surfaces real LanceDB errors instead of swallowing them. The original draft was unsafe (any error class in the delete path silently swallowed); typed exceptions surface unexpected failure modes.
4. **OPTIONAL_RETRIEVERS frozenset** in the typed config validator instead of dropping the 5-required check. The 5 frozen names are a Plan 02 contract; the 6th is a Plan 07-02 additive. Type-safe superset is cleaner than relaxing the validator entirely.
5. **`BundlerConfig.per_axis_byte_caps: dict[str, int]`** as an additive optional section (Phase-1 freeze policy precedent: `RerankerConfig` was added the same way in Plan 02-06). The book_pipeline.rag.budget.PER_AXIS_SOFT_CAPS module constant remains the source of truth for legacy axes; the YAML-driven dict overlays for the new axis only.
6. **Idempotency via delete-before-insert with deterministic chunk_id.** Simpler than upsert semantics and aligned with the existing entity_state idempotency pattern.

## Open Questions for Plan 07-03 / 07-04 / 07-05

- **Plan 07-03 will need to update CLI composition site to pass 6 retrievers.** `cli/draft.py` currently passes 5 retrievers to the bundler; Plan 07-03 must extend `build_retrievers_from_config` (book_pipeline.rag.__init__) to include `ContinuityBibleRetriever` and route the 6 retrievers through `bundle()`. After that wiring, the bundler will emit 7 events per scene call (per the new invariant landed here).
- **Plan 07-03 will consume the canonical-quantity row text field for D-23 stamping.** The drafter's pre-flight gate must (a) pull the canonical-quantity hits from `pack.retrievals['continuity_bible']`, (b) substring-extract the values from each hit's text field (the structured "Name: value" format makes this deterministic), (c) inject them at top-of-prompt as `CANONICAL: Andrés age=23, La Niña height=55ft, ...`. The five canary values are stable in the seed YAML so plan 07-03 can hardcode the substring-extraction patterns OR parse the structured "Name: VALUE (...)" head-of-line.
- **Plan 07-04 critic `named_quantity_drift` axis** consumes the same `pack.retrievals['continuity_bible']` hits + the produced scene text; checks that any reference to a canonical quantity in the produced text matches the canonical value verbatim (re.search anchored to canonical_value field).
- **Long-tail canonical-quantity extraction agent (OQ-05 (c) tail)** — RESOLVED 2026-04-25 to v1.1 deferral. The 5 hand-seeded canaries cover the failure-evidence anchors; the long tail (every named entity / quantity in ~250KB lore corpus) is tractable for an extraction agent with operator-review gating but not in scope here. No follow-up plan required for Phase 7 acceptance.
- **DraftRequest model_rebuild auto-trigger** (deferred-items.md). Plan 07-03 should pick fix candidate (1) — `interfaces/types.py` calls `_rebuild_for_physics_forward_ref()` opportunistically in a `try/except ImportError: pass` block at module-tail. Required to unblock the broader test suite for Plan 07-03's CLI composition tests.

## Self-Check: PASSED

- All 6 created files exist on disk:
  - FOUND: src/book_pipeline/rag/retrievers/continuity_bible.py
  - FOUND: src/book_pipeline/corpus_ingest/canonical_quantities.py
  - FOUND: config/canonical_quantities_seed.yaml
  - FOUND: tests/rag/test_continuity_bible_retriever.py
  - FOUND: tests/rag/test_bundler_seven_events.py
  - FOUND: tests/corpus_ingest/test_canonical_quantities.py
- All 4 task commits present in `git log`:
  - FOUND: `4602824` (Task 1 RED)
  - FOUND: `e00b45d` (Task 1 GREEN)
  - FOUND: `bb2a0ab` (Task 2 RED)
  - FOUND: `cd530e8` (Task 2 GREEN)
- Plan 07-02 acceptance gate (fast tests): 33 passed, 3 deselected, 0 failed
- Plan 07-02 slow integration gate: 3 passed, 31 deselected, 0 failed
- Import-linter contracts: 2 kept, 0 broken
- LanceDB row count: 5 (verified)
- All 5 canonical chunk_ids present in indexes/continuity_bible.lance
- T-07-03 adversarial id (`x'; DROP TABLE scene_embeddings; --`) raises ValidationError
