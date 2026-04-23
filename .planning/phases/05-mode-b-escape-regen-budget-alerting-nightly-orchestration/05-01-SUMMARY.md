---
phase: 05-mode-b-escape-regen-budget-alerting-nightly-orchestration
plan: 01
subsystem: drafter
tags: [anthropic, opus-4.7, prompt-cache, pydantic-settings, jinja2, tenacity, cli, pricing]

# Dependency graph
requires:
  - phase: 01-foundation-observability-baseline
    provides: OBS-01 Event schema + JsonlEventLogger + Pydantic-Settings + YamlConfigSettingsSource
  - phase: 03-drafter-critic-regenerator-scene-loop
    provides: Drafter Protocol + ModeADrafter shape (paraphrased per ADR-004) + tenacity retry pattern + cache_control system-block pattern from SceneCritic
  - phase: 04-chapter-assembly-post-commit-dag
    provides: CLI-composition-seam precedent (3 new subcommands + 2 import-linter exemptions per Plan 04-05)
provides:
  - ModeBDrafter kernel (Drafter Protocol impl, mode='B', Opus 4.7 + 1h ephemeral cache)
  - is_preflagged() + load_preflag_set() pure functions for Plan 05-02 preflag gate
  - event_cost_usd() + ModelPricing pure kernel for Plan 05-02 spend-cap conversion
  - PricingConfig / PreflagConfig / VoiceSamplesConfig Pydantic loaders
  - config/pricing.yaml authoritative \$5/\$25 Opus 4.7 table (Pitfall 5 drift canary)
  - book-pipeline curate-voice-samples CLI + book_specifics/voice_samples.py source pointers
affects: 05-02, 05-03, 05-04, 06

# Tech tracking
tech-stack:
  added:
    - No new PyPI deps — anthropic, tenacity, jinja2, pydantic-settings, yaml all pre-pinned
  patterns:
    - Clone-not-abstract (ADR-004) — ModeBDrafter paraphrases ModeADrafter rather than importing
    - Cache identity invariant — _system_blocks as preserved list object for byte-identical prefix
    - Pydantic-Settings + YamlConfigSettingsSource loaders with field_validator rate-guards
    - Frozen dataclass for immutable per-process cost rates (ModelPricing)
    - CLI composition seam — 4th import-linter exemption under Plan 03-02 / 04-05 precedent

key-files:
  created:
    - src/book_pipeline/drafter/mode_b.py
    - src/book_pipeline/drafter/preflag.py
    - src/book_pipeline/drafter/templates/mode_b.j2
    - src/book_pipeline/observability/pricing.py
    - src/book_pipeline/config/pricing.py
    - src/book_pipeline/config/mode_preflags.py
    - src/book_pipeline/config/voice_samples.py
    - src/book_pipeline/cli/curate_voice_samples.py
    - src/book_pipeline/book_specifics/voice_samples.py
    - config/pricing.yaml
    - config/mode_preflags.yaml
    - config/voice_samples.yaml
    - tests/drafter/test_mode_b.py
    - tests/drafter/test_preflag.py
    - tests/observability/test_pricing.py
    - tests/observability/__init__.py
    - tests/cli/test_curate_voice_samples.py
  modified:
    - src/book_pipeline/drafter/__init__.py (re-export ModeBDrafter / ModeBDrafterBlocked / preflag helpers)
    - src/book_pipeline/cli/main.py (SUBCOMMAND_IMPORTS += curate_voice_samples)
    - pyproject.toml (import-linter contract-1 ignore_imports += CLI seam)
    - tests/conftest.py (FakeAnthropicClient + fake_anthropic_factory + pricing_fixture)
    - tests/test_import_contracts.py (documented_exemptions += curate_voice_samples; +1 exemption-registered test)

