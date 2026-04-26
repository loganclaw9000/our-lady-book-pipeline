---
phase: 07-narrative-physics-engine-codified-storytelling-atomics-enfor
plan: 03
subsystem: physics
tags: [drafter-integration, pre-flight-gates, canon-bible, jinja2-template, canonical-stamp, beat-directive, pov-lock, motivation, ownership, treatment, quantity]
dependency-graph:
  requires:
    - book_pipeline.physics.schema (Plan 07-01)
    - book_pipeline.physics.locks (Plan 07-01)
    - book_pipeline.physics.gates.base (Plan 07-01)
    - book_pipeline.interfaces.types.RetrievalResult (Phase 1 frozen)
    - book_pipeline.interfaces.event_logger.EventLogger (Phase 1 frozen)
    - book_pipeline.drafter.mode_a.ModeADrafter (Plan 03-04)
    - book_pipeline.drafter.templates.mode_a.j2 (Plan 03-04)
  provides:
    - book_pipeline.physics.canon_bible.CanonBibleView + build_canon_bible_view + CanonicalQuantityRow
    - book_pipeline.physics.gates.{pov_lock,motivation,ownership,treatment,quantity}.check (5 pure-fn gates)
    - book_pipeline.physics.gates.run_pre_flight composer (short-circuit on first high-severity FAIL)
    - ModeADrafter ctor extension (3 new optional kwargs: physics_pre_flight, physics_canonical_stamp_factory, physics_beat_directive_factory)
    - ModeADrafterBlocked accepted-reason set extension (physics_pre_flight_fail + pov_lock_violated reservation) with runtime _ACCEPTED_REASONS frozenset enforcement (BLOCKER #4)
    - mode_a.j2 template extension (canonical_stamp + beat_directive top-of-system blocks)
    - DraftRequest forward-ref opportunistic rebuild (deferred-items.md item RESOLVED)
  affects:
    - src/book_pipeline/interfaces/types.py — opportunistic _rebuild_for_physics_forward_ref() at module-tail (fix candidate 1)
    - .planning/phases/07-narrative-physics-engine-codified-storytelling-atomics-enfor/deferred-items.md — Plan 07-01 DraftRequest item RESOLVED
tech-stack:
  added: []
  patterns:
    - Pure-function gate signature `check(stub, ...deps) -> GateResult` (analog: drafter/preflag.py)
    - Sequential composer with short-circuit on first severity='high' (analog: rag/bundler.py loop)
    - Pydantic BaseModel value object (CanonicalQuantityRow) with extra="forbid", frozen=True
    - Per-bundle local state (NO module-scope cache decorator per Pitfall 11)
    - Module-level frozenset + runtime ValueError validator (defense in depth on free-form str fields)
    - contextlib.suppress(ImportError) for opportunistic forward-ref resolution (clean lint surface)
    - Jinja2 conditional `{% if %}` blocks for empty-stamp/empty-directive clean degradation
key-files:
  created:
    - src/book_pipeline/physics/canon_bible.py (130 LOC; CanonBibleView reader + CanonicalQuantityRow + build_canon_bible_view)
    - src/book_pipeline/physics/gates/pov_lock.py (52 LOC; lock breach -> high; override -> pass with audit detail)
    - src/book_pipeline/physics/gates/motivation.py (60 LOC; anchored line-start regex stub-leak guard)
    - src/book_pipeline/physics/gates/ownership.py (78 LOC; owns/do_not_renarrate overlap -> high; cross-scene unresolved -> mid)
    - src/book_pipeline/physics/gates/treatment.py (37 LOC; defense-in-depth Treatment enum membership)
    - src/book_pipeline/physics/gates/quantity.py (94 LOC; iterates canon_bible.iter_canonical_quantities() — Warning #2 mitigation)
    - tests/physics/test_canon_bible.py (162 LOC; 8 tests)
    - tests/physics/test_gates.py (303 LOC; 14 tests including Test 7b synthetic-6th-row long-tail)
    - tests/drafter/test_mode_a_physics_header.py (414 LOC; 12 tests)
  modified:
    - src/book_pipeline/physics/__init__.py (re-export CanonBibleView family + run_pre_flight)
    - src/book_pipeline/physics/gates/__init__.py (run_pre_flight composer; per-gate Event emission via emit_gate_event)
    - src/book_pipeline/drafter/mode_a.py (3 new ctor kwargs + pre-flight call BEFORE Jinja2 render + canonical_stamp/beat_directive factories + _ACCEPTED_REASONS frozenset + ValueError validator)
    - src/book_pipeline/drafter/templates/mode_a.j2 (canonical_stamp + beat_directive top-of-system blocks; T-07-11 inline comment)
    - src/book_pipeline/interfaces/types.py (opportunistic _rebuild_for_physics_forward_ref at module-tail; deferred-items.md RESOLVED)
    - .planning/phases/07-narrative-physics-engine-codified-storytelling-atomics-enfor/deferred-items.md (Plan 07-01 DraftRequest item marked RESOLVED)
decisions:
  - run_pre_flight short-circuits on FIRST severity='high' FAIL via GateError (NOT severity='mid' or 'low'). The composer iterates 5 gates in deterministic order (pov_lock, motivation, ownership, treatment, quantity) and accumulates results up to and including the first high-severity FAIL. GateError carries `failed_gate` (str) + `results` (list[GateResult]) attributes for the drafter's error-event payload.
  - Ownership gate's cross-scene unresolved-reference branch fires at 'mid' severity (NOT 'high'). v1.1 OQ for operator: should this be hardened to high in a future plan? Current rationale: early-chapter scenes have no prior committed metadata so the gate can't distinguish "intentional shorthand" from "actual contradiction" without false positives.
  - Quantity gate iterates `canon_bible.iter_canonical_quantities()` directly (not a hardcoded entity keyword list) — Warning #2 mitigation. Synthetic 6th row test (`test_quantity_check_iterates_synthetic_sixth_row`) proves the gate covers long-tail extraction-agent rows automatically.
  - Motivation gate stub-leak regex INTENTIONALLY OMITS 'Goal'/'Conflict'/'Outcome' — these are legitimate motivation prefixes ("His goal: to warn Xochitl") that would over-fire on real operator-authored motivation strings. The full stub-leak axis (Plan 07-04 stub_leak.py) covers prose-level scans.
  - ModeADrafterBlocked accepted-reasons set is a frozenset declared at module level + runtime ValueError on unknown reasons. Defense in depth — surfaces typos at the raise site instead of routing through with an unknown reason that downstream handlers misclassify (BLOCKER #4 mitigation visible at runtime, not just via grep).
  - DraftRequest forward-ref auto-rebuild via fix candidate 1 (`contextlib.suppress(ImportError)` at interfaces/types.py module-tail). Cleaner than fix candidate 2 (per-test conftest sprinkles) and preserves Plan 07-01 import-linter contract semantics (the existing `interfaces.types -> physics.schema` ignore_imports edge already covers this coupling).
  - Used `contextlib.suppress(ImportError)` instead of `try/except ImportError: pass` — matches ruff SIM105 preferred style; both interfaces are equivalent.
  - All 3 physics factories on ModeADrafter are keyword-only and default to `None` (Phase 1 freeze additive-optional pattern; matches `embedder_for_fidelity` and `prompt_template_path` precedent in the same ctor).
  - Pre-flight runs BEFORE the Jinja2 render but AFTER scene_type resolution + sampling-profile lookup. Rationale: scene_id construction needs scene_request.{chapter,scene_index}; profile resolution is also cheap pre-vLLM work that the error-event payload would want to include.
metrics:
  duration: "32m 14s"
  completed: "2026-04-26T07:32:00Z"
  tasks_completed: 2
  tests_added: 34 (8 canon_bible + 14 gates + 12 mode_a_physics_header)
  files_created: 9
  files_modified: 6
  loc_added_src: 451 (130 canon_bible + 52 pov_lock + 60 motivation + 78 ownership + 37 treatment + 94 quantity)
  loc_added_tests: 879 (162 + 303 + 414)
---

# Phase 7 Plan 3: Drafter Physics Pre-Flight + Canonical Stamp + Fenced Beat Directive Summary

**One-liner:** ModeADrafter gains 3 keyword-only physics factories (pre-flight + canonical-stamp + beat-directive). Pre-flight composes 5 gates (pov_lock, motivation, ownership, treatment, quantity) sequentially, short-circuits on first high-severity FAIL, and emits one `role='physics_gate'` Event per check. CanonBibleView wraps CB-01 retrieval into a queryable book-state object whose `iter_canonical_quantities()` powers the quantity gate (Warning #2 mitigation: live rowset, not a hardcoded keyword list). Drafter Jinja2 template gains top-of-system `{{ canonical_stamp }}` (D-23 anchor) and fenced `{{ beat_directive }}` (D-13 ownership) blocks. ModeADrafterBlocked accepted-reasons frozenset rejects unknown reasons at runtime (BLOCKER #4). DraftRequest forward-ref now auto-rebuilds opportunistically (Plan 07-01 deferred-items.md item RESOLVED).

## What Landed

### CanonBibleView reader (Task 1)

`src/book_pipeline/physics/canon_bible.py` — 130 LOC. Three public symbols:

- **`CanonicalQuantityRow`** Pydantic model (`extra="forbid"`, `frozen=True`) — `id`, `text`, `name` extracted from CB-01 hit text head.
- **`CanonBibleView`** — `get_canonical_quantity(name)`, `iter_canonical_quantities()`, `get_pov_lock(character)`, `format_stamp()`. Per-bundle state (NO module-scope cache decorator per Pitfall 11).
- **`build_canon_bible_view(*, cb01_retrieval, pov_locks)`** — composes from already-bundled CB-01 RetrievalResult + load_pov_locks() output.

`format_stamp()` output for the 5 canaries:

```
CANONICAL: Andres age: 23 (ch01-ch14) | La Nina height: 55 ft apex deck (ch01-ch14) | Santiago del Paso scale: 210 ft apex deterrent (ch01-ch14) | Cholula date: October 18, 1519 (ch04-ch07) | Cempoala arrival: June 2, 1519 (ch03 sole arrival)
```

### 5 pre-flight gates (Task 1)

`src/book_pipeline/physics/gates/{pov_lock,motivation,ownership,treatment,quantity}.py` — each exports `GATE_NAME` (str) and `check(stub, ...deps) -> GateResult`. Severity ladder uses `pass|low|mid|high` matching CriticIssue.severity vocabulary.

| Gate | High-severity trigger | Mid-severity trigger | Notes |
|------|----------------------|----------------------|-------|
| `pov_lock` | character on-screen + lock applies + perspective != lock + no override | (n/a) | Override path emits dedicated audit detail (`pov_lock_override_used=True`, `rationale=...`) — T-07-08 mitigation |
| `motivation` | empty motivation OR stub-leak vocabulary at line start | (n/a) | Anchored regex (T-07-02 DoS-resistant); excludes Goal/Conflict/Outcome |
| `ownership` | owns ∩ do_not_renarrate non-empty OR callback_allowed ∩ do_not_renarrate non-empty | unresolved cross-scene reference (only when prior_committed_metadata is supplied) | Cross-scene check is opt-in via deps |
| `treatment` | (defensive only — Pydantic enum already enforces) | (n/a) | Defense in depth + audit emission point |
| `quantity` | (reserved for v1.1 — explicit value contradiction) | on-screen character with no canonical row | Iterates `canon_bible.iter_canonical_quantities()` — Warning #2 mitigation |

### run_pre_flight composer (Task 1)

`src/book_pipeline/physics/gates/__init__.py` — `run_pre_flight(stub, *, pov_locks, canon_bible, event_logger=None, prior_committed_metadata=None) -> list[GateResult]`. Iterates 5 gates in deterministic order; emits one `role='physics_gate'` Event per check via `emit_gate_event` (Plan 07-01 helper); short-circuits on first `severity='high'` by raising `GateError` with `err.failed_gate` (str) + `err.results` (accumulated list) attached.

**Short-circuit confirmed:** `test_run_pre_flight_short_circuits_on_high_severity_fail` injects a stub-leak motivation that fires HIGH at gate index 1 (motivation). Expected: pov_lock event + motivation event only — `len(fake_event_logger.events) == 2`. Verified.

### ModeADrafter integration (Task 2)

`src/book_pipeline/drafter/mode_a.py` ctor extension:

```python
def __init__(
    self,
    *,
    # ... existing args ...
    physics_pre_flight: Callable[[DraftRequest], list[GateResult]] | None = None,
    physics_canonical_stamp_factory: Callable[[DraftRequest], str] | None = None,
    physics_beat_directive_factory: Callable[[DraftRequest], str] | None = None,
) -> None:
```

Pre-flight runs at line ~315 — BEFORE Jinja2 render + vLLM call (D-24 cheap-first). On `GateError`, drafter emits `role='drafter'` `status='error'` `error='physics_pre_flight_fail'` Event with `failed_gate` + `gate_results` in `extra`, then raises `ModeADrafterBlocked('physics_pre_flight_fail', scene_id=..., attempt_number=..., failed_gate=..., gate_error=...)`.

When `physics_canonical_stamp_factory` is None, `canonical_stamp` defaults to `""`; the Jinja2 `{% if canonical_stamp %}` block omits the entire stamp line. Same pattern for `beat_directive`.

### ModeADrafterBlocked accepted-reasons (Task 2)

```python
_ACCEPTED_REASONS: frozenset[str] = frozenset({
    "training_bleed", "mode_a_unavailable", "empty_completion",
    "invalid_scene_type",
    "physics_pre_flight_fail",     # Plan 07-03 PHYSICS-05
    "pov_lock_violated",           # Plan 07-04 critic-axis reservation
})

class ModeADrafterBlocked(Exception):
    def __init__(self, reason: str, **context: Any) -> None:
        if reason not in _ACCEPTED_REASONS:
            raise ValueError(
                f"unknown ModeADrafterBlocked reason {reason!r}; "
                f"expected one of {sorted(_ACCEPTED_REASONS)}"
            )
        ...
```

**Runtime acceptance verified:**
- `ModeADrafterBlocked('physics_pre_flight_fail', scene_id='ch15_sc02', attempt_number=1)` — exits 0
- `ModeADrafterBlocked('bogus_reason', scene_id='x')` — exits 1 with `ValueError: unknown ModeADrafterBlocked reason 'bogus_reason'; expected one of [...]`

### Drafter Jinja2 template (Task 2)

`src/book_pipeline/drafter/templates/mode_a.j2` — canonical_stamp + beat_directive blocks land at the very top of the SYSTEM section (BEFORE the existing `You are Paul Logan, drafting...` line). T-07-11 mitigation comment inline.

```jinja2
===SYSTEM===
{% if canonical_stamp -%}
{{ canonical_stamp }}

{% endif -%}
{% if beat_directive -%}
{{ beat_directive }}

{% endif -%}
You are Paul Logan, drafting a scene for ...
```

`test_template_renders_canonical_stamp_at_top` asserts the canonical line appears at a smaller `str.find` index than the voice description string — confirms top-of-prompt placement.

### DraftRequest opportunistic rebuild (deferred-items.md RESOLVED)

`src/book_pipeline/interfaces/types.py` module-tail:

```python
import contextlib
# ...
with contextlib.suppress(ImportError):
    _rebuild_for_physics_forward_ref()
```

Resolves the Plan 07-01 latent issue: ~16 broken tests across `tests/drafter/`, `tests/cli/`, `tests/chapter_assembler/`, `tests/integration/` previously failed with `pydantic.errors.PydanticUserError: DraftRequest is not fully defined`. After this fix, those tests no longer hit that error (verified via `pytest tests/ -m "not slow" 2>&1 | grep "not fully defined"` returns empty).

Remaining failures in `tests/drafter/test_mode_a.py` and `tests/drafter/test_vllm_client.py` and `tests/chapter_assembler/test_dag.py` have DIFFERENT root causes (FakeVllmClient signature drift on `min_tokens`; SHA-mismatch in vllm_client tests; `CHAPTER_FAIL_SCENE_KICKED` vs `CHAPTER_FAIL` semantic mismatch in dag tests) — these pre-date Plan 07-03 and are out of SCOPE BOUNDARY. Documented in deferred-items.md.

### Composition root pattern (note for Plan 07-05)

The CLI composition site (`src/book_pipeline/cli/draft.py`) currently does NOT wire the 3 physics factories — Plan 07-03 ships them as **available** but **unwired**. Plan 07-05 integration test will call `ModeADrafter(...)` with all 3 factories populated:

```python
# Plan 07-05 wiring (not landed by Plan 07-03):
locks = load_pov_locks()
canon_bible = build_canon_bible_view(
    cb01_retrieval=context_pack.retrievals.get("continuity_bible"),
    pov_locks=locks,
)

def _physics_pre_flight(req: DraftRequest) -> list[GateResult]:
    return run_pre_flight(
        req.scene_metadata,
        pov_locks=locks,
        canon_bible=canon_bible,
        event_logger=event_logger,
    )

def _canonical_stamp_factory(req: DraftRequest) -> str:
    return canon_bible.format_stamp()

def _beat_directive_factory(req: DraftRequest) -> str:
    md = req.scene_metadata
    if md is None:
        return ""
    owns = ", ".join(md.owns)
    no_renarrate = ", ".join(md.do_not_renarrate)
    return f"<beat>OWNS: {owns}. DO NOT renarrate: {no_renarrate}.</beat>"

drafter = ModeADrafter(
    # ... existing args ...
    physics_pre_flight=_physics_pre_flight,
    physics_canonical_stamp_factory=_canonical_stamp_factory,
    physics_beat_directive_factory=_beat_directive_factory,
)
```

`request.scene_metadata` is available because Plan 07-01 landed `DraftRequest.scene_metadata: SceneMetadata | None`; the opportunistic rebuild in this plan ensures it's auto-resolved without needing an explicit `import book_pipeline.physics`.

## Threat Model Verification

| Threat ID | Mitigation Status | Evidence |
|-----------|-------------------|----------|
| T-07-02 (DoS via stub-leak regex in motivation gate) | mitigated | `_STUB_LEAK_IN_MOTIVATION` is anchored at line start (`^\s*(?:...)\s*:`) with bounded alternation, no nested quantifiers, no `.*\s*$`. Motivation field is also bounded by Pydantic min-words validator (single line in practice). The exclusion of 'Goal'/'Conflict'/'Outcome' from the keyword set prevents over-fire on legitimate motivation prefixes. |
| T-07-08 (pov_lock_override audit) | mitigated | `physics/gates/pov_lock.py` records `pov_lock_override_used: bool` + `rationale: str` in GateResult.detail when the override path triggers; `emit_gate_event` surfaces these in the Event extra dict; weekly digest (Phase 6) flags overrides via the unique audit Event. |
| T-07-09 (Anthropic prompt-cache leak via canonical_stamp / beat_directive) | mitigated | Both Jinja2 template variables receive STABLE schema-validated strings — canonical values don't change per scene (the 5 canaries are book-stable) and beat_directives are scene-stable. Per Pitfall 5, any chapter-/scene-CACHE-INVALIDATING value should be routed into the user prompt via the existing critic discipline (Plan 07-04 will land that wiring); the Jinja2 system template never renders raw stub frontmatter strings. |
| T-07-11 (Jinja2 template injection via stub fields) | mitigated | The Jinja2 system.j2 receives ONLY schema-validated stable strings: `canonical_stamp` is built from CanonicalQuantity rows whose `id` is regex-validated `^[a-z0-9_]+$` (Plan 07-02 T-07-03) and whose `text` is a fixed-shape canon line; `beat_directive` is built from SceneMetadata enum-validated fields. The drafter does NOT pass per-scene free-text user fields through the Jinja2 render — the inline T-07-11 comment in mode_a.j2 documents the boundary. Acceptance: `mode_a.py` render kwargs at line ~315 are all schema-derived (no `request.scene_metadata.contents.goal` direct passthrough through Jinja2). |
| T-07-12 (physics package boundary) | mitigated | All gates import only from `book_pipeline.physics.{schema, locks, canon_bible, gates.base}` + `book_pipeline.interfaces.{event_logger, types}`. NO book_specifics imports. import-linter contract 1 enforces; `lint_imports.sh`'s import-linter step exits 0 (2 contracts kept). The new `book_pipeline.drafter.mode_a -> book_pipeline.physics` import is allowed (drafter is kernel; physics is kernel; both in source_modules of contract 1). |

## Test Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `tests/physics/test_canon_bible.py` | 8 | get_canonical_quantity hit/miss; build returns view; iter_canonical_quantities exposes 5 canary rows + synthetic 6th row; format_stamp emits CANONICAL prefix + names; empty rowset -> empty stamp; get_pov_lock case-insensitive; per-instance composition (no module-scope cache) |
| `tests/physics/test_gates.py` | 14 | pov_lock pass for ungated ch09 + breach-high at ch15 + override path; motivation pass + stub-leak high; ownership pass + owns/donotrenarrate overlap high; treatment pass; quantity pass + soft-warn mid for unmapped on-screen char + Test 7b synthetic 6th row picked up without code change (Warning #2 acceptance); run_pre_flight returns 5 results on full pass; short-circuit on high (only 2 events emitted); event role='physics_gate' + deterministic ordering on full pass |
| `tests/drafter/test_mode_a_physics_header.py` | 12 | Ctor accepts new kwargs; backward-compat (omitting kwargs preserves pre-Phase-7 behavior); no-pre-flight drafts normally; passing pre-flight continues to vLLM; failing pre-flight raises ModeADrafterBlocked + emits error Event + skips vLLM; canonical_stamp renders at top; beat_directive renders fenced block; empty stamp omits CANONICAL line; ModeADrafterBlocked accepts physics_pre_flight_fail at runtime; ModeADrafterBlocked rejects bogus reasons; pov_lock_violated reservation accepted; subprocess smoke for standalone-import path |
| **Total** | **34** | All Wave 0 tests for Plan 07-03 |

Plan 07-03 acceptance gate: `uv run pytest tests/physics/test_canon_bible.py tests/physics/test_gates.py tests/drafter/test_mode_a_physics_header.py -m "not slow" -x` — **34 passed, 0 failed**.

Full physics + drafter regression: `uv run pytest tests/physics/ tests/drafter/test_mode_a_physics_header.py tests/interfaces/ -m "not slow"` — **86 passed**.

## Acceptance Gate Summary

| Gate | Required | Actual |
|------|----------|--------|
| `grep -c '_ACCEPTED_REASONS' src/book_pipeline/drafter/mode_a.py` | ≥ 2 | 4 |
| `grep -c 'physics_pre_flight_fail' src/book_pipeline/drafter/mode_a.py` | ≥ 2 | 5 |
| `grep -cE 'canonical_stamp|beat_directive' src/book_pipeline/drafter/templates/mode_a.j2` | ≥ 2 | 8 |
| `grep -c 'iter_canonical_quantities' src/book_pipeline/physics/gates/quantity.py` | ≥ 1 | 2 |
| `grep -ic 'andres\|la nina\|cholula\|cempoala\|santiago del paso' src/book_pipeline/physics/gates/quantity.py` | == 0 | 0 |
| Runtime `ModeADrafterBlocked('physics_pre_flight_fail', ...)` exits 0 | ok | ok |
| Runtime `ModeADrafterBlocked('bogus_reason')` exits non-zero | ValueError | ValueError |
| `python -c "from book_pipeline.physics import canon_bible; from book_pipeline.physics.gates import run_pre_flight; ..."` | ok | ok |
| `lint-imports` (import-linter) | 2/2 contracts kept | 2/2 kept |
| mypy on physics + drafter + interfaces | clean | clean |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug fix] Pre-existing DraftRequest forward-ref blocking ~16 tests (deferred-items.md item)**
- **Found during:** Pre-Task-2 sanity check (`pytest tests/drafter/test_mode_a.py::test_draft_happy_path_emits_one_drafter_event` failed with `PydanticUserError: DraftRequest is not fully defined`).
- **Issue:** Plan 07-01 deferred `DraftRequest.model_rebuild()` to `physics/__init__.py` to keep the runtime interfaces module free of physics imports. Tests that import only `interfaces.types` and construct DraftRequest didn't trigger the rebuild.
- **Fix:** Added opportunistic `with contextlib.suppress(ImportError): _rebuild_for_physics_forward_ref()` at the module-tail of `interfaces/types.py` (fix candidate 1 from deferred-items.md). The `interfaces.types -> physics.schema` ignore_imports edge in pyproject.toml already covers this coupling.
- **Files modified:** `src/book_pipeline/interfaces/types.py`, `.planning/phases/07-.../deferred-items.md`.
- **Commit:** `87b5ad5`.

**2. [Rule 1 - Bug fix] Test fixture data assumption (Xochitl missing canonical row)**
- **Found during:** Task 1 GREEN run.
- **Issue:** `test_quantity_check_passes_when_entity_resolves` had on-screen Xochitl in addition to Andres. The seeded canon bible only contains the 5 manuscript canaries (Andres, La Nina, Santiago del Paso, Cholula, Cempoala) — Xochitl has no canonical row -> soft-warn fires -> test expectation false.
- **Fix:** Updated test to use only Andres on-screen for the pass-path (matches the canon bible's seeded content).
- **Files modified:** `tests/physics/test_gates.py`.
- **Commit:** `8911435` (combined with Task 1 GREEN).

**3. [Rule 3 - Blocking] Ruff SIM105 + E402 on the new module-tail rebuild block**
- **Found during:** Post-Task-2 lint suite.
- **Issue:** `try/except ImportError: pass` triggered SIM105; subsequent `import contextlib as _contextlib` inside the module body triggered E402 (module-level import not at top).
- **Fix:** Hoisted `import contextlib` to the top imports block; replaced `try/except/pass` with `with contextlib.suppress(ImportError): ...`. Equivalent semantics; passes both lints.
- **Files modified:** `src/book_pipeline/interfaces/types.py`.
- **Commit:** `c893c41`.

**4. [Rule 1 - Bug fix] Acceptance grep oversensitive to docstring content**
- **Found during:** Final acceptance gate run.
- **Issue:** `grep -ic 'andres\|la nina\|cholula\|cempoala\|santiago del paso' src/book_pipeline/physics/gates/quantity.py` reported 1 — matching the literal "Cempoala" substring in an explanatory docstring (gate logic was clean).
- **Fix:** Scrubbed the literal "Cempoala" from the docstring (replaced with "double-arrival corner case"); inline pointer to NARRATIVE_PHYSICS.md §6.3 preserved. Gate logic unchanged.
- **Files modified:** `src/book_pipeline/physics/gates/quantity.py`.
- **Commit:** `ca4c448`.

### Out-of-Scope (logged, NOT fixed — pre-existing)

**Pre-existing test fixture drift in `tests/drafter/test_mode_a.py`** — `_FakeVllmClient.chat_completion` lacks the `min_tokens` kwarg added to real `VllmClient.chat_completion` at commit-prior 2026-04-25 work. Affects 11 tests in test_mode_a.py. Pre-dates Plan 07-03; out of SCOPE BOUNDARY (Plan 07-03 did not cause the drift). The 12 NEW `test_mode_a_physics_header.py` tests use a fresh `_FakeVllmClient` that DOES accept `min_tokens` (designed against the current real client signature).

**Pre-existing SHA-mismatch in `tests/drafter/test_vllm_client.py::test_boot_handshake_*`** — affects 2 tests. Pre-dates Plan 07-03.

**Pre-existing `CHAPTER_FAIL_SCENE_KICKED` vs `CHAPTER_FAIL` semantic mismatch in `tests/chapter_assembler/test_dag.py`** — affects 2 tests. Pre-dates Plan 07-03 (state-machine was renamed in Plan 05-02 LOOP-04 work; these specific tests were not updated).

**Pre-existing ruff failures in `src/book_pipeline/cli/draft.py`** — already logged by Plan 07-01. Plan 07-03 did not modify this file.

**Pre-existing ruff failure in `src/book_pipeline/corpus_ingest/canonical_quantities.py`** — F401 unused `import lancedb` from Plan 07-02. Plan 07-03 did not modify this file.

## Authentication Gates

None. Plan 07-03 was fully autonomous, NO LLM calls (Anthropic / vLLM untouched), NO GPU. Pure schema/composer/gate code + Jinja2 template extension. Verified `nvidia-smi` not consulted (no GPU work).

## Decisions Made

1. **Pre-flight insertion point:** AFTER scene_type resolution + sampling-profile lookup, BEFORE Jinja2 render + vLLM call. Rationale: scene_id construction needs scene_request fields; profile resolution is cheap pre-vLLM work that the error-event payload would want to include; pre-flight is the cheapest model-call-avoidance gate (D-24 cheap-first).
2. **5 gate ordering:** pov_lock → motivation → ownership → treatment → quantity. Rationale: pov_lock is the cheapest + most commonly-failing (operator stub-authoring drift); motivation second because D-02 says it's load-bearing and a failure short-circuits the rest cleanly; treatment is defensive-only so 4th; quantity is most-expensive (iterates the canon bible rowset) so last.
3. **Ownership v1 mid-severity for unresolved cross-scene reference:** Operator OQ for v1.1 — should this be hardened to high? Current rationale: early-chapter scenes have no prior committed metadata; can't distinguish "intentional shorthand" from "actual contradiction" without false positives.
4. **Quantity gate v1 'high' branch reserved for v1.1:** v1 fires only `pass` or `mid` (soft warn for missing on-screen-character canonical row). The 'high' branch (explicit canonical-value substring contradiction) is reserved for v1.1 — v1 leaves contradiction detection to the Plan 07-04 critic `named_quantity_drift` axis.
5. **Drafter <-> physics coupling direction:** drafter imports physics (allowed — both kernel packages in contract 1 source_modules). physics does NOT import drafter (would create a cycle). The coupling lives only in mode_a.py.
6. **`Callable[[DraftRequest], list[GateResult]]` factory signature:** the factories receive the full DraftRequest (NOT the SceneMetadata directly). Rationale: factories may want access to the context_pack retrievals (e.g., the canonical-stamp factory needs the CB-01 hits). Plan 07-05 wiring will pull `req.scene_metadata` and `req.context_pack.retrievals['continuity_bible']` separately.
7. **Opportunistic rebuild via contextlib.suppress over try/except/pass:** matches ruff SIM105 preferred style. Equivalent semantics.

## Open Questions for Plan 07-04 / 07-05

- **Plan 07-04 critic axes (`pov_fidelity`, `motivation_fidelity`, `treatment_fidelity`, `content_ownership`, `named_quantity_drift`, `stub_leak`, `repetition_loop`, `scene_buffer_similarity`)** consume scene_metadata + context_pack.retrievals['continuity_bible'] post-draft. Most rubric work runs after the drafter — the new axes fold into the existing CRITIC-01 5-axis flow with the same scene-kick recovery semantics. Plan 07-04 does NOT need to wire the drafter (Plan 07-03 did that); it extends `templates/scene_critic.j2` + the CriticResponse schema.
- **Ownership gate v1.1 hardening:** should the cross-scene unresolved-reference branch fire 'high' instead of 'mid'? Operator decision. Current 'mid' rationale captured above.
- **Plan 07-05 CLI composition site (`cli/draft.py`):** the integration smoke test will need to wire all 3 physics factories + load_pov_locks() + build_canon_bible_view(). Plan 07-05 should also include the integration test where ch15 sc02 stub frontmatter (with deliberate canon-violation) gets rejected at pre-flight.
- **DraftRequest forward-ref auto-rebuild side effect:** opportunistic rebuild fires when `interfaces.types` is imported, which happens at app startup. The model_rebuild() call has zero runtime cost beyond first import. No measured perf impact.
- **The 5 canary canonical values are book-stable** — they don't drift by chapter (ch01-ch14 scope). Plan 07-04 critic will need to handle the chapter-scope filter (Andres age=23 applies ch01-ch14; if a future plan adds ch15+ canonical values they'd be DIFFERENT rows in CB-01, not overwrites of the 5 canaries). The `canon update` workflow (deferred per OQ-05 RESOLVED) handles re-ingest; Phase 7 acceptance does NOT depend on it.

## Self-Check: PASSED

- All 9 created files exist on disk:
  - FOUND: src/book_pipeline/physics/canon_bible.py
  - FOUND: src/book_pipeline/physics/gates/pov_lock.py
  - FOUND: src/book_pipeline/physics/gates/motivation.py
  - FOUND: src/book_pipeline/physics/gates/ownership.py
  - FOUND: src/book_pipeline/physics/gates/treatment.py
  - FOUND: src/book_pipeline/physics/gates/quantity.py
  - FOUND: tests/physics/test_canon_bible.py
  - FOUND: tests/physics/test_gates.py
  - FOUND: tests/drafter/test_mode_a_physics_header.py
- All 6 task commits present in `git log`:
  - FOUND: `7dcbe80` (Task 1 RED)
  - FOUND: `8911435` (Task 1 GREEN)
  - FOUND: `683c1d7` (Task 2 RED)
  - FOUND: `87b5ad5` (Task 2 GREEN + deferred-items.md fix)
  - FOUND: `c893c41` (lint refactor: contextlib.suppress)
  - FOUND: `ca4c448` (docs: scrub canary entity name from quantity gate docstring)
- Plan 07-03 acceptance gate (fast tests): 34 passed, 0 failed
- Full physics + drafter test regression: 86 passed
- Import-linter: 2/2 kept; scoped mypy clean
- Runtime smoke: ModeADrafterBlocked('physics_pre_flight_fail', ...) -> exits 0; bogus reason -> ValueError
- canon_bible.format_stamp() output verified for 5 canaries
- Quantity gate iterates `canon_bible.iter_canonical_quantities()` (Warning #2 acceptance: synthetic 6th row test passes WITHOUT modifying gates/quantity.py)
- DraftRequest forward-ref auto-rebuild verified via standalone `from book_pipeline.interfaces.types import DraftRequest; DraftRequest(...).scene_metadata` -> None (no PydanticUserError)
