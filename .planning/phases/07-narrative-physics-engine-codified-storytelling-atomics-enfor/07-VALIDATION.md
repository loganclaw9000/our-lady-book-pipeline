---
phase: 7
slug: narrative-physics-engine-codified-storytelling-atomics-enfor
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-25
last_updated: 2026-04-25
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 07-RESEARCH.md `## Validation Architecture` + Nyquist Dimension 8.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8 + pytest-asyncio (in repo) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (already configured for `slow` marker) |
| **Quick run command** | `pytest tests/physics/ -m "not slow" -x` |
| **Full suite command** | `pytest tests/ -x` (vLLM stopped — see project memory `feedback_no_vllm_during_build.md`) |
| **Estimated runtime (quick)** | ~5 seconds |
| **Estimated runtime (full)** | ~60 seconds (includes BGE-M3 slow tests) |

---

## Sampling Rate

- **After every task commit:** `pytest tests/physics/ -m "not slow" -x` (~5s)
- **After every plan wave:** `pytest tests/ -m "not slow" -x` (~30s) — broader scoping
- **Before `/gsd-verify-work`:** Full suite green (`pytest tests/ -x` with vLLM stopped)
- **Max feedback latency:** 5 seconds (quick) / 60 seconds (full)

---

## Per-Task Verification Map

> Filled by gsd-planner during plan generation. Each PLAN.md task gets a row.

### Plan 07-01 (Wave 1) — Schema + locks + import-linter + REQUIREMENTS.md

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-T1 | 07-01 | 1 | PHYSICS-03 (REQ-IDs + import-linter contract) | T-07-04 | physics package added to BOTH import-linter contracts; mypy targets extended; lint_imports.sh stays green | static | `bash scripts/lint_imports.sh && grep -c "^- \[ \] \*\*PHYSICS-0[1-9]\|PHYSICS-1[0-3]\*\*" .planning/REQUIREMENTS.md` | ❌ W0 | ⬜ pending |
| 07-01-T2 | 07-01 | 1 | PHYSICS-01, PHYSICS-02 (schema + PovLock) | T-07-01, T-07-10, T-07-12 | Pydantic strict-validate; extra="forbid" rejects unknown frontmatter; yaml.safe_load via pydantic-settings; PovLock activation inclusive boundary | unit | `uv run pytest tests/physics/test_schema.py tests/physics/test_locks.py tests/physics/test_gates_base.py -x` | ❌ W0 | ⬜ pending |

### Plan 07-02 (Wave 2) — CB-01 retriever + canonical_quantity ingest + 7-event invariant

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-02-T1 | 07-02 | 2 | PHYSICS-04 (CB-01 retriever) | T-07-04, T-07-06 | LanceDBRetrieverBase subclass; rule_type filter as defense in depth; reuses BgeM3Embedder (one shared instance) | unit | `uv run pytest tests/rag/test_continuity_bible_retriever.py -m "not slow" -x` | ❌ W0 | ⬜ pending |
| 07-02-T2 | 07-02 | 2 | PHYSICS-04 (canonical_quantity ingest + bundler 7-event invariant) | T-07-05, T-07-10 | LanceDB additive non-column extension (D-22 contract); yaml.safe_load only; idempotent re-ingest via deterministic chunk_ids | unit + integration (slow) | `uv run pytest tests/corpus_ingest/test_canonical_quantities.py tests/rag/test_bundler_seven_events.py -x` | ❌ W0 | ⬜ pending |
| 07-02-T3 | 07-02 | 2 | PHYSICS-04 (end-to-end CB-01 retrieval) | T-07-05 | book-pipeline ingest writes 5 canonical quantities; CB-01 retriever returns rows for entity-and-context queries | integration (slow) | `uv run pytest tests/rag/test_continuity_bible_retriever.py -x` | ❌ W0 | ⬜ pending |

### Plan 07-03 (Wave 3, parallel with 07-04) — Pre-flight gates + canon_bible + drafter wiring

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-03-T1 | 07-03 | 3 | PHYSICS-05 (gates + composer) | T-07-02, T-07-08, T-07-12 | Per-bundle dict memoization (no module lru_cache per Pitfall 11); pov_lock_override emits dedicated Event for audit; gates kernel-pure (no book_specifics) | unit | `uv run pytest tests/physics/test_canon_bible.py tests/physics/test_gates.py -x` | ❌ W0 | ⬜ pending |
| 07-03-T2 | 07-03 | 3 | PHYSICS-05, PHYSICS-06 (drafter wiring + Jinja2 stamp + fenced beat) | T-07-09 | Jinja2 system.j2 receives only stable per-scene values (cache-safe); chapter-/scene-specific physics directives go in user prompt per Pitfall 5 | unit | `uv run pytest tests/drafter/test_mode_a_physics_header.py tests/drafter/ -x` | ❌ W0 | ⬜ pending |

