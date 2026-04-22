---
phase: 02-corpus-ingestion-typed-rag
fixed_at: 2026-04-22T09:59:00Z
review_path: .planning/phases/02-corpus-ingestion-typed-rag/02-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
deferred: 3
status: all_fixed
tests_before: 255 passed, 1 failed (pre-existing golden_queries)
tests_after: 267 passed, 1 failed (pre-existing golden_queries)
new_tests: 12
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-04-22T09:59 UTC
**Source review:** `.planning/phases/02-corpus-ingestion-typed-rag/02-REVIEW.md`
**Iteration:** 1
**Project root:** `/home/admin/Source/our-lady-book-pipeline`

## Summary

- Findings in scope (MUST + SHOULD): 4
- Fixed: 4 (1 blocker, 3 warnings)
- Skipped: 0
- Deferred (per fix-plan directive): 3 (WR-04, IN-01, IN-02)

**Test counts:**

| | Before | After | Delta |
|---|---|---|---|
| Passed (non-golden) | 249 | 261 | +12 |
| Passed (golden_queries) | 6 | 6 | 0 |
| Failed | 1 (pre-existing) | 1 (pre-existing, unchanged) | 0 |
| **Total new tests added** | | | **+12** |

The one pre-existing failure (`test_golden_queries_pass_on_baseline_ingest`)
is orthogonal to this fix set — it asserts that a negative-constraint
retriever doesn't surface forbidden "Adjusted Historical" heading chunks
from `our-lady-of-champion-known-liberties.md`. That's a baseline
ingestion-data issue (corpus routing / heading-classifier tuning), not
a bundler/ingester/conflict-detector bug.

---

## Fixed Issues

### BL-01: Bundler emits exactly 6 events even on exception paths

**Files modified:**
- `src/book_pipeline/rag/bundler.py`
- `tests/rag/test_bundler.py`

**Commit:** `d4f35ac`

**Applied fix:**
Wrapped the ENTIRE per-retriever emission path (retrieval + metadata +
Event construction + `_emit`) inside an outer try/except. The previous
code only caught exceptions from `retriever.retrieve()`, so later
raisers (`rr.model_dump_json()`, `Event(...)` validation, or
`JsonlEventLogger.emit()` disk-full / permission errors) aborted the
bundle loop mid-iteration and produced 1-5 events instead of the
promised 6.

On any failure the fallback synthesizes a minimal
`role="retriever"` Event with
`extra={"status": "error", "error_class": ..., "error_message": ...}`
so downstream always sees 5 retriever events + 1 bundler event per
scene_id, preserving the docstring invariant that Phase 3 critic depends
on. A last-resort swallow on the fallback `_emit` prevents an
emit-failure from aborting the bundle loop entirely.

**Regression coverage (3 new tests):**
- `test_bundler_emits_exactly_6_events_even_when_retriever_raises` —
  `retriever.retrieve()` raises `RuntimeError("GPU OOM")`; asserts 6 events
  with degraded error metadata on the failing axis.
- `test_bundler_emits_exactly_6_events_when_serialization_raises` —
  `RetrievalResult.model_dump_json()` raises (monkey-patched instance);
  asserts 6 events, error metadata present.
- `test_bundler_emits_exactly_6_events_when_event_construction_raises` —
  `book_pipeline.rag.bundler.Event` patched to raise once; asserts 6
  events still emit via the fallback construction path.

---

### WR-02: ArcPositionRetriever reindex preserves state on embedding failure

**Files modified:**
- `src/book_pipeline/rag/retrievers/arc_position.py`
- `tests/rag/test_arc_position_retriever.py`

**Commit:** `456996f`

**Applied fix:**
Reordered `reindex()` to the assemble-then-swap pattern: parse outline,
embed texts, and build the full row list IN MEMORY first; only then
`tbl.delete("true") + tbl.add(rows)`. If embedding raises (GPU OOM, HF
cache miss, network hiccup on revision resolution), the existing table
remains intact instead of being silently wiped.

Also moved the `if not beats: return` guard BEFORE the delete call as
defense-in-depth: an outline that parses to zero beats must not erase
prior valid state.

