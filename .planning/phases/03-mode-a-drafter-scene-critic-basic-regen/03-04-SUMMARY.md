---
phase: 03-mode-a-drafter-scene-critic-basic-regen
plan: 04
subsystem: mode-a-drafter-+-sampling-profiles-+-v-2-memorization-gate
tags: [mode-a, drafter, jinja2, sampling-profiles, memorization-gate, voice-fidelity-score, obs-03, draft-01, draft-02, v-2-mitigation, v-3-extension]
requirements_completed: [DRAFT-01, DRAFT-02, OBS-03]
dependency_graph:
  requires:
    - "03-01 (VoicePinData schema + voice_fidelity.sha helpers + 4 Phase 3 kernel packages — Plan 03-04 constructs ModeADrafter inside the drafter/ package)"
    - "03-02 (AnchorSet + compute_centroid + score_voice_fidelity + VoiceFidelityConfig — Plan 03-04 wires AnchorSetProvider on top of these, uses score_voice_fidelity per scene, classifies against VoiceFidelityConfig thresholds)"
    - "03-03 (VllmClient + VllmUnavailable + boot_handshake — Plan 03-04 consumes the already-handshook client; chat_completion is the per-scene call)"
  provides:
    - "src/book_pipeline/drafter/mode_a.py — ModeADrafter + ModeADrafterBlocked + VOICE_DESCRIPTION + RUBRIC_AWARENESS"
    - "src/book_pipeline/drafter/sampling_profiles.py — SamplingProfile + SamplingProfiles + resolve_profile + VALID_SCENE_TYPES"
    - "src/book_pipeline/drafter/memorization_gate.py — TrainingBleedGate + MemorizationHit (V-2 HARD BLOCK)"
    - "src/book_pipeline/drafter/templates/mode_a.j2 — Jinja2 system+user prompt template"
    - "src/book_pipeline/voice_fidelity/pin.py — AnchorSetProvider + AnchorSetDrift (V-3 extension for anchor drift)"
    - "src/book_pipeline/book_specifics/training_corpus.py — TRAINING_CORPUS_DEFAULT pointer (CLI composition seam)"
    - "config/mode_thresholds.yaml sampling_profiles: block — prose/dialogue_heavy/structural_complex defaults"
    - "Event role='drafter' shape with voice_fidelity_score + voice_fidelity_status + anchor_set_sha + voice_pin_sha in caller_context"
  affects:
    - "Plan 03-06 (regen + scene-loop orchestrator) — composes ModeADrafter + TrainingBleedGate(TRAINING_CORPUS_DEFAULT) + AnchorSetProvider(...) + shared BGE-M3 embedder; catches ModeADrafterBlocked to route HARD_BLOCKED into scene_state"
    - "Plan 03-05 (SceneCritic, already landed out-of-wave) — consumes Event.caller_context.scene_id + event_id to chain drafter→critic lineage"
    - "Plan 03-07/08 (CLI + smoke) — `book-pipeline draft <scene_id>` constructs the full chain; 03-08 smoke asserts exactly 1 role='drafter' Event per scene"
