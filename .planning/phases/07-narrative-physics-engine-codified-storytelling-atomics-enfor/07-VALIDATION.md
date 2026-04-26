---
phase: 7
slug: narrative-physics-engine-codified-storytelling-atomics-enfor
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
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

> Filled by gsd-planner during plan generation. Each PLAN.md task gets a row here.
> Skeleton from RESEARCH.md PHYSICS-01..13 → 5-plan rollout (07-01..07-05).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-* | 07-01 | 1 | PHYSICS-01, 02, 03 | T-07-01, T-07-04 | Pydantic strict-validate untrusted stub frontmatter; import-linter blocks book-domain leak into `physics/` | unit + static | `pytest tests/physics/test_schema.py tests/physics/test_locks.py -x && bash scripts/lint_imports.sh` | ❌ W0 | ⬜ pending |
| 07-02-* | 07-02 | 2 | PHYSICS-04 | T-07-05, T-07-06 | LanceDB additive-nullable schema migration; canonical_quantity rule_type retrieval | integration (slow) | `pytest tests/rag/test_continuity_bible_retriever.py -m slow -x` | ❌ W0 | ⬜ pending |
| 07-03-* | 07-03 | 3 | PHYSICS-05, 06 | T-07-02, T-07-09 | Pre-flight gate composition; drafter prompt header injection of canonical values | unit | `pytest tests/physics/test_gates.py tests/drafter/test_mode_a_prompt.py -k physics_header -x` | ❌ W0 | ⬜ pending |
| 07-04-* | 07-04 | 3 | PHYSICS-07, 08, 09, 13 | T-07-03, T-07-08, T-07-10 | 13-axis critic schema; stub_leak regex DoS resistant; motivation hard-stop in post-process | unit + property | `pytest tests/critic/test_scene_13axis.py tests/physics/test_stub_leak.py tests/physics/test_repetition_loop.py -x` | ❌ W0 | ⬜ pending |
| 07-05-* | 07-05 | 4 | PHYSICS-10, 11, 12 | T-07-07, T-07-11, T-07-12 | Scene-buffer cosine cache integrity; quote-corruption normalizer; ch15 sc02 + ch01-04 zero-FP smoke | integration (slow) | `pytest tests/physics/test_scene_buffer.py tests/chapter_assembler/test_quote_normalizer.py tests/integration/test_phase7_ch15.py -m slow -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Property Tests (where applicable)

- **stub_leak regex DoS resistance:** Run `_PATTERN_DIRECTIVE.match` against adversarial inputs (`" " * 100_000`, `"\\" * 100_000`) with `signal.alarm(2)` timeout — must complete in <100ms. T-07-03 mitigation.
- **D-28 cosine threshold sweep:** Property test sweeps threshold from 0.50 to 0.95, asserts the canary "manual_concat duplicate" is caught at 0.80 and a non-duplicate ch01 sc01 vs ch02 sc01 stays below 0.65.
- **PovLock activation boundary:** Property test sweeps chapter 1..30, asserts `applies_to(chapter)` is True iff `active_from_chapter <= chapter < (expires_at_chapter or ∞)`.
- **Pydantic schema fuzzing:** Hypothesis-style fuzz on SceneMetadata fields — exercises edge-case enum values, missing required fields, type mismatches. T-07-01 mitigation.

---

## Wave 0 Requirements

- [ ] `tests/physics/__init__.py` — package marker
- [ ] `tests/physics/conftest.py` — shared fixtures (FakeAnthropicClient, FakeBgeM3Embedder, sample stubs from drafts/ch15)
- [ ] `tests/physics/test_schema.py` — covers PHYSICS-01
- [ ] `tests/physics/test_locks.py` — covers PHYSICS-02
- [ ] `tests/physics/test_gates.py` — covers PHYSICS-05 (one test per gate file)
- [ ] `tests/physics/test_stub_leak.py` — covers PHYSICS-08 (synthetic + ch11 sc03 line 119 fixture)
- [ ] `tests/physics/test_repetition_loop.py` — covers PHYSICS-09 (canary "He did not sleep..." + LITURGICAL false-positive guard from ch01 sc01)
- [ ] `tests/physics/test_scene_buffer.py` — covers PHYSICS-10 (slow, BGE-M3 cosine integration)
- [ ] `tests/rag/test_continuity_bible_retriever.py` — covers PHYSICS-04 (slow)
- [ ] `tests/critic/test_scene_13axis.py` — covers PHYSICS-07 + PHYSICS-13 (motivation hard-stop)
- [ ] `tests/chapter_assembler/test_quote_normalizer.py` — covers PHYSICS-11
- [ ] `tests/integration/test_phase7_ch15.py` — covers PHYSICS-12 (slow, end-to-end mocked vLLM + Anthropic)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ch01-04 zero-false-positive smoke | PHYSICS-12 part 2 | Requires reading prose to confirm no false flags from a known-good baseline | After PHYSICS-12 integration test passes, run engine against ch01-04 read-only, eyeball physics-events.jsonl: any FAIL is a bug |
| OQ-05 canonical-quantity seed values | PHYSICS-04 prerequisite | Operator-supplied truth; engine cannot derive | Operator confirms values for Andrés age (ch02:23, ch04:23, ch08:25?), La Niña height (one canonical ft value), Santiago del Paso scale (one canonical), Cholula date (Oct 18 1519), Cempoala arrival (one canonical date), seeded into `config/canonical_quantities_seed.yaml` before Plan 07-02 lands |

*Most phase behaviors have automated verification. Manual checks are for FP confirmation against a real prose baseline + operator-truth seeding.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s (quick) / 60s (full)
- [ ] `nyquist_compliant: true` set in frontmatter (after planner fills task-level rows)

**Approval:** pending
