---
phase: 02-corpus-ingestion-typed-rag
reviewed: 2026-04-21T00:00:00Z
depth: standard
commit_range: aedfe14..c352992
files_reviewed: 23
files_reviewed_list:
  - src/book_pipeline/rag/__init__.py
  - src/book_pipeline/rag/budget.py
  - src/book_pipeline/rag/bundler.py
  - src/book_pipeline/rag/chunker.py
  - src/book_pipeline/rag/conflict_detector.py
  - src/book_pipeline/rag/embedding.py
  - src/book_pipeline/rag/lance_schema.py
  - src/book_pipeline/rag/outline_parser.py
  - src/book_pipeline/rag/reranker.py
  - src/book_pipeline/rag/types.py
  - src/book_pipeline/rag/retrievers/__init__.py
  - src/book_pipeline/rag/retrievers/arc_position.py
  - src/book_pipeline/rag/retrievers/base.py
  - src/book_pipeline/rag/retrievers/entity_state.py
  - src/book_pipeline/rag/retrievers/historical.py
  - src/book_pipeline/rag/retrievers/metaphysics.py
  - src/book_pipeline/rag/retrievers/negative_constraint.py
  - src/book_pipeline/corpus_ingest/__init__.py
  - src/book_pipeline/corpus_ingest/ingester.py
  - src/book_pipeline/corpus_ingest/mtime_index.py
  - src/book_pipeline/corpus_ingest/router.py
  - src/book_pipeline/cli/ingest.py
  - src/book_pipeline/cli/_entity_list.py
  - src/book_pipeline/book_specifics/heading_classifier.py
  - src/book_pipeline/openclaw/bootstrap.py
  - src/book_pipeline/interfaces/types.py
findings:
  blocker: 1
  warning: 4
  info: 2
  total: 7
status: findings
---

# Phase 2: Code Review Report

**Reviewed:** 2026-04-21
**Depth:** standard
**Commit range:** `aedfe14..c352992` (30 commits)
**Files Reviewed:** 23
**Status:** findings

## Summary

Phase 2 is well-structured: kernel/book-specifics boundary is respected, Protocol contracts are honored, and threat-model mitigations (T-02-05-01 path-traversal int-cast, T-02-05-07 no-regex-compile on entity_list) are explicit. One real bug was found in the bundler's event-emission contract (exceptions outside retriever.retrieve() bypass the guarantee), plus four warnings concerning conflict-detector false-positive surface, idempotency when ArcPositionRetriever fails post-ingest, ingester atomicity, and a subtle type contradiction in mtime_index. No security issues found — subprocess calls use arg-list form with literal strings, no shell=True, no eval/exec.

---

## BLOCKER

### BL-01: Bundler event-emission invariant is violated when failures occur outside `retriever.retrieve()`

**File:** `src/book_pipeline/rag/bundler.py:173-241` (`_run_one_retriever`)
**Issue:**
The bundler's core invariant (per module docstring line 7-15) is "exactly 6 events per `bundle()` call". `_run_one_retriever` only wraps `retriever.retrieve(request)` in try/except — NOT the subsequent lines that can also raise:

- Line 207: `rr.model_dump_json()` — on a malformed `RetrievalResult` from a buggy retriever, Pydantic serialization could raise.
- Line 208: `hash_text(output_hash_input)` — safe, xxhash is total.
- Line 219: `Event(...)` Pydantic construction — raises `ValidationError` if any metadata field (e.g., `idx_fp` truncated, `retriever.name` None, etc.) doesn't match the frozen Event schema.
- Line 240: `self._emit(event)` — depends on the injected `EventLogger`; a JsonlEventLogger disk-full / permission-denied exception would propagate.

If any of these raise, the `bundle()` loop at line 114-117 aborts mid-iteration. The bundler's own `_emit_bundler_event` (line 159) is never reached, and preceding retriever events have been emitted but downstream retrievers are not. Result: the scene either produces 1-4 events (if failure hits mid-iteration) or 5 events (if the last retriever triggers it), never the promised 6. The Phase 3 critic / downstream consumers that assume "5 retriever events + 1 bundler event per scene_id" will silently miss scenes.

**Fix:**
Widen the try/except in `_run_one_retriever` to cover the entire body, or emit a sentinel "bundler_error" event from the outer `bundle()` in a top-level except that re-raises:

