---
phase: 02-corpus-ingestion-typed-rag
plan: 04
subsystem: rag-retrievers-arc-entity-outline
tags: [rag, retriever, entity-state, arc-position, outline-parser, beat-ids, rag-01, rag-02, b-1, b-2, w-2, w-5]
requirements_completed: [RAG-01, RAG-02]
dependency_graph:
  requires:
    - "02-01 (book_pipeline.rag — CHUNK_SCHEMA, open_or_create_table, BgeM3Embedder; arc_position reindex writes rows against CHUNK_SCHEMA)"
    - "02-02 (CorpusIngester — populates outline.md as plain chunks on the arc_position axis before reindex() overwrites with beat-ID-stable rows)"
    - "02-03 (LanceDBRetrieverBase + BgeReranker + retrievers/__init__.py sole-owned)"
    - "01-02 (book_pipeline.interfaces.retriever.Retriever Protocol + SceneRequest/RetrievalResult frozen shapes)"
  provides:
    - "book_pipeline.rag.outline_parser.parse_outline(text) -> list[Beat] — stable beat IDs ch{NN}_b{block}_beat{NN}"
    - "book_pipeline.rag.outline_parser.Beat — frozen+extra-forbid Pydantic model (beat_id/chapter/block/beat/title/body/heading_path)"
    - "book_pipeline.rag.retrievers.EntityStateRetriever — zero-cards-tolerant via inherited empty-table short-circuit"
    - "book_pipeline.rag.retrievers.ArcPositionRetriever — W-5 exact-equality chapter filter + B-2 state-in-init reindex"
    - "Lenient fallback parser for real OLoC outline's # ACT / ## BLOCK / ### Chapter format — each ### Chapter N becomes one beat under its ## BLOCK N"
  affects:
    - "Plan 02-05 (ContextPackBundler) can now consume exactly 5 Retriever instances: all imports from book_pipeline.rag.retrievers resolve to real classes; bundler is the event-emission site"
    - "Plan 02-06 (golden-query CI gate) references the shipped beat ID format for expected_chunks allowlists on the arc_position axis"
    - "Phase 4 scene-sequencer (CORPUS-02) consumes beat IDs for SceneRequest.beat_function references; RAG-02 stability contract is load-bearing here"
tech-stack:
  added: []  # No new runtime deps. outline_parser uses stdlib re + logging + the existing pydantic.
  patterns:
    - "Two-mode lenient outline parser: STRICT (synthetic plan format with ``# Chapter N:`` / ``## Block X:`` / ``### Beat N:``) + FALLBACK (real OLoC ``# ACT`` / ``## BLOCK`` / ``### Chapter``). Strict regexes are CASE-SENSITIVE so fallback ALL-CAPS patterns don't get shadowed. One state machine handles both — each regex set writes into the same (chapter/block/beat) state and a common flush function emits a Beat when a new heading is seen."
    - "Stable beat ID is keyed ENTIRELY on chapter/block/beat numbering (not on body/title text). Body mutations don't shift IDs — this is the RAG-02 load-bearing contract for SceneRequest.beat_function cross-references."
    - "Insertion-order dict last-wins dedupe on duplicate beat_ids with WARNING log (T-02-04-05 mitigation). Orphaned sections (heading with no enclosing parent) warn + skip, never raise."
    - "State-in-__init__ pattern for reindex: ArcPositionRetriever stores outline_path + ingestion_run_id at construction; reindex(self) -> None reads from self.* and matches the frozen Protocol signature exactly (B-2)."
    - "Exact-equality chapter filter via CHUNK_SCHEMA int column (W-5): _where_clause returns ``f\"chapter = {int(request.chapter)}\"`` with int() cast as belt-and-suspenders despite Pydantic typing. Eliminates the whole prefix-match class of bug (``Chapter 1`` leaking ``Chapter 10..19``)."
    - "arc_position reindex overwrites the full table: ``tbl.delete('true')`` + ``tbl.add(rows)``. Plan 02-02 ingester-populated rows (generic markdown chunks) are replaced with beat-ID-stable rows. Beat ID = chunk_id mapping guaranteed after reindex."
