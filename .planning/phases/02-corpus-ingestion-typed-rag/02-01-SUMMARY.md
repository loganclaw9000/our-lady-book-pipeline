---
phase: 02-corpus-ingestion-typed-rag
plan: 01
subsystem: rag-kernel-foundation
tags: [rag, chunking, embedding, lancedb, schema, kernel, adr-004, foundation, found-05-extended]
requirements_completed: []  # CORPUS-01 remains open — Plan 02 ships the ingester that writes to these tables.
dependency_graph:
  requires:
    - "01-02 (book_pipeline.interfaces — RetrievalHit shape target, frozen)"
    - "01-05 (book_pipeline.observability.hashing.hash_text — used for stable chunk_id)"
    - "01-06 (import-linter contract extension policy — this plan is the first client)"
    - "Phase 1 Complete (pytest infra + uv venv + mypy --strict already green on 111 tests)"
  provides:
    - "book_pipeline.rag — kernel-eligible Python package with 4 leaf modules"
    - "chunk_markdown(text, source_file, *, target_tokens, overlap_tokens, ingestion_run_id) -> list[Chunk]"
    - "Chunk Pydantic model (frozen, extra='forbid', 7 fields: chunk_id, text, source_file, heading_path, rule_type, ingestion_run_id, chapter)"
    - "BgeM3Embedder (lazy-load, revision_sha pinned, embed_texts → (n, 1024) float32 unit-normalized)"
    - "EMBEDDING_DIM=1024 module constant"
    - "CHUNK_SCHEMA (8 pyarrow fields, additive-only contract)"
    - "open_or_create_table(db_path, axis_name) → Table (schema-enforced; raises on drift)"
    - "Import-linter contract 1 now covers book_pipeline.rag source_modules"
    - "Import-linter contract 2 now covers book_pipeline.rag forbidden_modules (DEVIATION — see below)"
    - "scripts/lint_imports.sh mypy target list extended with src/book_pipeline/rag"
  affects:
    - "Plan 02-02 (corpus ingester): consumes chunk_markdown + BgeM3Embedder + open_or_create_table; writes rows against CHUNK_SCHEMA; fills TBD-phase2 model_revision in config/rag_retrievers.yaml via revision_sha"
    - "Plan 02-03 (historical/metaphysics retrievers): reads from LanceDB with CHUNK_SCHEMA; filters on rule_type for metaphysics axis"
    - "Plan 02-04 (arc_position/entity_state retrievers): filters on chapter column directly (W-5)"
    - "Plan 02-05 (negative_constraint retriever + bundler): same schema"
    - "Plan 02-06 (RAG-04 golden-query CI gate): reads CHUNK_SCHEMA contents for golden-query accuracy"
    - "Plans 03+ (drafter/critic/regenerator/orchestration) will extend import-linter + mypy-target lists using the same append-as-you-add policy this plan first exercised"
tech_stack:
  added:
    - "tiktoken cl100k_base encoding — token counting in chunker (already in pyproject from Phase 1)"
    - "lancedb 0.30.2 — per-axis table storage (first kernel use; Phase 1 had it in deps but unused)"
    - "sentence-transformers 5.4.1 — BGE-M3 wrapper (first kernel use)"
    - "huggingface_hub 1.11.0 — HfApi().model_info().sha for revision resolution (first kernel use)"
    - "pyarrow 24.0.0 — LanceDB schema building (transitive from lancedb; first direct use)"
    - "numpy 2.4.4 — embedder return type (first direct use)"
  patterns:
    - "Heading-aware chunking: chunker NEVER crosses markdown heading boundaries within a single chunk; breadcrumb heading_path (`H1 > H2 > H3`) is the retrieval filter unit, not raw character offsets. PITFALLS R-4 mitigation."
    - "rule_type inference on heading path: regex-driven label written at chunk-time, not retrieval-time. Lets the metaphysics retriever (Plan 04) filter by `rule_type='rule'` to avoid surfacing hypotheticals / cross-references as authoritative facts."
    - "chapter inference on heading path (W-5 revision): int|None column populated at chunk-time by matching `Chapter N` in the breadcrumb. Plan 04 arc_position retriever uses this for exact equality filtering instead of fragile `heading_path LIKE 'Chapter N %'` — LIKE would fail on `Chapter 10` matching `Chapter 1` prefix."
    - "Lazy embedder loading: BgeM3Embedder.__init__ does NOT touch disk or GPU. First embed_texts / revision_sha call triggers model load. Unit tests never download the 2GB model (monkeypatched SentenceTransformer)."
    - "Pin-once revision_sha: if caller passes an explicit `revision`, it's returned verbatim (the pin). If `revision=None`, HfApi resolves the current HEAD SHA on first access and the result is cached for the lifetime of the process. Plan 02 writes this value into every `event_type=ingestion_run` event for reproducibility."
    - "Schema-on-reopen enforcement: open_or_create_table raises RuntimeError if the on-disk table schema drifts from CHUNK_SCHEMA. Never silently migrates — drift is the precursor to PITFALLS R-4 wrong-fact retrieval compounding across re-ingestions."
    - "Stable chunk_id = xxh64(source_file | heading_path | text): deterministic across processes, survives re-ingestion of unchanged sections. ingestion_run_id differs between runs; chunk_id does not. Same content → same id."