```python
def _run_one_retriever(self, retriever, request, request_fp, scene_id):
    start_ns = time.monotonic_ns()
    error_msg: str | None = None
    rr: RetrievalResult
    idx_fp = "unresolved"
    try:
        rr = retriever.retrieve(request)
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        rr = RetrievalResult(
            retriever_name=retriever.name, hits=[], bytes_used=0,
            query_fingerprint=request_fp,
        )
    latency_ms = max(1, (time.monotonic_ns() - start_ns) // 1_000_000)

    # Everything below MUST NOT raise — belt up the metadata path.
    try:
        idx_fp = retriever.index_fingerprint()
    except Exception as exc:
        idx_fp = f"error:{type(exc).__name__}"

    try:
        output_hash = hash_text(rr.model_dump_json())
    except Exception as exc:
        output_hash = "error"
        error_msg = f"{error_msg or ''}; serialize:{type(exc).__name__}"

    # ... build + emit Event, but wrap Event() + self._emit() in try/except that
    # falls back to a minimal Event with role='retriever' and extra['error']=...
```

Alternatively, consider adding a `bundle()`-level `try/finally` that emits the bundler Event (with `error` in `extra`) even on partial failure, so the 6-event promise holds even under adverse conditions. Without this fix, the "sole event-emission site" contract from the module docstring is not actually guaranteed.

---

## WARNINGS

### WR-01: `detect_conflicts` will produce heavy false positives from `_POSSESSION_PHRASE_RE` and the bare `in` in `_LOCATION_PHRASE_RE`

**File:** `src/book_pipeline/rag/conflict_detector.py:29-37`
**Issue:**
The two phrase regexes over-match on common English prose:

- `_POSSESSION_PHRASE_RE = re.compile(r"(?:has|carries|possesses|holds)\s+(?:the\s+)?(\w+)\b")` matches "has been", "has a", "has his", "holds his", capturing "been", "a", "his" as possession values.
- `_LOCATION_PHRASE_RE = re.compile(r"(?:is at|arrives at|stays at|returns to|in)\s+([A-Z][\w\-]+...)")` — the bare `in` is extremely promiscuous; any capitalized word after `in` becomes a "location" claim, e.g. "in Mesoamerica" (OK), "in Him" (pronoun), "in Christ" (title), "in March" (month).

Combined with the entity-candidate regex that matches any `[A-Z]\w+` word, a single retriever with heterogeneous chunks will produce (entity, dimension) pairs where the "entity" is actually a proper noun inside an unrelated phrase. When two retrievers independently surface the same such false entity with distinct spurious "locations" / "possessions" (likely under dense corpora), `ConflictReport` objects get generated, persisted to `drafts/retrieval_conflicts/*.json`, and surface to the Phase 3 critic as noise.

The docstring already flags this as a forcing-function, not an NLI engine (Thesis 005 in Phase 6 may replace). But the current thresholds will cause the critic to drown in false alarms — operationally painful.

**Fix:**
Two quick wins without re-architecting:
1. Drop `|in` from `_LOCATION_PHRASE_RE` — require an action verb (`is at`, `arrives at`, `stays at`, `returns to`). Losing recall on "in Tenochtitlan" is acceptable at Phase 2 given the false-positive cost.
2. Gate possession on a stop-list: reject if the captured `group(1)` is in `{"been", "a", "an", "the", "his", "her", "their", "my", "no", "any"}`.

```python
_POSSESSION_STOPLIST = {"been", "a", "an", "the", "his", "her", "their",
                        "my", "your", "no", "any", "some", "all"}

for pm in _POSSESSION_PHRASE_RE.finditer(window):
    val = pm.group(1).strip().lower()
    if val in _POSSESSION_STOPLIST:
        continue
    out.append(("possession", pm.group(1).strip()))
```

Also consider requiring that the detected `entity` actually be in `entity_list` (when `entity_list` is provided) to gate the full-text regex path — currently regex-only entities always flow through even if the injected canonical list is available.

---

### WR-02: `ArcPositionRetriever.reindex()` failure leaves the arc_position table in a half-migrated state