key-decisions:
  - "Clone-not-abstract enforced: zero imports from mode_a.py in mode_b.py (ADR-004). VOICE_DESCRIPTION + RUBRIC_AWARENESS paraphrased to allow future divergence."
  - "cache_control.ttl='1h' on the SYSTEM voice-samples block; _system_blocks list object preserved across calls for byte-identical cache prefix (D-02)."
  - "Authoritative Opus 4.7 pricing pinned at \$5 input / \$25 output / \$0.50 cache-read per MTok in config/pricing.yaml — rejecting the outdated \$15/\$75 in openclaw/cron_jobs.json (Pitfall 5). Hard-coded canary test catches future drift."
  - "ModeBDrafter.__init__ validates >=3 voice samples with word_count in slack band [300, 700]; curator CLI targets tighter [400, 600]. Drafter fails loud at wiring time rather than mid-scene (D-03)."
  - "B-3 lineage: Mode-B's DraftResponse.voice_pin_sha = voice_pin.checkpoint_sha. Mode-B claims FT checkpoint for lineage tracking even though the prose came from Opus — preserves chapter-frontmatter invariants downstream."
  - "curate-voice-samples CLI registered as 4th CLI-composition-seam exemption in import-linter contract 1 (pattern from Plan 03-02). book_specifics/voice_samples.py owns DEFAULT_SOURCE_DIRS + GENRE_BALANCE; kernel drafter stays book-agnostic."
  - "Error events emitted BEFORE raising ModeBDrafterBlocked on tenacity exhaustion (ADR-003 observability-is-load-bearing) — forensic trail survives even wedged nightly runs."

patterns-established:
  - "Pattern 1: Clone-not-abstract Mode-B — fresh concrete satisfying frozen Drafter Protocol; shared strings paraphrased; no import from the sibling mode."
  - "Pattern 2: Frozen-dataclass cost kernel — ModelPricing is immutable per-process so spend-cap accounting can't be hot-swapped mid-run."
  - "Pattern 3: 4th CLI-composition-seam — new subcommand + book_specifics pointer module + single pyproject ignore_imports entry; test_import_contracts documented_exemptions set updated in lockstep."

requirements-completed: [DRAFT-03, DRAFT-04]

# Metrics
duration: ~40 min
completed: 2026-04-23
---

# Phase 5 Plan 01: Mode-B Drafter + Preflag Reader + Pricing Table + Voice-Samples Curator Summary

**Mode-B frontier drafter (Opus 4.7 with 1h ephemeral cache on voice-samples prefix) + pure preflag reader + authoritative \$5/\$25 pricing table + atomic voice-samples curator CLI — unblocks Plan 05-02 regen-budget + spend-cap enforcement.**

## Performance

- **Duration:** ~40 min (3 tasks executed sequentially)
- **Completed:** 2026-04-23
- **Tasks:** 3 (all with TDD RED/GREEN cadence — 6 atomic commits)
- **Files created:** 17
- **Files modified:** 5
- **Tests added:** 26 new tests (8 pricing + 9 Mode-B + 4 preflag + 4 CLI + 1 exemption-contract)
- **Baseline:** 516 → 542 non-slow tests passing (+26, zero regressions)

## Accomplishments

- **DRAFT-03 landed:** `ModeBDrafter` concrete satisfies the frozen `Drafter` Protocol with `mode='B'`, calls Anthropic Opus 4.7 via `messages.create`, caches the voice-samples prefix at `ttl='1h'` on a preserved `_system_blocks` list object (byte-identical cache prefix across every `draft()` call — Pitfall 1 mitigated).
- **DRAFT-04 landed:** `is_preflagged(scene_id, preflag_set)` pure function + `load_preflag_set()` loader reading `config/mode_preflags.yaml` via `PreflagConfig` typed loader. Ready for Plan 05-02 scene-loop integration.
- **Authoritative pricing table:** `config/pricing.yaml` ships Opus 4.7 at \$5/\$25/\$0.50-cache-read per MTok + Sonnet 4.6 at \$3/\$15/\$0.30. `event_cost_usd(event, pricing)` pure function converts OBS-01 Event token counts to USD (unknown model → 0.0, not exception). Hard-coded canary test detects Pitfall 5 drift at CI time.
- **Voice-samples curation CLI:** `book-pipeline curate-voice-samples --source-dir <dir>` walks `narrative_/essay_/analytic_*.txt` files in the 300-700 word slack band, selects `GENRE_BALANCE` (2/2/1) for `TARGET_COUNT=5`, writes `config/voice_samples.yaml` atomically via tmp+rename. Exits 1 on insufficient candidates with actionable stderr hints.
- **Clone-not-abstract discipline preserved:** `grep -c "from book_pipeline.drafter.mode_a" src/book_pipeline/drafter/mode_b.py` returns 0. Mode-A untouched.
- **B-3 lineage invariant preserved:** `DraftResponse.voice_pin_sha == voice_pin.checkpoint_sha` on every Mode-B draft — downstream chapter-frontmatter assembly keeps working.
- **OBS-01 compliance:** exactly one `role='drafter'` Event per `draft()` call with `mode='B'`, `model='claude-opus-4-7'`, `cached_tokens` propagated from `resp.usage.cache_read_input_tokens`. Error paths emit BEFORE raising (ADR-003).