tech-stack:
  added: []  # All runtime deps already declared (jinja2 by Plan 03-03, pyarrow/xxhash by Plan 03-02).
  patterns:
    - "scene_type resolution order: (1) generation_config['scene_type'] if in VALID_SCENE_TYPES, (2) heuristic — join prior_scenes, count `\"[^\"]+\"` paired-quote substrings with re; >=3 → 'dialogue_heavy', (3) default 'prose'. Heuristic keeps the CLI orchestrator dumb — it can pass the outline scene_type straight through generation_config, and if the outline's silent on scene_type, the drafter still picks a sensible sampling profile."
    - "_emit_error_event() is called BEFORE raising ModeADrafterBlocked on every failure path (training_bleed, mode_a_unavailable, empty_completion, invalid_scene_type). T-03-04-03 mitigation — observability trail load-bearing. Future digest filter: `grep '\"error\":' runs/events.jsonl | grep '\"role\": \"drafter\"'` returns every drafter failure with expected shape."
    - "AnchorSetProvider caches (centroid, sha, config) after first .load(); Plan 03-06 CLI reconstructs the drafter per `book-pipeline draft` invocation so each CLI tick re-verifies the anchor SHA. Within a single tick, repeat loads skip the BGE-M3 embed — 15-30s saved per call in production."
    - "W-2 parquet fast-path: if indexes/voice_anchors/embeddings.parquet matches (N rows, 1024-dim), AnchorSetProvider assembles the centroid directly from parquet (L2-normalize rows, mean, L2-normalize) — no embedder call. On wrong shape or absence, log WARNING('parquet_mismatch_or_absent') and fall back to compute_centroid. Test 7a asserts embedder.call_count==0; 7b/7c assert ==1 plus warning."
    - "TrainingBleedGate xxh64_intdigest over UTF-8-encoded 12-grams. Stable across processes (unlike Python's stdlib hash() which randomizes per process via PYTHONHASHSEED). Plan 03-06 CLI builds the gate ONCE per run; the paul-thinkpiece-pipeline corpus (10,751 rows × ~100 12-grams ≈ 1M ints ≈ 8MB) preloads in ~5-10 seconds on DGX Spark SSD."
    - "Jinja2 Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True) + sentinel-split on ===SYSTEM=== / ===USER===. autoescape=False because the template output is LLM prompt text (not HTML) — escaping would corrupt retrieval chunks containing braces, quotes, em-dashes. Sentinel split makes the system/user messages trivially extractable; template authors can add prose above ===SYSTEM=== for inline documentation without corrupting the prompt."
    - "_to_int(value, default) helper: generation_config is dict[str, object] per the FROZEN types.py; int() doesn't accept object. Helper gracefully handles None, bad types, and fallback default — keeps the drafter robust to malformed generation_config without scattering try/except across call sites."
  key-files:
    created:
      - "src/book_pipeline/drafter/mode_a.py (~400 lines; ModeADrafter + ModeADrafterBlocked + VOICE_DESCRIPTION + RUBRIC_AWARENESS + helpers)"
      - "src/book_pipeline/drafter/sampling_profiles.py (~75 lines; SamplingProfile + SamplingProfiles + VALID_SCENE_TYPES + resolve_profile)"
      - "src/book_pipeline/drafter/memorization_gate.py (~130 lines; TrainingBleedGate + MemorizationHit)"
      - "src/book_pipeline/drafter/templates/mode_a.j2 (~35 lines; Jinja2 system+user template)"
      - "src/book_pipeline/voice_fidelity/pin.py (~180 lines; AnchorSetProvider + AnchorSetDrift + parquet fast-path)"
      - "src/book_pipeline/book_specifics/training_corpus.py (~20 lines; TRAINING_CORPUS_DEFAULT pointer)"
      - "tests/drafter/test_mode_a.py (~420 lines; 13 tests A-J covering Protocol conformance, happy path, scene_type, memorization, VllmUnavailable, empty completion, voice_fidelity classification, Event schema roundtrip, AnchorSetDrift)"
      - "tests/drafter/test_sampling_profiles.py (~130 lines; 8 tests)"
      - "tests/drafter/test_memorization_gate.py (~115 lines; 5 tests)"
      - "tests/voice_fidelity/test_pin.py (~300 lines; 6 tests — SHA match/mismatch, W-2 parquet branches, cache)"
      - ".planning/phases/03-mode-a-drafter-scene-critic-basic-regen/03-04-SUMMARY.md — this file"
    modified:
      - "src/book_pipeline/drafter/__init__.py (B-1 fallback-import exports for ModeADrafter + ModeADrafterBlocked + VOICE_DESCRIPTION + RUBRIC_AWARENESS)"
      - "src/book_pipeline/voice_fidelity/__init__.py (B-1 fallback-import exports for AnchorSetProvider + AnchorSetDrift)"
      - "src/book_pipeline/config/mode_thresholds.py (ModeThresholdsConfig.sampling_profiles: SamplingProfiles field with default_factory)"
      - "config/mode_thresholds.yaml (sampling_profiles: top-level block)"
key-decisions:
  - "(03-04) Quotes-heuristic threshold = 3 paired `\"..\"` substrings in prior_scenes concat. Any lower (e.g. 1 or 2) false-fires on quoted phrases in a prose scene's preceding summary; any higher (e.g. 5+) misses short dialogue-heavy scenes. 3 is the plan-pinned heuristic — Phase 6 thesis 005 can measure recall/precision on real book drafts. This is an observability default, not a correctness boundary: if wrong, the worst outcome is temp=0.7 vs 0.85 for one scene, which the critic will catch through voice-fidelity scoring."
  - "(03-04) voice_fidelity_status classification is PURELY observational — it does NOT gate the draft. Memorization gate is the separate hard block (V-2 mitigation); voice_fidelity_score is OBS-03 telemetry (eventually feeds into digest-level regressions via thesis registry). This decouples 'did Paul's voice come through' from 'did the model copy training data word-for-word'. Plan 03-02's thresholds: fail<0.75 / flag 0.75-0.78 / pass 0.78-0.95 / flag_memorization >=0.95."
  - "(03-04) _emit_error_event is a separate helper rather than a decorator / context manager. Plan 03-06 scene-loop orchestrator expects to see exactly ONE role='drafter' Event per draft() call (success XOR error). Using a helper keeps the emit-before-raise ordering explicit in the draft() body — easier to audit than decorator magic. Error event carries status='error', error=<reason>, and the failure-specific context (hits list, cause string, attempt_number) in extra."
  - "(03-04) Jinja2 mode_a.j2 uses `{% for retriever_name, result in retrievals.items() -%}` — dict iteration order is insertion order in Python 3.7+. ContextPack.retrievals comes from the Plan 02-05 bundler which iterates the 5 typed retrievers in fixed order. Prompt byte-shape is deterministic across runs given the same ContextPack, which keeps prompt_hash stable and cache-replayable for Phase 6 ablation harness."
  - "(03-04) ModeADrafter.__init__ calls anchor_provider.load() BEFORE accepting any draft request. AnchorSetDrift raised early makes the failure mode immediate (Plan 03-06 CLI fails at drafter construction, not mid-scene). Centroid + anchor_set_sha + VoiceFidelityConfig cached on self._centroid / self._anchor_set_sha / self._vf_config. Plan 03-06 reconstructs the drafter per CLI invocation — so stale cache inside one CLI tick is intentional (amortizes embed cost), and cross-tick freshness is enforced by re-construction."
  - "(03-04) `_to_int(value, default)` helper centralizes the dict[str, object] → int coercion. Alternative: assert isinstance at every call site. Helper is cleaner and matches the plan's goal-driven-execution karpathy guideline — 'make it robust, make it read naturally'."
  - "(03-04) Test 7 (SHA mismatch) uses `\"0\" * 64` for wrong SHA. My first-draft YAML fixture emitted that unquoted, which yaml.safe_load parses as int 0 — breaking the pydantic VoiceFidelityConfig (str field). Fixed by quoting the interpolated value `\"{anchor_set_sha}\"`. Same class of YAML footgun as Plan 03-01's yaml.safe_dump quoting decision (see Plan 03-01 Deviation #5); this time the fix is inline in the test fixture writer."
  - "(03-04) drafter/__init__.py uses B-1 fallback-import for ModeADrafter (not eager). Rationale: same wave-robustness as voice_fidelity/__init__.py; keeps Task 1's GREEN state importable before Task 2 lands mode_a.py. Plan 03-05 (SceneCritic, already landed) is unaffected because critic/ package has its own __init__.py."