key-files:
  created:
    - "src/book_pipeline/rag/outline_parser.py (210 lines; parse_outline + Beat + strict/fallback regex sets + state-machine walker with dedupe warning)"
    - "src/book_pipeline/rag/retrievers/entity_state.py (44 lines; EntityStateRetriever; W-2 explicit kwargs; B-2 inherited zero-arg reindex)"
    - "src/book_pipeline/rag/retrievers/arc_position.py (92 lines; ArcPositionRetriever; state-in-__init__; B-2 override body; W-5 exact-equality _where_clause)"
    - "tests/rag/fixtures/mini_outline.md (3 ch x 2 block x 2 beat = 12 beats synthetic outline)"
    - "tests/rag/test_outline_parser.py (7 tests — 12-beat synthetic, stability, body-mutation, lenient missing, dedupe, real-OLoC canary, empty input)"
    - "tests/rag/test_entity_state_retriever.py (4 tests — zero-cards, populated+heading_path, Protocol, B-2 reindex sig)"
    - "tests/rag/test_arc_position_retriever.py (6 tests — reindex 12 rows + chapter ints, W-5 chapter=1 filter, W-5 chapter=99 empty, B-2 sig, Protocol, idempotency)"
  modified: []  # B-1 honored: retrievers/__init__.py NOT touched; pyproject.toml / scripts/lint_imports.sh / tests/test_import_contracts.py already covered rag/ subpackage from Plan 02-01.
key-decisions:
  - "(02-04) Two-mode parser (strict + fallback) with CASE-SENSITIVE strict regexes. Strict regexes are title-case literal (Chapter/Block/Beat) so the ALL-CAPS real outline (BLOCK/ACT) falls through cleanly to fallback. Alternative: regex on each line against all 4 patterns in parallel. Rejected because the dispatch order matters for some edge cases (## Block in synthetic must not be shadowed by fallback's ## BLOCK check; case-sensitivity is the cheapest way to thread both)."
  - "(02-04) Fallback mode maps each ``### Chapter N`` to a single beat (beat=1) under its enclosing ``## BLOCK N``. The real OLoC outline's 27 chapters across 9 blocks fit cleanly into this model — each CHAPTER is itself the beat-level unit in the Kat O'Keeffe method; there's no finer ### Beat heading. If Phase 4 needs finer beats inside each chapter (e.g., inciting / reversal / resolution sub-beats), the parser can be extended with a fourth regex without breaking existing beat_ids (they'd move under the chapter prefix)."
  - "(02-04) Beat ID schema survived the real outline: `ch{chapter:02d}_b{block_num}_beat{beat:02d}` works for both synthetic (block_num=a/b letters) and fallback (block_num=digit). Zero-padding ensures lex order matches numeric order (ch01 < ch10 < ch27)."
  - "(02-04) CorpusIngester still ingests outline.md as plain chunks per Plan 02-02's 5-axis router. ArcPositionRetriever.reindex() OVERWRITES the arc_position table with beat-ID-stable rows. No classmethod wrapper needed; Plan 06 CLI composes: construct the retriever with outline_path + embedder + reranker, call .reindex(). This matches B-2 exactly — no method-level args."
  - "(02-04) Pydantic Beat model is frozen + extra-forbid. Field equality then compares all fields cleanly in the stability test (parse twice -> a_by_id == b_by_id). This is tight coupling to Pydantic v2 equality semantics but it's exactly the contract we want — any future silent field addition or flip will fail the test."
  - "(02-04) W-5 filter string uses ``f\"chapter = {int(request.chapter)}\"``. int() cast is redundant with Pydantic's ``chapter: int`` typing; kept for defense-in-depth against a future code path that constructs SceneRequest without Pydantic validation. Same class as MetaphysicsRetriever's ``[a-z_]+`` injection guard."
metrics:
  duration_minutes: 12
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 7
  files_modified: 0
  tests_added: 17  # 7 Task 1 + 10 Task 2 = 17 new tests.
  tests_passing: 209
commits:
  - hash: 64e6e7d
    type: test
    summary: RED — failing tests for outline_parser (Task 1)
  - hash: 9a07e1c
    type: feat
    summary: GREEN — outline_parser with stable beat IDs (Task 1)
  - hash: 57f2606
    type: test
    summary: RED — failing tests for entity_state + arc_position retrievers (Task 2)
  - hash: 4691c48
    type: feat
    summary: GREEN — entity_state + arc_position retrievers (Task 2)
---

# Phase 2 Plan 4: Completes RAG-01/RAG-02 — entity_state + arc_position retrievers + outline_parser Summary