## Task Commits

Each task followed strict TDD RED → GREEN cadence:

1. **Task 1: Pricing table + 3 config loaders (RED + GREEN)**
   - RED: `c54cfae` (`test(05-01): RED — failing tests for pricing kernel`)
   - GREEN: `decb984` (`feat(05-01): GREEN — pricing kernel + 3 config loaders`)

2. **Task 2: ModeBDrafter + preflag reader + Jinja2 template (RED + GREEN)**
   - RED: `9596f92` (`test(05-01): RED — failing tests for Mode-B drafter + preflag`)
   - GREEN: `e3df58f` (`feat(05-01): GREEN — Mode-B drafter + preflag reader (DRAFT-03 + DRAFT-04 per D-01..D-04)`)

3. **Task 3: curate-voice-samples CLI + book_specifics pointer + import-linter exemption (RED + GREEN)**
   - RED: `65c009a` (`test(05-01): RED — failing tests for curate-voice-samples CLI`)
   - GREEN: `d0f141d` (`feat(05-01): GREEN — curate-voice-samples CLI + book-specifics pointer + import-linter exemption`)

**Plan metadata commit:** pending (SUMMARY.md + STATE.md + ROADMAP.md metadata commit follows).

## Files Created/Modified

### Kernel modules (drafter)
- `src/book_pipeline/drafter/mode_b.py` — ModeBDrafter + ModeBDrafterBlocked + paraphrased VOICE_DESCRIPTION/RUBRIC_AWARENESS + tenacity-wrapped Opus call + single-Event emission on success/error.
- `src/book_pipeline/drafter/preflag.py` — `is_preflagged()` pure function + `load_preflag_set()` loader.
- `src/book_pipeline/drafter/templates/mode_b.j2` — USER-message Jinja2 template (scene-specific content only; cached voice-samples live in system=).
- `src/book_pipeline/drafter/__init__.py` — re-export Mode-B symbols via B-1 fallback-import pattern.

### Kernel modules (observability + config)
- `src/book_pipeline/observability/pricing.py` — `ModelPricing` frozen dataclass + `event_cost_usd()` pure fn.
- `src/book_pipeline/config/pricing.py` — `PricingConfig(BaseSettings)` + `ModelPricingEntry(BaseModel)` with negative-USD field_validator.
- `src/book_pipeline/config/mode_preflags.py` — `PreflagConfig(BaseSettings)`.
- `src/book_pipeline/config/voice_samples.py` — `VoiceSamplesConfig(BaseSettings)`.

### CLI + book-specifics
- `src/book_pipeline/cli/curate_voice_samples.py` — book-pipeline curate-voice-samples subcommand with atomic tmp+rename YAML write.
- `src/book_pipeline/book_specifics/voice_samples.py` — DEFAULT_SOURCE_DIRS + GENRE_BALANCE + TARGET_WORD_MIN/MAX + SLACK_* + classify_filename().
- `src/book_pipeline/cli/main.py` — append `book_pipeline.cli.curate_voice_samples` to SUBCOMMAND_IMPORTS.

### Config YAML
- `config/pricing.yaml` — Opus 4.7 \$5/\$25/\$0.50/\$10/\$6.25 + Sonnet 4.6 \$3/\$15/\$0.30/\$6/\$3.75.
- `config/mode_preflags.yaml` — 3 placeholder seed beats (Phase 6 reconciles against outline.md).
- `config/voice_samples.yaml` — empty placeholder (curate CLI populates).