**Regression coverage (2 new tests):**
- `test_arc_position_reindex_preserves_state_if_embedding_fails` — custom
  `_RaisingEmbedder` raises on second call; first `reindex()` populates
  12 rows, second `reindex()` raises and table still has 12 rows with
  identical beat_id set.
- `test_arc_position_reindex_empty_beats_preserves_existing_rows` —
  retarget to an outline that parses to zero beats; table retains 12
  rows.

**Note on related mtime-invalidation escape hatch:** the review's
Option 2 (CLI catching `arc.reindex()` exceptions and invalidating
`mtime_index.json`) was NOT applied at the CLI layer — it is
redundant now that reindex is crash-safe at the source. If the CLI
caller still wants belt-and-suspenders, Phase 2 Plan 06 already has
the WR-03 marker file which covers the cross-command crash case.

---

### WR-03: Ingester crash-safety with in-progress marker

**Files modified:**
- `src/book_pipeline/corpus_ingest/ingester.py`
- `tests/corpus_ingest/test_ingester.py`

**Commit:** `8d8b01f`

**Applied fix:**
Added two marker files under `indexes/`:

1. **`.ingest_in_progress`** — written at the START of a non-skipped
   ingest (before any table drop), removed only after
   `mtime_index.json` is written. If the process dies mid-ingest (OOM,
   SIGINT, disk-full), the marker survives. On subsequent runs the
   ingester checks for the marker FIRST and forces a full re-ingest
   regardless of mtime match, closing the pre-fix race where a crash
   between table-drop and mtime-write left the index permanently
   empty.

2. **`.last_ingestion_ok`** — written after a clean ingest. Contains
   `{completed_at_iso, ingestion_run_id}` for Phase 3 diagnostics
   ("when did the last ingest complete?"). Readable without any
   LanceDB connection so openclaw health checks can stat it cheaply.

**Regression coverage (3 new tests):**
- `test_ingester_writes_in_progress_marker_and_removes_it_on_success` —
  happy-path: markers transition correctly (in-progress removed,
  last-ok present, payload shape valid).
- `test_ingester_recovers_from_crash_between_drop_and_mtime_write` —
  THE pre-fix pathological state: fabricate a crashed run by writing
  a stale `.ingest_in_progress` marker plus an mtime_index that
  already matches current corpus mtimes. Next ingest must still
  re-run (`skipped=False`, one Event emitted, tables populated).
- `test_ingester_skips_cleanly_when_no_marker_and_no_changes` —
  happy-path idempotency guard: marker-check path doesn't falsely
  trigger re-ingest when there's no marker.

---

### WR-01: Conflict detector stoplist + saturation warning

**Files modified:**
- `src/book_pipeline/rag/conflict_detector.py`
- `tests/rag/test_conflict_detector.py`
- `tests/rag/test_bundler.py` (updated W-1 fixture to match tightened regex)

**Commit:** `5b89996`

**Applied fix:**
Three tightening measures on the forcing-function regexes:

1. **Drop bare `|in` from `_LOCATION_PHRASE_RE`** — it was catastrophically
   promiscuous ("in Him", "in March", "in Christ" all became "locations").
   Now requires an explicit spatial verb: `is at | arrives at | stays at |
   returns to`. The review explicitly accepted this recall trade-off
   ("Losing recall on 'in Tenochtitlan' is acceptable at Phase 2 given the
   false-positive cost.").

2. **Possession stoplist** — reject captured values in
   `{been, a, an, the, his, her, its, my, our, your, their, some, no, any,
   all, become}` (case-insensitive). Kills "has been" / "has a" /
   "holds his" false positives without touching legitimate possession
   phrases like "carries the sword" or "possesses the blade".

3. **Location stoplist** — reject captured values whose lowercased first
   token is a month, weekday, or title
   (`{january..december, monday..sunday, lord, lady, father, mother, king,
   queen, sir, dame, saint}`). Matches against the first token so
   multi-word phrases like "Lord Cortés" are suppressed at token 0.

4. **Saturation warning** — if `len(conflicts) > 50` for a single
   `detect_conflicts` call, a WARNING is logged via
   `logging.getLogger("book_pipeline.rag.conflict_detector")`. Log-only
   (no exception); bundler event still emits normally. Threshold chosen
   generously to avoid spamming on genuinely contentious scenes while
   still catching degraded-signal runs.

**Fixture updates:**
- `test_detect_conflicts_w1_nahuatl_entity_list_catches_motecuhzoma`:
  changed "Motecuhzoma in Tenochtitlan" → "Motecuhzoma stays at
  Tenochtitlan" to match the tightened regex.
- `test_g_w1_entity_list_catches_motecuhzoma_conflict` (bundler):
  same fixture update.

**Regression coverage (4 new tests):**
- `test_conflict_detector_ignores_possession_stopwords` — "has been",
  "has a", "holds his" across two retrievers → 0 possession conflicts
  for the entity (pre-fix would have produced 1-2 spurious).
- `test_conflict_detector_ignores_calendar_titles_as_locations` —
  "stays at March", "returns to Lord Cortés" → neither "March" nor
  "Lord" leaks into conflict values.
- `test_conflict_detector_saturation_warning_fires` — synthesize 60
  entities with location disagreements; assert WARNING log record
  with "saturation" substring.
- `test_conflict_detector_saturation_warning_silent_under_threshold` —
  single Andrés/Cempoala-vs-Cerro-Gordo scenario below threshold;
  assert NO saturation warning.

---

## Deferred Findings (per fix-plan directive)

The orchestrator's fix plan explicitly instructed these to be deferred,
with reasoning. Capturing that reasoning here so the next reviewer /
Phase 3 consumer has full context.

### WR-04: `mtime_index.py` float-precision type contradiction

**Deferred reason (from fix plan):** `st_mtime` gives millisecond-level
precision which is adequate for nightly cron; migrating to `st_mtime_ns`
would require replaying fixture `expected_chunks` because the
deterministic `_make_ingestion_run_id` hash incorporates the mtime map.

**Track as:** Phase 6 thesis. Symlink-heavy setups may still thrash if
the CLI runs from different cwd between cron invocations — a comment
in `mtime_index.py` would help. Not blocking for Phase 2 close.

### IN-01: Bundler doesn't enforce "5 retrievers" count

**Deferred reason (from fix plan):** the runtime-checkable
`Retriever` Protocol already catches wrong-type arguments at `bundle()`
entry; adding a length check is belt-and-suspenders. Cost of the
check is tiny but not strictly necessary for the 6-event invariant
now that BL-01 is fixed (the invariant is per-retriever, not
per-"expected count of retrievers").

**Track as:** add to the bundler docstring that the contract is "N
retrievers in, N+1 events out". If the CLI wires the wrong count we
catch it at composition, not bundle-time.

### IN-02: `_persist_conflicts` ingestion_run_id path traversal defense

**Deferred reason (from fix plan):** internal-only caller surface
today; all CLI callers pass `ing_<ts>_<hash>` which is already
allowlist-shaped. Revisit if the bundler is ever exposed via an
HTTP/API endpoint where `ingestion_run_id` becomes user-controlled.

**Track as:** add to Phase 3 threat-model review. Trivial to add the
`_INGEST_RUN_ID_RE` regex guard then.

---

## Commits (in order)

1. `d4f35ac` — fix(02): BL-01 — bundler emits exactly 6 events even on exception paths
2. `456996f` — fix(02): WR-02 — arc_position reindex preserves state on embedding failure
3. `8d8b01f` — fix(02): WR-03 — ingester crash-safety with in-progress marker
4. `5b89996` — fix(02): WR-01 — conflict detector stoplist + saturation warning

Each commit is self-contained: source + tests together, atomic, green
on its own test subset before moving to the next.

---

## Verification summary

- **Per-fix verification (Tier 1 + Tier 2):** every fix had its targeted
  test file rerun and passed before commit.
- **Per-fix syntax check (Tier 2):** `python ast.parse` clean on all
  modified source files.
- **Full non-golden suite post-fixes:** 261 passed, 216 warnings, 37.07s.
- **Golden-queries suite:** unchanged — same pre-existing failure
  (`forbidden-chunk leaks`), which is a corpus/routing issue, NOT a
  regression from this fix set.

---

_Fixed: 2026-04-22T09:59 UTC_
_Fixer: Claude Opus 4.7 (gsd-code-fixer, 1M context)_
_Iteration: 1_
