---
phase: 03-mode-a-drafter-scene-critic-basic-regen
verified: 2026-04-22T22:15:00Z
status: human_needed
score: 11/11 kernel+CLI must-haves verified; 1 live-smoke item deferred to operator
overrides_applied: 0
re_verification: null
human_verification:
  - test: "Plan 03-08 real-world end-to-end smoke: `book-pipeline draft ch01_sc01` against live vLLM (paul-v6-qwen3-32b-lora on :8002) + live Anthropic Opus 4.7 + live RAG indexes"
    expected: "Terminal state is one of: COMMITTED (drafts/ch01/ch01_sc01.md with 9 frontmatter keys + voice_pin_sha==checkpoint_sha) OR HARD_BLOCKED('failed_critic_after_R_attempts') OR HARD_BLOCKED('training_bleed'). runs/events.jsonl contains role='drafter', role='critic', and optionally role='regenerator' Events. runs/critic_audit/ch01_sc01_*.json audit records written for every critic call (success + failure). Budget ~$0.6 Anthropic; wall-time 3-10min."
    why_human: "Requires operator-managed ANTHROPIC_API_KEY (not set in this session), operator-started vllm-paul-voice.service (port 8002 unused), real GPU VRAM allocation, and ~$0.6 Anthropic spend. Pre-flight checklist + runbook fully documented in 03-08-SUMMARY.md and 03-08-PLAN.md."
---

# Phase 3: Mode-A Drafter + Scene Critic + Basic Regen Verification Report

**Phase Goal:** Single scene (ch01_sc01) can be drafted by the pinned voice-FT checkpoint, critiqued by Opus against the 5-axis rubric, regenerated on failure, and left on disk in a well-defined SceneStateMachine state — with voice-fidelity measured from the first commit (anchor set curated before any prose lands).

