---
phase: 01-foundation-observability-baseline
plan: 02
subsystem: protocol-interfaces-and-event-schema
tags: [protocol, pep-544, pydantic, stubs, event-schema, obs-01, foundation]
requirements_completed: [FOUND-04, OBS-01]
dependency_graph:
  requires:
    - "01-01 (book_pipeline package + src-layout + uv-managed venv)"
  provides:
    - "12 @runtime_checkable Protocols importable from book_pipeline.interfaces"
    - "13 Stub implementations importable from book_pipeline.stubs"
    - "OBS-01 Event Pydantic model — FROZEN at schema_version=1.0 (18 fields)"
    - "15 cross-Protocol Pydantic BaseModels (SceneRequest, ContextPack, DraftRequest/Response, CriticRequest/Response/Issue, RegenRequest, SceneStateRecord, EntityCard, Retrospective, ThesisEvidence, RetrievalHit, RetrievalResult, Event)"
    - "SceneState Enum (9 members) + transition() pure helper"
    - "Import-time structural-typing assertions (_: Protocol = StubX()) — Protocol drift fails fast"
  affects:
    - "Plan 01-05 (EventLogger concrete impl consumes Event + EventLogger Protocol verbatim)"
    - "Plan 01-06 (import-linter kernel/book_specifics rule uses interfaces/ as kernel boundary)"
    - "Phase 2 RAG-01/CORPUS-02 (Retriever, ContextPackBundler, EntityExtractor concrete impls)"
    - "Phase 3 DRAFT-01/CRITIC-01/REGEN-01/LOOP-01 (Drafter, Critic, Regenerator, Orchestrator, ChapterAssembler concrete impls)"
    - "Phase 4 CRITIC-02/RETRO-01/THESIS-01 (chapter-level Critic, RetrospectiveWriter, ThesisMatcher concrete impls)"
    - "Phase 5 DIGEST-01 (DigestGenerator concrete impl)"
tech_stack:
  added:
    - "typing.Protocol + @runtime_checkable (PEP 544) — pure stdlib, no new deps"
  patterns:
    - "One module per Protocol under src/book_pipeline/interfaces/"
    - "Structural-typing self-check at stub import time: `_: Protocol = StubX()` at module scope — module fails to import if Protocol shape drifts"
    - "Generic payload dicts use `dict[str, object]` (not bare `dict`) so mypy --strict stays clean"
    - "Plan-specified legacy pattern `class SceneState(str, Enum)` preserved (noqa UP042) rather than upgrading to StrEnum — stable MRO for downstream code"
key_files:
  created:
    - "src/book_pipeline/interfaces/__init__.py"
    - "src/book_pipeline/interfaces/types.py"
    - "src/book_pipeline/interfaces/scene_state_machine.py"
    - "src/book_pipeline/interfaces/retriever.py"
    - "src/book_pipeline/interfaces/context_pack_bundler.py"
    - "src/book_pipeline/interfaces/drafter.py"
    - "src/book_pipeline/interfaces/critic.py"
    - "src/book_pipeline/interfaces/regenerator.py"
    - "src/book_pipeline/interfaces/chapter_assembler.py"
    - "src/book_pipeline/interfaces/entity_extractor.py"
    - "src/book_pipeline/interfaces/retrospective_writer.py"
    - "src/book_pipeline/interfaces/thesis_matcher.py"
    - "src/book_pipeline/interfaces/digest_generator.py"
    - "src/book_pipeline/interfaces/orchestrator.py"
    - "src/book_pipeline/interfaces/event_logger.py"
    - "src/book_pipeline/stubs/__init__.py"
    - "src/book_pipeline/stubs/retriever.py"
    - "src/book_pipeline/stubs/context_pack_bundler.py"
    - "src/book_pipeline/stubs/drafter.py"
    - "src/book_pipeline/stubs/critic.py"
    - "src/book_pipeline/stubs/regenerator.py"
    - "src/book_pipeline/stubs/chapter_assembler.py"
    - "src/book_pipeline/stubs/entity_extractor.py"
    - "src/book_pipeline/stubs/retrospective_writer.py"
    - "src/book_pipeline/stubs/thesis_matcher.py"
    - "src/book_pipeline/stubs/digest_generator.py"
    - "src/book_pipeline/stubs/scene_state_machine.py"
    - "src/book_pipeline/stubs/orchestrator.py"
    - "src/book_pipeline/stubs/event_logger.py"
    - "tests/test_types.py"
    - "tests/test_interfaces.py"
  modified: []