metrics:
  duration_minutes: 28
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 10
  files_modified: 4
  tests_added: 32  # 8 sampling_profiles + 5 memorization_gate + 6 pin + 13 mode_a = 32 new
  tests_passing_after: 372  # was 343 baseline before Plan 03-04 (nominally; dialed by 3.05 landing out-of-wave); net +29 after Plan 03-04 (32 new - 0 removed + 0 parametrization savings; small discrepancy from parametrized test counting)
  slow_tests_added: 0
  scoped_mypy_source_files_after: 96
  scene_type_heuristic_quote_threshold: 3
  memorization_gate_ngram: 12
  memorization_gate_hash_algo: "xxhash.xxh64_intdigest"
  voice_fidelity_classification_thresholds:
    fail: "score < 0.75"
    flag_low: "0.75 <= score < 0.78"
    pass: "0.78 <= score < 0.95"
    flag_memorization: "score >= 0.95"
commits:
  - hash: 5b87b8b
    type: test
    summary: "Task 1 RED — failing tests for sampling_profiles + memorization_gate + AnchorSetProvider"
  - hash: 6d9dbce
    type: feat
    summary: "Task 1 GREEN — sampling_profiles + memorization_gate + AnchorSetProvider"
  - hash: c76950c
    type: test
    summary: "Task 2 RED — failing tests for ModeADrafter + Jinja2 template + Event shape"
  - hash: 6d69e1b
    type: feat
    summary: "Task 2 GREEN — ModeADrafter + Jinja2 mode_a.j2 template"
---

# Phase 3 Plan 04: Mode-A Drafter + Sampling Profiles + V-2 Memorization Gate Summary

**One-liner:** Mode-A drafter shipped end-to-end, Protocol-conformant — `book_pipeline.drafter.mode_a.ModeADrafter` satisfies the FROZEN Drafter Protocol (mode='A', `def draft(request) -> DraftResponse`, `isinstance(d, Drafter)` True) and composes six primitives into a single `draft()` call: (1) scene_type resolution (generation_config override → paired-quotes heuristic `re.findall(r'"[^"]+"', joined) >= 3` → default 'prose'), (2) DRAFT-02 per-scene-type sampling profile lookup via `SamplingProfiles` (prose temp=0.85 top_p=0.92, dialogue_heavy temp=0.7 top_p=0.90, structural_complex temp=0.6 top_p=0.88; all repetition_penalty=1.05 max_tokens=2048), (3) Jinja2 render of `drafter/templates/mode_a.j2` with sentinel-split on `===SYSTEM===` / `===USER===` assembling the vLLM messages list, (4) Plan 03-03 `VllmClient.chat_completion(model='paul-voice', temperature, top_p, max_tokens, repetition_penalty)` with `VllmUnavailable` → `ModeADrafterBlocked('mode_a_unavailable')` and empty/whitespace completion → `ModeADrafterBlocked('empty_completion')`, (5) V-2 `TrainingBleedGate(training_corpus_path, ngram=12)` preloading xxh64 12-gram hash set from paul-thinkpiece-pipeline `conversations[-1].from=='gpt'` rows — any hit → `ModeADrafterBlocked('training_bleed')` HARD BLOCK, (6) OBS-03 `score_voice_fidelity(scene_text, centroid, embedder)` with 4-way classification (fail <0.75, flag_low 0.75-0.78, pass 0.78-0.95, flag_memorization >=0.95). The AnchorSetProvider loads `config/voice_anchors/anchor_set_v1.yaml`, verifies its SHA against `mode_thresholds.voice_fidelity.anchor_set_sha` (mismatch → `AnchorSetDrift` at construction — V-3 extension for anchor drift), and exposes a W-2 parquet fast-path: if `indexes/voice_anchors/embeddings.parquet` matches (N rows × 1024 dim), the centroid is assembled from the parquet without calling BGE-M3; on shape mismatch or absence a WARNING is logged and `compute_centroid(anchors, embedder)` computes it fresh. Every draft emits exactly ONE `role='drafter'` OBS-01 Event — success path carries `mode='A'`, `checkpoint_sha=voice_pin.checkpoint_sha`, `caller_context={scene_id, chapter, pov, beat_function, scene_type, voice_pin_sha, anchor_set_sha, voice_fidelity_score, voice_fidelity_status, attempt_number, repetition_penalty}`, `extra={word_count, context_pack_fingerprint}`; failure path emits ONE error Event before raising with `extra={status: 'error', error: <reason>}` plus the failure-specific context. Kernel discipline preserved: `grep -c book_specifics src/book_pipeline/drafter/mode_a.py` == 0, substring scan green; CLI composition layer (Plan 03-06) injects `TRAINING_CORPUS_DEFAULT` + vllm endpoints via the sanctioned `ignore_imports` seams.

