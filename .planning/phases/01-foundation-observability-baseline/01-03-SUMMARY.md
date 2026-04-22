---
phase: 01-foundation-observability-baseline
plan: 03
subsystem: typed-config-loader-and-validate-cli
tags: [pydantic-settings, yaml, config, cli, validate-config, found-02, foundation]
requirements_completed: [FOUND-02]
dependency_graph:
  requires:
    - "01-01 (uv venv + CLI register_subcommand API + SUBCOMMAND_IMPORTS pre-declared entry)"
  provides:
    - "4 YAML config templates under config/ (voice_pin, rubric, rag_retrievers, mode_thresholds)"
    - "5 Pydantic-Settings models (VoicePinConfig, RubricConfig, RagRetrieversConfig, ModeThresholdsConfig, SecretsConfig)"
    - "Shared YamlConfigSettingsSource with strict FileNotFoundError + non-dict ValueError semantics"
    - "load_all_configs() — single call returning typed {voice_pin, rubric, rag_retrievers, mode_thresholds, secrets}"
    - "book-pipeline validate-config CLI subcommand (exit codes 0/1/2/3; secrets never leak)"
    - "pydantic-settings override pattern for tests: monkeypatch.chdir(tmp_path) with a local config/ subdir"
  affects:
    - "Plan 01-04 (openclaw workspace bootstrap — will read voice_pin.yaml via VoicePinConfig)"
    - "Plan 01-05 (EventLogger — may read rubric_version + mode tags via RubricConfig / ModeThresholdsConfig)"
    - "Phase 2 RAG-01/CORPUS-02 (RagRetrieversConfig drives all 5 retrievers' index paths + source files)"
    - "Phase 3 DRAFT-01 (VoicePinConfig.voice_pin.checkpoint_sha gets replaced with real SHA; runtime SHA match enforced)"
    - "Phase 3 CRITIC-01 (RubricConfig is the rubric-grading ground truth)"
    - "Phase 3 REGEN-01 / Phase 5 alerts (ModeThresholdsConfig drives R budget, Mode-A→B escalation, oscillation, Telegram cool-down)"
tech_stack:
  added:
    - "types-PyYAML-style ignore via mypy.ini [mypy-yaml] override (no new package — uses existing PyYAML at runtime)"
  patterns:
    - "Each config model subclasses BaseSettings with model_config.yaml_file=<relative path>"
    - "Shared YamlConfigSettingsSource subclasses pydantic_settings.YamlConfigSettingsSource so pydantic-settings' internal isinstance-based warning check recognizes us (no unused-yaml_file UserWarning)"
    - "field_validator enforces exact required key sets on axes + retrievers (frozenset comparisons, lexically-sorted error messages)"
    - "SecretStr + is_*_present() booleans so secret values are never handed to callers that don't call get_secret_value() deliberately"
    - "Tests override yaml_file by monkeypatch.chdir(tmp_path) + tmp_path/config/ subdir — the relative path in model_config resolves against cwd, never touching the real repo config/"
key_files:
  created:
    - "config/voice_pin.yaml"
    - "config/rubric.yaml"
    - "config/rag_retrievers.yaml"
    - "config/mode_thresholds.yaml"
    - "src/book_pipeline/config/__init__.py"
    - "src/book_pipeline/config/sources.py"
    - "src/book_pipeline/config/voice_pin.py"
    - "src/book_pipeline/config/rubric.py"
    - "src/book_pipeline/config/rag_retrievers.py"
    - "src/book_pipeline/config/mode_thresholds.py"
    - "src/book_pipeline/config/secrets.py"
    - "src/book_pipeline/config/loader.py"
    - "src/book_pipeline/cli/validate_config.py"
    - "tests/test_config.py"
    - "tests/test_validate_config_cli.py"
  modified:
    - "mypy.ini (added [mypy-yaml] ignore_missing_imports = True)"
