---
phase: 02-corpus-ingestion-typed-rag
plan: 03
subsystem: rag-retrievers
tags: [rag, retriever, lancedb, reranker, bge, protocol, pitfalls-r4, pitfalls-r5, b-1, b-2, w-2]
requirements_completed: [RAG-01]  # 3 of 5 retrievers land here; Plan 02-04 lands the other 2 (entity_state + arc_position) to complete RAG-01 fully.
dependency_graph:
  requires:
    - "02-01 (book_pipeline.rag — CHUNK_SCHEMA, open_or_create_table, BgeM3Embedder; base.py consumes open_or_create_table + uses BgeM3Embedder + reranker outputs)"
    - "02-02 (CorpusIngester — populates the 5 LanceDB tables these retrievers read from)"
    - "01-02 (book_pipeline.interfaces.retriever.Retriever Protocol + SceneRequest/RetrievalResult/RetrievalHit shapes, FROZEN)"
    - "01-05 (book_pipeline.observability.hashing.hash_text — used for query_fingerprint + index_fingerprint)"
  provides:
    - "book_pipeline.rag.reranker.BgeReranker — lazy cross-encoder wrapper (BAAI/bge-reranker-v2-m3; top-50 -> top-8 per axis)"
    - "book_pipeline.rag.retrievers.base.LanceDBRetrieverBase — shared retriever machinery (query embed -> top-50 vector search -> rerank -> top-8; empty-table tolerance; frozen B-2 reindex(self) -> None signature)"
    - "book_pipeline.rag.retrievers.HistoricalRetriever — axis='historical'; POV + date + location + beat_function query shape; no filter"
    - "book_pipeline.rag.retrievers.MetaphysicsRetriever — axis='metaphysics'; PITFALLS R-4 rule_type='rule' default filter with injection-guarded regex; widen via include_rule_types kwarg"
    - "book_pipeline.rag.retrievers.NegativeConstraintRetriever — axis='negative_constraint'; PITFALLS R-5 deliberate no-filter; bundler filters at assembly (Plan 02-05)"
    - "book_pipeline.rag.retrievers.__init__.py — B-1 sole-owned; pre-declares all 5 retriever symbols; Plan 02-04's entity_state + arc_position loaded via contextlib.suppress(ImportError) over importlib.import_module"
    - "W-2 explicit-kwargs retriever __init__ pattern as the template for Plan 02-04's ArcPositionRetriever + EntityStateRetriever"
  affects:
    - "Plan 02-04 (entity_state + arc_position retrievers): creates the 2 Plan-04 source files under src/book_pipeline/rag/retrievers/; does NOT modify __init__.py (B-1 contract). Inherits LanceDBRetrieverBase; keeps reindex(self) -> None signature (B-2)."
    - "Plan 02-05 (ContextPackBundler + negative_constraint assembly-time filter): consumes all 5 Retriever instances; Bundler emits ONE Event per bundle() call carrying per-axis RetrievalResult. Bundler is the event-emission site — retrievers never emit events."
    - "Plan 02-06 (RAG-04 golden-query CI gate): authors expected_chunks allowlists against the query_text shapes documented here; the top-50 -> top-8 pipeline is the assumed retrieval contract."
tech-stack:
  added:
    - "sentence_transformers.CrossEncoder (BgeReranker) — wraps the BAAI/bge-reranker-v2-m3 cross-encoder; lazy load mirrors BgeM3Embedder pattern from 02-01"
  patterns:
    - "LanceDBRetrieverBase two-hook subclass template: `_build_query_text(request)` (required) + `_where_clause(request)` (optional, default returns None). All 5 typed retrievers use this shape; Plan 02-04's ArcPositionRetriever overrides the `reindex` method body (not signature) to re-parse outline.md from state stored on self."
    - "W-2 explicit-kwargs retriever __init__: `def __init__(self, *, db_path, embedder, reranker, **kw)` with `super().__init__(name=\"axis\", db_path=db_path, embedder=embedder, reranker=reranker, **kw)`. NO positional-splat forwarding. Python raises SyntaxError for `super().__init__(name=..., *args, **kwargs)` anyway; even if it parsed, splat forwarding silently misroutes positional args."
    - "B-2 frozen Protocol signature: `reindex(self) -> None` with NO extra args. Axis-specific reindex state (e.g., ArcPositionRetriever's outline_path) is stored on `self` at `__init__` time and read during reindex(). Runtime-checkable Protocol isinstance passes for every subclass."
    - "B-1 sole-ownership of __init__.py: Plan 02-03 pre-declares all 5 retriever symbols via `importlib.import_module` + `contextlib.suppress(ImportError)` (dynamic import bypasses mypy's static can't-find-module complaints before Plan 02-04 lands). Plan 02-04 creates the 2 new source files but never touches __init__.py."
    - "Empty-table tolerance: every retrieve() call first checks `table.count_rows() == 0` and short-circuits to RetrievalResult(hits=[], bytes_used=0, ...) with a still-valid query_fingerprint. This is the entity_state zero-cards-tolerance guarantee from 02-CONTEXT.md applied as a general safety net for all 5 axes."
    - "candidate_k=50 -> final_k=8 pipeline: LanceDB vector search returns top-50 candidates; BgeReranker re-scores with cross-encoder; top-8 returned. Plan 02-05 bundler assumes 8-hits-per-axis inputs when sizing against the 40KB ContextPack ceiling."
    - "Metadata carrier shape: every RetrievalHit.metadata dict carries {rule_type, heading_path, ingestion_run_id, chapter, vector_distance}. Downstream: bundler uses rule_type + chapter for introspection; ingestion_run_id for cache keys; vector_distance for relative confidence signal."
    - "SQL-injection defense (defense in depth): MetaphysicsRetriever validates include_rule_types against `[a-z_]+` full-match via regex before embedding into the IN-clause. Today's callers are all trusted, but the guard prevents a future code path from accidentally leaking unsanitized input into the where clause."
    - "retrievers never log observability events (Protocol docstring contract): grep guard `EventLogger|\\.emit(` over src/book_pipeline/rag/retrievers/ + reranker.py returns 0 matches. Plan 02-05's bundler is the event-emission site; if a retriever ever started emitting its own event the bundle event stream would double-count — the grep guard + the bundler's exactly-one-event-per-bundle() test (coming in Plan 02-05) catch this together."