## Event Shape: `role='drafter'` (Mode-A success)

```json
{
  "schema_version": "1.0",
  "event_id": "<xxh64>",
  "ts_iso": "2026-04-22T19:14:10.123+00:00",
  "role": "drafter",
  "model": "paul-voice",
  "prompt_hash": "<xxh64 of rendered Jinja2 prompt>",
  "input_tokens": 42,
  "cached_tokens": 0,
  "output_tokens": 128,
  "latency_ms": 820,
  "temperature": 0.85,
  "top_p": 0.92,
  "caller_context": {
    "module": "drafter.mode_a",
    "function": "draft",
    "scene_id": "ch01_sc01",
    "chapter": 1,
    "pov": "Tonantzin",
    "beat_function": "discovery",
    "scene_type": "prose",
    "voice_pin_sha": "3f0ac5e2290dab633a19b6fb7a37d75f59d4961497e7957947b6428e4dc9d094",
    "anchor_set_sha": "28fd890bc4c8afc1d0e8cc33b444bc0978002b96fbd7516ca50460773e97df31",
    "voice_fidelity_score": 0.82,
    "voice_fidelity_status": "pass",
    "attempt_number": 1,
    "repetition_penalty": 1.05
  },
  "output_hash": "<xxh64 of scene_text>",
  "mode": "A",
  "rubric_version": null,
  "checkpoint_sha": "3f0ac5e2290dab633a19b6fb7a37d75f59d4961497e7957947b6428e4dc9d094",
  "extra": {
    "word_count": 1042,
    "context_pack_fingerprint": "<xxh64 of ContextPack>"
  }
}
```

## Event Shape: `role='drafter'` (error path)

```json
{
  "role": "drafter",
  "model": "paul-voice",
  "caller_context": {
    "module": "drafter.mode_a",
    "function": "draft",
    "scene_id": "ch01_sc01",
    "chapter": 1,
    "pov": "Tonantzin",
    "beat_function": "discovery",
    "scene_type": "prose",
    "voice_pin_sha": "<pin>",
    "anchor_set_sha": "<pin>",
    "attempt_number": 1
  },
  "output_hash": "<xxh64 of 'error:<reason>'>",
  "mode": "A",
  "checkpoint_sha": "<pin>",
  "extra": {
    "status": "error",
    "error": "training_bleed" | "mode_a_unavailable" | "empty_completion" | "invalid_scene_type",
    "hits": [<up to 5 12-gram strings, only on training_bleed>],
    "cause": "<underlying exception __str__, on mode_a_unavailable>",
    "attempt_number": 1
  }
}
```

Plan 03-06 scene-loop orchestrator: `except ModeADrafterBlocked as exc:` → `scene_state.transition_to_hard_blocked(reason=exc.reason, detail=exc.context)`. The error Event is already on disk for digest filtering before the exception propagates.

## SamplingProfiles Defaults (for Phase 6 ablation baselines)

| scene_type         | temperature | top_p | repetition_penalty | max_tokens |
| ------------------ | ----------- | ----- | ------------------ | ---------- |
| prose              | 0.85        | 0.92  | 1.05               | 2048       |
| dialogue_heavy     | 0.7         | 0.90  | 1.05               | 2048       |
| structural_complex | 0.6         | 0.88  | 1.05               | 2048       |

Committed to `config/mode_thresholds.yaml` `sampling_profiles:` block + reproduced in `SamplingProfiles` Pydantic model default_factory. Legacy yaml (without the block) still validates via the field's default_factory — tested by `test_mode_thresholds_config_loads_legacy_yaml_without_sampling_profiles`.