decisions:
  - "YamlConfigSettingsSource SUBCLASSES the built-in pydantic_settings.YamlConfigSettingsSource (rather than reimplementing from PydanticBaseSettingsSource as the plan's <action> code showed). Reason: pydantic-settings v2.14 emits a UserWarning at every instantiation if model_config has yaml_file set but no isinstance-matching YAML source is wired. Subclassing eliminates the warning while still layering our stricter FileNotFoundError + non-mapping ValueError semantics on top via __init__ post-check and _read_file override. Contract is identical."
  - "Relative yaml_file path in model_config (resolved against cwd) was kept as-is rather than promoted to an absolute path. The relative form is what makes the monkeypatch.chdir(tmp_path) test override pattern work without mutating model_config internals. A separate Phase 2 plan could introduce an env-var-based override (e.g., BOOK_PIPELINE_CONFIG_DIR) if bootstrapping from another cwd becomes necessary, but Phase 1 doesn't need it."
  - "SecretsConfig uses pydantic.SecretStr, not plain str. Guarantees repr() output stays masked even if a future caller accidentally prints a SecretsConfig instance. The only way to get the raw value is a deliberate .get_secret_value() call — which greps as self-documenting."
  - "Added `# type: ignore[call-arg]` on the zero-arg pydantic-settings instantiations in loader.py. These are the documented pydantic-settings usage pattern (fields are populated from external sources), but mypy --strict can't see past the BaseModel.__init__ signature. The ignore is tight to the call site and the surrounding comment documents why it's needed."
  - "pydantic-settings-emitted UserWarning avoided — chose subclassing over a warnings.filterwarnings('ignore', ...) call on startup, because suppressing the warning class would also hide other legitimate pydantic-settings warnings later phases might care about."
  - "Test fixture for missing-field error (`test_missing_field_in_voice_pin_raises_with_field_name`) uses monkeypatch.chdir into a hand-rolled voice_pin.yaml missing only `base_model`, so the assertion `'base_model' in str(exc.value)` pins the error-message contract directly to the field name pydantic reports."
  - "CLI subcommand registration leverages plan 01's already-declared SUBCOMMAND_IMPORTS entry (`book_pipeline.cli.validate_config`). Creating the module was sufficient — no main.py edit. This matches the plan 01 design intent (Wave 2+ plans add modules without coordinating main.py edits)."
metrics:
  duration_minutes: 7
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 15
  files_modified: 1
  tests_added: 22
  tests_passing: 22
commits:
  - hash: 5327615
    type: test
    summary: RED — failing tests for 4 YAML configs + Pydantic-Settings models + SecretsConfig
  - hash: 244d5a4
    type: feat
    summary: GREEN — 4 YAML configs + Pydantic-Settings models + load_all_configs
  - hash: 8e10933
    type: feat
    summary: book-pipeline validate-config CLI subcommand
---

# Phase 1 Plan 3: Typed Config Loader + validate-config CLI Summary

**One-liner:** FOUND-02 complete — 4 YAML configs under `config/` load into 5 Pydantic-Settings models via a shared strict `YamlConfigSettingsSource`, exposed through `load_all_configs()` and the `book-pipeline validate-config` CLI subcommand that reports presence-only secret status (values never leak).

## What Shipped

A typed, validated, fail-fast config surface for every downstream phase:

- **4 YAML config templates** under `config/` — each annotated with purpose, Phase-3-populates-later fields, and per-field rationale in header comments.
- **5 Pydantic-Settings models** (`VoicePinConfig`, `RubricConfig`, `RagRetrieversConfig`, `ModeThresholdsConfig`, `SecretsConfig`) — every field validated at load time; extra top-level keys rejected (`extra="forbid"`); 5-axis + 5-retriever name sets enforced by `@field_validator`.
- **`YamlConfigSettingsSource`** (`src/book_pipeline/config/sources.py`) — subclasses pydantic-settings' built-in YAML source to keep pydantic-settings' internal type-check happy (no UserWarnings), then layers strict FileNotFoundError + non-dict ValueError semantics on top.
- **`load_all_configs()`** — one call, one typed dict with 5 keys; any validation/filesystem/YAML error propagates with a clear message.
- **`book-pipeline validate-config`** CLI subcommand — registered via plan 01's `register_subcommand` API (no `main.py` edit required; plan 01 pre-declared this module in `SUBCOMMAND_IMPORTS`). Exit codes 0/1/2/3 for success / ValidationError / FileNotFoundError / other; prints structured config summary + PRESENT/MISSING for each of the 4 secrets.
- **22 new tests** (17 config + 5 CLI) — all pass; full suite at 81 passing.
- **mypy --strict clean** on `src/book_pipeline/config` and `src/book_pipeline/cli`.
- **ruff + ruff-format clean** on all touched files.