key_files:
  created:
    - "src/book_pipeline/rag/__init__.py (29 lines; re-exports Chunk, chunk_markdown, EMBEDDING_DIM, BgeM3Embedder, CHUNK_SCHEMA, open_or_create_table)"
    - "src/book_pipeline/rag/types.py (42 lines; Chunk Pydantic model, frozen + extra=forbid)"
    - "src/book_pipeline/rag/chunker.py (305 lines; heading splitter + sentence packer + rule_type/chapter inference)"
    - "src/book_pipeline/rag/embedding.py (122 lines; BgeM3Embedder lazy wrapper + HfApi revision resolution)"
    - "src/book_pipeline/rag/lance_schema.py (84 lines; CHUNK_SCHEMA + open_or_create_table)"
    - "tests/rag/__init__.py (empty)"
    - "tests/rag/test_chunker.py (250 lines; 9 tests)"
    - "tests/rag/test_embedding.py (170 lines; 6 tests + fake SentenceTransformer)"
    - "tests/rag/test_lance_schema.py (131 lines; 5 tests)"
    - "tests/rag/fixtures/mini_corpus.md (53 lines; 3 H1 siblings — Main Rules, Rule Cards — Hypotheticals, Cross References)"
    - "tests/rag/fixtures/chapter_corpus.md (21 lines; # Chapter 3: + ## Chapter 3 — Scene 2 for chapter-inference test)"
  modified:
    - "pyproject.toml (import-linter contract 1 source_modules += [book_pipeline.rag]; contract 2 forbidden_modules += [book_pipeline.rag])"
    - "scripts/lint_imports.sh (mypy target list += src/book_pipeline/rag)"
    - "tests/test_import_contracts.py (kernel_dirs grep-fallback list += Path('src/book_pipeline/rag'))"
decisions:
  - "Contract-2 extension semantics deviate from the plan's literal wording. Plan said 'append book_pipeline.rag to source_modules in BOTH contracts'. Doing so literally would have forbidden rag from importing observability (chunker uses observability.hashing.hash_text — a legitimate cross-kernel dep), which breaks the aggregate gate. Semantic fix: appended to contract-2 forbidden_modules instead. Intent preserved (each new kernel concrete appears in both contracts). Plan's acceptance criterion grep -c 'book_pipeline.rag' >= 2 still satisfied (4 occurrences: contract 1 source, contract 2 forbidden, plus two phase-2-done comments)."
  - "Chunker uses cl100k_base tokens (OpenAI tiktoken encoding), NOT BGE-M3's own tokenizer. Per PITFALLS R-4 the heading-boundary correctness is load-bearing; ±15% token drift is acceptable. Plan explicitly permits this. Alternative (loading BGE-M3 tokenizer at chunk time) would have required eager model load, breaking the lazy-embedder invariant."
  - "revision_sha strategy: 'explicit-pass-through OR HfApi-HEAD-on-first-access'. Rejected alternative: always resolve on first access regardless. Rationale: when config/rag_retrievers.yaml fills in `model_revision: <sha>`, that IS the reproducibility pin — we must NOT silently 'resolve' it to the HEAD sha and record a different value in the event log. Passing revision=None is an opt-in to 'whatever is current on the Hub', used only for first-time pin bootstrapping (Plan 02 fills the TBD-phase2 slot with the revision_sha resolved on its first ingest)."
  - "chapter column lives on the LanceDB schema at creation time (W-5 revision, captured in plan frontmatter). Rejected alternative: compute chapter at retrieval time from heading_path via LIKE clause. Rationale: `heading_path LIKE 'Chapter 1%'` would false-match Chapter 10-19, requiring `LIKE 'Chapter 1 %'` with exact space matching; fragile to breadcrumb-format changes. Storing the int directly sidesteps the whole string-match class of bugs and is trivially cheap (one int64 column per row)."
  - "open_or_create_table uses the (deprecated-in-0.30) `db.table_names()` API instead of the replacement `db.list_tables()`. Reason: `list_tables()` returns a `ListTablesResponse` object whose `__contains__` iterates (key, value) tuples — NOT table names. Using `axis_name in db.list_tables()` would always return False. `table_names()` still returns a plain list[str] in 0.30.x; we'll migrate to `list_tables().tables` when the deprecation actually removes the old method. Noted as TODO at the call site."
  - "Chunker splits fixture mini_corpus.md on three H1 (`#`) headings, not H1+H2 siblings. Initial fixture used `# Main Rules / ## Rule Cards — Hypotheticals / ## Cross References`, which correctly nested all three under Main Rules' breadcrumb; fixture flattened to three H1 peers so the heading_path.split(' > ')[0] invariant tested the intended semantics."