**Verified:** 2026-04-22T22:15:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Voice pin has real V6 SHA (no TBD-phase3 placeholders) | VERIFIED | `config/voice_pin.yaml` line 10: `checkpoint_sha: 3f0ac5e2290dab633a19b6fb7a37d75f59d4961497e7957947b6428e4dc9d094`; `grep -c TBD-phase3 config/voice_pin.yaml` = 0; ft_run_id=v6_qwen3_32b, base=Qwen/Qwen3-32B, source_commit=c571bb7b... |
| 2 | ModeADrafter composes ContextPack → prompt → vLLM call → DraftResponse | VERIFIED | `src/book_pipeline/drafter/mode_a.py:159` `class ModeADrafter` with `mode: str = "A"` (line 162) + `def draft(request: DraftRequest) -> DraftResponse` (line 209); Jinja2 `templates/mode_a.j2` sentinel-split; Protocol-conformant (Plan 04 Test A isinstance(Drafter) passes); 495 lines |
| 3 | SceneCritic calls Anthropic Opus 4.7 messages.parse → CriticReport | VERIFIED | `src/book_pipeline/critic/scene.py:116` `class SceneCritic` with level='scene'; line 364 `self.anthropic_client.messages.parse(... output_format=CriticResponse ...)`; 576 lines; model_id="claude-opus-4-7" |
| 4 | SceneLocalRegenerator takes critic issue list + rewrites | VERIFIED | `src/book_pipeline/regenerator/scene_local.py:108` `class SceneLocalRegenerator`; line 282 `self._anthropic_client.messages.create(...)`; ±10% word-count guard; severity-bucketed (high/mid actionable, low context); 462 lines |
| 5 | SceneStateMachine loop honors R=3, terminates in COMMITTED/FAILED_CRITIC | VERIFIED | `src/book_pipeline/cli/draft.py:327` `for attempt in range(1, max_regen + 2)` (R=3 → 4 total attempts); line 114 default max_regen=3; transitions: PENDING→RAG_READY→DRAFTED_A→{CRITIC_PASS→COMMITTED} \| {CRITIC_FAIL→REGENERATING→...→HARD_BLOCKED('failed_critic_after_R_attempts')}; regen_budget_R in `config/mode_thresholds.py:77` |
| 6 | Voice-fidelity via BGE-M3 cosine vs 22-anchor centroid | VERIFIED | `config/voice_anchors/anchor_set_v1.yaml` has 22 anchors (essay=8, analytic=8, narrative=6 confirmed via grep); `anchor_set_sha: 28fd890bc4c8afc1d0e8cc33b444bc0978002b96fbd7516ca50460773e97df31` in `config/mode_thresholds.yaml`; thresholds pass≥0.78 / flag 0.75-0.78 / fail<0.75 / memorization≥0.95; W-2 parquet fast-path at `indexes/voice_anchors/embeddings.parquet` |
| 7 | CRIT-04 audit log written every critic call (success + failure) | VERIFIED | `src/book_pipeline/critic/audit.py` write_audit_record() atomic tmp+rename; 11-key shape (event_id, scene_id, attempt_number, timestamp_iso, rubric_version, model_id, opus_model_id_response, caching_cache_control_applied, cached_input_tokens, system_prompt_sha, user_prompt_sha, context_pack_fingerprint, raw_anthropic_response, parsed_critic_response); W-7 failure path: parsed_critic_response=null + raw_anthropic_response={error, error_type, attempts_made} |
| 8 | OBS-03 Events emitted with proper caller_context | VERIFIED | `role="drafter"` emitted by `drafter/mode_a.py`; `role="critic"` by `critic/scene.py`; `role="regenerator"` by `regenerator/scene_local.py`; `role="anchor_curator"` by `cli/curate_anchors.py`. Drafter caller_context carries {scene_id, chapter, pov, beat_function, scene_type, voice_pin_sha, anchor_set_sha, voice_fidelity_score, voice_fidelity_status, attempt_number}. Schema v1.0 preserved (18 fields, additive-only). |
| 9 | V-3 boot_handshake raises VoicePinMismatch on SHA mismatch | VERIFIED | `src/book_pipeline/drafter/vllm_client.py:226` `boot_handshake(pin)`; line 254 recomputes `compute_adapter_sha(pin.checkpoint_path)`; line 268 raises `VoicePinMismatch` on drift; emits role='vllm_boot_handshake' Event with status='error' BEFORE raising (T-03-03-03 mitigation) |
| 10 | V-2 TrainingBleedGate hard-blocks on 12-gram overlap | VERIFIED | `src/book_pipeline/drafter/memorization_gate.py:44` `class TrainingBleedGate`; 12-gram enumeration + xxhash.xxh64_intdigest (stable across processes); any hit → ModeADrafterBlocked('training_bleed') HARD BLOCK; preload cost ~5-10s for 10,751-row corpus |
| 11 | B-3 invariant: voice_pin_sha == checkpoint_sha in frontmatter | VERIFIED | `src/book_pipeline/cli/draft.py:246` comment "B-3 invariant: single source of truth — do not diverge"; lines 256-257 both fields assigned from shared_sha local (single assignment); line 242 RuntimeError if draft.voice_pin_sha is None (defensive guard) |

