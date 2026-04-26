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

## Plan 07-01 latent — `DraftRequest.model_rebuild()` not auto-triggered when only `interfaces.types` is imported

**RESOLVED 2026-04-26 by Plan 07-03 (fix candidate 1).** `interfaces/types.py`
now calls `_rebuild_for_physics_forward_ref()` opportunistically at module-tail
in a `try/except ImportError: pass` block. Under normal install conditions
both packages are present so the rebuild succeeds and DraftRequest is fully
defined for any caller that imports `interfaces.types` alone. Previously-failing
tests no longer surface `pydantic.errors.PydanticUserError: DraftRequest is not
fully defined` (verified via `pytest tests/ -m "not slow"` — zero matches for
"not fully defined"). Remaining test failures in `tests/drafter/test_mode_a.py`
and elsewhere have DIFFERENT root causes (FakeVllmClient signature drift on
`min_tokens`; SHA-mismatch in vllm_client tests; ChapterState semantic mismatch
in dag tests) — these are pre-existing pre-Plan-07-03 issues out of SCOPE
BOUNDARY for Plan 07-03's surface area. Original detail below.

---

## Plan 07-01 latent — DraftRequest model_rebuild (HISTORICAL — see RESOLVED above)

Discovered 2026-04-26 during Plan 07-02 full-test-suite check. NOT introduced
by Plan 07-02. Plan 07-01 added `DraftRequest.scene_metadata: SceneMetadata |
None = None` as a forward-reference field; `_rebuild_for_physics_forward_ref()`
is called from `book_pipeline.physics.__init__.py`. Tests that import
`DraftRequest` WITHOUT also triggering a `book_pipeline.physics` import (e.g.
via `cli.draft` chain) hit:

```
pydantic.errors.PydanticUserError: `DraftRequest` is not fully defined; you
should define `SceneMetadata`, then call `DraftRequest.model_rebuild()`.
```

Affected tests at HEAD~3 (Plan 07-01) — verified pre-existing:
- `tests/drafter/test_mode_a.py` (multiple tests)
- `tests/drafter/test_vllm_client.py` (boot_handshake_*)
- `tests/cli/test_draft_loop.py` (test_E_r_exhaustion_hard_blocked,
  test_F_drafter_block_hard_blocked, test_G_critic_block_hard_blocked,
  test_H_b3_invariant_voice_pin_sha_equals_checkpoint_sha,
  test_K_regen_word_count_drift_counts_toward_R)
- `tests/cli/test_draft_spend_cap.py` (4 tests)
- `tests/chapter_assembler/test_dag.py` (test_B_chapter_critic_fail_no_canon_commit,
  test_J_chapter_fail_all_non_specific_remains_chapter_fail)
- `tests/integration/test_chapter_dag_end_to_end.py` (3 scene + mid-chapter pin-upgrade)
- `tests/integration/test_scene_loop_escalation.py` (4 parametrized branches)

Fix candidates (Plan 07-03 should pick one):
1. `interfaces/types.py` calls `_rebuild_for_physics_forward_ref()` opportunistically
   in a `try/except ImportError: pass` block at import time.
2. Add a per-test `import book_pipeline.physics` at the affected test files'
   conftest level.
3. Move `SceneMetadata` import out of TYPE_CHECKING and accept the
   import-linter ignore_imports edge as runtime-resolved (current
   ignore_imports already covers this edge).

Plan 07-02 leaves these failing (out of scope per SCOPE BOUNDARY); the
Plan 07-02-scoped acceptance gate (`uv run pytest
tests/rag/test_continuity_bible_retriever.py
tests/rag/test_bundler_seven_events.py
tests/corpus_ingest/test_canonical_quantities.py -m "not slow" -x`) is green.

## Plan 07-05 — Pre-existing ChapterState DAG-test failures

Discovered 2026-04-26 during Plan 07-05 fast-test regression check. NOT
introduced by Plan 07-05. Reproduces on `git stash` against current main:

- `tests/chapter_assembler/test_dag.py::test_B_chapter_critic_fail_no_canon_commit`
- `tests/chapter_assembler/test_dag.py::test_J_chapter_fail_all_non_specific_remains_chapter_fail`

Both assert `state == CHAPTER_FAIL` but receive `CHAPTER_FAIL_SCENE_KICKED`
— scene-kick state was added in Plan 05-02 LOOP-04 and the DAG tests were
never updated to the new sub-state semantics. Out of scope for Plan 07-05;
the Plan 07-05 acceptance gate (physics + chapter_assembler/quote_normalizer
+ critic pre-LLM short-circuits + scene_buffer integration) is green.