decisions:
  - "Event schema v1.0 is now FROZEN — 18 fields, plan 05 consumes Event verbatim. Later phases may ADD OPTIONAL fields only; renaming or removing fields bumps schema_version."
  - "Generic payload dicts annotated as dict[str, object] (not bare dict). This is the minimum change needed for mypy --strict to pass while preserving the plan's 'free-form JSON-shaped payload' semantics for fields like Event.caller_context, Event.extra, generation_config, chapter_context, EntityCard.state, Retrospective.candidate_theses."
  - "SceneState kept as `class SceneState(str, Enum)` with noqa UP042 rather than upgrading to StrEnum — changing the MRO would be visible to downstream isinstance-chained code (e.g., `isinstance(state, str)` still needs to work trivially)."
  - "Stubs verify structural typing at import time via `_: Protocol = StubX()` at module scope. If a Protocol's shape drifts in a later refactor, stub imports fail before tests even run."
  - "StubSceneStateMachine is a uniform wrapper around the pure-function transition helper — not a Protocol stub. Kept for parity with the 12 other stubs (so the 'Phase 1 has 13 stubs' count holds) and to demonstrate the uniform constructor pattern for callers."
metrics:
  duration_minutes: 18
  completed_date: 2026-04-21
  tasks_completed: 2
  files_created: 31
  files_modified: 0
  tests_added: 55
  tests_passing: 59
commits:
  - hash: 6b7a137
    type: test
    summary: RED — failing tests for interfaces.types Pydantic models + Event schema
  - hash: 99815cc
    type: feat
    summary: GREEN — Pydantic type contracts + frozen OBS-01 Event schema
  - hash: 810a50b
    type: test
    summary: RED — failing tests for 12 Protocols + 13 stubs (isinstance + NotImplementedError)
  - hash: a18b48e
    type: feat
    summary: GREEN — 12 Protocol interfaces + 13 stub implementations
---

# Phase 1 Plan 2: Protocol Interfaces + Frozen Event Schema Summary

**One-liner:** 12 `@runtime_checkable` PEP-544 Protocols with companion `NotImplementedError` stubs that self-verify structural typing at import time, plus 15 cross-Protocol Pydantic BaseModels including the now-frozen OBS-01 Event schema (18 fields, `schema_version="1.0"`) that plan 05 will consume verbatim.

## What Shipped

A complete kernel-extraction-ready contract surface for the pipeline:

- **12 Protocol modules** under `src/book_pipeline/interfaces/`: Retriever, ContextPackBundler, Drafter, Critic, Regenerator, ChapterAssembler, EntityExtractor, RetrospectiveWriter, ThesisMatcher, DigestGenerator, Orchestrator, EventLogger. Each uses `@runtime_checkable` so `isinstance()` works, carries a module + class docstring stating pre/post conditions and event-emit expectations, and imports only from `interfaces.types`.
- **13 Stub modules** under `src/book_pipeline/stubs/`: one per Protocol plus `StubSceneStateMachine` (wrapper around the pure `transition` helper for uniformity). Every stub method raises `NotImplementedError` with a message pointing to the later-phase plan that implements it (e.g. `"concrete impl lands in Phase 3 (DRAFT-01)"`). Every non-`SceneStateMachine` stub module ends with `_: Protocol = StubX()` — an import-time structural-typing check that makes Protocol drift fail before tests run.
- **15 Pydantic BaseModels + 1 Enum + 1 helper function** under `interfaces/types.py` and `interfaces/scene_state_machine.py`: SceneRequest, RetrievalHit, RetrievalResult, ContextPack, DraftRequest, DraftResponse, CriticIssue, CriticRequest, CriticResponse, RegenRequest, SceneState (Enum, 9 members), SceneStateRecord, EntityCard, Retrospective, ThesisEvidence, Event, transition().
- **55 new tests** across `tests/test_types.py` (21) and `tests/test_interfaces.py` (34). All 59 tests in the repo pass (4 CLI + 21 types + 34 interfaces).
- **mypy --strict clean** on 29 source files (`uv run mypy src/book_pipeline/interfaces src/book_pipeline/stubs`).
- **ruff + ruff-format clean**.

## The Frozen OBS-01 Event Schema (v1.0)

This is the contract plan 05 (EventLogger concrete implementation) consumes. The 18 fields:

```python
class Event(BaseModel):
    schema_version: str = "1.0"
    event_id: str                                       # xxhash(ts + role + caller + prompt_sha)
    ts_iso: str                                         # RFC3339
    role: str                                           # drafter|critic|regenerator|entity_extractor|retrospective_writer|thesis_matcher|digest_generator
    model: str                                          # concrete model id
    prompt_hash: str                                    # xxhash of prompt text
    input_tokens: int
    cached_tokens: int = 0
    output_tokens: int
    latency_ms: int
    temperature: float | None = None
    top_p: float | None = None
    caller_context: dict[str, object] = {}              # {module, function, scene_id?, chapter_num?}
    output_hash: str                                    # xxhash of output text
    mode: str | None = None                             # "A"|"B"|None
    rubric_version: str | None = None                   # populated for critic events
    checkpoint_sha: str | None = None                   # populated for Mode-A drafter (V-3 pitfall)
    extra: dict[str, object] = {}                       # escape hatch
```

**Freeze rule (per CONTEXT.md D-06):** later phases MAY add optional fields; they MUST NOT rename or remove existing fields. Migration path: bump `schema_version`.

`tests/test_types.py::test_event_has_18_fields_total` asserts `set(Event.model_fields.keys()) == <the 18 names>` — regressions blow up the test suite.

## The 12 Protocols and Their Downstream Consumers

| # | Protocol              | Concrete-impl plan           | File                                                      |
|---|-----------------------|------------------------------|-----------------------------------------------------------|
| 1 | Retriever             | Phase 2 RAG-01               | `src/book_pipeline/interfaces/retriever.py`               |
| 2 | ContextPackBundler    | Phase 2 RAG-01               | `src/book_pipeline/interfaces/context_pack_bundler.py`    |
| 3 | Drafter               | Phase 3 DRAFT-01 / DRAFT-02  | `src/book_pipeline/interfaces/drafter.py`                 |
| 4 | Critic                | Phase 3 CRITIC-01 (scene) / Phase 4 CRITIC-02 (chapter) | `src/book_pipeline/interfaces/critic.py` |
| 5 | Regenerator           | Phase 3 REGEN-01             | `src/book_pipeline/interfaces/regenerator.py`             |
| 6 | ChapterAssembler      | Phase 3 LOOP-01              | `src/book_pipeline/interfaces/chapter_assembler.py`       |
| 7 | EntityExtractor       | Phase 2 CORPUS-02            | `src/book_pipeline/interfaces/entity_extractor.py`        |
| 8 | RetrospectiveWriter   | Phase 4 RETRO-01             | `src/book_pipeline/interfaces/retrospective_writer.py`    |
| 9 | ThesisMatcher         | Phase 4 THESIS-01            | `src/book_pipeline/interfaces/thesis_matcher.py`          |
| 10| DigestGenerator       | Phase 5 DIGEST-01            | `src/book_pipeline/interfaces/digest_generator.py`        |
| 11| Orchestrator          | Phase 3 LOOP-01              | `src/book_pipeline/interfaces/orchestrator.py`            |
| 12| EventLogger           | Phase 1 plan 05 (OBS-01)     | `src/book_pipeline/interfaces/event_logger.py`            |