**One-liner:** The 2 remaining typed retrievers land — `EntityStateRetriever` (zero-cards-tolerant via inherited empty-table short-circuit; primary source pantheon + secondary-characters, secondary source Phase 4's `entity-state/`) and `ArcPositionRetriever` (state-in-`__init__` pattern, `reindex(self) -> None` matches frozen Protocol exactly, W-5 exact-equality filter on the `chapter` int column replacing the fragile prefix-match-on-heading-string approach) — alongside a two-mode lenient outline parser (`parse_outline` handles both the synthetic ``# Chapter N: / ## Block X: / ### Beat N:`` format expected by tests AND the real OLoC outline's ``# ACT / ## BLOCK / ### Chapter`` format via a case-sensitive strict-first fallback cascade), producing stable `ch{NN}_b{block}_beat{NN}` IDs that survive body-text edits (RAG-02), with 17 new tests (209 total green), `retrievers/__init__.py` NOT modified (B-1 honored — Plan 02-03's `importlib` + `contextlib.suppress(ImportError)` guards resolve to real classes once this plan's two source files exist), and the aggregate `bash scripts/lint_imports.sh` gate still exit-0 across 71 mypy source files.

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-22T07:28:14Z
- **Completed:** 2026-04-22T07:40:24Z
- **Tasks:** 2 (Task 1: outline_parser + stability tests; Task 2: 2 retrievers + Protocol/W-5/B-2 tests)
- **Files created:** 7
- **Files modified:** 0

## Accomplishments

- **RAG-01 fully shipped.** All 5 typed retrievers (`HistoricalRetriever`, `MetaphysicsRetriever`, `NegativeConstraintRetriever` from Plan 02-03 + `EntityStateRetriever`, `ArcPositionRetriever` from this plan) are importable from `book_pipeline.rag.retrievers` with `isinstance(r, Retriever) == True` for each; the runtime-checkable Protocol guard in `book_pipeline.interfaces.retriever` plus `inspect.signature(r.reindex).parameters == {}` assertions in each retriever test file prevent any future subclass from breaking B-2 conformance.
- **RAG-02 fully shipped.** `parse_outline(text)` produces stable beat IDs. Same-input re-parses yield identical `Beat` field sets (test 2); body-only mutations preserve every beat_id unchanged and only change the target beat's body (test 3). Real OLoC outline parses to 27 beats via the lenient fallback — the canary test asserts `len >= 20`, currently at 27 (full chapter coverage).
- **arc_position W-5 cemented.** `_where_clause` returns `f"chapter = {int(request.chapter)}"`; `chapter=1` retrieval returns only chapter-1 hits (test 2); `chapter=99` retrieval returns `hits=[]` (test 3 — proves no prefix-match false-positives leak across). `chapter` int column populated directly from `Beat.chapter` during reindex, not inferred from heading strings at query time.
- **entity_state zero-cards-tolerance guarantee backed by a dedicated test.** Empty table -> `RetrievalResult(retriever_name="entity_state", hits=[], bytes_used=0, query_fingerprint=<hash>)` — a non-raising, structurally-valid result that Phase 4's scene-sequencer entry path depends on when `entity-state/` is empty (zero-cards Phase 4 cold-start case, PITFALLS I-1 transient-entity mitigation).
- **B-1 file-ownership honored.** `git log src/book_pipeline/rag/retrievers/__init__.py` shows only Plan 02-03 commits (`4ea3dac`, `e7acc52`); Plan 02-04's commits (`64e6e7d`, `9a07e1c`, `57f2606`, `4691c48`) didn't touch it. The `importlib.import_module(...).Class` + `contextlib.suppress(ImportError)` dance Plan 02-03 set up resolves cleanly now that `entity_state.py` and `arc_position.py` exist.
- **Aggregate gate + full suite green.** `bash scripts/lint_imports.sh` exits 0 (2 import-linter contracts kept, ruff clean, mypy: no issues on 71 files — up from 68 pre-plan). `uv run pytest tests/ -q` passes 209 tests (was 192 pre-plan; +7 Task 1 + +10 Task 2 = 17 new).

## Task Commits

1. **Task 1 RED** — `64e6e7d` (test): 7 failing tests for outline_parser — 12-beat synthetic, stability across reparses, body-mutation preservation, lenient on missing Chapter heading, duplicate-ID last-wins + warning, real-OLoC canary, empty-input ValueError.
2. **Task 1 GREEN** — `9a07e1c` (feat): `src/book_pipeline/rag/outline_parser.py` + `tests/rag/fixtures/mini_outline.md` — two-mode case-sensitive parser (strict first, lenient fallback for real OLoC format); state-machine walker with WARNING-based dedupe.
3. **Task 2 RED** — `57f2606` (test): 10 failing tests — 4 entity_state (zero-cards, populated+heading_path, Protocol, reindex sig) + 6 arc_position (reindex 12 rows + chapter ints, W-5 chapter=1, W-5 chapter=99, B-2 reindex sig, Protocol, idempotency).
4. **Task 2 GREEN** — `4691c48` (feat): EntityStateRetriever + ArcPositionRetriever. B-1 honored: `retrievers/__init__.py` unchanged.

**Plan metadata commit** follows this SUMMARY in a separate `docs(02-04): complete RAG-01/RAG-02 plan` commit.

## Beat ID format shipped (for Plan 02-05 bundler + Plan 02-06 golden-query references)

`ch{chapter:02d}_b{block_id}_beat{beat:02d}` where:

- `chapter` is the `# Chapter N` (strict) or `### Chapter N` (fallback) integer, zero-padded to 2 digits.
- `block_id` is:
    - **Strict mode:** the `## Block X:` identifier lowercased + alphanumerics-only (e.g. `## Block A:` -> `a`; `## Block B:` -> `b`).
    - **Fallback mode:** the `## BLOCK N —` integer as a digit string (e.g. `## BLOCK 1` -> `1`; `## BLOCK 9` -> `9`).
- `beat` is the `### Beat N` (strict) integer, zero-padded; in fallback mode every `### Chapter N` becomes beat=1.

Examples (synthetic): `ch01_ba_beat01`, `ch02_bb_beat02`, `ch03_ba_beat01`.
Examples (real OLoC fallback): `ch01_b1_beat01` (Chapter 1 under BLOCK 1), `ch07_b3_beat01` (Chapter 7 under BLOCK 3), `ch27_b9_beat01` (Chapter 27 under BLOCK 9).

Stability rule: ID is determined **entirely** by chapter/block/beat numbering. Body-text edits, title edits, and any non-heading prose mutations do NOT shift IDs. Re-parse the same input -> identical ID set with identical `Beat` fields (proven by `test_parse_outline_is_stable_across_reparses`).

**Consumer note for Plan 02-06:** expected_chunks allowlists for the arc_position axis should reference beat_ids directly. Since reindex() overwrites the table on every call, the chunk_id IS the beat_id — no indirection through heading_path or source_file required.

## W-5 chapter filter — arc_position pattern (Plan 02-06 golden queries)

```python
def _where_clause(self, request: SceneRequest) -> str | None:
    return f"chapter = {int(request.chapter)}"
```

`chapter` is a `pa.int64()` nullable column in CHUNK_SCHEMA (Plan 02-01). ArcPositionRetriever.reindex() populates it directly from `Beat.chapter`, so every arc_position row has a non-null int chapter. Exact-equality vs an int — no prefix-match semantics, no `LIKE`, no string handling. Golden queries should assume this semantic: chapter-N request returns rows with metadata.chapter == N; chapter-99 (nonexistent) returns empty.

No other retriever uses the chapter filter at this phase. Plan 02-06 CI should include at least one arc_position golden query with `chapter` set to each act's mid-chapter (e.g., 5 in Act 1, 14 in Act 2, 22 in Act 3) to baseline the filter's correctness.

## Test 6 (real OLoC outline parse) — PASSED

`test_parse_outline_real_oloc_canary` ran against `~/Source/our-lady-of-champion/our-lady-of-champion-outline.md` and **parsed 27 beats cleanly** via the fallback mode. No skip needed on this machine.

The real outline uses the `# ACT N — TITLE` / `## BLOCK N — TITLE` / `### Chapter N — TITLE` format (Kat O'Keeffe's 3 Act / 9 Block / 27 Chapter method). Since this is NOT the synthetic plan-assumed format (`# Chapter N:` / `## Block X:` / `### Beat N:`), the parser's **fallback** mode activates:

- Each `## BLOCK N` sets the enclosing block context (with block_id = `N`).
- Each `### Chapter N` becomes a single beat (beat=1) under that block, with chapter=N.
- `# ACT N` headings are IGNORED for beat-id purposes (Act is purely organizational; Block numbering is globally unique 1..9 across the 3 Acts).

The canary test threshold is `len >= 20` so minor future edits to the outline don't fail CI; current observed value is 27 (full chapter coverage).

## Decision: CorpusIngester + ArcPositionRetriever.reindex split (Plan 06 CLI shape)

- **CorpusIngester (Plan 02-02)** ingests outline.md as plain markdown chunks routed to the `arc_position` axis by the 5-axis filename router. The ingester uses the generic `chunk_markdown` function — NOT beat-aware.
- **ArcPositionRetriever.reindex()** (shipped in this plan) OVERWRITES the `arc_position` table with beat-ID-stable rows via `tbl.delete("true")` + `tbl.add(rows)`. Every call re-parses the outline and re-embeds (cheap at 12 beats synthetic / 27 beats real).
- **Plan 06 CLI expected sequence** (per the `book-pipeline ingest` subcommand, not shipped here):
    1. `CorpusIngester.ingest(indexes_dir, force=...)` runs — writes ingester-generic arc_position rows + 4 other axis tables.
    2. `ArcPositionRetriever(db_path=indexes_dir, outline_path=CORPUS_ROOT/"our-lady-of-champion-outline.md", embedder=shared_embedder, reranker=shared_reranker, ingestion_run_id=ingester.last_run_id)` is constructed.
    3. `retriever.reindex()` (no args, B-2) is called, overwriting arc_position rows with beat-ID-stable versions.

No `classmethod` workaround, no method-level args, no state-threading through the Protocol: the construction site provides outline_path; the method signature stays `reindex(self) -> None`. B-2 clean.

## B-1 file-ownership decision (Plan 03 owns retrievers/__init__.py)

Verification:
```bash
$ git log --oneline --all -- src/book_pipeline/rag/retrievers/__init__.py
4ea3dac feat(02-03): GREEN — historical + metaphysics + negative_constraint retrievers + B-1 sole-owned __init__.py (Task 2)
e7acc52 feat(02-03): GREEN — BgeReranker + LanceDBRetrieverBase shared retriever machinery (Task 1)
```

Only Plan 02-03 commits touched `retrievers/__init__.py`. Plan 02-04's 4 commits (`64e6e7d`, `9a07e1c`, `57f2606`, `4691c48`) did NOT modify it. Plan 02-03's `importlib.import_module("book_pipeline.rag.retrievers.entity_state").EntityStateRetriever` + `contextlib.suppress(ImportError)` guard now resolves to the real class (verified by `from book_pipeline.rag.retrievers import EntityStateRetriever, ArcPositionRetriever` exiting 0 with both attributes non-None).

## B-2 reindex signature conformance — all 5 retrievers

Verified by `inspect.signature(r.reindex).parameters`:

| Retriever | parameters (excl self) |
|---|---|
| HistoricalRetriever | `{}` (inherited) |
| MetaphysicsRetriever | `{}` (inherited) |
| NegativeConstraintRetriever | `{}` (inherited) |
| EntityStateRetriever | `{}` (inherited — B-2) |
| ArcPositionRetriever | `{}` (overridden, same signature — B-2) |

All runtime `isinstance(r, Retriever)` checks pass. No classmethod workarounds, no positional-splat forwarding, no extra method-level args.

## Files Created/Modified

### Created

- `src/book_pipeline/rag/outline_parser.py` — parse_outline + Beat + strict/fallback regex cascade.
- `src/book_pipeline/rag/retrievers/entity_state.py` — EntityStateRetriever (zero-cards-tolerant).
- `src/book_pipeline/rag/retrievers/arc_position.py` — ArcPositionRetriever (state-in-init + W-5 + B-2).
- `tests/rag/fixtures/mini_outline.md` — 3 ch x 2 block x 2 beat synthetic outline (12 beats).
- `tests/rag/test_outline_parser.py` — 7 tests.
- `tests/rag/test_entity_state_retriever.py` — 4 tests.
- `tests/rag/test_arc_position_retriever.py` — 6 tests.
- `.planning/phases/02-corpus-ingestion-typed-rag/02-04-SUMMARY.md` — this file.

### Modified

None. B-1 honored: `retrievers/__init__.py` was NOT modified. Plan 02-01 already extended `pyproject.toml` / `scripts/lint_imports.sh` / `tests/test_import_contracts.py` for `src/book_pipeline/rag`; the new `outline_parser.py` + `retrievers/{entity_state,arc_position}.py` sit under that umbrella and need no fresh cross-cutting changes.

## Decisions Made

See frontmatter `key-decisions` — will be extracted to STATE.md by the state-update step. Summary:

1. Two-mode parser (strict case-sensitive + lenient ALL-CAPS fallback). Both modes write into the same state machine.
2. Fallback maps `### Chapter N` under `## BLOCK N` to a single beat=1 entry. Real OLoC parses cleanly to 27 beats.
3. Beat ID schema `ch{chapter:02d}_b{block_id}_beat{beat:02d}` works for both synthetic (letter) and fallback (digit) block_ids. Zero-padding ensures lex order matches numeric.
4. CorpusIngester + ArcPositionRetriever.reindex split — ingester is generic; retriever overwrites arc_position with beat-ID-stable rows after ingest. Plan 06 CLI composes. No classmethod needed.
5. Pydantic Beat is frozen + extra-forbid. Equality compares all fields cleanly — the stability test's `a_by_id == b_by_id` assertion relies on this.
6. W-5 filter uses `int(request.chapter)` cast for defense-in-depth despite Pydantic typing. Same class as MetaphysicsRetriever's `[a-z_]+` injection guard.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in plan's literal grep acceptance criterion] Plan's `grep -c "heading_path LIKE" src/book_pipeline/rag/retrievers/arc_position.py == 0` required zero matches, but my initial docstring and inline comment referenced the literal substring `heading_path LIKE` when EXPLAINING what was being REPLACED by the W-5 fix.**

