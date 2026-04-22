---
phase: 02-corpus-ingestion-typed-rag
plan: 02
subsystem: corpus-ingestion
tags: [corpus, ingestion, lancedb, routing, event-logging, book-specifics, mtime-idempotency, w-3, w-4, w-5]
requirements_completed: [CORPUS-01]
dependency_graph:
  requires:
    - "02-01 (book_pipeline.rag — chunker, BgeM3Embedder, CHUNK_SCHEMA, open_or_create_table consumed here)"
    - "01-02 (book_pipeline.interfaces.types.Event — emitted at end of each non-skipped ingest)"
    - "01-05 (book_pipeline.observability.JsonlEventLogger + hash_text + event_id)"
    - "01-06 (import-linter contract extension policy + CLI-composition exemption precedent)"
  provides:
    - "book_pipeline.corpus_ingest — kernel-eligible ingestion package (router + mtime_index + ingester)"
    - "CorpusIngester.ingest(indexes_dir, *, force=False) -> IngestionReport (Pydantic, extra='forbid')"
    - "route_file_to_axis(path: Path) -> list[str] (filename-stem-based primary router; brief.md -> [historical, metaphysics]; handoff.md -> [])"
    - "AXIS_NAMES: Final[tuple[str, ...]] (frozen 5-name tuple)"
    - "mtime_index.json + resolved_model_revision.json persistence helpers (W-4 replaces YAML write-back)"
    - "book_pipeline.book_specifics.corpus_paths now exposes CORPUS_FILES and 10 filename constants (our-lady-of-champion-*.md)"
    - "book_pipeline.book_specifics.heading_classifier.BRIEF_HEADING_AXIS_MAP + classify_brief_heading (W-3: 12 explicit entries, no regex)"
    - "book-pipeline ingest CLI subcommand with --dry-run / --force / --indexes-dir / --json"
    - "Import-linter contract 1 extended: corpus_ingest in source_modules; CLI-composition exemption ignore_imports for cli.ingest -> {corpus_paths, heading_classifier}"
    - "Import-linter contract 2 extended: corpus_ingest in forbidden_modules"
    - "scripts/lint_imports.sh mypy target list extended with src/book_pipeline/corpus_ingest"
    - "Grep-fallback kernel list extended with corpus_ingest + documented exemption for cli/ingest.py"
    - ".gitignore excludes indexes/mtime_index.json + indexes/resolved_model_revision.json"
  affects:
    - "Plan 02-03/04/05 (retrievers): read from the 5 LanceDB tables this plan populates; filter on chunk metadata (rule_type, chapter, source_file, heading_path)"
    - "Plan 02-05 (bundler): consumes the resolved BGE-M3 revision_sha persisted to indexes/resolved_model_revision.json"
    - "Plan 02-06 (golden-query CI gate): baselines against the first ingestion_run Event + the BRIEF_HEADING_AXIS_MAP per-heading routing"
    - "Plan 06 (openclaw cron): compares corpus mtimes nightly; this plan's read_mtime_index / write_mtime_index is the contract"
    - "Plans 03+: CLI-composition exemption precedent (documented in pyproject.toml + test_import_contracts.py) is the pattern for drafter/critic/regenerator CLI seams"
tech-stack:
  added:
    - "Plan 02-02 adds no new runtime deps (uses only libraries already pinned by 02-01: lancedb, sentence-transformers, pyarrow, numpy, plus stdlib json/pathlib/datetime/time)"
    - "Test harness uses pyarrow.to_pylist() directly (no pandas) — pandas is not in dev deps; avoided adding it"
  patterns:
    - "CLI composition seam as the sanctioned book-specific <-> kernel bridge: book_pipeline.cli.ingest imports both book_pipeline.corpus_ingest (kernel) and book_pipeline.book_specifics.{corpus_paths,heading_classifier}. Every other kernel module stays ignorant of book_specifics. Documented as pyproject.toml ignore_imports entries + a specific-file exemption in the grep-fallback test."
    - "Mtime idempotency via indexes/mtime_index.json: {abs_path: mtime_float}. Equality-based skip with force-flag bypass. No partial-file detection (full rebuild on any change) — acceptable because corpus is ~250KB and full rebuild is <2 min."
    - "resolved_model_revision.json (W-4) replaces the STACK.md-rejected YAML write-back approach: {sha, model, resolved_at_iso}, gitignored, written only on successful ingest, read on subsequent ingests when config yaml has a TBD-* / latest-stable placeholder. config/rag_retrievers.yaml is READ-ONLY to the ingester (regression-guarded by test_w4_yaml_config_is_not_modified)."
    - "Multi-axis heading routing via injected classifier (W-3): kernel router returns multi-axis list for brief.md; ingester calls heading_classifier per chunk; classifier returns axis OR None (fall back to file's primary axis). Allowlist-only (no regex) in the book-specific classifier module."
    - "Event emission discipline: EXACTLY one Event per non-skipped ingest, emitted at the end after all writes. Skipped ingests (mtime unchanged) emit NO event — no-op is no-op all the way down to runs/events.jsonl."
    - "ingestion_run_id format: ing_<utc ts YYYYMMDDTHHMMSS + microseconds>Z_<8-char xxhash digest>. Hash input mixes sorted source paths + revision_sha + mtime snapshot + timestamp, guaranteeing uniqueness across rapid rebuilds (including back-to-back --force runs)."
    - "Deduplicated-flat source list: CorpusIngester iterates axis lists, dedupes by Path identity preserving insertion order. brief.md in both historical + metaphysics becomes one chunking pass; per-chunk axis assignment happens downstream."
    - "Chunk -> row mapping: all 7 Chunk fields + embedding[1024] float32 list, exactly matching CHUNK_SCHEMA. chapter column inserted as-is (may be None — pyarrow nullable int64)."
    - "Drop-and-recreate table semantics for rebuild: db.drop_table(axis) then open_or_create_table(axis). Schema enforcement from Plan 02-01 means any drift in the recreated schema fails closed."