## TrainingBleedGate Preload Latency (for Plan 03-06 CLI startup UX)

Synthetic fixtures preload instantly (single-digit milliseconds). Production expectation on the real paul-thinkpiece-pipeline corpus at `/home/admin/paul-thinkpiece-pipeline/v3_data/train_filtered.jsonl` (10,751 rows from Plan 03-01 source_commit `c571bb7b`):

- Row scan + 12-gram enumeration + xxh64 hashing: ~5-10 seconds on DGX Spark SSD.
- Hash set size: ~1M 12-grams → ~8MB memory.
- Plan 03-06 CLI should preload ONCE per `book-pipeline draft` invocation and reuse across any regen attempts. Plan 03-06 CLI startup Event can include `preload_ms` for observability.

Plan 03-06 can override the default via `TrainingBleedGate(path, ngram=12)` if paul-thinkpiece-pipeline ships a v4 training corpus.

## AnchorSetProvider Caching Semantics

- **Per-instance.** The tuple `(centroid, sha, VoiceFidelityConfig)` is cached on `self._cache` after the first `.load()` call. Subsequent `.load()` calls skip the BGE-M3 embed.
- **Plan 03-06 reconstructs the drafter per CLI invocation** — so cross-CLI-tick freshness is enforced by the fact that `AnchorSetProvider.load()` runs anew each time, re-verifying the anchor SHA against the current `mode_thresholds.yaml`. Within a single tick, the cache amortizes the ~15-30s embed cost across any re-drafts of the same scene (Plan 03-06 regen inside one CLI call reuses the cached centroid).
- **W-2 parquet fast-path.** If `indexes/voice_anchors/embeddings.parquet` exists AND has shape `(len(anchors.anchors), 1024)`, the centroid is loaded directly from parquet — no BGE-M3 embed call. On wrong shape or absence, a WARNING is logged (`parquet_mismatch_or_absent at <path> ...; falling back to compute_centroid`) and the embedder path runs. Operators regenerate the parquet by re-running `book-pipeline curate-anchors` (Plan 03-02 CLI).

## VOICE_DESCRIPTION / RUBRIC_AWARENESS (for Plan 03-05 critic)

```python
VOICE_DESCRIPTION = (
    "You write in clean declarative prose with em-dash rhythm, numeric "
    "specificity in sensory description, and structural asides that sharpen "
    "rather than decorate. You resist purple prose, expository dumps, and "
    "genre-tropes-as-shorthand. Your sentences tend short; your paragraphs "
    "close on decisions, not gestures."
)

RUBRIC_AWARENESS = (
    "Do not reference factual claims the corpus section does not support. "
    "Preserve named-entity continuity from prior chapters. Do not romanticize, "
    "exoticize, or cartoonify violence, sexuality, or faith. Hit the stated "
    "beat function without narrating meta-structure."
)
```

Exported from `book_pipeline.drafter` so Plan 03-05's SceneCritic system prompt can share the rubric-awareness phrasing verbatim. The drafter's Jinja2 template embeds both strings; the critic can reuse `RUBRIC_AWARENESS` for consistency across phases.

## Plan 03-06 Composition Signature (drafter expected shape)

```python
from pathlib import Path

from book_pipeline.book_specifics.training_corpus import TRAINING_CORPUS_DEFAULT
from book_pipeline.book_specifics.vllm_endpoints import DEFAULT_BASE_URL, LORA_MODULE_NAME
from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
from book_pipeline.config.voice_pin import VoicePinConfig
from book_pipeline.drafter.memorization_gate import TrainingBleedGate
from book_pipeline.drafter.mode_a import ModeADrafter
from book_pipeline.drafter.vllm_client import VllmClient
from book_pipeline.observability.event_logger import JsonlEventLogger
from book_pipeline.rag.embedding import BgeM3Embedder
from book_pipeline.voice_fidelity.pin import AnchorSetProvider

# 1. Configs + pins.
pin = VoicePinConfig().voice_pin
thresholds = ModeThresholdsConfig()

# 2. Shared embedder (same BGE-M3 revision as RAG ingester).
embedder = BgeM3Embedder(...)

# 3. vLLM client + boot handshake (V-3 live).
event_logger = JsonlEventLogger()
vllm_client = VllmClient(
    base_url=DEFAULT_BASE_URL,
    event_logger=event_logger,
    lora_module_name=LORA_MODULE_NAME,
)
vllm_client.boot_handshake(pin)  # Plan 03-03 V-3 enforcement

# 4. Anchor provider + memorization gate (both preloaded once per CLI tick).
anchor_provider = AnchorSetProvider(
    yaml_path=Path("config/voice_anchors/anchor_set_v1.yaml"),
    thresholds_path=Path("config/mode_thresholds.yaml"),
    embedder=embedder,
)
memorization_gate = TrainingBleedGate(TRAINING_CORPUS_DEFAULT, ngram=12)

# 5. Drafter composition.
drafter = ModeADrafter(
    vllm_client=vllm_client,
    event_logger=event_logger,
    voice_pin=pin,
    anchor_provider=anchor_provider,
    memorization_gate=memorization_gate,
    sampling_profiles=thresholds.sampling_profiles,
    embedder_for_fidelity=embedder,
)
```