- **Found during:** Task 2 GREEN acceptance criteria verification pass.
- **Issue:** Docstring line `` `heading_path LIKE 'Chapter N %'` matcher from the original plan`` and inline comment `from the plan's original heading_path LIKE approach` both matched the plan's zero-occurrences grep guard. Semantically correct prose, grep-failing.
- **Fix:** Rewrote both mentions: docstring → `prefix-match-on-heading-string approach`; inline comment → `heading-path-prefix approach`. Same meaning, no literal `heading_path LIKE` substring. `grep -c` now returns 0.
- **Rationale:** Substring-level grep guards in plans are belt-and-suspenders next to what actually matters (no runtime LIKE clause — which was always the case in my implementation; `_where_clause` returns exact-equality SQL). Plan 02-03 hit the same class of issue 4 times with `*args` / `super().__init__(name=` / `EventLogger` docstrings and resolved the same way.
- **Files modified:** `src/book_pipeline/rag/retrievers/arc_position.py` (2 docstring/comment lines).
- **Committed in:** `4691c48` (Task 2 GREEN).

**2. [Rule 2 - Missing critical functionality] Kernel grep-fallback test (`test_kernel_does_not_import_book_specifics`) failed on the literal substring `book_specifics` in entity_state.py docstring.**

- **Found during:** Task 2 GREEN full-suite verify (`uv run pytest tests/ -q`).
- **Issue:** My initial entity_state.py docstring had the line `routed to entity_state by the book_specifics/corpus_paths.CORPUS_FILES map in Plan 02-02`. The Phase 1 grep-fallback test scans all kernel files for the literal substring "book_specifics" and asserts zero hits (except for `cli/ingest.py` which has a documented composition-seam exemption). My docstring introduced a drift risk into the substring belt — not because `entity_state.py` imports anything from book_specifics (it doesn't), but because the test can't distinguish a prose mention from a hidden import.
- **Fix:** Rewrote the docstring line to `routed to entity_state by the book-specific corpus-paths axis map established in Plan 02-02`. Same meaning, no literal `book_specifics` substring. Test passes.
- **Rationale:** Same class as Plan 02-01 Deviation #4 (rewrote `rag/__init__.py` docstring to avoid the `book_specifics` literal) and Plan 02-02 Deviation #4 (rewrote 3 corpus_ingest docstrings). Following the established precedent: prose about the boundary uses hyphenated phrasing ("book-specific"); underscored `book_specifics` refers only to the actual package, and only `cli/ingest.py` gets the documented exemption.
- **Files modified:** `src/book_pipeline/rag/retrievers/entity_state.py` (1 docstring line).
- **Committed in:** `4691c48` (Task 2 GREEN).

**3. [Rule 3 - Blocking] Ruff I001 + RUF002 violations on test files blocking the aggregate gate.**

- **Found during:** Task 1 GREEN verify (`bash scripts/lint_imports.sh`) and Task 2 GREEN verify (after landing entity_state/arc_position tests).
- **Issues:**
    - `tests/rag/test_outline_parser.py` had I001 (unsorted imports) and RUF002 (`×` MULTIPLICATION SIGN in docstring — ruff flags as ambiguous with `x`).
    - `tests/rag/test_entity_state_retriever.py` + `tests/rag/test_arc_position_retriever.py` had I001 (blank line between `__future__` and subsequent imports).
- **Fix:**
    - `uv run ruff check --fix` auto-resolved I001 across all three files (removed stray blank lines between import blocks).
    - Manually replaced `×` → `x` in test_outline_parser.py docstring (`3-chapter × 2-block × 2-beat` → `3-chapter x 2-block x 2-beat`). Test outcomes unchanged.
- **Rationale:** Aggregate gate cannot exit 0 without ruff clean. All fixes are docstring/imports only — zero behavior change.
- **Files modified:** 3 test files.
- **Committed in:** `9a07e1c` (Task 1 GREEN) + `4691c48` (Task 2 GREEN).

**4. [Rule 1 - Bug in my first draft] Strict regex CASE-INSENSITIVITY was shadowing the fallback path on the real OLoC outline.**

- **Found during:** Task 1 GREEN verify first run (6/7 tests passed; real-OLoC canary failed).
- **Issue:** My initial `_STRICT_BLOCK_RE` / `_STRICT_BEAT_RE` / `_STRICT_CHAPTER_RE` had `re.IGNORECASE`, so `## BLOCK 1 — Beginning` (from the real outline) matched strict block regex, and the strict-flow then saw no enclosing `# Chapter` and warned-and-skipped. `### Chapter 7 — Pressure` then had no open block context and was also skipped. Result: 0 beats extracted from the real outline.
- **Fix:** Removed `re.IGNORECASE` from the three strict regexes. Title-case `Chapter/Block/Beat` remains matched by strict; ALL-CAPS `CHAPTER/BLOCK` now falls through to the fallback regexes (which are case-sensitive to ALL-CAPS). Two-mode parsing works as intended.
- **Rationale:** Strict and fallback formats have distinct case patterns (synthetic is title-case, real is ALL-CAPS for block/act), so case-sensitivity is the cheapest signal to distinguish them. Documented in the module docstring + inline comment.
- **Files modified:** `src/book_pipeline/rag/outline_parser.py`.
- **Committed in:** `9a07e1c` (Task 1 GREEN).

---

**Total deviations:** 4 auto-fixed — 1 Rule 1 bug in my first parser draft, 1 Rule 2 missing critical (grep-fallback substring), 1 Rule 3 blocking (ruff cleanup), 1 Rule 1 "plan's grep acceptance criterion required a specific substring that my textually-equivalent phrasing didn't match" (W-5 LIKE reference in docstring).

**Impact on plan:** All 4 fixes were necessary to reach the plan's own `<success_criteria>` + `<acceptance_criteria>`. No scope creep. Deviation #4 was semantic — the fallback design was the right answer all along; the regex case-sensitivity was the specific fix that enabled it.

## Authentication Gates

None. All work is local — the tests use `_FakeEmbedder` + `_FakeReranker` (no model download), the real outline is read from `~/Source/our-lady-of-champion/` (read-only local filesystem), no HF / LanceDB cloud / Anthropic calls.

## Deferred Issues

1. **Real BGE-M3 end-to-end smoke test** — inherited from Plans 02-01/02-02/02-03. ArcPositionRetriever.reindex() with a real embedder + 12 beats is fast enough to add to a Plan 02-06 integration test; deferred here only to keep CI purely local-fake.
2. **`lancedb.table_names()` deprecation warnings** — inherited. 156 warnings in full test run, no functional impact; migration path is still a single-line change when lancedb fully removes `table_names()`.
3. **Outline format evolution** — the real OLoC outline uses `— ` (em dash) as the heading separator. My regexes accept `:`, `-`, `—` as separators, so a format switch to `–` (en dash) or `:` would still parse. The canary test at `len >= 20` catches drastic format drift; finer drift (e.g., a hypothetical `#### Beat N — Sub-beat` inside each Chapter) is not yet supported and would require a 4th regex in the cascade.

## Known Stubs

None. Every public surface has a real implementation:

- `parse_outline` really walks the text, really emits Beats, really logs warnings on malformed sections.
- `EntityStateRetriever` / `ArcPositionRetriever` really subclass `LanceDBRetrieverBase` and really hit the real LanceDB table via `open_or_create_table`. Test doubles for the embedder / reranker are scoped to each test file (prefixed `_Fake`).
- `ArcPositionRetriever.reindex` really calls `parse_outline(self.outline_path.read_text())`, really deletes the existing arc_position table, really re-embeds + re-inserts.
- The `Beat` Pydantic model is frozen + extra-forbid — real validation, not a dataclass stub.

The only TODO in the codebase touched by this plan is the inherited `lancedb.table_names()` deprecation comment in `lance_schema.py` — forward-looking migration note, not a current stub.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 6 threats covered as planned:

- **T-02-04-01** (W-5 f-string chapter interpolation): MITIGATED. `int(request.chapter)` cast + Pydantic's `chapter: int` typing = double-guarded. Exact-equality on typed int column eliminates the prefix-match class of bug.
- **T-02-04-02** (parse_outline DoS on huge outline): ACCEPTED. Outline is ~20KB; single-pass line walk; bounded small input.
- **T-02-04-03** (reindex writes to LanceDB without emitting an event): ACCEPTED. Per Retriever Protocol docstring, reindex is not an event-emission site. Plan 05 bundler / Plan 06 CLI is.
- **T-02-04-04** (beat bodies carry spoilers into RetrievalResult): ACCEPTED. Internal pipeline; no public exposure.
- **T-02-04-05** (silent dedupe on duplicate beat_ids): MITIGATED. Parser logs WARNING via `logger.warning(...)`; `test_parse_outline_deduplicates_duplicate_beat_ids_last_wins` asserts the warning + last-wins semantics.
- **T-02-04-06** (reindex args breaking Protocol conformance): MITIGATED. `test_arc_position_reindex_has_no_extra_args` asserts `inspect.signature(r.reindex).parameters` is empty; `test_arc_position_satisfies_retriever_protocol` re-checks via runtime `isinstance(r, Retriever)`. Same pair of tests exist for the other 4 retrievers (Plan 02-03 added 3; this plan adds 2).

## Verification Evidence

Plan `<success_criteria>` + `<verification>` coverage:

| Criterion | Status | Evidence |
|---|---|---|
| RAG-01: 5 typed retrievers importable from `book_pipeline.rag.retrievers` | PASS | `from book_pipeline.rag.retrievers import HistoricalRetriever, MetaphysicsRetriever, EntityStateRetriever, ArcPositionRetriever, NegativeConstraintRetriever` exits 0 + all non-None |
| RAG-02: outline parsed into arc_position with stable beat IDs | PASS | test_parse_outline_mini_produces_12_beats_with_stable_ids + test_arc_position_reindex_populates_12_rows_with_stable_beat_ids |
| entity_state zero-cards-tolerance | PASS | test_entity_state_empty_table_returns_empty_result |
| No retriever emits EventLogger events | PASS | `grep -c "EventLogger\|\.emit(" src/book_pipeline/rag/retrievers/entity_state.py src/book_pipeline/rag/retrievers/arc_position.py src/book_pipeline/rag/outline_parser.py` → 0 per file |
| parse_outline idempotent (same input -> same beat_ids) | PASS | test_parse_outline_is_stable_across_reparses + test_arc_position_reindex_is_idempotent |
| B-1: retrievers/__init__.py unchanged by Plan 04 | PASS | `git log --oneline --all -- src/book_pipeline/rag/retrievers/__init__.py` shows only Plan 02-03 commits (`4ea3dac`, `e7acc52`) |
| B-2: reindex(self) -> None on all 5 subclasses | PASS | `inspect.signature(ArcPositionRetriever.reindex).parameters == ['self']`; Protocol isinstance passes for all 5 |
| W-5: arc_position filters by `chapter = {int}` exact equality | PASS | `grep "chapter = {int(request.chapter)}" src/book_pipeline/rag/retrievers/arc_position.py` matches; `grep -c "heading_path LIKE"` → 0; test_arc_position_retrieve_filters_by_chapter_exact_equality + test_arc_position_retrieve_chapter_99_returns_no_hits |
| W-2: explicit-kwarg forwarding | PASS | `grep "super().__init__(name=" src/book_pipeline/rag/retrievers/entity_state.py src/book_pipeline/rag/retrievers/arc_position.py` matches once per file (2 total) |
| `grep "PITFALLS\|02-CONTEXT" ...` matches for each new retriever | PASS | entity_state.py mentions 02-CONTEXT + PITFALLS I-1; arc_position.py mentions RAG-02 + W-5 |
| `grep -c "classmethod" src/book_pipeline/rag/retrievers/arc_position.py` == 0 | PASS | 0 (no classmethod workarounds) |
| `bash scripts/lint_imports.sh` exits 0 | PASS | "Contracts: 2 kept, 0 broken." + ruff clean + mypy 71 source files clean |
| All tests pass | PASS | 209/209 (was 192 pre-plan; +17 added) |

## Self-Check: PASSED

Artifact verification (files on disk):

- FOUND: `src/book_pipeline/rag/outline_parser.py`
- FOUND: `src/book_pipeline/rag/retrievers/entity_state.py`
- FOUND: `src/book_pipeline/rag/retrievers/arc_position.py`
- FOUND: `tests/rag/fixtures/mini_outline.md`
- FOUND: `tests/rag/test_outline_parser.py`
- FOUND: `tests/rag/test_entity_state_retriever.py`
- FOUND: `tests/rag/test_arc_position_retriever.py`

Commit verification on `main` branch of `/home/admin/Source/our-lady-book-pipeline/`:

- FOUND: `64e6e7d test(02-04): RED — failing tests for outline_parser (Task 1)`
- FOUND: `9a07e1c feat(02-04): GREEN — outline_parser with stable beat IDs (Task 1)`
- FOUND: `57f2606 test(02-04): RED — failing tests for entity_state + arc_position retrievers (Task 2)`
- FOUND: `4691c48 feat(02-04): GREEN — entity_state + arc_position retrievers (Task 2)`

All four per-task commits (2 RED + 2 GREEN, per TDD) landed on `main`. Aggregate gate + full test suite green. retrievers/__init__.py NOT modified by this plan (B-1 honored).

## Next Plan Readiness

- **Plan 02-05 (ContextPackBundler + negative_constraint assembly-time filter) can start immediately.** All 5 concrete retrievers are importable; the runtime-checkable Protocol guard is in place for each; the candidate_k=50 → final_k=8 pipeline is cemented. Bundler's 40KB ContextPack cap math (8 hits per axis × 5 axes = 40 hits max) is directly supported by the current retriever surface.
- **Plan 02-06 (RAG-04 golden-query CI gate) can baseline against:**
    - Query-text shapes documented in Plan 02-03's SUMMARY for the 3 retrievers + `EntityStateRetriever._build_query_text` (POV + location + date + beat context) + `ArcPositionRetriever._build_query_text` (chapter + beat_function + POV + location).
    - Beat ID format `ch{NN}_b{block}_beat{NN}` (both letter and digit variants) for expected_chunks allowlists on the arc_position axis.
    - W-5 chapter-exact-equality filter semantics — golden queries can depend on returning ONLY chapter-N rows when SceneRequest.chapter=N.
- **RAG-01 fully closed.** RAG-02 fully closed. Both move to complete on REQUIREMENTS.md.
- **No blockers.**

---
*Phase: 02-corpus-ingestion-typed-rag*
*Plan: 04*
*Completed: 2026-04-22*