key-files:
  created:
    - "src/book_pipeline/corpus_ingest/__init__.py (29 lines; re-exports CorpusIngester, IngestionReport, AXIS_NAMES, route_file_to_axis)"
    - "src/book_pipeline/corpus_ingest/router.py (62 lines; AXIS_NAMES + route_file_to_axis with 10-file routing table + unknown-stem ValueError)"
    - "src/book_pipeline/corpus_ingest/mtime_index.py (79 lines; read_mtime_index + write_mtime_index + corpus_mtime_map + W-4 read_resolved_model_revision + write_resolved_model_revision)"
    - "src/book_pipeline/corpus_ingest/ingester.py (268 lines; CorpusIngester class + IngestionReport Pydantic model + _EmbedderProtocol + _EventLoggerProtocol structural types)"
    - "src/book_pipeline/cli/ingest.py (170 lines; book-pipeline ingest subcommand; W-4 revision resolution; dry-run / force / indexes-dir / json flags)"
    - "src/book_pipeline/book_specifics/heading_classifier.py (83 lines; W-3 BRIEF_HEADING_AXIS_MAP with 12 explicit entries + classify_brief_heading matching full breadcrumb OR trailing segment)"
    - "tests/corpus_ingest/__init__.py (empty)"
    - "tests/corpus_ingest/test_corpus_paths.py (115 lines; 6 tests on the book_specifics CORPUS_FILES mapping)"
    - "tests/corpus_ingest/test_router.py (98 lines; 7 tests on file-stem routing incl. kernel-boundary grep)"
    - "tests/corpus_ingest/test_mtime_index.py (88 lines; 7 tests covering both mtime and W-4 resolved-revision persistence)"
    - "tests/corpus_ingest/test_ingester.py (465 lines; 11 tests — skip/rebuild/force/Event/W-3/W-4/W-5/truncate/handoff — with fake embedder + fake EventLogger + fake heading_classifier)"
    - "tests/corpus_ingest/fixtures/mini_corpus/{historical_seed,metaphysics_seed,brief_seed}.md (3 fixture md files with headings that exercise the W-3 multi-axis path)"
    - "tests/book_specifics/__init__.py (empty)"
    - "tests/book_specifics/test_heading_classifier.py (82 lines; 5 tests incl. the no-regex regression guard)"
  modified:
    - "src/book_pipeline/book_specifics/corpus_paths.py (stale `brief.md` etc. → `our-lady-of-champion-brief.md` for 10 constants; added CORPUS_FILES 5-axis mapping; added RELICS/GLOSSARY/MAPS/HANDOFF)"
    - "src/book_pipeline/cli/main.py (SUBCOMMAND_IMPORTS += book_pipeline.cli.ingest)"
    - "pyproject.toml (contract 1 source_modules += corpus_ingest; contract 1 ignore_imports gains 2 CLI-composition exemptions; contract 2 forbidden_modules += corpus_ingest)"
    - "scripts/lint_imports.sh (mypy targets += src/book_pipeline/corpus_ingest)"
    - ".gitignore (added indexes/mtime_index.json + indexes/resolved_model_revision.json)"
    - "tests/test_import_contracts.py (kernel_dirs += corpus_ingest + documented_exemptions set containing cli/ingest.py)"
key-decisions:
  - "(02-02) CLI-composition exemption as the only sanctioned bridge across the kernel/book_specifics line. Documented in 3 places: pyproject.toml ignore_imports (static analysis), test_import_contracts.py documented_exemptions set (grep fallback), and the ingest.py module docstring. Pattern is reusable for Phase 3+ drafter/critic/regenerator CLI seams."
  - "(02-02) resolved_model_revision.json under indexes/ (gitignored) replaces the plan-original YAML write-back (W-4). Eliminates the round-trip requirement that STACK.md used to reject ruamel.yaml. config/rag_retrievers.yaml is READ-ONLY to the ingester — regression-guarded by test_w4_yaml_config_is_not_modified."
  - "(02-02) BRIEF_HEADING_AXIS_MAP is an explicit allowlist with 12 hand-authored entries from inspection of the real brief.md — 4 metaphysics keys + 8 historical keys. W-3 revision forbids regex fallback; drift now surfaces as 'unmapped heading -> primary axis fallback' rather than silently misclassifying."
  - "(02-02) classify_brief_heading accepts either the full breadcrumb OR the trailing segment (split on ' > '), because the chunker can emit either shape depending on H1/H2 nesting. Covers the current chunker behavior and the most plausible near-future shape without pinning to one."
  - "(02-02) ingestion_run_id gets microsecond timestamp + mtime-snapshot hash mix so that back-to-back force rebuilds or the third-ingest-after-touch path always produce distinct IDs. Plan's original digest (sorted paths + revision_sha) is stable across mtime changes and would have collided on rapid rebuilds; the extra entropy closes that hole."
  - "(02-02) Tests use pyarrow.to_pylist() + table.count_rows() rather than to_pandas(). pandas is not in the project's dev deps and pulling it in for tests would be a 30MB+ transitive surcharge. The pyarrow-direct path produces the same assertions and keeps the dep surface minimal."
  - "(02-02) Kernel grep-fallback test extended with a documented_exemptions set (currently {cli/ingest.py}) rather than dropping cli/ from kernel_dirs. Keeping cli/ in kernel_dirs preserves coverage for cli/version.py, cli/smoke_event.py, cli/validate_config.py, cli/openclaw_cmd.py — only the one CLI file that legitimately bridges gets waived."