**Score:** 11/11 kernel+CLI truths verified. 1 live-smoke truth (real `book-pipeline draft ch01_sc01` against live infra) deferred to operator via Plan 03-08.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `config/voice_pin.yaml` | Real V6 SHA (no TBD) | VERIFIED | 64-hex SHA present; 0 TBD-phase3 matches |
| `config/voice_anchors/anchor_set_v1.yaml` | 20-30 anchors with sub-genre split | VERIFIED | 22 anchors (8 essay / 8 analytic / 6 narrative) |
| `config/mode_thresholds.yaml` voice_fidelity block | anchor_set_sha + thresholds | VERIFIED | SHA 28fd890b…df31 + pass/flag/fail/memorization thresholds |
| `src/book_pipeline/drafter/mode_a.py` | ModeADrafter Protocol impl | VERIFIED | 495 lines, mode='A', Jinja2 template, VllmClient.chat_completion |
| `src/book_pipeline/critic/scene.py` | SceneCritic Opus 4.7 messages.parse | VERIFIED | 576 lines, model=claude-opus-4-7, output_format=CriticResponse |
| `src/book_pipeline/regenerator/scene_local.py` | SceneLocalRegenerator REGEN-01 | VERIFIED | 462 lines, messages.create, ±10% word-count guard |
| `src/book_pipeline/cli/draft.py` | CLI composition root | VERIFIED | 695 lines, CompositionRoot dataclass, run_draft_loop, B-3 enforcement |
| `scenes/ch01/ch01_sc01.yaml` | Hand-authored SceneRequest stub | VERIFIED | Andrés de Mora POV, Havana 1519-02-18, outline-aligned (NOT plan's original Cortés stub — plan was out of sync with outline.md triptych) |
| `src/book_pipeline/voice_fidelity/{sha,anchors,pin,scorer}.py` | V-3 + OBS-03 kernel | VERIFIED | All present; compute_adapter_sha, AnchorSet, AnchorSetProvider, score_voice_fidelity (real BGE-M3 impl) |
| `src/book_pipeline/drafter/vllm_client.py` | VllmClient + boot_handshake | VERIFIED | httpx + tenacity 3x, boot_handshake raises VoicePinMismatch |
| `src/book_pipeline/critic/audit.py` | CRIT-04 audit writer | VERIFIED | write_audit_record atomic tmp+rename |
| `drafts/ch01/` | Commit directory ready | VERIFIED | .gitkeep present; drafts/scene_buffer/ gitignored |
| `tests/cli/test_draft_loop.py` | Integration tests | VERIFIED | 11 mocked tests A-K; 396 total suite passing (up from 261 Phase-2-exit) |

### Key Link Verification

| From | To | Via | Status |
|---|---|---|---|
| `cli/draft.py` CompositionRoot | `drafter.mode_a.ModeADrafter` + `critic.scene.SceneCritic` + `regenerator.scene_local.SceneLocalRegenerator` | `_build_composition_root` instantiates all 6 kernel components | WIRED |
| `drafter.vllm_client.boot_handshake` | `voice_fidelity.sha.compute_adapter_sha` + `VoicePinMismatch` | direct kernel→kernel import, strict=True raises on drift | WIRED |
| `drafter.mode_a.ModeADrafter.draft()` | `voice_fidelity.pin.AnchorSetProvider` + `score_voice_fidelity` + `TrainingBleedGate` | composition via ModeADrafter.__init__ (Plan 04 key-files) | WIRED |
| `cli/draft.py:_commit_scene` | `drafts/ch{NN}/{scene_id}.md` YAML frontmatter | B-3 invariant enforcement line 246-257 (shared_sha) | WIRED |
| `critic.scene.SceneCritic.review()` | `runs/critic_audit/*.json` + role='critic' Event | write_audit_record (success + W-7 failure) + event_logger.emit | WIRED |
| `regenerator.scene_local.SceneLocalRegenerator` | `drafter.mode_a.VOICE_DESCRIPTION` | kernel→kernel import (import-linter contract 1 allows intra-kernel) | WIRED |
| import-linter contract 1 + 2 | drafter/, critic/, regenerator/, voice_fidelity/ | 8 references in pyproject.toml (2 per package × 4 packages); `bash scripts/lint_imports.sh` green | WIRED |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| DRAFT-01 | 03-01, 03-03, 03-04 | Mode-A drafter → vLLM with SHA-pinned voice-FT; boot handshake enforces SHA | SATISFIED | REQUIREMENTS.md line 36 marked [x] complete; V6 SHA pinned + boot_handshake → VoicePinMismatch |
| DRAFT-02 | 03-04 | Per-scene sampling via scene_type (prose/dialogue_heavy/structural_complex) | SATISFIED | REQUIREMENTS.md line 37 [x]; SamplingProfiles in mode_thresholds.yaml with 3 profiles |
| CRIT-01 | 03-05 | 5-axis structured JSON via messages.parse + Pydantic | SATISFIED | REQUIREMENTS.md line 43 [x]; output_format=CriticResponse; 5 REQUIRED_AXES enforced |
| CRIT-04 | 03-05 | Versioned rubric; per-call audit log | SATISFIED | REQUIREMENTS.md line 46 [x]; rubric_version stamped 3 ways; audit writes success+failure |
| OBS-03 | 03-02, 03-04 | Voice-fidelity cosine vs anchor centroid, curated before first commit | SATISFIED | REQUIREMENTS.md line 22 [x]; 22 anchors pinned; score on drafter Event |
| REGEN-01 | 03-06, 03-07 | Scene-local rewrite on critic issues | SATISFIED at kernel+CLI | REQUIREMENTS.md line 157 marked "In Progress (kernel landed 03-06; CLI composition + smoke pending 03-07/03-08)"; 03-07 landed CLI; 03-08 smoke deferred |

**All 6 phase requirement IDs implemented in code + tests. REGEN-01's "In Progress" marker reflects the intentional kernel/CLI-vs-smoke split; live smoke is Plan 03-08's operator task.**

### Anti-Patterns Found

No blockers. Spot-checks on key files via stub-detection patterns:

- `drafter/mode_a.py`: no `return None` stubs, no `raise NotImplementedError` in production paths, no TODO/FIXME/placeholder markers. Real Jinja2 render + VllmClient.chat_completion + score_voice_fidelity.
- `critic/scene.py`: real anthropic.messages.parse (kwarg verified as `output_format=CriticResponse` per SDK v0.96.0), real tenacity retry, real audit write.
- `regenerator/scene_local.py`: real anthropic.messages.create, real word-count guard, real Event emission.
- `cli/draft.py`: real composition with no mock/fake paths in production; tests inject fakes via CompositionRoot dataclass.
- `voice_fidelity/scorer.py`: Plan 03-01 stub replaced with real BGE-M3 cosine impl in 03-02 (Plan 03-02 Deviation #5 deleted the obsolete stub-raises test).
- `tests/cli/test_draft_loop.py`: 11 integration tests mocking LLM clients (expected — smoke is deferred).

### Human Verification Required

**1. Plan 03-08 real-world end-to-end smoke**

**Test:** Execute `book-pipeline draft ch01_sc01 --max-regen 3` with ANTHROPIC_API_KEY set and `vllm-paul-voice.service` running on port 8002.

**Expected:** Terminal state is ONE of (any = Phase 3 PASS):
- **PASS-COMMIT:** `drafts/ch01/ch01_sc01.md` with all 9 YAML frontmatter keys (voice_pin_sha, checkpoint_sha, critic_scores_per_axis, attempt_count, ingestion_run_id, draft_timestamp, voice_fidelity_score, mode, ...); B-3 invariant live (voice_pin_sha == checkpoint_sha == `3f0ac5e2...d094`); scene_text ~1000 words.
- **PASS-HARDBLOCK-FAIL-CRITIC:** `drafts/scene_buffer/ch01/ch01_sc01.state.json` HARD_BLOCKED + `failed_critic_after_R_attempts` (R=3 exhausted).
- **PASS-HARDBLOCK-TRAINING-BLEED:** HARD_BLOCKED + `training_bleed` (V-2 live on real corpus).

Observability expectations: runs/events.jsonl contains role='drafter' + role='critic' + optionally role='regenerator'; runs/critic_audit/ch01_sc01_*.json written for every critic call (W-7: failure-path audits have parsed_critic_response=null + raw_anthropic_response.error populated).

**Why human:** Requires (a) operator-managed ANTHROPIC_API_KEY (not present in this session), (b) operator-started `vllm-paul-voice.service` (port 8002 confirmed unused — never started in this session), (c) ~$0.6 Anthropic spend. All pre-flight + runbook documented in `03-08-SUMMARY.md` (Operator runbook section) and `03-08-PLAN.md` (<pre-flight-checklist> + <how-to-verify>). Operator signals `approved: committed` | `approved: hardblocked <reason>` | `blocked: <gap>` | `failed: <traceback>` per 03-08-PLAN <resume-signal>.

### Gaps Summary

No structural gaps. All Phase 3 kernel + CLI work shipped:
- 7 of 8 plans complete (03-01 through 03-07)
- All 6 phase REQs (DRAFT-01, DRAFT-02, CRIT-01, CRIT-04, REGEN-01, OBS-03) satisfied in code + mocked integration tests
- 11 key links wired (ModeADrafter→VllmClient, SceneCritic→Anthropic, SceneLocalRegenerator→Anthropic, cli/draft.py→all 6 kernel components, B-3 invariant, V-2 gate, V-3 handshake)
- 396 tests passing (up from 261 at Phase 2 exit; +135 net new across 7 plans); zero regressions on Phase 1 + 2 suites
- `bash scripts/lint_imports.sh` green across 98 source files
- import-linter contracts extended: 4 kernel packages × 2 contracts = 8 pyproject.toml references confirmed

The ONE outstanding item is Plan 03-08 live smoke — a deliberate `checkpoint:human-verify` gate, not a defect. The mocked integration suite (11 tests in `tests/cli/test_draft_loop.py`) proves the loop wiring; the operator smoke proves the wiring survives contact with real vLLM + real Opus + real RAG + real V6 weights.

---

*Verified: 2026-04-22T22:15:00Z*
*Verifier: Claude (gsd-verifier)*