Plan 03-06 CLI catches `ModeADrafterBlocked` + `AnchorSetDrift` + `VoicePinMismatch` + `VllmHandshakeError` + `VllmUnavailable` at the top level and routes each to the appropriate HARD_BLOCKED scene_state reason.

## Deferred Items (Phase 6 + beyond)

1. **Per-sub-genre centroid scoring in the drafter Event.** `compute_per_sub_genre_centroids` exists (Plan 03-02) but the drafter only scores vs overall centroid. Phase 6 digest can report voice-drift by sub-genre using the existing function — no drafter change needed.
2. **Self-consistency check between per-sub-genre cosine and overall cosine.** Large discrepancy (e.g. overall=0.85, narrative=0.60) flags "this scene is drifting toward essay register in a narrative beat". Phase 6 digest computation.
3. **Structural preflag DRAFT-04** (not this plan; Phase 5). Phase 3 honors `scene_type: structural_complex` only for sampling profile dispatch; structural preflag routing to Mode-B is Phase 5.
4. **Memorization gate soft-flag band.** Currently any 12-gram hit is HARD BLOCK. Phase 6 thesis 005 may refine — e.g. flag band for <3 hits, hard block for >=3. Plan 03-04's choice is conservative: V-2 is the load-bearing pitfall, false positives cost one regen, false negatives cost voice-FT credibility.
5. **Parquet fast-path schema evolution.** Current parquet reader looks for columns `id`, `sub_genre`, `embedding`. If a future Plan adds per-anchor metadata (e.g. `word_count`, `date_curated`), the reader stays backwards-compatible because it only reads `embedding` — but the W-2 tests should gain coverage for new columns.
6. **vllm_endpoints import at CLI-composition layer** (not this plan; Plan 03-03 landed `src/book_pipeline/book_specifics/vllm_endpoints.py` and Plan 03-06 CLI will import it directly).
7. **Memorization gate that's corpus-version-aware.** Currently `TrainingBleedGate(path)` — no SHA check. If paul-thinkpiece-pipeline's `train_filtered.jsonl` drifts mid-run, the gate still works but operators lose the "which corpus version was blocked against?" audit trail. Phase 6 can wrap the gate path with its git-HEAD SHA and emit as Event.caller_context.training_corpus_sha.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] YAML interpolation of `"0" * 64` parsed as int.**

- **Found during:** Task 1 GREEN `test_anchor_set_provider_load_on_sha_mismatch_raises_drift`.
- **Issue:** My test fixture used `{anchor_set_sha}` unquoted in the YAML f-string. For SHA `"0" * 64` (pure digits), yaml.safe_load returned `int(0)` — pydantic's VoiceFidelityConfig rejected it (str field). Test failed with `validation error: Input should be a valid string`.
- **Fix:** Quoted the interpolated value: `anchor_set_sha: "{anchor_set_sha}"`. Same-class YAML footgun as Plan 03-01's yaml.safe_dump decision (unquoted 64-hex is ambiguous — sometimes parses as int for "0"-only strings).
- **Files modified:** `tests/voice_fidelity/test_pin.py`.
- **Commit:** `6d9dbce` (Task 1 GREEN — fold-in).
- **Scope:** Test-only; no product impact. Rule 3 applies (blocking Task 1 GREEN verify).

**2. [Rule 3 - Blocking] mypy `int(object-typed) — no overload match.**

- **Found during:** Task 2 GREEN mypy gate.
- **Issue:** `DraftRequest.generation_config: dict[str, object]` (FROZEN types.py). My draft() body called `int(request.generation_config.get("attempt_number", 1))` and `int(...max_tokens...)` and `int(...word_target...)` — mypy rejected with `No overload variant of "int" matches argument type "object"`.
- **Fix:** Added `_to_int(value, default=...)` helper with TypeError/ValueError fallback. Call sites now use `_to_int(request.generation_config.get(...))` uniformly. Cleaner than scattering `# type: ignore` and more robust to malformed generation_config from upstream.
- **Files modified:** `src/book_pipeline/drafter/mode_a.py`.
- **Commit:** `6d69e1b` (Task 2 GREEN).
- **Scope:** Caused by Plan 03-04 authoring. Rule 3 applies.

**3. [Rule 3 - Blocking] ruff RUF015 (`[...][0]` → `next(...)`), RUF059 (unused unpacked var), RUF003 (× multiplication glyph in comment), F401 (unused imports).**