metrics:
  duration_minutes: 16
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 14
  files_modified: 6
  tests_added: 36  # 11 task-1 + 25 task-2 tests
  tests_passing: 167
commits:
  - hash: fa1adfc
    type: test
    summary: RED — failing tests for corpus_paths + heading_classifier (Task 1)
  - hash: 9d31263
    type: feat
    summary: GREEN — reconcile corpus_paths with our-lady-of-champion-* + W-3 heading_classifier
  - hash: e2af2a8
    type: test
    summary: RED — failing tests for corpus_ingest kernel (Task 2)
  - hash: 6d7d981
    type: feat
    summary: GREEN — CorpusIngester + mtime idempotency + book-pipeline ingest CLI
---

# Phase 2 Plan 2: Corpus Ingestion + Typed RAG Wave 2 Summary

**One-liner:** `book-pipeline ingest` lands as a kernel `corpus_ingest` package (router + mtime-index + 5-axis CorpusIngester) with a CLI composition seam, idempotent via mtime, emitting exactly one `role="corpus_ingester"` Event per non-skipped run, persisting the BGE-M3 revision SHA to a gitignored `indexes/resolved_model_revision.json` (W-4: no YAML write-back), routing brief.md per an explicit 12-entry `BRIEF_HEADING_AXIS_MAP` allowlist (W-3: no regex), and inserting rows that include the new `chapter` column (W-5) — all guarded by 36 new tests (167 total green) and an extended import-linter + grep-fallback that covers the new kernel module with a single documented CLI-composition exemption.

## Performance

- **Duration:** ~16 min
- **Started:** 2026-04-22T06:35:14Z
- **Completed:** 2026-04-22T06:51:04Z
- **Tasks:** 2 (Task 1: corpus_paths + W-3 heading_classifier, Task 2: CorpusIngester + mtime + CLI)
- **Files created:** 14
- **Files modified:** 6

## Accomplishments

- **CORPUS-01 shipped.** `book-pipeline ingest --help` works; `--dry-run --indexes-dir /tmp/...` prints the routing plan for all 10 bible files over 5 axes in <1 second.
- **Kernel discipline extended.** `book_pipeline.corpus_ingest` is a new kernel package covered by import-linter contracts 1 + 2, mypy, and the grep-fallback substring test. The single cross-boundary import (CLI composition) is documented in 3 places: pyproject ignore_imports, test_import_contracts.py documented_exemptions, and the ingest.py module docstring.
- **Idempotency + observability wired.** Mtime map under `indexes/mtime_index.json` drives skip-vs-rebuild; exactly one `role="corpus_ingester"` Event per non-skipped ingest with all six required `extra` fields (`ingestion_run_id`, `source_files`, `chunk_counts_per_axis`, `embed_model_revision`, `db_version`, `wall_time_ms`); skipped ingests emit zero Events. Test 2 of the ingester asserts this directly.
- **W-4 revision persistence replaces YAML write-back.** `indexes/resolved_model_revision.json` is the new SHA anchor; `config/rag_retrievers.yaml` is not modified by the ingester and a dedicated regression test asserts its bytes are unchanged pre/post ingest.
- **W-3 heading classifier explicit.** `BRIEF_HEADING_AXIS_MAP` has 12 hand-authored entries (4 metaphysics + 8 historical) drawn from the real `brief.md`. Regex-absence is asserted by a dedicated test.
- **W-5 chapter column round-trip.** Rows inserted into LanceDB carry the `chapter` column (may be None for non-chapter fixtures); test_w5 asserts the column is present.

## Task Commits

1. **Task 1 RED** — `fa1adfc` (test): failing tests for corpus_paths reconciliation + W-3 heading_classifier (11 tests across 2 files).
2. **Task 1 GREEN** — `9d31263` (feat): 10 `our-lady-of-champion-*.md` constants + CORPUS_FILES 5-axis mapping + HANDOFF exclusion + explicit W-3 allowlist classifier.
3. **Task 2 RED** — `e2af2a8` (test): 25 failing tests across 3 files — router, mtime_index, ingester (+ mini_corpus fixture).
4. **Task 2 GREEN** — `6d7d981` (feat): book_pipeline.corpus_ingest kernel package (router + mtime_index + ingester) + `book-pipeline ingest` CLI + pyproject/lint/gitignore extensions + grep-fallback exemption.