key-files:
  created:
    - "src/book_pipeline/rag/reranker.py (83 lines; BgeReranker with lazy CrossEncoder + top-K sort + non-mutating rerank + zero-load empty-candidates short circuit)"
    - "src/book_pipeline/rag/retrievers/__init__.py (56 lines; B-1 sole-owned 5-retriever surface; importlib + contextlib.suppress(ImportError) for Plan 02-04's forthcoming files)"
    - "src/book_pipeline/rag/retrievers/base.py (178 lines; LanceDBRetrieverBase + two subclass hooks + B-2 reindex + index_fingerprint with empty sentinel)"
    - "src/book_pipeline/rag/retrievers/historical.py (44 lines; HistoricalRetriever subclass; W-2 kwargs pattern)"
    - "src/book_pipeline/rag/retrievers/metaphysics.py (75 lines; MetaphysicsRetriever with R-4 rule_type filter + include_rule_types injection guard)"
    - "src/book_pipeline/rag/retrievers/negative_constraint.py (52 lines; NegativeConstraintRetriever with R-5 deliberate-no-filter)"
    - "tests/rag/test_reranker.py (137 lines; 4 tests — empty-zero-load, top-K sort, oversized top_k, non-mutation)"
    - "tests/rag/test_retriever_base.py (290 lines; 8 tests — empty-tolerance, metadata shape, query_fingerprint stability, index_fingerprint distinctness + empty sentinel, where_clause hook, B-2 signature, Protocol runtime check)"
    - "tests/rag/test_historical_retriever.py (139 lines; 4 tests — name, populated result, B-2 Protocol, reindex signature)"
    - "tests/rag/test_metaphysics_retriever.py (157 lines; 5 tests — default rule-only filter, include_rule_types widening, _where_clause SQL IN shape, injection guard ValueError, B-2 Protocol)"
    - "tests/rag/test_negative_constraint_retriever.py (148 lines; 4 tests — R-5 _where_clause-is-None invariant across 2 requests, top-K-regardless, query_fingerprint stability, B-2 Protocol)"
  modified: []  # Plan 02-03 adds the retrievers subpackage wholesale; no cross-cutting pyproject / lint changes needed because `src/book_pipeline/rag` was already covered by Phase 2 Plan 01's import-linter contract 1 source_modules + contract 2 forbidden_modules entries + scripts/lint_imports.sh mypy target list.
key-decisions:
  - "(02-03) B-1 sole ownership of retrievers/__init__.py: Plan 02-03 owns the file exclusively. All 5 imports pre-declared; Plan 02-04's entity_state + arc_position loaded via importlib.import_module inside contextlib.suppress(ImportError). Rationale: eliminates the Wave 3 file-ownership conflict the plan's earlier revision had. Dynamic-import was needed because static `try/except from X import Y` tripped mypy's import-untyped false positive once the mypy scope included src/book_pipeline/rag/retrievers."
  - "(02-03) B-2 frozen Protocol signature for reindex(self) -> None: every concrete retriever inherits this from LanceDBRetrieverBase unchanged. Any axis-specific reindex state (Plan 02-04's ArcPositionRetriever outline_path, embedder handle, ingestion_run_id) is stored on `self` at `__init__` time and read from `self.*` during reindex(). Runtime-checkable isinstance(r, Retriever) passes — verified by a dedicated test in each retriever test file AND a `inspect.signature(r.reindex).parameters` emptiness test."
  - "(02-03) W-2 explicit-kwargs retriever __init__ pattern (NOT *args forwarding): `def __init__(self, *, db_path, embedder, reranker, **kw) -> None: super().__init__(name=\"axis\", db_path=db_path, embedder=embedder, reranker=reranker, **kw)`. Rationale: `super().__init__(name=..., *args, **kwargs)` is a Python SyntaxError; even if it parsed, positional-splat forwarding silently misroutes args. Explicit-kwargs surfaces misuse immediately. Pattern is the template Plan 02-04's two retrievers MUST follow."
  - "(02-03) candidate_k=50 -> final_k=8 pipeline cemented here. Plan 02-05 bundler assumes 8 hits per axis × 5 axes = 40 hits max for its 40KB cap calculation. final_k default is an __init__ param on LanceDBRetrieverBase for future tuning without API break."
  - "(02-03) Dynamic importlib over static try/except for Plan 02-04 imports. Initial attempt used `try: from book_pipeline.rag.retrievers.entity_state import EntityStateRetriever except ImportError: EntityStateRetriever = None`. Once mypy scope included the retrievers subpackage, mypy flagged `import-untyped` for these (even though the modules don't exist yet — mypy's static resolver tried to analyze the from-import at face value). Switched to `importlib.import_module(...).Attr` + `contextlib.suppress(ImportError)` — bypasses mypy's static analysis (the runtime behavior is identical) while keeping the graceful-absence semantics. Ruff SIM105 rule forced the contextlib.suppress idiom anyway."
  - "(02-03) Metadata on every RetrievalHit carries `vector_distance` (from LanceDB `_distance` column on search.to_list()) as a relative-confidence signal for Plan 02-05 bundler + Plan 02-06 CI baseline introspection. This is additive over the plan's literal behavior spec (which listed 4 metadata keys); tightens Plan 05's signal surface without API change."
  - "(02-03) Injection guard on MetaphysicsRetriever._where_clause: regex `[a-z_]+` full-match per include_rule_types entry; ValueError on any non-conformant value. Today's callers are all trusted (Plan 02-05 bundler passes the tuple from config/rag_retrievers.yaml), but the guard prevents a future path from accidentally leaking unsanitized input into the where clause — defense in depth."