- **Found during:** Task 1 + Task 2 GREEN lint gate.
- **Issue:** Standard ruff hygiene:
  - `evt = [e for e in logger.events if e.role == "drafter"][0]` → `next(e for e in ...)`.
  - `centroid, sha, _vf = provider.load()` where `sha` was unused → `_sha`.
  - Comment `# 3 rows × 1024-dim` → `# 3 rows x 1024-dim`.
  - Unused `httpx`, `VllmClient`, `Any`, `compute_centroid` imports in test files removed.
- **Fix:** `uv run ruff check ... --fix` for the 4 auto-fixable cases; manual edits for the rest.
- **Files modified:** `tests/drafter/test_mode_a.py`, `tests/drafter/test_sampling_profiles.py`, `tests/voice_fidelity/test_pin.py`.
- **Commits:** `6d9dbce`, `6d69e1b`.
- **Scope:** Test hygiene only. Rule 3 (blocking lint gate).

**4. [Rule 2 - Missing critical] memorization_gate.py docstring contained `book_specifics`.**

- **Found during:** Task 1 GREEN `test_kernel_does_not_import_book_specifics`.
- **Issue:** Docstring literally named `book_specifics.training_corpus.TRAINING_CORPUS_DEFAULT` to explain the CLI injection pattern. Same-class as Plan 03-01 + 03-02 + 03-03 docstring fixes (substring scan catches literal mentions).
- **Fix:** Reworded to "book-domain pointer module" without naming the banned symbol.
- **Files modified:** `src/book_pipeline/drafter/memorization_gate.py`.
- **Commit:** `6d9dbce` (Task 1 GREEN fold-in — I caught this in the regression after landing).
- **Scope:** Caused by my docstring authoring. Rule 2 (correctness — kernel substring scan is part of the test suite).

**5. [Rule 2 - Missing critical] mode_a.py docstring contained `book_specifics`.**

- **Found during:** Task 2 GREEN acceptance-criteria grep.
- **Issue:** Docstring said "NEVER imports from book_specifics" — substring scan caught it.
- **Fix:** Reworded to "Never crosses the kernel/book-domain boundary".
- **Files modified:** `src/book_pipeline/drafter/mode_a.py`.
- **Commit:** `6d69e1b` (Task 2 GREEN fold-in).
- **Scope:** Caused by my docstring authoring. Rule 2.

---

**Total deviations:** 5 auto-fixed (3 Rule 3 blocking lint / YAML / mypy; 2 Rule 2 docstring substring scans). All minor; none changed the plan's intent or the shipped API.

## Authentication Gates

**None.** Plan 03-04 does not touch Anthropic API, openclaw gateway, or live vLLM serve. All tests use stubs (FakeVllmClient, _FakeEventLogger, _FakeAnchorProvider, _FakeEmbedder, _FakeGate). The real paul-thinkpiece-pipeline corpus path is referenced as TRAINING_CORPUS_DEFAULT but not opened during testing; Plan 03-06 CLI is where the real corpus preload executes.

## Deferred Issues

1. **Per-scene-type sampling profile tuning.** Defaults are reasonable starting points (CONTEXT-derived) but Phase 6 thesis 005 should measure voice-fidelity / critic-pass-rate per profile and adjust. Not urgent — Plan 03-06's R=3 regen loop provides recovery headroom for weak initial profiles.
2. **TrainingBleedGate memory footprint on 32B-train corpora.** At 10,751 rows the gate fits easily in ~8MB. If paul-thinkpiece-pipeline grows to 100k+ rows (unlikely near-term), the set[int] grows linearly. Phase 6 can swap to a Bloom filter for a constant-memory variant — but false-positive rate would need careful tuning vs V-2's HARD BLOCK semantics.
3. **voice_fidelity_score as float | None.** When embedder_for_fidelity is None (e.g. dry-run, quick smoke), status='not_scored'. Plan 03-06 CLI must provide an embedder for production runs; the drafter does NOT enforce this (per plan spec — phase 6 thesis can filter events by status to validate coverage).
4. **Jinja2 template path is hardcoded.** Template lives at `src/book_pipeline/drafter/templates/mode_a.j2` and is resolved via `Path(__file__).parent / "templates" / "mode_a.j2"`. When installed as a wheel, this is still inside the package. Plan 03-04 does NOT add a MANIFEST.in — the template is under the source tree, so `hatchling` picks it up. Verified: `uv run python -c "from pathlib import Path; from book_pipeline.drafter.mode_a import _DEFAULT_TEMPLATE_PATH; print(_DEFAULT_TEMPLATE_PATH.exists())"` → True.
5. **AnchorSetProvider parquet-path override at construction.** `parquet_path` kwarg defaults to `Path("indexes/voice_anchors/embeddings.parquet")`. If CLI invocation CWD is not the repo root, the default path is relative and won't find the parquet — falls back to compute_centroid silently. Plan 03-06 CLI should set `parquet_path` explicitly from repo root. Not a blocker: fallback is correct (just slower).

## Known Stubs

**None.** Every function in the plan's shipped surface has a real implementation exercised by at least one test. 32 new tests cover the 4 new modules + 2 modified modules (ModeThresholdsConfig, drafter/__init__.py).

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 10 threats in the register are addressed:

- **T-03-04-01** (aggressive temp in yaml): ACCEPTED. Pydantic bounds 0<=t<=2 enforced.
- **T-03-04-02** (prompt injection via scene_request): MITIGATED. Jinja2 autoescape=False but no code-execution path.
- **T-03-04-03** (drafter failure with no event): MITIGATED. _emit_error_event called before raising on every failure path.
- **T-03-04-04** (training_corpus echoed in hits list): ACCEPTED. Paul-authored corpus.
- **T-03-04-05** (TrainingBleedGate preload DoS): MITIGATED. ONCE per CLI run; ~5-10s budget.
- **T-03-04-06** (oversized Jinja2 render): MITIGATED. Plan 02-05 bundler 40KB cap inherited.
- **T-03-04-07** (kernel contamination): MITIGATED. grep-clean; import-linter green.
- **T-03-04-08** (stale centroid cache mid-run): MITIGATED. Plan 03-06 reconstructs per CLI tick.
- **T-03-04-09** (scene_text in events): ACCEPTED. Only output_hash + word_count emitted.
- **T-03-04-10** (draft without voice_fidelity_score): MITIGATED. Plan 03-06 must provide embedder; status='not_scored' when absent (observability filter).

## Verification Evidence

| Criterion | Status | Evidence |
|---|---|---|
| All tasks in 03-04-PLAN.md executed + committed atomically | PASS | 4 per-task commits (2 × RED/GREEN): 5b87b8b, 6d9dbce, c76950c, 6d69e1b. |
| SUMMARY.md at .planning/phases/.../03-04-SUMMARY.md | PASS | This file. |
| drafter/mode_a.py ModeADrafter — Drafter Protocol impl | PASS | `grep "class ModeADrafter" src/book_pipeline/drafter/mode_a.py` = 1; `ModeADrafter.mode == 'A'`; `isinstance(d, Drafter)` True (Test A). |
| drafter/memorization_gate.py TrainingBleedGate | PASS | `grep "class TrainingBleedGate" src/book_pipeline/drafter/memorization_gate.py` = 1; 5 gate tests pass. |
| drafter/sampling_profiles.py per-scene-type profiles | PASS | `grep "class SamplingProfiles" src/book_pipeline/drafter/sampling_profiles.py` = 1; 8 profile tests pass. |
| drafter/templates/mode_a.j2 Jinja2 prompt | PASS | `===SYSTEM===` + `===USER===` sentinels present; rendered happy-path test succeeds. |
| voice_fidelity/pin.py AnchorSetProvider with parquet fallback (W-2) | PASS | Tests 7a/7b/7c cover present+match / wrong-shape / absent branches. |
| Event role='drafter' with voice_fidelity_score in caller_context | PASS | Test B asserts caller_context['voice_fidelity_score'] + anchor_set_sha + voice_pin_sha. |
| bash scripts/lint_imports.sh green | PASS | 2 contracts kept, ruff clean, mypy clean on 96 source files. |
| Full test suite pass count increases | PASS | 372 passed (was 343 pre-Plan-04; +29 new). |
| DRAFT-01 + DRAFT-02 + OBS-03 marked complete in REQUIREMENTS.md | PENDING | state_updates step marks complete via requirements mark-complete. |

## Self-Check: PASSED

Artifact verification (files on disk at `/home/admin/Source/our-lady-book-pipeline/`):

- FOUND: `src/book_pipeline/drafter/mode_a.py`
- FOUND: `src/book_pipeline/drafter/sampling_profiles.py`
- FOUND: `src/book_pipeline/drafter/memorization_gate.py`
- FOUND: `src/book_pipeline/drafter/templates/mode_a.j2`
- FOUND: `src/book_pipeline/voice_fidelity/pin.py`
- FOUND: `src/book_pipeline/book_specifics/training_corpus.py`
- FOUND: `config/mode_thresholds.yaml` (with `sampling_profiles:` block)
- FOUND: `tests/drafter/test_mode_a.py`
- FOUND: `tests/drafter/test_sampling_profiles.py`
- FOUND: `tests/drafter/test_memorization_gate.py`
- FOUND: `tests/voice_fidelity/test_pin.py`

Commit verification on `main` branch:

- FOUND: `5b87b8b test(03-04): RED — failing tests for sampling_profiles + memorization_gate + AnchorSetProvider`
- FOUND: `6d9dbce feat(03-04): GREEN — sampling_profiles + memorization_gate + AnchorSetProvider`
- FOUND: `c76950c test(03-04): RED — failing tests for ModeADrafter + Jinja2 template + Event shape`
- FOUND: `6d69e1b feat(03-04): GREEN — ModeADrafter + Jinja2 mode_a.j2 template`

All 4 per-task commits landed on `main`. Aggregate gate green. Full non-slow test suite 372 passed.

---

*Phase: 03-mode-a-drafter-scene-critic-basic-regen*
*Plan: 04*
*Completed: 2026-04-22*