**Plan metadata commit** follows this SUMMARY in a separate `docs(02-02): complete corpus-ingestion-typed-rag Wave 2 plan` commit.

## Routing table as shipped (for Plan 06 golden-query CI baseline)

| Filename stem (after stripping `our-lady-of-champion-` prefix) | Axes returned by `route_file_to_axis` |
|---|---|
| `brief` | `["historical", "metaphysics"]` (multi-axis; per-heading split via `classify_brief_heading`) |
| `engineering` | `["metaphysics"]` |
| `pantheon` | `["entity_state"]` |
| `secondary-characters` | `["entity_state"]` |
| `outline` | `["arc_position"]` |
| `known-liberties` | `["negative_constraint"]` |
| `relics` | `["metaphysics"]` |
| `glossary` | `["historical"]` |
| `maps` | `["historical"]` |
| `handoff` | `[]` (meta-document; never ingested) |

## BRIEF_HEADING_AXIS_MAP (W-3; Plan 06 golden queries reference these)

12 explicit entries hand-authored from inspection of `~/Source/our-lady-of-champion/our-lady-of-champion-brief.md`:

**Metaphysics axis (4 entries):**
- `The Metaphysics (Lock This First)` → `metaphysics`
- `Reliquary Mecha (Spanish / European / Mediterranean)` → `metaphysics`
- `Teōmecahuītlī (Mexica God-Engines)` → `metaphysics`
- `Engagement Doctrine (What Battles Look Like)` → `metaphysics`

**Historical axis (8 entries):**
- `Premise` → `historical`
- `The Three POVs` → `historical`
- `Historical Framework (Condensed)` → `historical`
- `Thematic Spine` → `historical`
- `The Two-Thirds Revelation` → `historical`
- `The Climax` → `historical`
- `Things to Avoid` → `historical`
- `Deliverables Required Before Drafting` → `historical`

Unmapped brief.md headings default to the file's primary axis (`historical`, per `CORPUS_FILES["historical"]` ordering). `classify_brief_heading` accepts either the full breadcrumb OR the trailing segment when split on ` > ` — works with current chunker breadcrumb shape + near-future alternatives without pinning to one.

## BGE-M3 revision SHA (W-4 persistence — reproducibility trail)