### Tests
- `tests/drafter/test_mode_b.py` — 9 tests (Protocol conformance, cache identity, cache_control shape, voice-samples validators, tenacity exhaustion, single Event per call, B-3 passthrough, error Event on exhaustion).
- `tests/drafter/test_preflag.py` — 4 tests (True / False / empty-set / load_preflag_set returns frozenset).
- `tests/observability/test_pricing.py` — 8 tests (cost uncached / cached / unknown / frozen dataclass / pricing YAML loads \$5 canary / negative rejection / preflag YAML / voice_samples YAML).
- `tests/observability/__init__.py` — new test package anchor.
- `tests/cli/test_curate_voice_samples.py` — 4 tests (CLI discoverable / writes YAML / rejects short sources / atomic write).

### Meta
- `pyproject.toml` — 4th CLI composition-seam exemption in contract-1 ignore_imports.
- `tests/conftest.py` — FakeAnthropicClient + FakeAnthropicUsage + fake_anthropic_factory + pricing_fixture.
- `tests/test_import_contracts.py` — documented_exemptions set += curate_voice_samples.py; new test_cli_curate_voice_samples_exemption_registered test.

## Decisions Made

Every locked user decision (D-01..D-04, D-17) has a corresponding shipped artifact:

- **D-01** → `src/book_pipeline/drafter/mode_b.py` with zero imports from `mode_a.py` (clone-not-abstract verified via grep).
- **D-02** → `cache_control={'type':'ephemeral','ttl':'1h'}` on preserved `_system_blocks` list; Opus 4.7 via `anthropic.messages.create`.
- **D-03** → `ModeBDrafter.__init__` validates `len(samples) >= 3` + word_count in `[300, 700]`; `curate-voice-samples` CLI + `book_specifics/voice_samples.py` with ANALYTIC/ESSAY/NARRATIVE balance; `config/voice_samples.yaml` populated via curator.
- **D-04** → `PreflagConfig` loader + `is_preflagged()` pure function + `load_preflag_set()` returning immutable frozenset; `config/mode_preflags.yaml` with 3 seed beats.
- **D-17** → `config/pricing.yaml` with verified \$5/\$25 Opus 4.7 pricing; Pitfall 5 canary test hard-codes `input_usd_per_mtok == 5.0`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Subprocess CLI invocation pattern required `uv run`, not bare `sys.executable`**
- **Found during:** Task 3 (CLI test run)
- **Issue:** Initial `tests/cli/test_curate_voice_samples.py` used `subprocess.run([sys.executable, "-m", "book_pipeline.cli.main", ...])`. The system `python3` on the test host doesn't have the book_pipeline venv on its path, so the subprocess silently exited with zero output and non-zero returncode.
- **Fix:** Switched to `["uv", "run", "book-pipeline", ...]` — the Plan 04-05 `tests/cli/test_chapter_cli.py` precedent pattern. Works because `uv run` auto-resolves the project venv + the installed book-pipeline entry point.
- **Files modified:** `tests/cli/test_curate_voice_samples.py`
- **Verification:** All 4 CLI tests green (`uv run pytest tests/cli/test_curate_voice_samples.py`).
- **Committed in:** `d0f141d` (Task 3 GREEN commit)

**2. [Rule 3 - Blocking] `test_kernel_does_not_import_book_specifics` grep scan missed new CLI seam file**
- **Found during:** Final aggregate test run
- **Issue:** `tests/test_import_contracts.py::test_kernel_does_not_import_book_specifics` enforces a grep-level invariant (no kernel source file contains the literal "book_specifics" substring outside documented exemptions). Adding `cli/curate_voice_samples.py` as the 4th CLI-composition-seam required extending the `documented_exemptions` set — same pattern as Plans 03-02 / 04-05 followed.
- **Fix:** Added `pathlib.Path("src/book_pipeline/cli/curate_voice_samples.py")` to the `documented_exemptions` set in `tests/test_import_contracts.py`.
- **Files modified:** `tests/test_import_contracts.py`
- **Verification:** All 11 import-contract tests green.
- **Committed in:** `d0f141d` (Task 3 GREEN commit)

