# Deferred Items — Phase 07 Execution

Out-of-scope discoveries logged during Phase 07 execution per <deviation_rules>
SCOPE BOUNDARY (only auto-fix issues directly caused by the current task).

## Plan 07-01 — Pre-existing ruff failures in src/book_pipeline/cli/draft.py

Discovered 2026-04-26 during Plan 07-01 lint run. NOT introduced by Phase 7;
last touched in commit `6e87f58 feat(dag): scene-kick recovery loop`.

- I001: Import block un-sorted at line ~58 (existing import order from prior
  feature work).
- I001: Import block un-sorted inside function body at line ~746 (local
  imports `import json as _json` + `from book_pipeline.interfaces.types
  import CriticIssue as _CriticIssue`).
- SIM105: try/except/pass that should be `contextlib.suppress(Exception)` at
  line ~837.
- 3 additional related issues at the same locations.

These are unrelated to physics package work. Recommend a Phase 5/Phase 6
follow-up plan or a docs(repo): chore commit to clean up.