## The 4 YAML Configs (Final Shape)

### `config/voice_pin.yaml`

Pins the voice-FT checkpoint consumed by Mode-A drafter. Phase 1 uses placeholders for `source_commit_sha`, `checkpoint_sha`, `ft_run_id`, `trained_on_date` — all with the literal `"TBD-phase3"`. Phase 3 DRAFT-01 replaces them with real values and enforces a runtime SHA match at the vLLM-serve handshake.

```yaml
voice_pin:
  source_repo, source_commit_sha, ft_run_id, checkpoint_path, checkpoint_sha,
  base_model, trained_on_date, pinned_on_date, pinned_reason,
  vllm_serve_config: { port, max_model_len, dtype, tensor_parallel_size }
```

Validators: `port ∈ [1024, 65535]`, `max_model_len ≥ 512`, `dtype ∈ {bfloat16, float16, fp8, nvfp4}`, `tensor_parallel_size ∈ [1, 8]`.

### `config/rubric.yaml`

5-axis critic rubric. Axis names are **frozen** at v1: `{historical, metaphysics, entity, arc, donts}` — renaming or adding requires bumping `rubric_version`. Events (plan 01-02 Event schema) already carry `rubric_version` so historical data remains interpretable after a version bump.

```yaml
rubric_version: "v1"
axes:
  <axis_name>: { description, severity_thresholds: {low, mid, high}, weight }
```

Validators: per-axis `severity_thresholds` ∈ [0,1], `weight` ∈ [0, 2], and `@field_validator("axes")` rejects any key set other than the required 5.

### `config/rag_retrievers.yaml`

5 typed retrievers + shared embeddings + bundler. Retriever names are **frozen**: `{historical, metaphysics, entity_state, arc_position, negative_constraint}`.

```yaml
embeddings: { model, model_revision, dim, device }
bundler: { max_bytes, assembly_strategy, enforce_cap, emit_conflicts_to }
retrievers:
  <retriever_name>: { index_path, source_files[], chunk_strategy, auto_update_from? }
```

`bundler.max_bytes = 40960` per RAG-03 (ContextPack cap). `embeddings.model_revision` is placeholder `"TBD-phase2"` — Phase 2 RAG-01 pins the real HF revision hash.

### `config/mode_thresholds.yaml`

Mode A/B dial per ADR-001 + oscillation detector + Telegram alert cool-down.

```yaml
mode_a: { regen_budget_R, per_scene_cost_cap_usd, voice_fidelity_band: {min, max} }
mode_b: { model_id, per_scene_cost_cap_usd, regen_attempts, prompt_cache_ttl }
oscillation: { enabled, max_axis_flips }
alerts: { telegram_cool_down_seconds, dedup_window_seconds }
preflag_beats: []   # Phase 5 populates with Cholula stir / two-thirds reveal / siege climax
```

Phase-1 defaults that later phases override:
- `mode_a.regen_budget_R = 3` (REGEN-02; Phase 5 LOOP-01 enforces)
- `mode_a.per_scene_cost_cap_usd = 0.0` (local model, zero marginal cost)
- `mode_b.model_id = claude-opus-4-7` (active 2026-04-16+ per STACK.md)
- `mode_b.per_scene_cost_cap_usd = 2.00` (Phase 5 enforces as hard cap)
- `alerts.telegram_cool_down_seconds = 3600` per ALERT-02

## Secrets Handling (`.env` via Pydantic-Settings)

`SecretsConfig` reads 4 env vars (via alias to canonical upper-case names), wraps each in `SecretStr`, and exposes only boolean presence:

| env var                  | field                    | presence check             |
| ------------------------ | ------------------------ | -------------------------- |
| `ANTHROPIC_API_KEY`      | `anthropic_api_key`      | `is_anthropic_present()`   |
| `OPENCLAW_GATEWAY_TOKEN` | `openclaw_gateway_token` | `is_openclaw_present()`    |
| `TELEGRAM_BOT_TOKEN`     | `telegram_bot_token`     | `is_telegram_present()` \* |
| `TELEGRAM_CHAT_ID`       | `telegram_chat_id`       | (part of telegram check)   |

`is_telegram_present()` requires **both** bot token and chat id.