- **Target path:** `indexes/resolved_model_revision.json` (gitignored via the new .gitignore entry)
- **Shape:** `{"sha": "<resolved-sha>", "model": "BAAI/bge-m3", "resolved_at": "<ISO UTC>"}`
- **Resolution policy (W-4; implemented in `book_pipeline.cli.ingest._resolve_revision`):**
  - If `config/rag_retrievers.yaml` has `embeddings.model_revision` == `"latest-stable"` OR matches `/^TBD-.*/`, load `indexes/resolved_model_revision.json`; if it exists, use its `sha`. If absent (first run), pass `revision=None` to `BgeM3Embedder` → embedder resolves HEAD from HfApi → ingester persists the result to `resolved_model_revision.json` for future runs.
  - Otherwise, pass the yaml value verbatim (it's the pin).
- **First real ingest still pending** — will happen when `uv run book-pipeline ingest --force` runs against the real corpus on a box with GPU + HF access. Test suite uses a `_FakeEmbedder` with `revision_sha="fake-sha-abc123"` so the persistence path + shape are validated without the 2GB model download.
- **config/rag_retrievers.yaml is NOT modified by the ingester.** `test_w4_yaml_config_is_not_modified` asserts byte-identical pre/post ingest.

## ingestion_run_id format (Plan 05 bundler stamps the ContextPack with this)

`ing_<YYYYMMDDTHHMMSS><microseconds>Z_<8-char xxhash>`

Examples:
- `ing_20260422T064312125473Z_4f9a1c8b`
- `ing_20260422T064315981102Z_d2e7b490`

The microsecond precision + hash-of-(sorted paths + revision_sha + mtime snapshot + timestamp) input guarantees uniqueness across back-to-back force rebuilds (test_force_flag_bypasses_mtime_check asserts two IDs differ for rapid consecutive force runs).

## First ingestion's chunk_counts_per_axis (baseline for Plan 06 CI)

Not captured yet — this plan ships the ingester and the test fixture; the real first ingest against `~/Source/our-lady-of-champion/` has not been run (it requires a GPU + HF download of BGE-M3 weights, which is deferred to the operator per Plan 02-01 Deferred Issue #2). Plan 02-06 will run the real ingest, capture chunk_counts_per_axis, and freeze it as the CI baseline.

**Fixture-driven chunk counts** (test mini_corpus.md set, ~500 words × 3 files):
- `historical`: non-zero (brief_seed fallback headings + historical_seed)
- `metaphysics`: non-zero (brief_seed Metaphysics/Engine headings + metaphysics_seed)
- `entity_state`, `arc_position`, `negative_constraint`: 0 (empty source lists in the fixture)

## CLI-composition import-linter exemptions (verbatim — Plan 03/04 precedent)

```toml
# In pyproject.toml, contract 1:
# CLI-composition exemption (Phase 2 Plan 02): book_pipeline.cli.ingest is the
# documented composition seam that wires kernel (corpus_ingest) with
# book-specific CORPUS_FILES + heading_classifier. Every other kernel module
# stays ignorant of book_specifics.
ignore_imports = [
    "book_pipeline.cli.ingest -> book_pipeline.book_specifics.corpus_paths",
    "book_pipeline.cli.ingest -> book_pipeline.book_specifics.heading_classifier",
]
```

And in `tests/test_import_contracts.py::test_kernel_does_not_import_book_specifics`:

```python
# Phase 2 plan 02: CLI-composition exemption per pyproject ignore_imports.
documented_exemptions = {
    pathlib.Path("src/book_pipeline/cli/ingest.py"),
}
```

**Precedent for Plans 03+:** when a drafter/critic/regenerator CLI command needs to pull a book-specific path (e.g., `voice_pin.yaml` or entity-state directories), add:
1. A matching `ignore_imports` entry under contract 1.
2. The new cli file to `documented_exemptions` in the grep-fallback.
3. A short rationale in the file's module docstring referencing this plan.

## Files Created/Modified

### Created

- `src/book_pipeline/corpus_ingest/__init__.py` — kernel re-exports (CorpusIngester, IngestionReport, AXIS_NAMES, route_file_to_axis).
- `src/book_pipeline/corpus_ingest/router.py` — AXIS_NAMES frozen tuple + `route_file_to_axis` (stem → list[axis]).
- `src/book_pipeline/corpus_ingest/mtime_index.py` — mtime idempotency JSON + W-4 resolved_model_revision helpers.
- `src/book_pipeline/corpus_ingest/ingester.py` — CorpusIngester class + IngestionReport Pydantic model + structural Protocols.
- `src/book_pipeline/cli/ingest.py` — `book-pipeline ingest` subcommand (CLI composition seam).
- `src/book_pipeline/book_specifics/heading_classifier.py` — W-3 explicit BRIEF_HEADING_AXIS_MAP + classify_brief_heading (no regex).
- `tests/corpus_ingest/__init__.py` — empty package marker.
- `tests/corpus_ingest/test_corpus_paths.py` — 6 tests.
- `tests/corpus_ingest/test_router.py` — 7 tests.
- `tests/corpus_ingest/test_mtime_index.py` — 7 tests.
- `tests/corpus_ingest/test_ingester.py` — 11 tests (fake embedder / fake event logger / fake classifier).
- `tests/corpus_ingest/fixtures/mini_corpus/historical_seed.md` + `metaphysics_seed.md` + `brief_seed.md` — 3 fixture markdown files.
- `tests/book_specifics/__init__.py` + `tests/book_specifics/test_heading_classifier.py` — 5 tests (W-3 invariants + no-regex regression guard).
- `.planning/phases/02-corpus-ingestion-typed-rag/02-02-SUMMARY.md` — this file.

### Modified

- `src/book_pipeline/book_specifics/corpus_paths.py` — all 10 filename constants now use `our-lady-of-champion-<stem>.md`; new CORPUS_FILES mapping; RELICS/GLOSSARY/MAPS/HANDOFF defined; HANDOFF excluded from any axis.
- `src/book_pipeline/cli/main.py` — SUBCOMMAND_IMPORTS += `book_pipeline.cli.ingest`.
- `pyproject.toml` — contract 1 source_modules += `book_pipeline.corpus_ingest`; contract 1 ignore_imports += 2 CLI-composition exemptions; contract 2 forbidden_modules += `book_pipeline.corpus_ingest`.
- `scripts/lint_imports.sh` — mypy targets += `src/book_pipeline/corpus_ingest`.
- `.gitignore` — `indexes/mtime_index.json` + `indexes/resolved_model_revision.json`.
- `tests/test_import_contracts.py` — kernel_dirs += `corpus_ingest`; `documented_exemptions = {cli/ingest.py}`.

## Decisions Made

Decisions are captured verbatim in the frontmatter's `key-decisions` field and will be extracted to STATE.md by the state-update step. Summary:

1. CLI-composition exemption is the only sanctioned bridge and is documented in 3 places.
2. W-4 resolved_model_revision.json replaces YAML write-back; config yaml is read-only to ingester.
3. W-3 BRIEF_HEADING_AXIS_MAP is explicit allowlist with 12 entries; no regex fallback.
4. classify_brief_heading accepts full breadcrumb OR trailing segment for chunker-shape robustness.
5. ingestion_run_id uses microsecond TS + mtime-snapshot hash for rapid-rebuild uniqueness.
6. Tests use pyarrow.to_pylist() + count_rows(), not pandas (avoids dev-deps bloat).
7. Grep-fallback kept cli/ in kernel_dirs with a narrow per-file exemption rather than dropping cli/.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Ruff violations blocking the aggregate gate on first run of Task 1.**
- **Found during:** Task 1 GREEN verify (first run of `bash scripts/lint_imports.sh`).
- **Issue:** Stray blank line between `from __future__ import` and `import pytest`; stray `f` prefix on a string literal without placeholders in `test_corpus_paths.py`.
- **Fix:** Removed the stray blank line and `f` prefix. No behavior change.
- **Files modified:** `tests/corpus_ingest/test_corpus_paths.py`.
- **Verification:** `uv run ruff check` clean; aggregate gate green.
- **Committed in:** `9d31263` (Task 1 GREEN).

**2. [Rule 1 - Bug] ingestion_run_id collided on back-to-back force rebuilds.**
- **Found during:** Task 2 GREEN verify (`test_third_ingest_after_touch_rebuilds_and_new_run_id` and `test_force_flag_bypasses_mtime_check` both failed on the first GREEN attempt).
- **Issue:** The plan's original digest input (sorted paths + revision_sha) was stable across mtime changes and timestamp-matched runs. Two consecutive ingests within the same second against the same file set produced IDENTICAL `ingestion_run_id` values. The tests that assert "new ID after rebuild" correctly caught this.
- **Fix:** Extended the id-generation to mix in (a) microseconds in the timestamp component and (b) the current mtime snapshot in the hash input + timestamp itself. Guarantees uniqueness even for back-to-back `--force` runs. See `CorpusIngester._make_ingestion_run_id` docstring.
- **Files modified:** `src/book_pipeline/corpus_ingest/ingester.py`.
- **Verification:** All 11 ingester tests pass; rapid-rebuild tests produce distinct IDs.
- **Committed in:** `6d7d981` (Task 2 GREEN).

**3. [Rule 3 - Blocking] pandas not installed — tests using `.to_pandas()` couldn't run.**
- **Found during:** Task 2 GREEN verify (4 ingester tests crashed in `pyarrow/pandas-shim.pxi:_check_import` with `ModuleNotFoundError: No module named 'pandas'`).
- **Issue:** My initial test drafts used lancedb's `Table.to_pandas()` API to assert row-level content. Project dev deps do not include pandas (intentionally — the production code only uses pyarrow). Pulling pandas in for tests would be a 30MB+ transitive surcharge.
- **Fix:** Switched to `Table.to_arrow().to_pylist()` for row enumeration and `Table.count_rows()` for row counts. Same assertions, no new dep.
- **Files modified:** `tests/corpus_ingest/test_ingester.py` (3 test bodies).
- **Verification:** All affected tests pass; project dev deps unchanged.
- **Committed in:** `6d7d981` (Task 2 GREEN).

**4. [Rule 2 - Missing critical] Grep-fallback test didn't cover the new kernel module.**
- **Found during:** Task 2 GREEN verify (`tests/test_import_contracts.py::test_kernel_does_not_import_book_specifics` failed).
- **Issue:** The Phase 1 belt-and-suspenders static grep test in `test_import_contracts.py` asserts that no kernel source file contains the literal `book_specifics`. With `corpus_ingest` now a kernel package, it needed to be in `kernel_dirs`. Additionally, my initial ingester/router/__init__ docstrings mentioned `book_specifics` in prose — those needed to be rewritten to avoid the substring (same pattern Plan 02-01 used for `rag/__init__.py`). AND, `cli/ingest.py` legitimately imports both book_specifics sub-modules (documented CLI composition seam), so it needed a narrow per-file exemption rather than dropping cli/ from kernel_dirs (which would have removed coverage for the 4 other cli files).
- **Fix:** (a) Added `Path("src/book_pipeline/corpus_ingest")` to `kernel_dirs`. (b) Added a `documented_exemptions = {Path("src/book_pipeline/cli/ingest.py")}` set to the test and skip files in it. (c) Rewrote docstrings in `corpus_ingest/ingester.py` and `corpus_ingest/__init__.py` and `corpus_ingest/router.py` to avoid the literal substring while still documenting the boundary (using "book-specific" or "book-specifics package" phrasing instead).
- **Files modified:** `tests/test_import_contracts.py`, `src/book_pipeline/corpus_ingest/__init__.py`, `src/book_pipeline/corpus_ingest/ingester.py`, `src/book_pipeline/corpus_ingest/router.py`.
- **Verification:** `uv run pytest tests/ -x` green (167 passed).
- **Committed in:** `6d7d981` (Task 2 GREEN).

**5. [Rule 3 - Blocking] More minor ruff violations after auto-fix: `match="[Uu]nknown"` raw-string warning.**
- **Found during:** Task 2 GREEN verify (after auto-fix pass).
- **Issue:** `RUF043` — pattern passed to `match=` contains regex metacharacters but is not a raw string.
- **Fix:** Added `r` prefix: `match=r"[Uu]nknown"`.
- **Files modified:** `tests/corpus_ingest/test_router.py`.
- **Verification:** Aggregate gate green.
- **Committed in:** `6d7d981` (Task 2 GREEN).

---

**Total deviations:** 5 auto-fixed (3 Rule 3 blocking, 1 Rule 1 bug in my initial ingester draft, 1 Rule 2 missing critical on the grep-fallback).

**Impact on plan:** All five fixes were necessary to reach the plan's own success criteria. Fix #2 (ingestion_run_id uniqueness) is a semantic improvement over the plan's literal digest input — documented here so Plan 05 bundler knows the id format it's stamping. No scope creep.

## Issues Encountered

- One minor friction point during development: PreToolUse read-before-edit hooks fired a few times on files I had just created via Write. The runtime treats Write + subsequent Edit on the same file as permitted (read-state is established by the Write), but the hook noise didn't affect any actual operations — all edits landed.

## Authentication Gates

None. No new secret scope; no LLM calls. The ingester uses a local embedder (BGE-M3 via sentence-transformers) and the CLI talks only to local disk + the existing JsonlEventLogger handle.

## Deferred Issues

1. **Real end-to-end `book-pipeline ingest --force` against `~/Source/our-lady-of-champion/`** — requires GPU + HF download of the 2GB BGE-M3 weights. Not blocking for Plan 02-03/04/05 test development (they can use `_FakeEmbedder` the same way this plan does). Plan 02-06 will run the real ingest, capture `chunk_counts_per_axis` as the golden-query CI baseline, and commit the resolved BGE-M3 SHA into `indexes/resolved_model_revision.json`.

2. **T-02-02-04 (partial-state window on crash):** Acceptance criterion in the plan's threat register was "wrap 5-table rebuild in try/except; restore prior mtime_index.json on failure." Current implementation writes mtime_index.json AFTER tables are populated + resolved_model_revision.json is written, so a crash mid-rebuild leaves the prior mtime_index.json intact and the next run re-ingests. The try/except safety net is NOT explicitly implemented — but the failure mode is equivalent (next run sees "mtime changed, rebuild" because the stored mtime map was never updated). Plan 02-06 CI can harden this if needed.

3. **lancedb `table_names()` deprecation** — still deferred (inherited from Plan 02-01). Ingester adds another call site; all use the same deprecated API for the same reason (`list_tables()` returns a ListTablesResponse whose `__contains__` misbehaves in 0.30.x).

## Known Stubs

None. Every public surface has a real implementation:

- `route_file_to_axis` really enumerates the 10 stems and returns real axis lists.
- `CorpusIngester.ingest` really reads files, chunks them, embeds, writes rows to LanceDB, and emits a populated Event.
- `classify_brief_heading` really looks up the explicit table (no placeholder returns).
- `IngestionReport` is a real Pydantic model with `extra="forbid"` — not a dataclass stub.
- The `_FakeEmbedder` / `_FakeEventLogger` in the test suite are explicitly test doubles (prefixed `_Fake`) and are scoped to `tests/corpus_ingest/test_ingester.py` — they do not leak into the production surface.

The `TODO(Plan 02+)` comment inherited from `rag/lance_schema.py` (about the `list_tables()` API migration) applies to the new ingester call site as well. Still a forward-looking migration note, not a current stub.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 7 threats covered:

- **T-02-02-01** (W-4 resolved_model_revision.json tamper): mitigated as planned. File is gitignored + local-only; HF will raise on bad SHA.
- **T-02-02-02** (Event emits full paths): accepted as planned. Paths are local-disk-only per OBS-01 contract.
- **T-02-02-03** (chunker hang on unknown file): mitigated as planned. `route_file_to_axis` raises `ValueError` on unknown stems before chunker is called.
- **T-02-02-04** (partial-state crash window): partially mitigated by ordering (see Deferred Issues #2 above). The try/except-wrap hardening is deferred to Plan 02-06 CI.
- **T-02-02-05** (kernel corpus_ingest leaks book_specifics import): mitigated. Contract 1 covers `corpus_ingest` in source_modules; only `cli.ingest` has the documented exemption; the grep-fallback belt catches substring-level drift.
- **T-02-02-06** (ingestion without Event): mitigated. `test_first_ingest_populates_tables_and_emits_one_event` + `test_second_ingest_with_no_changes_skips_and_no_event` assert the exact-1-or-0-event contract.
- **T-02-02-07** (W-4 regression — YAML write-back re-introduction): mitigated. `test_w4_yaml_config_is_not_modified` asserts byte-identical pre/post ingest. Plan's grep acceptance criterion `grep -c "yaml\\.dump\\|yaml.safe_dump" src/book_pipeline/corpus_ingest/ingester.py == 0` also holds.

## Verification Evidence

Plan `<success_criteria>` + task `<acceptance_criteria>` coverage:

| Criterion | Status | Evidence |
|---|---|---|
| 5 LanceDB tables populated on first non-skipped run | PASS | Test `test_first_ingest_populates_tables_and_emits_one_event` asserts all 5 axes appear in `chunk_counts_per_axis`; W-3 test reads rows back from metaphysics + historical tables via `to_arrow()` |
| `runs/events.jsonl` ingestion_run line with required `extra` fields | PASS | Test asserts `role="corpus_ingester"` + `model="BAAI/bge-m3"` + 6 `extra` keys present |
| Idempotency: second run with no changes is a no-op | PASS | `test_second_ingest_with_no_changes_skips_and_no_event` |
| Force flag triggers rebuild with new run_id | PASS | `test_force_flag_bypasses_mtime_check` |
| Touch → rebuild with new run_id | PASS | `test_third_ingest_after_touch_rebuilds_and_new_run_id` |
| Import-linter still enforces ADR-004; documented exemptions | PASS | `bash scripts/lint_imports.sh` green; pyproject.toml has both exemptions with comment |
| W-4: resolved_model_revision.json persists; yaml not modified | PASS | `test_w4_resolved_model_revision_json_written` + `test_w4_yaml_config_is_not_modified` |
| W-3: brief.md multi-axis uses classifier, not regex | PASS | `test_heading_classifier_module_has_no_regex` + `test_w3_multi_axis_file_routes_by_heading_classifier` |
| W-5: inserted rows include chapter column | PASS | `test_w5_chapter_column_present_in_rows` (asserts key exists in `to_arrow().to_pylist()` row dicts) |
| `uv run book-pipeline ingest --help` exits 0 + lists flags | PASS | Verified manually; output shows `--dry-run`, `--force`, `--indexes-dir`, `--json`, `-h` |
| `uv run book-pipeline ingest --dry-run` prints routing plan | PASS | Verified manually against real corpus; 9 unique files (brief.md deduped) printed across 5 axes |
| `grep -c "book_pipeline.corpus_ingest" pyproject.toml` >= 2 | PASS | 4 occurrences (contract 1 source + contract 2 forbidden + 2 phase-2-done comments) |
| `grep` for each CLI-composition exemption | PASS | Both `cli.ingest -> book_specifics.corpus_paths` and `-> heading_classifier` present |
| `grep "src/book_pipeline/corpus_ingest" scripts/lint_imports.sh` | PASS | Line added to mypy target list |
| `grep "indexes/resolved_model_revision.json" .gitignore` | PASS | Both json patterns added |
| `grep -c "yaml\\.safe_dump\\|yaml.dump" src/book_pipeline/corpus_ingest/ingester.py == 0` | PASS | 0 matches (W-4 regression guard) |
| All tests pass | PASS | 167 passed (was 131 pre-plan); 36 added (11 Task 1 + 25 Task 2) |
| Aggregate lint gate green | PASS | 2 contracts kept, ruff clean, mypy 62 files clean |

## Self-Check: PASSED

Artifact verification (files on disk):

- FOUND: `src/book_pipeline/corpus_ingest/__init__.py`
- FOUND: `src/book_pipeline/corpus_ingest/router.py`
- FOUND: `src/book_pipeline/corpus_ingest/mtime_index.py`
- FOUND: `src/book_pipeline/corpus_ingest/ingester.py`
- FOUND: `src/book_pipeline/cli/ingest.py`
- FOUND: `src/book_pipeline/book_specifics/heading_classifier.py`
- FOUND: `tests/corpus_ingest/__init__.py`
- FOUND: `tests/corpus_ingest/test_corpus_paths.py`
- FOUND: `tests/corpus_ingest/test_router.py`
- FOUND: `tests/corpus_ingest/test_mtime_index.py`
- FOUND: `tests/corpus_ingest/test_ingester.py`
- FOUND: `tests/corpus_ingest/fixtures/mini_corpus/historical_seed.md`
- FOUND: `tests/corpus_ingest/fixtures/mini_corpus/metaphysics_seed.md`
- FOUND: `tests/corpus_ingest/fixtures/mini_corpus/brief_seed.md`
- FOUND: `tests/book_specifics/__init__.py`
- FOUND: `tests/book_specifics/test_heading_classifier.py`
- FOUND: `pyproject.toml` has `corpus_ingest` in both contracts + 2 ignore_imports
- FOUND: `scripts/lint_imports.sh` mypy list includes `src/book_pipeline/corpus_ingest`
- FOUND: `.gitignore` excludes both `indexes/mtime_index.json` + `indexes/resolved_model_revision.json`

Commit verification on `main` branch of `/home/admin/Source/our-lady-book-pipeline/`:

- FOUND: `fa1adfc test(02-02): RED — failing tests for corpus_paths + heading_classifier (Task 1)`
- FOUND: `9d31263 feat(02-02): GREEN — reconcile corpus_paths with our-lady-of-champion-* names + W-3 heading_classifier`
- FOUND: `e2af2a8 test(02-02): RED — failing tests for corpus_ingest kernel (Task 2)`
- FOUND: `6d7d981 feat(02-02): GREEN — CorpusIngester + mtime idempotency + book-pipeline ingest CLI`

All four per-task commits (2 RED + 2 GREEN, per TDD) landed on `main`. Aggregate gate + full test suite green.

## Next Plan Readiness

- **Plan 02-03 (historical/metaphysics retrievers) can start immediately.** The 5 LanceDB tables are creatable via `open_or_create_table` (Plan 02-01 primitive); their schema is stable; the ingester populates them against CHUNK_SCHEMA. Plan 02-03 queries those tables with filters on `rule_type`, `heading_path`, `chapter`.
- **Plan 02-04 (arc_position/entity_state retrievers)** can also start — the `chapter` column (W-5) is present on every row, so exact-equality filters will work.
- **Plan 02-05 (negative_constraint + bundler)** consumes the same CHUNK_SCHEMA; no surprises.
- **Plan 02-06 (RAG-04 golden-query CI gate)** will run the first real ingest against `~/Source/our-lady-of-champion/`, baseline `chunk_counts_per_axis` + `indexes/resolved_model_revision.json`, and gate future ingests against that baseline.
- **No blockers.** CORPUS-01 moves from open to complete.

---
*Phase: 02-corpus-ingestion-typed-rag*
*Plan: 02*
*Completed: 2026-04-22*