The 13th "interface" — SceneStateMachine — is intentionally NOT a Protocol: it's a Pydantic model (`SceneStateRecord`) + Enum (`SceneState`, 9 members) + pure-Python helper (`transition`). Kept under `interfaces/` for cohesion per ARCHITECTURE.md §2.7.

## The Stub Pattern (for future plan authors)

Every Protocol stub under `src/book_pipeline/stubs/` follows this shape:

```python
# src/book_pipeline/stubs/drafter.py
"""Stub Drafter — NotImplementedError. Concrete impl lands in Phase 3 (DRAFT-01 / DRAFT-02)."""
from __future__ import annotations

from book_pipeline.interfaces.drafter import Drafter
from book_pipeline.interfaces.types import DraftRequest, DraftResponse


class StubDrafter:
    """Structurally satisfies Drafter Protocol. NotImplementedError on every call."""

    mode: str = "A"

    def draft(self, request: DraftRequest) -> DraftResponse:
        raise NotImplementedError(
            "StubDrafter.draft: concrete impl lands in Phase 3 (DRAFT-01 for Mode A, "
            "DRAFT-02 for Mode B)."
        )


# Verify structural typing at import time (fails early if Protocol changes).
_: Drafter = StubDrafter()
```

**Why the import-time `_: Protocol = StubX()` assertion:** structural typing failures would otherwise surface only in tests that happen to exercise the affected code path. With the assertion at module scope, any Protocol signature change that desyncs from its stub causes `import book_pipeline.stubs` itself to fail — impossible to miss during a refactor.