**3. [Rule 1 - Bug] Ruff ambiguous-character + unused-import cleanup**
- **Found during:** Tasks 1, 2, 3 lint gates
- **Issue:** `ruff check` flagged (a) unicode `×` in pricing.py docstring (RUF002), (b) unused `from anthropic import APIConnectionError` + unused `ModeBDrafter` re-import in test_mode_b.py, (c) import sort order.
- **Fix:** Replaced `×` → `x` in docstring; removed unused imports; auto-ran `ruff check --fix` for import order.
- **Files modified:** `src/book_pipeline/observability/pricing.py`, `tests/drafter/test_mode_b.py`, `tests/cli/test_curate_voice_samples.py`.
- **Committed in:** Task GREEN commits (inline with the feat landing).

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 bug/lint).
**Impact on plan:** All auto-fixes preserve intended behavior. No scope creep.

## Issues Encountered

- None beyond the 3 deviations above.

## Known Stubs

- `config/voice_samples.yaml` ships with `passages: []` (placeholder). The `curate-voice-samples` CLI is ready to populate it from paul-thinkpiece-pipeline voice-samples directories; production use requires the operator to run the curator once. `ModeBDrafter.__init__` fails loud if instantiated against empty/short samples, so this stub cannot silently reach production. Not blocking Plan 05-02.
- `config/mode_preflags.yaml` ships with 3 placeholder beat IDs (`ch01_sc01`, `ch14_sc02`, `ch26_sc03`). `TODO(phase6): verify beat IDs against outline.md`. Plan 05-02 reads the frozenset opaquely; exact beat IDs are a book-domain operator task, not a kernel correctness one.

## Operator Follow-ups (Phase 6)

- **Pricing drift in `openclaw/cron_jobs.json`:** the openclaw cron config references outdated \$15/\$75 Opus 4.7 pricing. Our `config/pricing.yaml` is authoritative for spend-cap conversion; the openclaw drift is documentation-only and non-blocking. File a Phase 6 housekeeping task to reconcile.
- **Verify placeholder preflag beat IDs** against `outline.md` canonical beat inventory before the first production nightly run.
- **Populate `config/voice_samples.yaml`** via `book-pipeline curate-voice-samples` before wiring Plan 05-02 Mode-B escalation into the scene loop.

## Next Phase Readiness

Plan 05-02 can now consume:
- `ModeBDrafter` class (Drafter Protocol impl).
- `ModeBDrafterBlocked` exception class (scene-loop routing).
- `is_preflagged()` + `load_preflag_set()` pure functions (preflag gate).
- `event_cost_usd()` + `ModelPricing` + `PricingConfig` (spend-cap conversion).
- `PreflagConfig` loader.
- `VoiceSamplesConfig` loader (for wiring the drafter at composition-root time).

No blockers for Plan 05-02. No new PyPI dependencies added.

## Self-Check: PASSED

**Files:**
- FOUND: src/book_pipeline/drafter/mode_b.py
- FOUND: src/book_pipeline/drafter/preflag.py
- FOUND: src/book_pipeline/drafter/templates/mode_b.j2
- FOUND: src/book_pipeline/observability/pricing.py
- FOUND: src/book_pipeline/config/pricing.py
- FOUND: src/book_pipeline/config/mode_preflags.py
- FOUND: src/book_pipeline/config/voice_samples.py
- FOUND: src/book_pipeline/cli/curate_voice_samples.py
- FOUND: src/book_pipeline/book_specifics/voice_samples.py
- FOUND: config/pricing.yaml
- FOUND: config/mode_preflags.yaml
- FOUND: config/voice_samples.yaml
- FOUND: tests/drafter/test_mode_b.py
- FOUND: tests/drafter/test_preflag.py
- FOUND: tests/observability/test_pricing.py
- FOUND: tests/cli/test_curate_voice_samples.py

**Commits:**
- FOUND: c54cfae (test 05-01 RED pricing)
- FOUND: decb984 (feat 05-01 GREEN pricing + loaders)
- FOUND: 9596f92 (test 05-01 RED Mode-B + preflag)
- FOUND: e3df58f (feat 05-01 GREEN Mode-B + preflag)
- FOUND: 65c009a (test 05-01 RED CLI)
- FOUND: d0f141d (feat 05-01 GREEN CLI + exemption)

**Test suite:** 542 non-slow tests passing (baseline 516 + 26 new, zero regressions).

**Lint gate:** `bash scripts/lint_imports.sh` green (import-linter 2 contracts kept + ruff + mypy scoped).

---
*Phase: 05-mode-b-escape-regen-budget-alerting-nightly-orchestration*
*Completed: 2026-04-23*
