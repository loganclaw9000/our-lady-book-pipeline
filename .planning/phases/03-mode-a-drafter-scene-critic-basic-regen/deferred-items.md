# Deferred Items — Phase 03

Pre-existing issues discovered during Phase 03 plan execution that are NOT in
the scope of the current plan and are not caused by the current plan's
changes. Logged here for future-me; not auto-fixed per GSD SCOPE BOUNDARY.

## tests/rag/test_golden_queries.py::test_golden_queries_pass_on_baseline_ingest — FAILING

- **Discovered during:** Plan 03-06 regression run (2026-04-22).
- **Source:** Pre-existing — failure reproduces on `main` with all Plan 03-06
  changes stashed. Not caused by the regenerator kernel.
- **Symptom:** Golden-queries gate fails on baseline ingest. RAG test, likely
  tied to index state or BGE-M3 embedder drift (Phase 2 Plan 06 ownership).
- **Not fixed because:** Out of scope for Plan 03-06 (regenerator kernel).
  Rule: "Only auto-fix issues DIRECTLY caused by the current task's changes."
- **Owner:** Phase 2 Plan 06 or a later RAG maintenance plan. Not a Phase 3
  concern — regenerator does not exercise the RAG ingest path.