**Contract:** `repr(SecretsConfig())` and `str(SecretsConfig())` never contain the raw secret value (`test_secrets_does_not_leak_value_in_repr` asserts this directly). The only way to extract a raw key is a deliberate `.get_secret_value()` call — which greps cleanly and is self-documenting.

## pydantic-settings Test-Override Pattern (for Phase 2+ authors)

**Problem:** `config/*.yaml` paths are declared in each config model's `model_config` as relative paths. Tests need to exercise validators with bad fixtures without touching the real `config/` directory.

**Solution (the only one that works):** `monkeypatch.chdir(tmp_path)` into a directory that contains a `config/` subdir with the test fixture. Pydantic-settings resolves the relative `yaml_file` against `cwd` at instantiation time, so the test fixture is loaded instead of the real repo config.

```python
def test_rubric_rejects_wrong_axes(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "rubric.yaml").write_text(... bad fixture ...)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as exc:
        RubricConfig()   # loads tmp_path/config/rubric.yaml
    assert "axes" in str(exc.value)
```

**Anti-pattern — DOES NOT WORK:** `RubricConfig(_yaml_file=str(bad))`. `_yaml_file` is **not** a valid `BaseSettings` constructor kwarg; pydantic-settings silently drops it and loads the real repo config. The `ValidationError` assertion would then pass trivially (the real 5-axis config loads fine) — a false green that never exercises the validator.

`tests/test_config.py` ships a counterpart `test_rubric_accepts_valid_5_axes` that uses the same `monkeypatch.chdir` pattern with a **valid** 5-axis fixture and asserts the load succeeds — this proves the chdir actually redirected the loader and that the rejection test isn't a no-op.

Grep-verifiable:

- `grep -c 'monkeypatch.chdir' tests/test_config.py` → 10
- `grep '_yaml_file=' tests/test_config.py` → only in a docstring warning readers NOT to use it (zero production uses)

## CLI Contract

### Invocation

- `uv run book-pipeline validate-config` (installed entry point)
- `uv run python -m book_pipeline validate-config` (module invocation)

### Exit codes

| Code | Meaning                                       |
| ---- | --------------------------------------------- |
| 0    | All 4 configs valid; secrets summary printed  |
| 1    | Pydantic `ValidationError` (fields missing/bad) |
| 2    | `FileNotFoundError` (a required YAML absent)  |
| 3    | Other load error (malformed YAML, OS error)   |

### Sample success output

```
[OK] All 4 configs validated successfully.
  voice_pin.base_model        = Qwen/Qwen3-32B
  voice_pin.ft_run_id         = v9_or_v10_latest_stable
  rubric.rubric_version       = v1
  rubric.axes                 = ['arc', 'donts', 'entity', 'historical', 'metaphysics']
  rag_retrievers              = ['arc_position', 'entity_state', 'historical', 'metaphysics', 'negative_constraint']
  rag_retrievers.bundler_cap  = 40960 bytes
  mode_thresholds.regen_R     = 3
  mode_thresholds.mode_b_ttl  = 1h
  secrets (values never printed):
    ANTHROPIC_API_KEY        = MISSING
    OPENCLAW_GATEWAY_TOKEN   = MISSING
    TELEGRAM (bot+chat_id)   = MISSING (ok for Phase 1)
```

### Registration via plan 01's `register_subcommand` API

Zero `main.py` edits needed. Plan 01 pre-declared `"book_pipeline.cli.validate_config"` in `SUBCOMMAND_IMPORTS`; creating the module with a module-level `register_subcommand("validate-config", _add_parser)` was sufficient. On next CLI invocation, `_load_subcommands` imports the module, the registration fires, and `--help` lists the subcommand.

## Verification Evidence

Plan acceptance criteria:

| Criterion                                                                                  | Status | Evidence                                                                                                       |
| ------------------------------------------------------------------------------------------ | ------ | -------------------------------------------------------------------------------------------------------------- |
| `config/voice_pin.yaml`, `rubric.yaml`, `rag_retrievers.yaml`, `mode_thresholds.yaml` exist | PASS   | `test_yaml_file_exists_and_parses` (4 parametrized tests, all green)                                           |
| `yaml.safe_load` succeeds on each                                                          | PASS   | Same test                                                                                                      |
| `load_all_configs()` returns dict with 5 exact keys                                        | PASS   | `test_load_all_configs_returns_5_keys`                                                                         |
| `c['voice_pin'].voice_pin.base_model == "Qwen/Qwen3-32B"`                                  | PASS   | `test_voice_pin_loads_with_qwen3_32b` + CLI smoke                                                              |
| `c['rubric'].axes` has the 5 required names                                                | PASS   | `test_rubric_real_config_has_5_axes` + CLI smoke (`sorted(axes.keys())` matches)                               |
| `c['rag_retrievers'].retrievers` has the 5 required names                                  | PASS   | `test_rag_retrievers_has_5_required_names` + CLI smoke                                                         |
| `c['mode_thresholds'].mode_a.regen_budget_R == 3`                                          | PASS   | `test_mode_thresholds_regen_budget_is_3` + CLI smoke                                                           |
| `c['rag_retrievers'].bundler.max_bytes == 40960`                                           | PASS   | Asserted in `test_rag_retrievers_has_5_required_names`                                                         |
| `c['mode_thresholds'].mode_b.prompt_cache_ttl == "1h"`                                     | PASS   | `test_mode_thresholds_regen_budget_is_3`                                                                       |
| `test_rubric_rejects_wrong_axes` uses `monkeypatch.chdir(tmp_path)`                        | PASS   | Grep-verified 10 occurrences of `monkeypatch.chdir`; zero production uses of `_yaml_file=`                     |
| `test_rubric_rejects_wrong_axes` raises `ValidationError` with "axes" in message           | PASS   | Asserted in the test                                                                                           |
| `test_rubric_accepts_valid_5_axes` passes (counterpart proof of chdir override)            | PASS   | Green                                                                                                          |
| Missing-field + malformed-YAML error tests                                                 | PASS   | `test_missing_field_in_voice_pin_raises_with_field_name`, `test_malformed_yaml_raises_clear_error`             |
| `SecretsConfig` repr does not contain raw secret                                           | PASS   | `test_secrets_does_not_leak_value_in_repr`                                                                     |
| `uv run mypy src/book_pipeline/config` exits 0                                             | PASS   | "Success: no issues found in 8 source files"                                                                   |
| `uv run mypy src/book_pipeline/cli` exits 0                                                | PASS   | "Success: no issues found in 4 source files"                                                                   |
| `uv run pytest tests/test_config.py` passes all tests                                      | PASS   | 17 passed                                                                                                      |
| `uv run book-pipeline validate-config` exits 0 with `[OK]`                                 | PASS   | CLI smoke test output above                                                                                    |
| `uv run book-pipeline --help` contains `validate-config`                                   | PASS   | Verified via `grep validate-config`                                                                            |
| Setting bogus `ANTHROPIC_API_KEY` → output shows `PRESENT` but NOT the value               | PASS   | `test_validate_config_does_not_leak_secret`                                                                    |
| `main.py` contains `"book_pipeline.cli.validate_config"` in SUBCOMMAND_IMPORTS             | PASS   | Grep-verified (1 match)                                                                                        |
| `validate_config.py` contains `register_subcommand("validate-config", _add_parser)`        | PASS   | Grep-verified (1 match)                                                                                        |
| Deleting field from `config/voice_pin.yaml` → exit 1 + field name in stderr                | PASS   | `test_validate_config_fails_with_missing_field`                                                                |
| Full regression (81 tests pre + new)                                                       | PASS   | `uv run pytest` → 81 passed in 1.80s                                                                           |

Plan verify-block commands executed and produced expected output:

```
$ uv run pytest tests/test_config.py -x -v
17 passed in 0.19s

$ uv run python -c "from book_pipeline.config.loader import load_all_configs; ..."
voice_pin.base_model = Qwen/Qwen3-32B
rubric.axes count = 5
retrievers count = 5
R = 3

$ uv run book-pipeline validate-config         # exit 0, [OK] printed
$ uv run book-pipeline --help | grep validate-config   # match
$ uv run pytest tests/test_validate_config_cli.py -x -v
5 passed
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] `YamlConfigSettingsSource` subclassed built-in to silence pydantic-settings UserWarning**

- **Found during:** Task 1 GREEN verification (`uv run pytest tests/test_config.py`)
- **Issue:** The plan's `<action>` code implemented `YamlConfigSettingsSource` as a subclass of `PydanticBaseSettingsSource`. With pydantic-settings v2.14, every instantiation emitted `UserWarning: Config key 'yaml_file' is set in model_config but will be ignored because no YamlConfigSettingsSource source is configured. ...` because pydantic-settings' internal `_settings_warn_unused_config_keys` uses `isinstance(source, YamlConfigSettingsSource)` against its own built-in class.
- **Fix:** Kept the class name the plan specified (`YamlConfigSettingsSource`) and kept all its contractual semantics (FileNotFoundError on missing file, ValueError on non-dict payload), but changed the base class from `PydanticBaseSettingsSource` to pydantic-settings' built-in `YamlConfigSettingsSource`. Overrode `__init__` (post-super check for file existence and dict-mapping shape) and `_read_file` (same strict check earlier in the read path). This preserves 100% of the plan's specified external behavior while satisfying pydantic-settings' internal type check — no UserWarnings remain.
- **Files modified:** `src/book_pipeline/config/sources.py`
- **Commit:** `244d5a4`

**2. [Rule 3 — Blocking] mypy strict complained about bare `import yaml` and `BaseSettings()` zero-arg**

- **Found during:** Task 1 mypy pass (`uv run mypy src/book_pipeline/config`)
- **Issue a:** `import yaml` → `Library stubs not installed for "yaml"  [import-untyped]`. mypy strict refuses to type-check unknown third-party modules without stubs.
- **Fix a:** Added `[mypy-yaml]` section with `ignore_missing_imports = True` to `mypy.ini` — matching the existing pattern for `lancedb`, `sentence_transformers`, `python_json_logger`. Chose the mypy-config route over installing `types-PyYAML` to keep the dev dependency surface minimal (yaml type stubs would be another install for a single strategic `safe_load` call).
- **Issue b:** `VoicePinConfig()` (and the other 3 settings classes) → `Missing named argument "voice_pin" ...  [call-arg]`. mypy doesn't see that pydantic-settings populates fields from the YAML source wired in `settings_customise_sources`. This is the documented pydantic-settings usage pattern.
- **Fix b:** Added `# type: ignore[call-arg]` per line in `loader.py` with a comment block documenting why. Same pattern is standard across pydantic-settings codebases; `# type: ignore` is tight to the call site so any future refactor that makes mypy see through doesn't leave dangling ignores.
- **Files modified:** `mypy.ini`, `src/book_pipeline/config/loader.py`
- **Commit:** `244d5a4`

**3. [Style] ruff-format / import-sort auto-applied**

- **Found during:** Task 1/2 ruff verification
- **Issue:** `tests/test_config.py` had a blank line after the docstring before imports that ruff-format's import-sort rule normalizes; a handful of config modules had long lines ruff-format tightened.
- **Fix:** `uv run ruff check --fix` + `uv run ruff format`. Tests re-run and pass.
- **Commit:** Included in `244d5a4` and `8e10933` respectively.

**4. [Quality] Removed a redundant `# type: ignore[attr-defined]` on `"PRESENT"` literal**

- **Found during:** Task 2 mypy pass
- **Issue:** Initial CLI code had a stale `# type: ignore[attr-defined]` comment on a string literal where no attribute access occurred; mypy flagged it as `[unused-ignore]`.
- **Fix:** Removed the unused ignore. Kept the legitimate one on `secrets.is_telegram_present()`.
- **Commit:** `8e10933`

No Rule 4 (architectural) deviations. No checkpoints reached.

## Authentication Gates

None. This plan is config scaffolding — no network, no LLM calls, no secret values read for runtime use. `SecretsConfig` reads env vars **for presence reporting only**; Phase 1 doesn't dial out.

## Deferred Issues

None. Every acceptance criterion has an automated check; every verify command in the plan runs green.

**Future work already named in the plan** (not deferred bugs, just scheduled follow-ons):

- `voice_pin.checkpoint_sha` = `"TBD-phase3"` — Phase 3 DRAFT-01 replaces with real hash + enforces runtime SHA match at vLLM-serve handshake.
- `voice_pin.ft_run_id` = `"v9_or_v10_latest_stable"` — Phase 3 pins whichever is latest-stable at that time per PROJECT.md Key Decisions.
- `rag_retrievers.embeddings.model_revision` = `"TBD-phase2"` — Phase 2 RAG-01 pins real HF revision hash per LanceDB schema-migration concerns (changing embedding dims requires re-index).
- `mode_thresholds.preflag_beats` = `[]` — Phase 5 DRAFT-04 populates with Cholula stir / two-thirds reveal / siege climax per PROJECT.md.
- `mode_thresholds.oscillation.enabled` = true but Phase 5 LOOP-01 wires the actual detector.