metrics:
  duration_minutes: 14
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 11
  files_modified: 0  # Plan 02-01 already extended pyproject import-linter + scripts/lint_imports.sh + tests/test_import_contracts.py for src/book_pipeline/rag; the retrievers subpackage sits under that umbrella and needs no fresh cross-cutting changes.
  tests_added: 25  # 12 Task 1 + 13 Task 2 = 25 new tests.
  tests_passing: 192
commits:
  - hash: 2b2dab1
    type: test
    summary: RED — failing tests for BgeReranker + LanceDBRetrieverBase (Task 1)
  - hash: e7acc52
    type: feat
    summary: GREEN — BgeReranker + LanceDBRetrieverBase shared retriever machinery (Task 1)
  - hash: 0de228b
    type: test
    summary: RED — failing tests for 3 concrete retrievers (Task 2)
  - hash: 4ea3dac
    type: feat
    summary: GREEN — historical + metaphysics + negative_constraint retrievers + B-1 sole-owned __init__.py (Task 2)
---

# Phase 2 Plan 3: 3-of-5 Typed Retrievers + Shared Base + BGE Reranker Summary

**One-liner:** 3 of the 5 typed retrievers (historical, metaphysics with PITFALLS R-4 rule_type filter + injection guard, negative_constraint with PITFALLS R-5 deliberate-no-filter) land on top of a shared LanceDBRetrieverBase (candidate_k=50 -> final_k=8 pipeline with empty-table tolerance, B-2 frozen `reindex(self) -> None` Protocol signature, W-2 explicit-kwargs __init__ template) and a lazy BgeReranker cross-encoder wrapper — all four exported through a Plan-03-sole-owned `retrievers/__init__.py` (B-1) that pre-declares Plan 02-04's two forthcoming retriever symbols via `importlib.import_module` + `contextlib.suppress(ImportError)`, never call the observability event logger (Protocol docstring contract; grep-guarded to zero matches), and add 25 new tests (192 total green) with the aggregate import-linter + ruff + mypy gate still exit-0.

## Performance

- **Duration:** ~14 min
- **Started:** 2026-04-22T07:03:05Z
- **Completed:** 2026-04-22T07:16:43Z
- **Tasks:** 2 (Task 1: BgeReranker + LanceDBRetrieverBase; Task 2: 3 concrete retrievers + B-1 __init__.py)
- **Files created:** 11
- **Files modified:** 0 (cross-cutting pyproject / lint targets were already extended for `src/book_pipeline/rag` by Plan 02-01)

## Accomplishments