The 13th stub (`StubSceneStateMachine`) is a uniform method-wrapper around the pure-function `transition` helper. It exists for API parity (so callers can write `StubSceneStateMachine().transition(...)` the same way they'd call other stubs) and to keep the "Phase 1 exit has 13 stubs" count truthful. It does NOT carry the `_: Protocol = ...` guard because SceneStateMachine isn't a Protocol.

## Verification Evidence

All plan acceptance criteria:

| Criterion                                                                  | Status | Evidence                                                                                                              |
| -------------------------------------------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------- |
| types.py contains all 15 Pydantic models + Enum                            | PASS   | `grep -c "^class" src/book_pipeline/interfaces/types.py` = 15 BaseModels + 1 Enum                                     |
| Event has all 18 OBS-01 fields                                             | PASS   | `test_event_has_18_fields_total` asserts `set(Event.model_fields.keys())` matches the 18-name spec                    |
| SceneState has exactly 9 members                                           | PASS   | `test_scene_state_has_9_members` + `test_scene_state_values_are_snake_case`                                           |
| 12 Protocol files exist with @runtime_checkable + docstrings               | PASS   | `ls src/book_pipeline/interfaces/*.py \| wc -l` = 14 (types + scene_state_machine + 12 protocols); `test_protocol_has_docstring` parametrized over all 12 |
| 13 stub files with NotImplementedError + import-time structural typing     | PASS   | `ls src/book_pipeline/stubs/*.py` = 14 (init + 13 stubs); `_: Protocol = StubX()` present in 12 files                 |
| book_pipeline.interfaces re-exports all 12 Protocols + types               | PASS   | `test_all_protocols_importable_from_package`, `test_all_protocol_names_in_package_all`                                |
| `isinstance(StubX(), X)` True for all 12 pairs                             | PASS   | `test_stub_satisfies_protocol_isinstance` parametrized over 12 pairs — all green                                      |
| Stubs raise NotImplementedError with informative messages                  | PASS   | 6 direct per-stub tests; StubDrafter asserts regex `"Phase 3"`, StubEventLogger asserts regex `"plan 05"`             |
| `uv run mypy src/book_pipeline/interfaces src/book_pipeline/stubs` exits 0 | PASS   | "Success: no issues found in 29 source files"                                                                         |
| `uv run pytest tests/test_types.py tests/test_interfaces.py` all pass      | PASS   | 55 tests passed (21 + 34)                                                                                             |
| Full suite regression check                                                | PASS   | 59 tests passed (4 CLI + 21 types + 34 interfaces) — no plan 01-01 regressions                                        |
| ruff check                                                                 | PASS   | "All checks passed!" on 31 touched files                                                                              |
| ruff format --check                                                        | PASS   | "31 files already formatted"                                                                                          |

Smoke-test per plan `<verify>` block:

```
$ uv run python -c "from book_pipeline.interfaces import Drafter, Critic, Retriever, ContextPackBundler, Regenerator, ChapterAssembler, EntityExtractor, RetrospectiveWriter, ThesisMatcher, DigestGenerator, Orchestrator, EventLogger, SceneState, SceneStateRecord; print('13 interfaces OK')"
13 interfaces OK
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking issue] Generic `dict` annotations tightened to `dict[str, object]` for mypy --strict.**

- **Found during:** Task 1 (types.py mypy run)
- **Issue:** Plan `<interfaces>` block specifies bare `dict` on payload fields (e.g. `caller_context: dict = Field(default_factory=dict)`). The plan's own acceptance criterion requires `uv run mypy src/book_pipeline/interfaces/types.py` to exit 0, but mypy --strict emits `type-arg: Missing type arguments for generic type "dict"` for bare `dict`.
- **Fix:** Changed bare `dict` → `dict[str, object]` (9 occurrences across Event, SceneStateRecord, EntityCard, Retrospective, DraftRequest, CriticRequest, RetrievalHit, and type-only class-level annotations in stubs). Preserved every field name, field type identity, and structural behavior. `dict[str, object]` is strictly more informative than bare `dict` and accepts the same JSON-shaped payloads.
- **Files modified:** `src/book_pipeline/interfaces/types.py`, `src/book_pipeline/interfaces/orchestrator.py`, `src/book_pipeline/interfaces/thesis_matcher.py`, `src/book_pipeline/interfaces/digest_generator.py`, and matching stubs.
- **Commits:** `99815cc` (types.py), `a18b48e` (rest).

**2. [Rule 3 — Blocking issue] `SceneState(str, Enum)` kept; UP042 suppressed with justification.**

- **Found during:** Task 1 ruff run.
- **Issue:** Ruff UP042 suggests upgrading `class SceneState(str, Enum)` to `class SceneState(StrEnum)`. The plan `<interfaces>` block explicitly specifies the `(str, Enum)` form, and the plan's wording ("Do NOT add extra fields. Do NOT rename fields.") rhymes with "don't mutate class hierarchy either." Upgrading to `StrEnum` would also change MRO visible to downstream code (any `isinstance(state, str)` check would behave subtly differently across Python versions — `StrEnum` was added in 3.11 with different semantics than the `(str, Enum)` pattern).
- **Fix:** Added `# noqa: UP042` with a comment explaining the rationale. No functional change.
- **Files modified:** `src/book_pipeline/interfaces/types.py`.
- **Commit:** `a18b48e`.

**3. [Style] Ruff-format pass applied across 31 touched files.**

- **Found during:** Task 2 style validation.
- **Issue:** ruff-format wanted a blank line after `"""docstring"""` before `from __future__ import annotations` (PEP 257 black-compatible), and some string concatenations could be replaced with iterable unpacking (`[*list, item]` instead of `list + [item]`).
- **Fix:** `uv run ruff format` auto-applied formatting. `uv run ruff check --fix` applied safe lint fixes (I001 import sort, UP017 UTC alias). Tests re-run and pass.
- **Files modified:** 31 files.
- **Commit:** `a18b48e` (same commit as Task 2 GREEN — the reformat was run before committing).

**4. [Quality] Redundant `# noqa: F401` de-duplicated in tests/test_interfaces.py.**

- **Found during:** Task 2 ruff run after autofix merged import blocks.
- **Issue:** Ruff's import-sort autofix merged two separate import blocks in `test_all_protocols_importable_from_package` and left a duplicated `# noqa: F401  # noqa: F401` comment.
- **Fix:** Manually cleaned up to single `# noqa: F401` with a proper docstring explaining what the test proves.
- **Commit:** `a18b48e`.

No Rule 4 (architectural) deviations. No checkpoints reached.

## Authentication Gates

None. This plan is pure Python type definitions — no network, no filesystem writes outside the repo, no secrets required.

## Deferred Issues

None. All tests and all tooling passes. Every acceptance criterion has an automated check.

## Known Stubs

**Intentional stubs by design** (this plan's deliverable IS the stub surface):

All 13 stub classes under `src/book_pipeline/stubs/` raise `NotImplementedError`. This is FOUND-04's explicit requirement: "Stub implementations satisfy `isinstance(stub, Protocol)` structural checks" — they exist to let Phase 3/4/5 code be written and tested against the contract before the concrete impls arrive.

Each stub's error message points at the plan that will implement it (e.g. `"concrete impl lands in Phase 3 (DRAFT-01)"`), so a runtime error is self-describing. Each Protocol module docstring documents its concrete-impl phase too.

Nothing is wired to user-visible UI surface in this plan, so there are no user-facing stubs that could leak into production.

## Threat Flags

No new security-relevant surface introduced. Per the plan's own `<threat_model>`:

- **T-02-01 (Tampering — Event schema drift) — MITIGATED:** `Event.schema_version = "1.0"` declared; `test_event_has_18_fields_total` blocks silent field additions/removals; plan 05 (next Wave 2 executor) will import Event verbatim. Add-only for optional fields per CONTEXT.md D-06.
- **T-02-02 (Repudiation — Stub NotImplementedError silently swallowed) — ACCEPTED:** stubs are import-time-visible (`_: Protocol = StubX()`), runtime errors are self-describing ("concrete impl lands in Phase X"). Production code cannot silently fall through to a stub.

No new threat flags surfaced during execution.

## Self-Check: PASSED

Artifact verification (files on disk):

- FOUND: `src/book_pipeline/interfaces/__init__.py` (29-symbol `__all__`)
- FOUND: `src/book_pipeline/interfaces/types.py` (15 BaseModels + SceneState Enum + `Event` with 18 fields)
- FOUND: `src/book_pipeline/interfaces/scene_state_machine.py` (re-exports SceneState/SceneStateRecord + `transition()`)
- FOUND: 12 Protocol files: `retriever.py`, `context_pack_bundler.py`, `drafter.py`, `critic.py`, `regenerator.py`, `chapter_assembler.py`, `entity_extractor.py`, `retrospective_writer.py`, `thesis_matcher.py`, `digest_generator.py`, `orchestrator.py`, `event_logger.py`
- FOUND: 13 stub files under `src/book_pipeline/stubs/` (12 Protocol stubs + `StubSceneStateMachine`) + `stubs/__init__.py` exporting all 13
- FOUND: `tests/test_types.py` (21 tests) and `tests/test_interfaces.py` (34 tests)

Commit verification:

- FOUND: `6b7a137` (test RED — types)
- FOUND: `99815cc` (feat GREEN — types)
- FOUND: `810a50b` (test RED — interfaces)
- FOUND: `a18b48e` (feat GREEN — interfaces + stubs)

All 4 per-task commits landed on `main` branch of `/home/admin/Source/our-lady-book-pipeline/`.