metrics:
  duration_minutes: 45
  completed_date: 2026-04-22
  tasks_completed: 1
  files_created: 11
  files_modified: 3
  tests_added: 20
  tests_passing: 131
commits:
  - hash: 8cd8169
    type: test
    summary: RED — 20 failing tests for rag kernel (chunker + embedder + lance_schema)
  - hash: be38615
    type: feat
    summary: GREEN — book_pipeline.rag kernel (chunker + BGE-M3 embedder + LanceDB schema) + import-linter/mypy extensions
---

# Phase 2 Plan 1: RAG Kernel Foundation Summary

**One-liner:** `book_pipeline.rag` lands as a new kernel package exporting six primitives — `Chunk` (Pydantic, 7 fields, frozen), `chunk_markdown` (heading-aware, 512-token / 64-overlap, rule-type + chapter tagging per PITFALLS R-4 and W-5), `BgeM3Embedder` (lazy `SentenceTransformer` wrapper with `revision_sha` pin-or-resolve-via-`HfApi`), `EMBEDDING_DIM=1024`, `CHUNK_SCHEMA` (8 pyarrow fields; additive-only), and `open_or_create_table` (LanceDB schema-enforced with RuntimeError on drift) — plus import-linter contract 1 extended to forbid `rag → book_specifics`, contract 2 extended to forbid `interfaces → rag` (a semantic fix-up of the plan's literal-but-broken instruction), and the aggregate lint+ruff+mypy gate now covers `src/book_pipeline/rag` with zero failures across 131 tests.

## What Shipped

`book_pipeline.rag` is now a first-class kernel package — Wave 1 unblocks Plans 02-03/04/05/06:

- **`src/book_pipeline/rag/types.py`** — `Chunk(BaseModel)` with 7 fields (`chunk_id`, `text`, `source_file`, `heading_path`, `rule_type`, `ingestion_run_id`, `chapter`). `model_config = ConfigDict(extra="forbid", frozen=True)`. Intentionally NOT in `interfaces/types.py` — that module is for Protocol contracts that flow between components; `Chunk` is an axis-local persistence row (LanceDB).
- **`src/book_pipeline/rag/chunker.py`** — `chunk_markdown(text, source_file, *, target_tokens=512, overlap_tokens=64, ingestion_run_id="") -> list[Chunk]`. Splits on ATX headings (`^#{1,6} `) via regex, builds `heading_path` breadcrumbs ("`H1 > H2 > H3`"), and within each section runs a sentence-aware sliding window that targets `target_tokens` cl100k_base tokens (±20%) with `overlap_tokens` carry-over between adjacent chunks. Empty / whitespace sections produce zero chunks. `chunk_id = hash_text(source_file | heading_path | text)` — stable across runs.
- **`src/book_pipeline/rag/embedding.py`** — `BgeM3Embedder` (lazy wrapper around `sentence_transformers.SentenceTransformer`). `__init__` never touches disk or GPU. First `embed_texts` or `revision_sha` call resolves the revision (explicit passthrough OR `HfApi().model_info(model_name).sha`) and loads the model. `embed_texts` returns `(n, 1024) float32` unit-normalized arrays. `EMBEDDING_DIM = 1024` module constant.
- **`src/book_pipeline/rag/lance_schema.py`** — `CHUNK_SCHEMA` (8 pyarrow fields, see byte-for-byte reproduction below) + `open_or_create_table(db_path, axis_name)`. The function is schema-enforcing: on reopen, if the on-disk table schema ≠ `CHUNK_SCHEMA`, it raises `RuntimeError` (`Schema mismatch on table ...`) — it never silently migrates. `mkdir(parents=True, exist_ok=True)` on the db directory so callers don't have to pre-create.
- **`src/book_pipeline/rag/__init__.py`** — re-exports the 6 public symbols: `Chunk`, `chunk_markdown`, `EMBEDDING_DIM`, `BgeM3Embedder`, `CHUNK_SCHEMA`, `open_or_create_table`.
- **Import-linter extensions** (pyproject.toml):
    - Contract 1 (`Kernel packages MUST NOT import from book_specifics`): appended `"book_pipeline.rag"` to `source_modules`. Already enforcing.
    - Contract 2 (`Interfaces MUST NOT import from concrete kernel implementations`): appended `"book_pipeline.rag"` to `forbidden_modules` (NOT `source_modules` — see "Deviations" below). Contract 2 now forbids `interfaces` from importing `observability`, `stubs`, OR `rag`.
- **`scripts/lint_imports.sh`** — mypy targets list appended with `src/book_pipeline/rag`. The aggregate gate (`bash scripts/lint_imports.sh`) now covers the new module with zero failures.
- **`tests/test_import_contracts.py`** — belt-and-suspenders `test_kernel_does_not_import_book_specifics` grep-fallback list extended with `Path("src/book_pipeline/rag")`.

## Chunker's rule_type regex patterns (downstream consumer: Plan 04 metaphysics retriever)

`chunk.rule_type` is inferred from the full `heading_path` breadcrumb (not just the leaf), case-insensitive, first-match-wins in the following priority:

| Priority | Regex              | Result             |
| -------- | ------------------ | ------------------ |
| 1        | `hypothetic`       | `"hypothetical"`   |
| 2        | `\bexample(s)?\b`  | `"example"`        |
| 3        | `cross[- ]?ref`    | `"cross_reference"`|
| default  | —                  | `"rule"`           |

This is how Plan 04's metaphysics retriever will avoid surfacing hypotheticals as authoritative (PITFALLS R-4). Filter clause example: `WHERE rule_type = 'rule'` at query time.

## Chunker's chapter-inference regex (W-5 revision — downstream consumer: Plan 04 arc_position retriever)

`chunk.chapter` is populated by scanning the `heading_path` breadcrumb for `\bChapter\s+(\d+)\b` (case-insensitive). If matched, `chunk.chapter = int(group(1))`; otherwise `chunk.chapter = None`. Matches either `# Chapter N:` top-level OR any nested breadcrumb segment `... > Chapter N — Scene 2 > ...`.

**Decision captured per plan's output requirement:** W-5 revision introduces `chapter` at chunk-time (not retrieval-time) so Plan 04 can filter on exact equality (`WHERE chapter = 3`) instead of `heading_path LIKE 'Chapter 3 %'`. The LIKE approach has a sharp false-match edge (`Chapter 1` prefix matches `Chapter 10..19`); the int-column approach doesn't.

## BgeM3Embedder revision SHA resolution strategy

Plan 02 needs this to fill `model_revision: TBD-phase2` in `config/rag_retrievers.yaml`.

Strategy: **pin-or-resolve-on-first-access**.

- **If `BgeM3Embedder(revision="sha-or-tag")` is passed explicitly:** `revision_sha` returns that string verbatim. This IS the pin. Never overridden. `SentenceTransformer(..., revision=revision)` loads exactly that revision.
- **If `BgeM3Embedder(revision=None)`:** On first access to `revision_sha` (or first `embed_texts`), `huggingface_hub.HfApi().model_info("BAAI/bge-m3").sha` resolves the current HEAD SHA on the Hub; result is cached on `self._revision_sha` for the process lifetime. `SentenceTransformer(..., revision=None)` then loads that HEAD.

**Bootstrap plan (Plan 02):** first ingest runs with `revision=None`, reads `embedder.revision_sha` after load, writes that SHA into `config/rag_retrievers.yaml`'s `model_revision` field AND into the `event_type=ingestion_run` event's `embed_model_version` extra. Subsequent ingests use the explicit pin.

## LanceDB CHUNK_SCHEMA (byte-for-byte — Plan 02 writes against this; mismatch = RuntimeError)

```python
CHUNK_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("chunk_id", pa.string(), nullable=False),
        pa.field("text", pa.string(), nullable=False),
        pa.field("source_file", pa.string(), nullable=False),
        pa.field("heading_path", pa.string(), nullable=False),
        pa.field("rule_type", pa.string(), nullable=False),
        pa.field("ingestion_run_id", pa.string(), nullable=False),
        pa.field("chapter", pa.int64(), nullable=True),
        pa.field("embedding", pa.list_(pa.float32(), EMBEDDING_DIM), nullable=False),
    ]
)
```

All 8 fields. `chapter` is the only nullable column. `embedding` is `fixed_size_list<float32, 1024>` (not a variable list — fixed to `EMBEDDING_DIM=1024` for zero-copy pyarrow). Plans 02-06 write rows against these exact column names; any write that doesn't carry all 7 non-nullable fields will fail on commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's contract-2 extension instruction would break the aggregate gate.**

- **Found during:** Task 1 action step 11 (writing the pyproject.toml change).
- **Issue:** The plan's `<interfaces>` block said to append `"book_pipeline.rag"` to `source_modules` in BOTH `[[tool.importlinter.contracts]]` blocks. Contract 1's intent is correct (rag MUST NOT import from book_specifics → add rag as a source). But contract 2's intent is "interfaces MUST NOT import from concrete kernel implementations" — its `source_modules` is and should stay `["book_pipeline.interfaces"]` only. Adding rag to contract-2 source_modules would mean "rag MUST NOT import from observability or stubs" — but rag's chunker LEGITIMATELY uses `book_pipeline.observability.hashing.hash_text`. Literal execution of the plan's instruction would break the `uv run lint-imports` step of the aggregate gate, which the plan's own success criterion requires to pass.
- **Fix:** Appended `"book_pipeline.rag"` to contract-2's `forbidden_modules` instead (forbids `interfaces` from importing `rag` — semantically correct for contract 2's stated purpose of keeping interfaces clean of concretes). Added extension-policy comment rewriting: contract-2's source_modules is frozen at `[interfaces]`; new kernel concretes extend contract-2's `forbidden_modules`, not its source_modules.
- **Rationale:** Plan's clear *intent* was "both contracts grow with new kernel packages." Contract 1's growth point is source_modules (adding new sources that must be kept clean of book_specifics). Contract 2's growth point is forbidden_modules (adding new concretes that interfaces must stay ignorant of). The plan author conflated the two growth points under "source_modules in both"; the fix preserves intent while keeping semantics correct.
- **Files modified:** `pyproject.toml`
- **Commit:** `be38615`