**File:** `src/book_pipeline/rag/retrievers/arc_position.py:72-103` + `src/book_pipeline/cli/ingest.py:151-169`
**Issue:**
`reindex()` does `tbl.delete("true")` at line 85, then conditionally returns (if no beats) or embeds + adds rows. If `self.embedder.embed_texts(...)` raises (GPU OOM, HF model not yet cached, network hiccup on revision resolution, etc.) between the delete and the add, the arc_position table is left EMPTY. The CorpusIngester already wrote beat-bearing outline chunks there via the file-level router; those are gone. The next ingest run will be skipped by mtime check (outline.md mtime unchanged), so the table stays empty until someone runs `--force`.

Downstream: ArcPositionRetriever.retrieve() will return an empty `RetrievalResult` for every scene (`count_rows() == 0` early return at base.py:98) — ContextPacks silently lose their arc-position axis. This survives across CLI invocations because mtime index was written by the successful ingester BEFORE arc.reindex() ran (ingester.py:317 vs cli/ingest.py:168).

**Fix:**
Two options:
1. Write new rows first, then delete the old ones (reverse order) — requires a staging approach.
2. Preferred for Phase 2: Move the `arc.reindex()` call INSIDE the ingester so it runs before `write_mtime_index`, or have the CLI catch reindex failures and invalidate the mtime index:

```python
if not report.skipped:
    ...
    try:
        arc.reindex()
        arc_note = "arc_position reindex: beat-ID-stable rows written"
    except Exception as exc:
        # Invalidate mtime index so the next run retries.
        (indexes_dir / "mtime_index.json").unlink(missing_ok=True)
        raise RuntimeError(
            f"arc_position reindex failed; mtime index invalidated so the "
            f"next ingest retries: {exc}"
        ) from exc
```

Also: for defense-in-depth, consider checking `beats` BEFORE calling `tbl.delete("true")` — if `parse_outline` returns an empty list, the current code deletes rows and skips the rebuild, effectively wiping the table. The line 86-87 `if not beats: return` sits AFTER the delete — should be before.

---

### WR-03: CorpusIngester is not crash-safe — partial state persisted across the truncate-then-rebuild path

**File:** `src/book_pipeline/corpus_ingest/ingester.py:240-307`
**Issue:**
The ingester does:

1. Drop all axis tables (line 240).
2. Open (recreate empty) active axis tables.
3. For each file: read, chunk, route chunks per-axis (in-memory).
4. For each axis: embed in batches, insert into table.
5. Persist `resolved_model_revision.json` + `mtime_index.json`.

If the process crashes (GPU OOM during batch embedding, disk full, SIGINT from operator) between step 1 and step 5, the indexes are wiped and `mtime_index.json` still reflects the PREVIOUS successful run (because write happens at step 5). The NEXT invocation will still detect mtime drift (because the user likely re-edited or the clock moved), so it'll retry — but in the meantime the index is empty, and any retriever query in between returns empty results. If mtimes happened to match the pre-crash snapshot exactly (e.g., no corpus edits since the last successful ingest, but this run was a `--force`), the NEXT non-force run would see `stored_mtimes == current_mtimes` and `skipped=True`, leaving the wiped index unreparsed permanently.

**Fix:**
Simplest mitigation: write `mtime_index.json` with an EMPTY map (or a sentinel) at the START of the non-skipped path, and replace it with the real map ONLY after all axis inserts succeed. Failed runs leave the sentinel in place, guaranteeing the next ingest re-runs:

```python
# Immediately after deciding to rebuild (after mtime check)
write_mtime_index(indexes_dir, {"__in_progress__": 0.0})
try:
    # ... existing build / embed / insert ...
    write_mtime_index(indexes_dir, current_mtimes)  # replace sentinel
except Exception:
    # Leave sentinel; next run will not match current_mtimes → rebuild.
    raise
```

Alternatively (more invasive but cleaner): write to `mtime_index.json.tmp` and atomically rename at the very end; drop tables ONLY after successful embeddings + pre-stage to a side table, then swap. Phase 2 simplicity may not warrant that — but at minimum the sentinel mitigation is five lines.

---

### WR-04: `mtime_index.py` return type lies — JSON keys are always strings, yet the public API types values as `float`

**File:** `src/book_pipeline/corpus_ingest/mtime_index.py:25-31, 43-48`
**Issue:**
`read_mtime_index` declares `-> dict[str, float]` and casts the result via `data: dict[str, float] = json.loads(...)`. JSON round-tripping turns `stat().st_mtime` (Python float, often like `1713734812.4821523`) into a JSON number, then back to a Python float on read. That's OK for floats — BUT:

`corpus_mtime_map` returns `{str(p.resolve()): p.stat().st_mtime for p in source_files}`. The comparison in `ingester.py:216` is `stored_mtimes == current_mtimes`. Float equality after JSON round-trip is NOT guaranteed identical: a float like `1713734812.4821523` MAY serialize as `1713734812.4821522` and mis-compare. In practice Python `json` writes up to 17 significant digits and the round-trip is stable for IEEE-754 doubles (per spec) — BUT `stat().st_mtime` on some filesystems (NFS, certain Docker overlays) returns different precision than on the host, and `p.resolve()` can differ across invocations if symlinks change.

More concretely: the CURRENT shape of `corpus_mtime_map` uses absolute-resolved paths as keys. If the CLI runs from a different CWD, or if one of the corpus files is symlinked differently between runs, the `str(p.resolve())` keys change, and `stored == current` becomes False, triggering a false rebuild. This isn't a crash but will defeat the idempotency design promise on symlink-heavy setups (e.g., the `our-lady-of-champion` corpus living in `~/Source/` while indexes live under project root).

**Fix:**
1. Store mtimes as strings (or integers in nanoseconds) to remove float-comparison risk entirely:
   ```python
   def corpus_mtime_map(source_files: list[Path]) -> dict[str, int]:
       return {str(p.resolve()): p.stat().st_mtime_ns for p in source_files}
   ```
   Update `read_mtime_index` return type to `dict[str, int]` and cast accordingly.
2. Add a comment documenting the symlink sensitivity, or keep paths RELATIVE to the repo root (stored alongside `indexes_dir.parent`).

Low-severity but worth fixing during Phase 2 cleanup — the test fixture likely passes because tests use a fixed cwd and no symlinks; real cron-driven re-ingests might silently thrash.

---

## INFO

### IN-01: Bundler doesn't enforce "5 retrievers" count — the `retrievers: list[Retriever]` parameter lets the caller pass any number

**File:** `src/book_pipeline/rag/bundler.py:98-105`
**Issue:**
The docstring and threat model assume exactly 5 retrievers (historical, metaphysics, entity_state, arc_position, negative_constraint — 5 typed axes). The signature accepts `list[Retriever]` of any length. A mis-wired CLI (or a future test harness) could pass 3 retrievers and produce 4 events total (not 6). Downstream consumers lose axes silently.

**Fix:**
Add a validation assertion at `bundle()` entry:
```python
expected_axes = {"historical", "metaphysics", "entity_state",
                 "arc_position", "negative_constraint"}
provided = {r.name for r in retrievers}
if provided != expected_axes:
    raise ValueError(
        f"bundle() requires all 5 typed retrievers; "
        f"missing={expected_axes - provided}, "
        f"extra={provided - expected_axes}"
    )
```
Or document the contract explicitly in the docstring and rely on CLI wiring discipline. Keep it simple — an assertion near the module docstring's "exactly 6 events" claim makes the guarantee machine-checkable.

---

### IN-02: `_persist_conflicts` filename allows caller-controlled `ingestion_run_id` in the filename stem

**File:** `src/book_pipeline/rag/bundler.py:290-308`
**Issue:**
`scene_id` is int-cast-sanitized (T-02-05-01 mitigation). `self.ingestion_run_id`, however, is accepted verbatim from the constructor. Current production callers pass `report.ingestion_run_id` (shape `ing_<ts>_<hash>`) — safe. But a malicious or misconfigured caller could pass `../../etc/whatever` and the file write at line 308 would escape `conflicts_dir`. Defense-in-depth only; no current attack surface since all callers are trusted CLI code.

**Fix:**
Apply the same sanitization pattern used for `scene_id` — a cheap allowlist check at bundler construction time:
```python
import re
_INGEST_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

def __init__(self, ..., ingestion_run_id: str | None = None, ...):
    if ingestion_run_id is not None and not _INGEST_RUN_ID_RE.fullmatch(ingestion_run_id):
        raise ValueError(f"ingestion_run_id contains unsafe characters: {ingestion_run_id!r}")
    self.ingestion_run_id = ingestion_run_id
```

---

_Reviewed: 2026-04-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