### Plan 07-04 (Wave 3, parallel with 07-03) — 13-axis critic + stub_leak + repetition_loop + motivation hard-stop

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-04-T1 | 07-04 | 3 | PHYSICS-08, PHYSICS-09 (deterministic detectors) | T-07-03 | Anchored line-start regex + re.MULTILINE (no nested quantifiers); property test verifies <100ms on 100k-byte adversarial inputs; LITURGICAL false-positive guard | unit + property | `uv run pytest tests/physics/test_stub_leak.py tests/physics/test_repetition_loop.py -x` | ❌ W0 | ⬜ pending |
| 07-04-T2 | 07-04 | 3 | PHYSICS-07, PHYSICS-13 (13-axis critic + motivation hard-stop) | T-07-08, T-07-10 | Anthropic structured-output validation (messages.parse); _post_process fills missing axes; motivation_fidelity FAIL forces overall_pass=False unconditionally | unit | `uv run pytest tests/critic/test_scene_13axis.py tests/critic/ -x` | ❌ W0 | ⬜ pending |

### Plan 07-05 (Wave 4) — Scene-buffer + quote normalizer + CLI composition + integration smokes

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-05-T1 | 07-05 | 4 | PHYSICS-10, PHYSICS-11 (SceneEmbeddingCache + quote normalizer + critic pre-LLM hooks) | T-07-07, T-07-11 | SQLite parameterized queries; PRIMARY KEY (scene_id, bge_m3_revision_sha); db_path constructor-injected; quote regex anchored line-by-line (no `.*` backtracking) | unit + integration (slow) | `uv run pytest tests/physics/test_scene_buffer.py tests/chapter_assembler/test_quote_normalizer.py tests/critic/ -m "not slow" -x` | ❌ W0 | ⬜ pending |
| 07-05-T2 | 07-05 | 4 | PHYSICS-12 (CLI composition + ch15 + ch01-04 smokes) | T-07-12 | All physics deps wired at CLI composition root; ch15 sc02 mocked-vLLM/mocked-Anthropic + REAL BGE-M3 + REAL LanceDB; ch01-04 zero-FP read-only smoke | integration (slow) | `uv run pytest tests/integration/test_phase7_ch15.py tests/integration/test_phase7_ch01_baseline.py -m slow -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Property Tests (where applicable)

- **stub_leak regex DoS resistance (T-07-03):** Run `_PATTERN_DIRECTIVE.match` against adversarial inputs (`" " * 100_000`, `"\\" * 100_000`) with `signal.alarm(2)` timeout — must complete in <100ms. **Plan 07-04-T1.**
- **D-28 cosine threshold sweep:** Property test sweeps threshold from 0.50 to 0.95, asserts the canary "manual_concat duplicate" is caught at 0.80 and a non-duplicate ch01 sc01 vs ch02 sc01 stays below 0.65. **Plan 07-05-T1.**
- **PovLock activation boundary (Pitfall 8):** Property test sweeps chapter 1..30, asserts `applies_to(chapter)` is True iff `active_from_chapter <= chapter < (expires_at_chapter or ∞)`. **Plan 07-01-T2.**
- **Pydantic schema fuzzing (T-07-01):** Direct `extra="forbid"` rejection tests cover happy + sad paths; Test 2-3 in Plan 07-01-T2 exercise on_screen + motivation invariant; Test 1 exercises unknown-key rejection. (Hypothesis-style fuzz deferred — explicit boundary tests sufficient at v1.)

---

## Wave 0 Requirements

- [ ] `tests/physics/__init__.py` — package marker (Plan 07-01-T2)
- [ ] `tests/physics/conftest.py` — shared fixtures (FakeEventLogger, valid_scene_payload) (Plan 07-01-T2)
- [ ] `tests/physics/test_schema.py` — covers PHYSICS-01 (Plan 07-01-T2)
- [ ] `tests/physics/test_locks.py` — covers PHYSICS-02 (Plan 07-01-T2)
- [ ] `tests/physics/test_gates_base.py` — covers gates/base.py emit_gate_event (Plan 07-01-T2)
- [ ] `tests/physics/test_canon_bible.py` — covers CanonBibleView (Plan 07-03-T1)
- [ ] `tests/physics/test_gates.py` — covers PHYSICS-05 (one test per gate file) (Plan 07-03-T1)
- [ ] `tests/physics/test_stub_leak.py` — covers PHYSICS-08 (synthetic + ch11 sc03 line 119 fixture + DoS property tests) (Plan 07-04-T1)
- [ ] `tests/physics/test_repetition_loop.py` — covers PHYSICS-09 (canary "He did not sleep..." + LITURGICAL false-positive guard) (Plan 07-04-T1)
- [ ] `tests/physics/test_scene_buffer.py` — covers PHYSICS-10 (slow, BGE-M3 cosine integration) (Plan 07-05-T1)
- [ ] `tests/rag/test_continuity_bible_retriever.py` — covers PHYSICS-04 (slow) (Plan 07-02-T1, T3)
- [ ] `tests/rag/test_bundler_seven_events.py` — covers bundler 7-event invariant (Plan 07-02-T2)
- [ ] `tests/corpus_ingest/test_canonical_quantities.py` — covers canonical_quantities ingest (Plan 07-02-T2)
- [ ] `tests/critic/test_scene_13axis.py` — covers PHYSICS-07 + PHYSICS-13 (motivation hard-stop) (Plan 07-04-T2)
- [ ] `tests/chapter_assembler/test_quote_normalizer.py` — covers PHYSICS-11 (Plan 07-05-T1)
- [ ] `tests/drafter/test_mode_a_physics_header.py` — covers Jinja2 stamp + beat directive injection (Plan 07-03-T2)
- [ ] `tests/integration/__init__.py` — package marker (Plan 07-05-T2)
- [ ] `tests/integration/test_phase7_ch15.py` — covers PHYSICS-12 ch15 sc02 end-to-end (slow) (Plan 07-05-T2)
- [ ] `tests/integration/test_phase7_ch01_baseline.py` — covers PHYSICS-12 ch01-04 zero-FP read-only smoke (slow) (Plan 07-05-T2)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ch01-04 zero-false-positive eyeball sweep on LLM-judged axes | PHYSICS-12 part 2 | Some 13-axis checks (pov_fidelity, content_ownership, treatment_fidelity, named_quantity_drift) need Anthropic spend; deterministic axes (stub_leak, repetition_loop) are automated; LLM-judged sweep is operator-eyeball | After PHYSICS-12 integration test passes the deterministic axes, optionally run engine against ch01-04 in read-only with REAL Anthropic; eyeball physics-events.jsonl for FAIL events on the LLM-judged axes (zero-FP target — any FAIL is a bug) |
| OQ-05 canonical-quantity seed values | PHYSICS-04 prerequisite | Operator-supplied truth; engine cannot derive | Operator confirms values for Andrés age (currently seeded 23), La Niña height (55ft), Santiago del Paso scale (210ft), Cholula date (Oct 18 1519), Cempoala arrival (Jun 02 1519) seeded into `config/canonical_quantities_seed.yaml` before/during Plan 07-02 |
| ch15 sc02 production smoke (REAL vLLM + REAL Anthropic on V7C LoRA) | PHYSICS-12 part 1 | Acceptance gate per 07-RESEARCH.md ("ch15 sc02 produces a clean draft on V7C LoRA via the new engine in <15 min") | Operator runs `book-pipeline draft --chapter 15 --scene 2` after Plan 07-05 lands with vLLM + Anthropic active; observes physics-events.jsonl + critic events; confirms PASS or scene-kick-recovers-then-PASS within 15 min |

*Most phase behaviors have automated verification. Manual checks are for FP confirmation against a real prose baseline + operator-truth seeding + final acceptance smoke.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify (per-task table above filled)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has a pytest command)
- [x] Wave 0 covers all MISSING references (19 test files enumerated above)
- [x] No watch-mode flags (all commands are one-shot)
- [x] Feedback latency < 5s (quick) / 60s (full)
- [x] `nyquist_compliant: true` set in frontmatter (planner filled task-level rows)

**Approval:** planner-approved 2026-04-25; awaiting execution.