**2. [Rule 1 - Bug] lancedb 0.30.x `list_tables()` API return type incompatible with `in` operator.**

- **Found during:** Task 1 GREEN verify — first `pytest tests/rag/` run after writing production code with `db.list_tables()` (chosen to avoid the deprecation warning on `db.table_names()`).
- **Issue:** `lancedb.LanceDBConnection.list_tables()` in v0.30.2 returns a `ListTablesResponse` pydantic-style object (NOT a `list[str]`). Its `__iter__` yields `(field_name, field_value)` tuples (the object's own attributes), so `"historical" in db.list_tables()` always returns False — every call path would fall through to the create branch, raising on the second `open_or_create_table` call because `create_table(..., mode="create")` fails on an existing table.
- **Fix:** Reverted to `db.table_names()` (still present in 0.30.x, emits a `DeprecationWarning`). Added TODO note at the call site for the eventual migration to `list_tables().tables` when `table_names()` is fully removed. 20 test warnings are expected and documented; no functional impact.
- **Rationale:** The deprecation is ~2 lancedb minor versions out per typical patterns, well past this plan's horizon. Using the working API today with a migration note is preferable to writing code that doesn't work.
- **Files modified:** `src/book_pipeline/rag/lance_schema.py` (TODO comment + api call)
- **Commit:** `be38615`

**3. [Rule 1 - Bug] Initial fixture for mini_corpus.md used `## Rule Cards` nested under `# Main Rules`, collapsing the test's top-heading invariant.**

- **Found during:** Task 1 GREEN verify — first full pytest run.
- **Issue:** `test_chunker_mini_corpus_produces_heading_aware_chunks` asserts that the set of unique `heading_path.split(' > ')[0]` values equals `{"Main Rules", "Rule Cards — Hypotheticals", "Cross References"}`. The initial fixture had one H1 and two H2's; the chunker's breadcrumb builder (correct behavior) yielded `"Main Rules > Rule Cards — Hypotheticals"` and `"Main Rules > Cross References"`, so the top-of-breadcrumb was "Main Rules" for every chunk. Test's assumption was wrong for the fixture's nesting.
- **Fix:** Changed fixture to three H1 (`#`) sibling headings so each section's breadcrumb is a single entry and the test's semantics match the intent.
- **Rationale:** The test-level invariant (each named top-heading contributes chunks) is the real behavior being exercised; the fixture's nesting shape was an accidental choice, not a semantic requirement.
- **Files modified:** `tests/rag/fixtures/mini_corpus.md`
- **Commit:** `be38615`

**4. [Rule 2 - Missing critical functionality] `test_kernel_does_not_import_book_specifics` grep-fallback didn't cover the new `rag` kernel.**

- **Found during:** Task 1 full-suite verify (pytest tests/).
- **Issue:** 01-06 Phase 1 shipped a belt-and-suspenders static grep test that asserts no file under `src/book_pipeline/{interfaces,observability,stubs,config,cli,openclaw}/` contains the literal string "book_specifics". With `rag` now being a kernel package, it needed to be in that list too — otherwise the fallback would silently stop covering the new kernel if import-linter ever got misconfigured.
- **Fix:** Appended `Path("src/book_pipeline/rag")` to the `kernel_dirs` list in `test_kernel_does_not_import_book_specifics`. Rewrote the rag `__init__.py` docstring to avoid the literal substring "book_specifics" (previously mentioned it as a "DON'T" reference; now phrased as "lives outside this kernel package"), since the static test is substring-level.
- **Rationale:** Kernel membership is invariant — being part of the boundary-enforced kernel MUST also mean being part of the grep fallback. Missing this would be a Rule 2 gap (critical correctness requirement for the static analysis belt).
- **Files modified:** `tests/test_import_contracts.py`, `src/book_pipeline/rag/__init__.py`
- **Commit:** `be38615`

**5. [Rule 3 - Blocking] Ruff violations blocking the aggregate gate.**

- **Found during:** Task 1 verify (ruff step of scripts/lint_imports.sh).
- **Issues + fixes:**
    - `RUF023` `_Section.__slots__` not alphabetically sorted → sorted.
    - `RUF022` `__all__` not sorted in embedding.py → sorted.
    - `UP037` forward-reference string quote on `Table` return annotation → removed (lancedb.table.Table is top-level-importable now).
    - `I001` import reorder in lance_schema.py → fixed by ruff `--fix`.
    - `B017` `pytest.raises(Exception)` → replaced with `pytest.raises(ValidationError)` (the actual exception pydantic raises).
    - `UP037` forward-reference string quote on `_FakeSentenceTransformer` in test → removed (has `from __future__ import annotations`).
    - `RUF012` mutable class-attr `_instances: list[...] = []` → typed as `ClassVar[list[...]]`.
- **Rationale:** Aggregate gate cannot exit 0 without ruff clean. All fixes are either type-annotation cleanups (no runtime effect) or stylistic. Zero behavior change.
- **Commit:** `be38615`

**6. [Rule 3 - Blocking] mypy strict `no-any-return` on `embed_texts`.**

- **Found during:** Task 1 verify (mypy step).
- **Issue:** `self._model.encode(...)` returns `Any` (sentence_transformers types are unstubbed under mypy per existing `mypy.ini` config). Assigning the result and returning it as `np.ndarray` triggered mypy's `no-any-return` rule.
- **Fix:** Routed the result through `np.asarray(raw)` — which has a concrete `np.ndarray` return type in numpy's stubs — and added an explicit annotation on the local. No runtime effect.
- **Commit:** `be38615`

---

**Total deviations:** 6 auto-fixed (2 Rule 1 bugs in the plan or its deps, 1 Rule 1 bug in my own first draft, 1 Rule 2 missing-critical (grep fallback), 2 Rule 3 blockers (ruff + mypy)).

**Impact on plan:** All six fixes were necessary for the plan's own success criteria to pass (`bash scripts/lint_imports.sh exits 0`, `uv run pytest tests/rag -x -v` passes, 20 rag tests green). No scope creep.

## Authentication Gates

None. This plan is entirely local — no network calls (the `huggingface_hub.HfApi` dependency is stubbed in unit tests; actual first load will happen in Plan 02's ingest run where HF access is assumed ambient and cached).

## Deferred Issues

**1. `lancedb.table_names()` deprecation warning** — 20 test warnings during `pytest tests/rag/`, all pointing at the same line in `lance_schema.py`. API migration blocked by `list_tables()` return-type regression (see Deviation #2). Will revisit when lancedb fully removes `table_names()` (probably 0.32+); all callers of `open_or_create_table` are self-contained so the migration will be a one-line change.

**2. Real BGE-M3 end-to-end smoke test** — unit tests monkeypatch `SentenceTransformer` to avoid the 2GB download. A real load test against the actual model is out-of-scope for this plan; Plan 02's ingest pipeline is the natural forcing function (it will do a real first load, resolve `revision_sha`, and write it to `config/rag_retrievers.yaml`).

**3. Golden-query fixture set** — Plan 02-06 owns `tests/rag/golden_queries.jsonl` per CONTEXT.md; not a deliverable here.

## Known Stubs

None. Every symbol in the public surface has a real implementation:

- `chunk_markdown` really splits on headings and really returns `Chunk` instances.
- `BgeM3Embedder` has a real lazy-load path (`SentenceTransformer(..., revision=...)`) and a real HF hub revision resolver (`HfApi().model_info(...).sha`). Unit tests monkeypatch but production code is concrete.
- `CHUNK_SCHEMA` is a real pyarrow Schema with 8 real fields.
- `open_or_create_table` really creates / opens / schema-checks a LanceDB table.

The single `TODO(Plan 02+)` comment in lance_schema.py references a future API migration when lancedb removes `table_names()` — this is a forward-looking migration note, not a current stub. The current code works correctly.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 5 threats (T-02-01-01 through T-02-01-05) are covered as planned:

- **T-02-01-01 (Tampering — malformed markdown DoS):** Chunker operates on `str`, not `Path`; caller bounds input. No guard added beyond what's implicit in sentence-split regex (no catastrophic backtracking patterns).
- **T-02-01-02 (Tampering — untrusted `revision` string):** Accepted. Revision flows from git-tracked config, not user input.
- **T-02-01-03 (Info disclosure — HF download traffic):** Accepted. CI/dev trusts HF infra.
- **T-02-01-04 (EoP — rag→book_specifics import):** MITIGATED. Contract 1 now covers `book_pipeline.rag` in source_modules. The Phase 1 proof test in `tests/test_lint_rule_catches_violation.py` still injects a real violation every CI run — adding rag to the grep fallback (tests/test_import_contracts.py) extends the belt-and-suspenders coverage.
- **T-02-01-05 (DoS — schema drift):** MITIGATED. `open_or_create_table` raises `RuntimeError` on mismatch; `test_open_or_create_table_schema_mismatch_raises` asserts this on every test run.

## Verification Evidence

Plan `<success_criteria>` + task `<acceptance_criteria>`:

| Criterion                                                                                                                                           | Status | Evidence                                                                                                       |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------- |
| `book_pipeline.rag` module ships with chunker, embedder, schema, types                                                                              | PASS   | `src/book_pipeline/rag/{__init__,types,chunker,embedding,lance_schema}.py` all created                         |
| Import-linter contracts extended (BOTH contracts reference `book_pipeline.rag`)                                                                     | PASS   | `grep -c "book_pipeline.rag" pyproject.toml` → 4 (≥ 2 required); contract 1 source_modules + contract 2 forbidden_modules |
| `scripts/lint_imports.sh` mypy targets list includes `src/book_pipeline/rag`                                                                        | PASS   | `grep "src/book_pipeline/rag" scripts/lint_imports.sh` matches                                                 |
| `uv run python -c "from book_pipeline.rag import Chunk, chunk_markdown, BgeM3Embedder, CHUNK_SCHEMA, open_or_create_table, EMBEDDING_DIM; ..."` OK  | PASS   | exits 0; `assert EMBEDDING_DIM == 1024` green                                                                  |
| `uv run python -c "import book_pipeline.rag.types as t; assert 'book_specifics' not in open(t.__file__).read()"` OK (kernel boundary)               | PASS   | exits 0                                                                                                        |
| `CHUNK_SCHEMA` has `chapter` column (W-5)                                                                                                           | PASS   | `assert 'chapter' in [f.name for f in CHUNK_SCHEMA]` green                                                     |
| `bash scripts/lint_imports.sh` exits 0                                                                                                              | PASS   | "Contracts: 2 kept, 0 broken."; ruff clean; mypy: no issues in 56 files                                       |
| `uv run pytest tests/rag/ -x -v` passes                                                                                                             | PASS   | 20 passed (9 chunker + 6 embedding + 5 lance_schema)                                                           |
| Full suite still green                                                                                                                              | PASS   | 131 passed (was 111 pre-plan); no regressions                                                                  |

## Self-Check: PASSED

Artifact verification (files on disk):

- FOUND: `src/book_pipeline/rag/__init__.py`
- FOUND: `src/book_pipeline/rag/types.py` (Chunk class)
- FOUND: `src/book_pipeline/rag/chunker.py` (chunk_markdown)
- FOUND: `src/book_pipeline/rag/embedding.py` (BgeM3Embedder, EMBEDDING_DIM=1024)
- FOUND: `src/book_pipeline/rag/lance_schema.py` (CHUNK_SCHEMA, open_or_create_table)
- FOUND: `tests/rag/__init__.py`
- FOUND: `tests/rag/test_chunker.py` (9 tests)
- FOUND: `tests/rag/test_embedding.py` (6 tests)
- FOUND: `tests/rag/test_lance_schema.py` (5 tests)
- FOUND: `tests/rag/fixtures/mini_corpus.md` (3 H1 siblings)
- FOUND: `tests/rag/fixtures/chapter_corpus.md` (Chapter 3 fixture)
- FOUND: `pyproject.toml` contract 1 source_modules includes `book_pipeline.rag`; contract 2 forbidden_modules includes `book_pipeline.rag`
- FOUND: `scripts/lint_imports.sh` mypy target list includes `src/book_pipeline/rag`

Commit verification on `main` branch of `/home/admin/Source/our-lady-book-pipeline/`:

- FOUND: `8cd8169 test(02-01): add failing tests for rag kernel ...`
- FOUND: `be38615 feat(02-01): add book_pipeline.rag kernel ...`

Both per-task commits (RED + GREEN) landed on `main`. Aggregate gate + full test suite green.

## Next Plan Readiness

- **Plan 02-02 (corpus ingester) can start immediately.** All 6 kernel primitives are importable, typed, and schema-enforced. Plan 02-02 will:
    1. Resolve `CORPUS_ROOT` + iterate actual filenames (note per plan's `<corpus_notes>`: `book_specifics/corpus_paths.py` has stale filenames like `brief.md` vs real `our-lady-of-champion-brief.md` — Plan 02 reconciles).
    2. For each file, call `chunk_markdown(...)`, embed chunks in batches via `BgeM3Embedder.embed_texts`, route each chunk to the appropriate axis (5 LanceDB tables via `open_or_create_table`), and write rows matching CHUNK_SCHEMA.
    3. Fill `config/rag_retrievers.yaml`'s `model_revision: TBD-phase2` with `embedder.revision_sha`.
    4. Emit `event_type=ingestion_run` event with `{source_files[], chunk_counts_per_axis, embed_model_version, db_version, ingestion_run_id}` per CONTEXT.md.
- **No blockers.** Plan 02-01 closes.

---
*Phase: 02-corpus-ingestion-typed-rag*
*Plan: 01*
*Completed: 2026-04-22*