- **3 of 5 typed retrievers operational.** `HistoricalRetriever`, `MetaphysicsRetriever`, `NegativeConstraintRetriever` each satisfies the frozen `book_pipeline.interfaces.retriever.Retriever` Protocol at runtime (`isinstance(r, Retriever) == True` per dedicated test in each retriever test file) and inherits the zero-arg `reindex(self) -> None` signature from `LanceDBRetrieverBase` (B-2 frozen Protocol — verified by `inspect.signature` test).
- **Shared retriever machinery cemented.** `LanceDBRetrieverBase` owns the `query_fingerprint -> open_or_create_table -> empty-table short-circuit -> embed -> top-50 vector search -> rerank -> top-8 hits -> metadata assembly` pipeline; concrete subclasses add only `_build_query_text` + optional `_where_clause`. The 8 base-class tests cover every axis of this contract including the "empty" sentinel from `index_fingerprint()` when the table has no rows yet (Plan 02-04's ArcPositionRetriever and EntityStateRetriever will hit this path on first run before their source files are parsed).
- **PITFALLS R-4 and R-5 mitigations in place with regression tests.** Metaphysics default filter excludes hypothetical + example rows; widening via `include_rule_types` kwarg is allowed, but an SQL-injection attempt (`"rule'; DROP TABLE"`) raises `ValueError` (test 4). Negative-constraint's `_where_clause` returns `None` for every `SceneRequest` — not configurable, not bypassable — so the bundler (Plan 02-05) is the ONLY place where tag-based filtering happens, preventing the silent-miss failure.
- **B-1 sole-ownership of `retrievers/__init__.py` resolved cleanly.** Plan 02-03 owns the file; Plan 02-04 does not touch it. Pre-Plan-04 behavior: `from book_pipeline.rag.retrievers import EntityStateRetriever, ArcPositionRetriever` yields `None, None`. Post-Plan-04 behavior: both resolve to real classes. The dynamic `importlib.import_module` + `contextlib.suppress(ImportError)` pattern threads mypy, ruff, and the test suite all at once.
- **"retrievers never emit observability events" grep-guard holds at zero.** `grep -rn "EventLogger\\|\\.emit(" src/book_pipeline/rag/retrievers/ src/book_pipeline/rag/reranker.py` returns no matches. Plan 02-05's bundler will be the event-emission site; Plan 02-05 will add a "exactly one event per `bundle()` call" test that collaborates with this grep guard to catch any future drift.
- **Aggregate gate + full test suite green.** `bash scripts/lint_imports.sh` exits 0 (2 import-linter contracts kept, ruff clean, mypy clean on 68 source files including the new retrievers subpackage). `uv run pytest tests/ -q` passes 192 tests (was 167 baseline; +25 this plan).

## Task Commits

1. **Task 1 RED** — `2b2dab1` (test): 12 failing tests for BgeReranker + LanceDBRetrieverBase — empty-zero-load, top-K sort, non-mutation (reranker) + empty-tolerance, metadata shape, query_fingerprint stability, index_fingerprint distinctness + empty sentinel, where_clause hook, B-2 signature, Protocol runtime check (base).
2. **Task 1 GREEN** — `e7acc52` (feat): BgeReranker (lazy CrossEncoder wrapper; empty-candidates zero-load) + LanceDBRetrieverBase (candidate_k=50 -> final_k=8 with empty-table tolerance + B-2 frozen reindex signature + `empty` sentinel for index_fingerprint on empty tables) + placeholder retrievers/__init__.py.
3. **Task 2 RED** — `0de228b` (test): 13 failing tests for the 3 concrete retrievers — 4 historical, 5 metaphysics (incl. R-4 filter + injection guard), 4 negative_constraint (incl. R-5 no-filter invariant).
4. **Task 2 GREEN** — `4ea3dac` (feat): historical + metaphysics + negative_constraint retrievers + B-1 sole-owned retrievers/__init__.py (importlib + contextlib.suppress for Plan 02-04 imports).

**Plan metadata commit** follows this SUMMARY in a separate `docs(02-03): complete Wave 3 typed retrievers (3 of 5) plan` commit.

## Query-text shape per retriever (Plan 06 golden-query CI baseline)

Authored once here so Plan 02-06's golden-query seed set can pin against these exact shapes (any future edit is an intentional RAG quality signal, not silent behavior drift):

| Retriever | `_build_query_text(request)` returns | `_where_clause(request)` returns |
|---|---|---|
| historical | `f"{request.date_iso} {request.location} {request.beat_function} historical context for {request.pov}"` | `None` |
| metaphysics | `f"{request.beat_function} engine metaphysics rules at {request.location} on {request.date_iso}"` | `f"rule_type IN ({quoted})"` where `quoted` comes from `include_rule_types` (default `('rule',)`); raises `ValueError` on any value that doesn't match `[a-z_]+` full-match. |
| negative_constraint | `f"landmines and things to avoid when {request.pov} is at {request.location} on {request.date_iso}; beat: {request.beat_function}"` | `None` (PITFALLS R-5 — deliberate; tag filtering lives in Plan 02-05 bundler) |

## RetrievalHit metadata shape (post-rerank)

Every hit carries a 5-key metadata dict for downstream introspection:

```
{
  "rule_type": <str>,               # 'rule' | 'hypothetical' | 'example' | 'cross_reference'
  "heading_path": <str>,            # chunker's H1 > H2 > H3 breadcrumb
  "ingestion_run_id": <str>,        # per 02-02 ingester format ing_<ts><us>Z_<8-char>
  "chapter": <int | None>,          # W-5 column; None for non-chapter chunks
  "vector_distance": <float | None> # LanceDB _distance from the search() call
}
```

## candidate_k=50 -> final_k=8 pipeline (Plan 02-05 bundler assumes 8-hits-per-axis)

`LanceDBRetrieverBase.__init__` defaults: `candidate_k=50`, `final_k=8`. The pipeline per retrieve() call:

1. `query_fingerprint = hash_text(request.model_dump_json())` — xxh64 of the request JSON (Plan 02-05 + Plan 02-06 reuse as cache key).
2. `table = open_or_create_table(self.db_path, self.name)` — 02-01 schema-enforced; raises on drift.
3. If `table.count_rows() == 0`: short-circuit to `RetrievalResult(hits=[], bytes_used=0, retriever_name=self.name, query_fingerprint=...)`.
4. `query_text = self._build_query_text(request)`; `query_vec = self.embedder.embed_texts([query_text])[0]` (drop batch dim).
5. `search = table.search(query_vec).limit(self.candidate_k)`; optionally `search = search.where(self._where_clause(request))`.
6. `candidates = search.to_list()` (list of CHUNK_SCHEMA dicts + `_distance`).
7. `pair_inputs = [(row["text"], row) for row in candidates]`; `reranked = self.reranker.rerank(query_text, pair_inputs, top_k=self.final_k)` returns `[(text, row, rerank_score), ...]`.
8. Build `RetrievalHit` list; `bytes_used = sum(len(h.text.encode("utf-8")) for h in hits)`; return `RetrievalResult`.

Plan 02-05 bundler assumes 8 hits per axis × 5 axes = up to 40 hits feeding the 40KB ContextPack cap. The `final_k` default is an `__init__` kwarg for future tuning without API break.

## B-1 retrievers/__init__.py dynamic-import pattern (Plan 02-04 surface)

```python
import contextlib as _contextlib
import importlib as _importlib
from typing import Any as _Any

from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase
from book_pipeline.rag.retrievers.historical import HistoricalRetriever
from book_pipeline.rag.retrievers.metaphysics import MetaphysicsRetriever
from book_pipeline.rag.retrievers.negative_constraint import NegativeConstraintRetriever

EntityStateRetriever: _Any = None
ArcPositionRetriever: _Any = None
with _contextlib.suppress(ImportError):  # Plan 02-04 not yet executed
    EntityStateRetriever = _importlib.import_module(
        "book_pipeline.rag.retrievers.entity_state"
    ).EntityStateRetriever
with _contextlib.suppress(ImportError):  # Plan 02-04 not yet executed
    ArcPositionRetriever = _importlib.import_module(
        "book_pipeline.rag.retrievers.arc_position"
    ).ArcPositionRetriever

__all__ = [
    "ArcPositionRetriever",
    "EntityStateRetriever",
    "HistoricalRetriever",
    "LanceDBRetrieverBase",
    "MetaphysicsRetriever",
    "NegativeConstraintRetriever",
]
```

Plan 02-04 only creates `src/book_pipeline/rag/retrievers/entity_state.py` and `src/book_pipeline/rag/retrievers/arc_position.py` — it does NOT modify this file. Plan 02-04's `<verify>` step should grep that these two attributes resolve to real classes (not `None`) after its two source files exist.

## B-2 frozen `reindex(self) -> None` signature

Every concrete retriever MUST keep this signature. Plan 02-04's `ArcPositionRetriever` will override the method body to re-parse `~/Source/our-lady-of-champion/outline.md` using `self.outline_path`, `self.embedder`, `self.ingestion_run_id` — all of which are stored on `self` at `__init__` time and read from `self.*` during `reindex()`. No args-extending overrides; no classmethod workarounds. Runtime-checkable Protocol isinstance must pass. The test assertion in each retriever test file is:

```python
from book_pipeline.interfaces.retriever import Retriever
assert isinstance(r, Retriever)
# AND
assert len(inspect.signature(r.reindex).parameters) == 0
```

## W-2 explicit-kwargs retriever __init__ template (Plan 02-04 MUST follow)

```python
class XyzRetriever(LanceDBRetrieverBase):
    def __init__(
        self,
        *,
        db_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        # axis-specific kwargs HERE, all keyword-only
        **kw: Any,
    ) -> None:
        super().__init__(name="xyz", db_path=db_path, embedder=embedder, reranker=reranker, **kw)
        # store axis-specific state from __init__ args
```

No `*args` forwarding. No positional-after-keyword splat. Any axis-specific state needed by a non-trivial `reindex()` override is stored here.

## Files Created/Modified

### Created

- `src/book_pipeline/rag/reranker.py` — BgeReranker lazy CrossEncoder wrapper.
- `src/book_pipeline/rag/retrievers/__init__.py` — B-1 sole-owned 5-retriever surface with dynamic-import guards for Plan 02-04.
- `src/book_pipeline/rag/retrievers/base.py` — LanceDBRetrieverBase shared machinery + B-2 reindex.
- `src/book_pipeline/rag/retrievers/historical.py` — HistoricalRetriever.
- `src/book_pipeline/rag/retrievers/metaphysics.py` — MetaphysicsRetriever with R-4 filter + injection guard.
- `src/book_pipeline/rag/retrievers/negative_constraint.py` — NegativeConstraintRetriever with R-5 deliberate-no-filter.
- `tests/rag/test_reranker.py` — 4 tests.
- `tests/rag/test_retriever_base.py` — 8 tests.
- `tests/rag/test_historical_retriever.py` — 4 tests.
- `tests/rag/test_metaphysics_retriever.py` — 5 tests.
- `tests/rag/test_negative_constraint_retriever.py` — 4 tests.
- `.planning/phases/02-corpus-ingestion-typed-rag/02-03-SUMMARY.md` — this file.

### Modified

None. Plan 02-01 already extended `pyproject.toml` (import-linter contract 1 source_modules + contract 2 forbidden_modules) and `scripts/lint_imports.sh` (mypy target list) and `tests/test_import_contracts.py` (kernel_dirs grep-fallback) for `src/book_pipeline/rag`; the new `rag/retrievers/` subpackage sits under that umbrella and needs no fresh cross-cutting changes.

## Decisions Made

See frontmatter `key-decisions` — extracted to STATE.md by the state-update step. Summary:

1. **B-1 sole ownership of __init__.py** — Plan 03 writes it; Plan 04 never touches. Plan 04's two new source files are imported via `importlib.import_module` inside `contextlib.suppress(ImportError)`. Threads mypy + ruff + runtime all at once.
2. **B-2 frozen Protocol `reindex(self) -> None`** — every concrete retriever inherits; state stored on `self` at `__init__`. Runtime-checkable isinstance tested in each test file.
3. **W-2 explicit-kwargs __init__ template** — no `*args`/`**kwargs` forwarding; `super().__init__(name="axis", db_path=..., embedder=..., reranker=..., **kw)`. Plan 02-04 MUST follow.
4. **candidate_k=50 -> final_k=8 pipeline cemented** — Plan 02-05 bundler's 40KB cap math assumes 8 hits per axis.
5. **Dynamic importlib over static try/except** — mypy's static resolver flagged the static form as import-untyped once the retrievers package came under mypy's scope; ruff SIM105 forced the `contextlib.suppress(ImportError)` idiom anyway. Runtime behavior identical to the plan's literal spec.
6. **RetrievalHit.metadata adds `vector_distance`** — 5th metadata key beyond the plan's literal 4; zero-cost additive signal for Plan 02-05 bundler + Plan 02-06 CI introspection.
7. **MetaphysicsRetriever `[a-z_]+` injection guard** — defense in depth; today's callers are all trusted (Plan 02-05 bundler reads from `config/rag_retrievers.yaml`) but the guard prevents a future regression from leaking unsanitized input into the where clause.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Ruff import-ordering violations on test files after I wrote them.**

- **Found during:** Task 1 GREEN verify (first `bash scripts/lint_imports.sh` after landing base.py + reranker.py) and Task 2 GREEN verify (first full-gate run after landing the 3 concrete retrievers).
- **Issues:**
    - `tests/rag/test_retriever_base.py` had unused imports (`pyarrow as pa`, `pytest`) and then an I001 unsorted-imports violation once those were removed.
    - `tests/rag/test_historical_retriever.py` had an I001 unsorted-imports violation.
- **Fix:** `uv run ruff check --fix tests/rag/` resolved all three. No behavior change.
- **Files modified:** `tests/rag/test_retriever_base.py`, `tests/rag/test_historical_retriever.py`.
- **Verification:** `bash scripts/lint_imports.sh` exits 0 after each fix.
- **Committed in:** `e7acc52` (Task 1 GREEN) + `4ea3dac` (Task 2 GREEN).

**2. [Rule 1 - Bug in plan's literal wording] "EventLogger" in docstring triggers the plan's `grep -c "EventLogger|emit("` zero-match acceptance criterion.**

- **Found during:** Task 1 GREEN verify, on first check of the acceptance grep.
- **Issue:** The plan's acceptance criterion was `grep -c "EventLogger\\|emit(" src/book_pipeline/rag/retrievers/base.py == 0`. My initial base.py docstring referenced "EventLogger" in a "retrievers NEVER call EventLogger directly" explanation — textually correct, grep-failing. Plan 02-01 hit the same class of issue on the `book_specifics` grep-fallback (fixed by rewriting docstrings to avoid the substring).
- **Fix:** Rewrote the base.py docstring line to: "Retrievers NEVER log observability events directly (Protocol docstring contract — the bundler in Plan 05 is the event-emission site for all 5 retrievers)." — same semantic, no substring match. Same fix for reranker.py module docstring.
- **Rationale:** Substring-level grep guards are belt-and-suspenders next to actual code references (which also wouldn't match at runtime because the retrievers don't import EventLogger); the docstring phrasing is just prose and is free to reword without any behavior change.
- **Files modified:** `src/book_pipeline/rag/retrievers/base.py` (+ `src/book_pipeline/rag/reranker.py` had no EventLogger refs initially so no change there).
- **Committed in:** `e7acc52` (Task 1 GREEN).

**3. [Rule 1 - Bug in plan's literal wording] Plan's `grep "super().__init__(name=" ...` acceptance criterion required a single-line super-init call; my multi-line stylistic version failed the literal grep.**

- **Found during:** Task 2 GREEN verify, first pass through the acceptance criteria.
- **Issue:** I initially wrote the super init call across multiple lines for readability:
    ```python
    super().__init__(
        name="historical",
        db_path=db_path, ...
    )
    ```
  Plan's acceptance grep is `grep "super().__init__(name=" ...` — matches only if `name=` is on the same line as `super().__init__(`. Semantically equivalent, grep-failing.
- **Fix:** Collapsed the super init to a single line per retriever: `super().__init__(name="historical", db_path=db_path, embedder=embedder, reranker=reranker, **kw)`. All 3 retrievers now match the grep exactly 1× each (3 total, as required).
- **Rationale:** Line length is at the edge of ruff's default (99 chars for ruff) but under; the single-line form is semantically identical and honors the plan's literal check. The plan writer clearly meant "W-2 explicit-kwarg forwarding happens on the super call"; the grep is a cheap proof-test.
- **Files modified:** `src/book_pipeline/rag/retrievers/historical.py`, `src/book_pipeline/rag/retrievers/metaphysics.py`, `src/book_pipeline/rag/retrievers/negative_constraint.py`.
- **Committed in:** `4ea3dac` (Task 2 GREEN).

**4. [Rule 1 - Bug in plan's literal wording] Plan's `grep -c "\\*args" ... == 0` acceptance criterion matched docstring mentions of "*args".**

- **Found during:** Task 2 GREEN verify, same pass as #3.
- **Issue:** My retriever docstrings mentioned "W-2 compliance: explicit keyword-only __init__ args. No *args forwarding." — documentation of the invariant, not a use of `*args`. The grep counts substring hits, so it matched each docstring, giving 1 per file (not 0).
- **Fix:** Rewrote the docstring line to "No positional-splat forwarding." — same meaning, no `*args` substring. Grep now counts 0 across all 3 files.
- **Rationale:** Same class as #2 — substring greps are belt-and-suspenders; the actual runtime signatures have no `*args` positional-splat parameter.
- **Files modified:** `src/book_pipeline/rag/retrievers/historical.py`, `src/book_pipeline/rag/retrievers/metaphysics.py`, `src/book_pipeline/rag/retrievers/negative_constraint.py`.
- **Committed in:** `4ea3dac` (Task 2 GREEN).

**5. [Rule 3 - Blocking] mypy rejected the plan's literal static `try/except from book_pipeline.rag.retrievers.entity_state import EntityStateRetriever except ImportError: ...` guard with `import-untyped` once the retrievers subpackage came under mypy scope.**

- **Found during:** Task 2 GREEN verify, first full aggregate gate run after landing all 3 concrete retrievers and the B-1 __init__.py.
- **Issue:** Even though `book_pipeline.rag.retrievers.entity_state` does not exist on disk (Plan 02-04 not yet executed), mypy's static resolver flagged the `from book_pipeline.rag.retrievers.entity_state import EntityStateRetriever` line as `error: Skipping analyzing "book_pipeline.rag.retrievers.entity_state": module is installed, but missing library stubs or py.typed marker [import-untyped]`. (The phrasing is misleading — mypy picks up the fact that the `book_pipeline.rag.retrievers` namespace is mypy-scoped but the submodule isn't, which it reports as "installed but untyped".) The `# type: ignore[assignment,misc]` on the fallback assignment was then flagged as `unused-ignore`.
- **Fix:** Switched to dynamic `importlib.import_module("book_pipeline.rag.retrievers.entity_state").EntityStateRetriever` inside `contextlib.suppress(ImportError)` (forced by ruff SIM105 over the equivalent `try/except-pass`). mypy does not statically analyze string-argument `import_module` calls, so the guard is clean; ruff is happy with `contextlib.suppress`; runtime behavior is identical to the plan's literal spec (pre-Plan-04 attribute is None; post-Plan-04 attribute is the real class).
- **Rationale:** Plan 02-01 exposed the same class of mypy-scope friction with `lancedb.list_tables()` (fixed by reverting to `table_names()`). Keeping the runtime semantics ("pre-Plan-04 is None, post-Plan-04 is real class") is load-bearing; the choice of static-import-with-type-ignore vs dynamic-import-with-suppress is an implementation detail. Dynamic import also reads more cleanly ("this is a best-effort cross-plan import, not a hard dep").
- **Files modified:** `src/book_pipeline/rag/retrievers/__init__.py`.
- **Verification:** `bash scripts/lint_imports.sh` exits 0 (mypy 68 source files clean, import-linter 2 contracts kept, ruff clean). `uv run python -c "from book_pipeline.rag.retrievers import EntityStateRetriever, ArcPositionRetriever; print(EntityStateRetriever, ArcPositionRetriever)"` prints `None None` pre-Plan-04 as specified.
- **Committed in:** `4ea3dac` (Task 2 GREEN).

---

**Total deviations:** 5 auto-fixed (2 Rule 3 blocking on ruff + mypy friction, 3 Rule 1 "plan's grep acceptance criterion required a specific substring that my textually-equivalent phrasing didn't match" — all trivially reworded).

**Impact on plan:** All 5 fixes are necessary to reach the plan's own `<success_criteria>` and `<verification>` blocks. No scope creep. Deviation #5 (dynamic importlib over static try/except) is a semantic improvement over the plan's literal B-1 implementation spec — the runtime behavior is identical and the static-analysis friction goes away, which Plan 02-04 will thank us for when it adds its two retriever source files.

## Issues Encountered

- Same `PreToolUse` read-before-edit hook friction as Plan 02-02 — I created some files via Write, then Edited them in the same session, and the hook warned about re-reading. The runtime accepts Write-then-Edit on the same file in a single session (Write establishes read state), so no operations were blocked; the warnings were noise. No workflow change needed.

## Authentication Gates

None. All work is local — no HF Hub calls (CrossEncoder is monkeypatched in tests), no LLM calls, no GPU (the `_ensure_loaded` paths are fake-patched).

## Deferred Issues

1. **Real BGE reranker-v2-m3 end-to-end smoke test** — unit tests monkeypatch `sentence_transformers.CrossEncoder` to avoid the 2GB model download (same pattern as Plan 02-01's BgeM3Embedder test). A real cross-encoder load against `BAAI/bge-reranker-v2-m3` will happen during Plan 02-06's first CI run against the populated corpus on a GPU box. All the shapes we care about (scores, ordering, top_k truncation) are covered by the fake; the "does the real model load cleanly on cuda:0" question is Plan 02-06's concern.

2. **Real LanceDB `search(query_vec).limit()` performance at production scale** — tests use in-memory tables with ≤10 rows per axis. Plan 02-01 already noted "5×500 rows ≈ 2.5K vectors" per STACK.md; LanceDB is quoted as trivial at that scale. Real scale characterization is Plan 02-06's CI baseline.

3. **lancedb `table_names()` deprecation** — still deferred (inherited from Plan 02-01 and 02-02). `open_or_create_table` is the one call site that still uses the deprecated API; 20+ test warnings fire. Migration to `list_tables().tables` is a single-line change when lancedb removes `table_names()` (~0.32+).

## Known Stubs

None. Every public surface has a real implementation:

- `BgeReranker._ensure_loaded` really instantiates `sentence_transformers.CrossEncoder` on first non-empty rerank (unit tests monkeypatch to avoid the download).
- `LanceDBRetrieverBase.retrieve` really opens a LanceDB table, really embeds the query, really runs a vector search, really reranks.
- `LanceDBRetrieverBase.reindex` is intentionally a no-op + logging.info call at the base level (the CorpusIngester in Plan 02-02 owns full-corpus reindex); this is the B-2 contract, not a stub. Plan 02-04's ArcPositionRetriever will override the method body — not signature — with a real re-parse of `outline.md`.
- `MetaphysicsRetriever._where_clause` really emits a SQL-esque `rule_type IN (...)` string and really raises `ValueError` on injection attempts.
- `NegativeConstraintRetriever._where_clause` intentionally returns `None` for every request — PITFALLS R-5 contract, not a stub.

The `TODO(Plan 02+)` comment inherited from `rag/lance_schema.py` (about the `list_tables()` API migration) applies at the `open_or_create_table` call site used by all three retrievers. Still a forward-looking migration note, not a current stub.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 5 threats in the register are covered as planned:

- **T-02-03-01** (Tampering: metaphysics where_clause SQL-injection): MITIGATED. `MetaphysicsRetriever._where_clause` regex-validates every entry in `self._rule_types` with `[a-z_]+` full-match before embedding into the IN-clause. `test_metaphysics_injection_guard_rejects_malicious_rule_type` asserts `ValueError` on `"rule'; DROP TABLE"`.
- **T-02-03-02** (Repudiation: retrievers emit events, breaking Plan 05's bundler schema): MITIGATED. `grep -rn "EventLogger\\|\\.emit(" src/book_pipeline/rag/retrievers/ src/book_pipeline/rag/reranker.py` returns 0 matches. Plan 02-05 will add the complementary "exactly one event per `bundle()` call" test to double-check from the other direction.
- **T-02-03-03** (Info Disclosure: RetrievalHit.metadata leaks ingestion_run_id): ACCEPTED. ingestion_run_id is project-internal (lives in `runs/events.jsonl` already per OBS-01). Downstream cache-key utility.
- **T-02-03-04** (DoS: reranker cross-encoder on CPU takes minutes): MITIGATED. BgeReranker default `device="cuda:0"`; device is configurable via `__init__` kwarg; CI tests monkeypatch to avoid real inference. Plan 02-06 will expose `device` in `config/rag_retrievers.yaml`'s reranker section.
- **T-02-03-05** (Tampering: retriever subclass adds args to `reindex()` and breaks Protocol conformance): MITIGATED. `isinstance(r, Retriever)` test in each of the 3 concrete retriever test files + `inspect.signature(r.reindex).parameters` emptiness test. Any future subclass that re-opens `reindex` with args would fail the isinstance check (runtime_checkable Protocol) and/or the signature-emptiness check. Plan 02-04's ArcPositionRetriever override MUST preserve the zero-arg signature — its tests will re-run the same isinstance + signature checks.

## Verification Evidence

Plan `<success_criteria>` + task `<acceptance_criteria>` coverage:

| Criterion | Status | Evidence |
|---|---|---|
| 3 retrievers importable from `book_pipeline.rag.retrievers` | PASS | `uv run python -c "from book_pipeline.rag.retrievers import HistoricalRetriever, MetaphysicsRetriever, NegativeConstraintRetriever"` exits 0 |
| Shared LanceDBRetrieverBase + BgeReranker cover query-embed -> top-50 -> rerank -> top-8 | PASS | `test_populated_table_returns_hits_with_metadata` asserts `len(out.hits) == min(final_k, row_count)` + metadata carrier shape |
| MetaphysicsRetriever default filter rule_type='rule' | PASS | `test_metaphysics_default_filter_is_rule_only` — hypothetical + example filtered out |
| MetaphysicsRetriever injection guard | PASS | `test_metaphysics_injection_guard_rejects_malicious_rule_type` raises ValueError |
| NegativeConstraintRetriever returns top-K unconditionally | PASS | `test_negative_constraint_where_clause_is_none_for_every_request` (2 SceneRequests) + `test_negative_constraint_returns_top_k_regardless_of_request` |
| No retriever calls EventLogger / emit | PASS | `grep -rn "EventLogger\|\.emit(" src/book_pipeline/rag/retrievers/ src/book_pipeline/rag/reranker.py` returns nothing |
| B-2: `reindex(self) -> None` frozen signature on all subclasses | PASS | `test_reindex_has_no_extra_args_and_does_not_raise` (base) + `test_historical_reindex_has_no_extra_args` + `inspect.signature` checks in each retriever's `isinstance(r, Retriever)` test |
| W-2: explicit-kwarg forwarding (no *args antipattern) | PASS | `grep -F -c "super().__init__(name=" src/book_pipeline/rag/retrievers/*.py` == 1 per concrete retriever (3 total); `grep -F -c "*args" ...` == 0 per concrete retriever |
| B-1: Plan 03 sole-owns retrievers/__init__.py with all 5 imports | PASS | `uv run python -c "from book_pipeline.rag.retrievers import EntityStateRetriever, ArcPositionRetriever; print(EntityStateRetriever, ArcPositionRetriever)"` prints `None None` pre-Plan-04 (as specified). Post-Plan-04 the contextlib.suppress block will succeed and both will be real classes. |
| Tests cover empty-table tolerance + Protocol structural satisfaction + per-axis filter semantics | PASS | test_empty_table_returns_empty_result + 4 isinstance(r, Retriever) tests across base + 3 retriever test files + per-axis filter tests for R-4 + R-5 |
| `uv run pytest tests/rag/test_reranker.py tests/rag/test_retriever_base.py tests/rag/test_historical_retriever.py tests/rag/test_metaphysics_retriever.py tests/rag/test_negative_constraint_retriever.py -v` all green | PASS | 25 passed (12 Task 1 + 13 Task 2) |
| `bash scripts/lint_imports.sh` exits 0 | PASS | "Contracts: 2 kept, 0 broken." + ruff clean + mypy: no issues found in 68 source files |
| Full suite still green | PASS | 192 passed (was 167 pre-plan); +25 added; no regressions |

## Self-Check: PASSED

Artifact verification (files on disk):

- FOUND: `src/book_pipeline/rag/reranker.py`
- FOUND: `src/book_pipeline/rag/retrievers/__init__.py` (B-1 sole-owned, 5-retriever surface)
- FOUND: `src/book_pipeline/rag/retrievers/base.py` (LanceDBRetrieverBase with B-2 reindex)
- FOUND: `src/book_pipeline/rag/retrievers/historical.py`
- FOUND: `src/book_pipeline/rag/retrievers/metaphysics.py` (R-4 + injection guard)
- FOUND: `src/book_pipeline/rag/retrievers/negative_constraint.py` (R-5 no-filter)
- FOUND: `tests/rag/test_reranker.py` (4 tests)
- FOUND: `tests/rag/test_retriever_base.py` (8 tests)
- FOUND: `tests/rag/test_historical_retriever.py` (4 tests)
- FOUND: `tests/rag/test_metaphysics_retriever.py` (5 tests)
- FOUND: `tests/rag/test_negative_constraint_retriever.py` (4 tests)

Commit verification on `main` branch of `/home/admin/Source/our-lady-book-pipeline/`:

- FOUND: `2b2dab1 test(02-03): RED — failing tests for BgeReranker + LanceDBRetrieverBase (Task 1)`
- FOUND: `e7acc52 feat(02-03): GREEN — BgeReranker + LanceDBRetrieverBase shared retriever machinery (Task 1)`
- FOUND: `0de228b test(02-03): RED — failing tests for 3 concrete retrievers (Task 2)`
- FOUND: `4ea3dac feat(02-03): GREEN — historical + metaphysics + negative_constraint retrievers + B-1 sole-owned __init__.py (Task 2)`

All four per-task commits (2 RED + 2 GREEN, per TDD) landed on `main`. Aggregate gate + full test suite green.

## Next Plan Readiness

- **Plan 02-04 (entity_state + arc_position retrievers) can start immediately.** The B-1 sole-owned __init__.py is in place; Plan 02-04 only creates `src/book_pipeline/rag/retrievers/entity_state.py` and `src/book_pipeline/rag/retrievers/arc_position.py` and does NOT modify `__init__.py`. The W-2 explicit-kwargs pattern is the template (see above). The B-2 `reindex(self) -> None` signature is frozen — ArcPositionRetriever may override the method body to re-parse outline.md using `self.outline_path`, `self.embedder`, `self.ingestion_run_id` stored at `__init__` time. The `LanceDBRetrieverBase` empty-table tolerance path is exactly the EntityStateRetriever zero-cards-tolerance guarantee.
- **Plan 02-05 (ContextPackBundler) can start in Wave 4.** The 5 retrievers will be constructed (via config/rag_retrievers.yaml) and passed into `ContextPackBundler.bundle(request, retrievers)`. The bundler is the event-emission site. The candidate_k=50 -> final_k=8 pipeline means the bundler sees up to 8 hits per axis × 5 axes = 40 hits for the 40KB ContextPack cap.
- **Plan 02-06 (golden-query CI gate)** will baseline against the query_text shapes documented above + the candidate_k=50 -> final_k=8 pipeline; any regression in retrieval precision is a CI-blocking signal.
- **No blockers.** RAG-01 moves to 60% complete (3 of 5 retrievers); closes fully after Plan 02-04.

---
*Phase: 02-corpus-ingestion-typed-rag*
*Plan: 03*
*Completed: 2026-04-22*