## Known Stubs

None. Every config loader returns real validated data from a real YAML file on disk. No placeholder returns, no hard-coded empty dicts leaking to any UI surface.

The `"TBD-phase3"` / `"TBD-phase2"` string values in the YAMLs are **not** stubs in the UI sense — they are explicitly-documented phase-later pin points, readable by `validate-config`, and will be replaced with real values by the plan that owns each. Downstream code (Phase 3 SHA-check handshake) will fail loudly on the `"TBD"` string if it runs before Phase 3 replaces them, which is the desired behavior.

## Threat Flags

No new threat surface introduced beyond the plan's declared `<threat_model>`:

- **T-03-01 (Information Disclosure — SecretsConfig leak) — MITIGATED:** `SecretStr` + `is_*_present()` booleans; `test_secrets_does_not_leak_value_in_repr` asserts `repr()` never contains the value; `test_validate_config_does_not_leak_secret` asserts the CLI never prints the raw value.
- **T-03-02 (Tampering — Arbitrary YAML deserialization) — MITIGATED:** `yaml.safe_load` only (never `yaml.load`); all 4 root configs use `extra="forbid"` so unknown top-level keys raise a clear ValidationError.
- **T-03-03 (DoS — Malformed YAML crashes) — MITIGATED:** `validate-config` catches `ValidationError` (exit 1), `FileNotFoundError` (exit 2), and `yaml.YAMLError | ValueError | OSError` (exit 3) distinctly. `test_malformed_yaml_raises_clear_error` verifies the YAML error path.
- **T-03-04 (Repudiation — Silent config changes) — ACCEPTED:** Pre-commit hooks (from plan 01-01) include `check-yaml`; reviewer sees diffs. No change from plan.

No new threat flags.

## Self-Check: PASSED

Artifact verification (files on disk):

- FOUND: `config/voice_pin.yaml` (20 lines, valid YAML, base_model=Qwen/Qwen3-32B)
- FOUND: `config/rubric.yaml` (5 axes with severity_thresholds + weight)
- FOUND: `config/rag_retrievers.yaml` (5 retrievers + BGE-M3 embeddings + 40960-byte bundler)
- FOUND: `config/mode_thresholds.yaml` (mode_a.regen_budget_R=3, mode_b.model_id=claude-opus-4-7)
- FOUND: `src/book_pipeline/config/__init__.py` (7-symbol `__all__`)
- FOUND: `src/book_pipeline/config/sources.py` (YamlConfigSettingsSource subclassing built-in)
- FOUND: `src/book_pipeline/config/voice_pin.py` (VllmServeConfig + VoicePinData + VoicePinConfig)
- FOUND: `src/book_pipeline/config/rubric.py` (AxisSeverity + RubricAxis + RubricConfig, 5-axis validator)
- FOUND: `src/book_pipeline/config/rag_retrievers.py` (EmbeddingsConfig + BundlerConfig + RetrieverConfig + RagRetrieversConfig, 5-retriever validator)
- FOUND: `src/book_pipeline/config/mode_thresholds.py` (VoiceFidelityBand + ModeAConfig + ModeBConfig + OscillationConfig + AlertsConfig + ModeThresholdsConfig)
- FOUND: `src/book_pipeline/config/secrets.py` (SecretsConfig with 4 SecretStr fields + 3 is_*_present() methods)
- FOUND: `src/book_pipeline/config/loader.py` (load_all_configs returning 5-key dict)
- FOUND: `src/book_pipeline/cli/validate_config.py` (registers `validate-config` via plan 01's API)
- FOUND: `tests/test_config.py` (17 tests)
- FOUND: `tests/test_validate_config_cli.py` (5 tests)
- FOUND: `mypy.ini` (added [mypy-yaml] override)

Commit verification on main:

- FOUND: `5327615` (test RED — config tests)
- FOUND: `244d5a4` (feat GREEN — 4 YAMLs + Pydantic-Settings models)
- FOUND: `8e10933` (feat — validate-config CLI subcommand)

All 3 per-task commits landed on `main` branch of `/home/admin/Source/our-lady-book-pipeline/`.
