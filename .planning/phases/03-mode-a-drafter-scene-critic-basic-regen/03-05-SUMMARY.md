---
phase: 03-mode-a-drafter-scene-critic-basic-regen
plan: 05
subsystem: scene-critic-anthropic-opus-4-7-+-crit-04-audit
tags: [critic, scene-critic, anthropic, opus-4-7, messages-parse, rubric-version, audit-log, crit-01, crit-04, phase-3]
requirements_completed: [CRIT-01, CRIT-04]
dependency_graph:
  requires:
    - "03-01 (kernel critic/ package skeleton + import-linter contract — Plan 03-05 adds files inside the package without touching pyproject.toml)"
    - "01-02 (FROZEN Critic Protocol + CriticRequest/Response/Issue Pydantic types)"
    - "01-03 (RubricConfig loader for config/rubric.yaml — rubric_version + 5 axes)"
    - "01-05 (JsonlEventLogger + Event schema with top-level rubric_version field)"
    - "02-05 (ContextPack.fingerprint + conflicts — consumed by SceneCritic._build_user_prompt)"
  provides:
    - "src/book_pipeline/critic/scene.py — SceneCritic (Protocol-conformant scene critic; Anthropic Opus 4.7 + messages.parse + ephemeral 1h cache_control + rubric_version stamp + per-call audit log + Event emission) + SystemPromptBuilder + SceneCriticError"
    - "src/book_pipeline/critic/audit.py — write_audit_record() atomic-write JSON audit entry (CRIT-04) + AuditRecord Pydantic mirror"
    - "src/book_pipeline/critic/templates/system.j2 — Jinja2 template embedding rubric.yaml verbatim + 5-axis instructions + bad/good few-shot"
    - "src/book_pipeline/critic/templates/scene_fewshot.yaml — CURATED bad + good scenes (B-2 closure: real Nahua/Spanish entities, 173/192 words, two historical anachronisms in the bad scene)"
    - "tests/critic/test_audit.py + test_rubric_version_stamping.py + test_scene_critic.py + fixtures.py — 20 tests covering audit writer + SystemPromptBuilder + SceneCritic end-to-end"
  affects:
    - "Plan 03-06 (scene-local regenerator) — consumes CriticIssue list from CriticResponse; calls SceneCritic.review(...) in the regen loop; reads SceneCriticError.context to persist HARD_BLOCKED on retry-exhaustion"
    - "Plan 03-07 (book-pipeline draft CLI orchestrator) — composes SceneCritic(anthropic_client=Anthropic(), event_logger=shared_logger, rubric=RubricConfig()) once per CLI run so the 1h ephemeral cache hits across all scenes"
    - "Phase 4 CRIT-02 (chapter-level critic) — reuses SystemPromptBuilder + audit record shape; needs only a different fewshot yaml + rubric id"
    - "Phase 6 OBS-02 (observability ingester) — reads runs/critic_audit/*.json to reconstruct per-axis score trends by rubric_version; joins via event_id to runs/events.jsonl"
    - "Phase 6 CRIT-03 (cross-family critic audit) — re-scores scenes whose SceneCritic events carry rubric_version=v1 so longitudinal compare survives rubric bumps"
tech-stack:
  added:
    - "tenacity retry on SceneCritic._call_opus_inner: stop_after_attempt(5), wait_exponential(multiplier=2, min=2, max=30), reraise=True — only on APIConnectionError + APIStatusError (other exceptions pass through unretried)"
    - "anthropic.messages.parse(output_format=CriticResponse) with ParsedMessage.parsed_output — NOT client.responses.create() or a separate Pydantic post-parse (v0.96.0 native structured output)"
  patterns:
    - "System-prompt pre-render at __init__: SceneCritic builds the rendered system prompt ONCE via SystemPromptBuilder + stores self._system_blocks as an object-stable list so two successive review() calls pass the identical object (Test H) — maximizes 1h ephemeral cache hit rate. Anthropic's cache key is the system prompt prefix byte-string, so this is the difference between 0% and ~100% cache-read tokens on scene #2 of a run."
    - "Per-invocation audit log (W-7 CRIT-04 semantics): every review() call writes runs/critic_audit/{scene_id}_{attempt:02d}_{timestamp}.json — success AND tenacity-exhaustion failure. Failure path records raw_anthropic_response={error, error_type, attempts_made} and parsed_critic_response=None; all other fields (event_id, scene_id, attempt_number, timestamp_iso, rubric_version, model_id, system_prompt_sha, user_prompt_sha) still populated so Phase 6 OBS-02 ingester can count infrastructure failure rate separately from critic-fail rate."
    - "Axis-completeness post-process: REQUIRED_AXES (historical|metaphysics|entity|arc|donts) are enforced on every CriticResponse. Missing axis in pass_per_axis → fill pass=True, score=75.0; missing in scores_per_axis → fill 75.0. filled_axes list attached to Event.extra['filled_axes'] so Phase 6 digest can flag when Opus drops axes. Keeps the scene loop unblocked on partial responses."
    - "overall_pass invariant enforcement: parsed.overall_pass == all(parsed.pass_per_axis.values()). Mismatch → silently corrected (parsed.overall_pass = all(...)) + Event.extra['invariant_fixed']=True flagged. Rare given messages.parse's Pydantic coercion, but the guard exists because Opus occasionally emits structurally-valid-but-semantically-inconsistent JSON (especially in few-shot regimes)."
    - "rubric_version 3-way stamp: (a) CriticResponse.rubric_version overridden to self.rubric.rubric_version (trusts config over the LLM's echo); (b) Event.rubric_version top-level Phase-1 field; (c) audit record rubric_version. Request's rubric_version may mismatch (W-6 Test I: Phase 6 rubric migrations); warning logged + Event.extra['request_rubric_version_mismatch']=True, but the critic continues with its own version (soft guardrail)."
    - "tenacity retry-wait monkeypatch for tests: @tenacity.retry captures wait_exponential at decoration time, so class-__init__ monkeypatch is ineffective. Tests use `monkeypatch.setattr(SceneCritic._call_opus_inner.retry, 'wait', tenacity.wait_fixed(0))` — Test E drops from 30s to <1s. Future plans that add tenacity-wrapped methods should publish their retry.wait monkeypatch helpers in the same place (tests/critic/test_scene_critic._patch_tenacity_wait_fast)."
    - "FakeAnthropicClient fixture shape: messages.parse accepts kwargs (captured in call_args_list), returns a FakeParsedMessage with .parsed_output property + .usage object + .model_dump() — mirrors anthropic.types.ParsedMessage's public surface without touching the network. side_effect=list_of_exceptions simulates tenacity exhaustion (Test E uses [APIConnectionError, APIConnectionError, ...] × 5)."
key-files:
  created:
    - "src/book_pipeline/critic/audit.py (~94 lines; write_audit_record + AuditRecord)"
    - "src/book_pipeline/critic/scene.py (~576 lines; SceneCritic + SystemPromptBuilder + SceneCriticError + helpers)"
    - "src/book_pipeline/critic/templates/system.j2 (~37 lines; Jinja2 system prompt template)"
    - "src/book_pipeline/critic/templates/scene_fewshot.yaml (~100 lines; CURATED B-2 few-shot)"
    - "tests/critic/__init__.py (empty package marker)"
    - "tests/critic/fixtures.py (~221 lines; FakeAnthropicClient + FakeParsedMessage + FakeUsage + FakeEventLogger + make_canonical_critic_response + make_critic_request)"
    - "tests/critic/test_audit.py (~83 lines; 3 tests — filename shape, no-overwrite reruns, auto-mkdir)"
    - "tests/critic/test_rubric_version_stamping.py (~175 lines; 7 tests covering SystemPromptBuilder render + B-2 fewshot curation checks)"
    - "tests/critic/test_scene_critic.py (~377 lines; 10 tests A-J for SceneCritic end-to-end)"
    - ".planning/phases/03-mode-a-drafter-scene-critic-basic-regen/03-05-SUMMARY.md — this file"
  modified:
    - "src/book_pipeline/critic/__init__.py — exports AuditRecord + write_audit_record + SystemPromptBuilder + SceneCriticError + SceneCritic (latter via importlib+contextlib.suppress fallback per B-1 pattern)"
    - ".gitignore — `runs/critic_audit/` added per plan verification §12 (audit artifacts are local-truth, not committed; same trust boundary as runs/events.jsonl)"
key-decisions:
  - "(03-05) Used anthropic v0.96.0 keyword `output_format=CriticResponse` (NOT `response_format=` per the plan text). Plan text was written against an earlier SDK draft; live SDK inspection of `anthropic.resources.messages.Messages.parse` shows `output_format: Optional[type[ResponseFormatT]]` + merged `output_config`. No behavioral difference — Pydantic schema flows through either path — but the kwarg name is the one that actually binds to the SDK. ParsedMessage exposes `.parsed_output` (NOT `.parsed`), again per the v0.96.0 inspection. Sticking literal-to-plan would have failed Test A import."
  - "(03-05) Few-shot content was curated to exercise the historical axis with TWO distinct anachronisms in the bad scene, not one. Plan text allowed 1+ anachronism; B-2 test requires >=2 entities AND >=150 words AND plausible prose. Chose Cempoala-1520 (off by 1 year) + Tlaxcalteca-auxiliaries-at-Cempoala (the alliance was sealed weeks AFTER Cempoala, not before). Two anachronisms + specific corpus citation (hist_brief_042, hist_brief_051) gives Opus a clearer calibration target — single-anachronism few-shot would be weaker at teaching the 'factual drift = FAIL' rule. Good scene is a straight Malintzin-translation beat grounded in Aug 1519, Totonac cacique, Mexica envoys present — no anachronisms, all 5 axes pass."
  - "(03-05) SceneCritic's system_blocks list is STORED on the instance (self._system_blocks) and passed by reference to every messages.parse call (Test H object-equality). Subtle but load-bearing: if we rebuilt the list per-call, Anthropic's cache key might still match byte-wise, but the observable system_blocks argument would differ and some proxies / logging layers would break the cache. Storing the object means `sb1 is sb2` True AND `sb1 == sb2` True — future-proof against any middleware that keys on object identity."
  - "(03-05) tenacity retry captures wait_exponential at decoration time. Test E's original monkeypatch (on tenacity.wait_exponential.__init__) silently failed — Test E took 30s. Fix: patch SceneCritic._call_opus_inner.retry.wait directly to tenacity.wait_fixed(0). Keeping wait_exponential as the production config (multiplier=2, min=2, max=30 → 2+4+8+16 = 30s total wall-time for 5 retries; PITFALLS DoS mitigation T-03-05-05 wants this bounded total)."
  - "(03-05) _handle_failure writes the audit record BEFORE raising SceneCriticError. If the audit write itself fails (disk full, permissions), we log-and-swallow rather than masking the original anthropic-unavailable exception. Rationale: the caller cares most about the root cause (Anthropic down); a missing audit is a secondary observability failure, handled by Phase 6's ingester which scans events.jsonl for role='critic' + status='error' and reconciles against the expected-audit-count."
  - "(03-05) attempt_number derivation from CriticRequest.chapter_context: plan proposes overloading `chapter_context.get('attempt_number', 1)` because CriticRequest doesn't have a top-level attempt field (the Phase 1 freeze locked the shape). Phase 4's chapter critic will have different chapter_context semantics — this SUMMARY flags that divergence so Phase 4 plans can decide whether to ADD an OPTIONAL attempt_number field to CriticRequest (Phase 1 freeze permits additions) or keep the chapter_context overload. Phase 3's scene loop + Phase 4's chapter loop should land on the same convention."
  - "(03-05) Mypy fallout from `response.parsed_output` being typed `Any` via the generic ParsedMessage[ResponseFormatT]: added `parsed: CriticResponse = parsed_raw` pin after the None-check so mypy --strict stops complaining about Returning Any from CriticResponse-typed function. Future Anthropic SDK versions with better generic inference can drop the pin — non-load-bearing."
metrics:
  duration_minutes: 35
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 9  # audit.py, scene.py, system.j2, scene_fewshot.yaml, tests/critic/__init__.py, fixtures.py, test_audit.py, test_rubric_version_stamping.py, test_scene_critic.py, plus this SUMMARY = 10 if we count it
  files_modified: 2  # critic/__init__.py, .gitignore
  tests_added: 20  # 3 audit + 7 rubric-version-stamping + 10 scene_critic = 20
  tests_passing: 340  # was 320 baseline; +20 new (Plan 03-05)
  regression_tests_passing: 340
  baseline_before_plan: 320
  anthropic_sdk_version: "0.96.0"
  opus_model_id: "claude-opus-4-7"
  scene_fewshot_bad_word_count: 173
  scene_fewshot_good_word_count: 192
  scene_fewshot_real_entities_bad: "Cempoala, Moctezuma, Cholula, Tlaxcalteca, Veracruz, Cortés, 1520"
  scene_fewshot_real_entities_good: "Malintzin, Cempoala, Moctezuma, Cortés, 1519"
commits:
  - hash: e6f599c
    type: test
    summary: "Task 1 RED — failing tests for audit.py + scene_fewshot.yaml + SystemPromptBuilder"
  - hash: d073a30
    type: feat
    summary: "Task 1 GREEN — audit.py + curated scene_fewshot.yaml + system.j2 + SystemPromptBuilder skeleton + SceneCriticError"
  - hash: ae5a1b6
    type: test
    summary: "Task 2 RED — failing tests A-J for SceneCritic (CRIT-01 + CRIT-04)"
  - hash: b7035b7
    type: feat
    summary: "Task 2 GREEN — SceneCritic (Anthropic messages.parse + cache_control + tenacity + audit log + Event emission)"
---

# Phase 3 Plan 05: Scene Critic (CRIT-01 + CRIT-04) Summary

**One-liner:** Ship SceneCritic — a Protocol-conformant scene-level critic wrapping Anthropic Opus 4.7's `messages.parse(output_format=CriticResponse)` with ephemeral 1h prompt caching on the pre-rendered 5-axis rubric system prompt (rubric.yaml verbatim + curated bad/good few-shot in `scene_fewshot.yaml`); every invocation writes a CRIT-04 audit record to `runs/critic_audit/{scene_id}_{attempt:02d}_{timestamp}.json` (success AND W-7 tenacity-exhaustion failure with `parsed_critic_response=null` + `raw_anthropic_response={error, error_type, attempts_made}`) and emits exactly one `role='critic'` Event with `rubric_version` on the top-level Phase-1 field (W-6: dynamically read from `config/rubric.yaml`, not hardcoded `"v1"`); post-process fills missing REQUIRED_AXES with `pass=True, score=75.0` (via `Event.extra['filled_axes']`) and enforces the `overall_pass == all(pass_per_axis.values())` invariant (via `Event.extra['invariant_fixed']`); tenacity 5× exponential backoff on transient `APIConnectionError`/`APIStatusError` exhaustion raises `SceneCriticError('anthropic_unavailable', ...)` so Plan 03-06 scene-loop orchestrator can persist `HARD_BLOCKED`. CRIT-01 + CRIT-04 REQUIREMENTS marked complete.

## Exact Event shape emitted by SceneCritic

Success path (role='critic', status=implicit-ok):

```python
Event(
    event_id=event_id(ts_iso, "critic", f"critic.scene.review:{scene_id}", user_prompt_sha),
    ts_iso="<UTC microsecond ISO>",
    role="critic",
    model="claude-opus-4-7",
    prompt_hash=hash_text(system_prompt + "\n---\n" + user_prompt),
    input_tokens=<anthropic.usage.input_tokens>,
    cached_tokens=<anthropic.usage.cache_read_input_tokens>,
    output_tokens=<anthropic.usage.output_tokens>,
    latency_ms=<wall-time>,
    temperature=0.1,
    top_p=None,
    caller_context={
        "module": "critic.scene",
        "function": "review",
        "scene_id": "ch01_sc01",
        "chapter": 1,
        "attempt_number": <1..R>,
        "num_issues": len(parsed.issues),
        "overall_pass": parsed.overall_pass,
        "pass_per_axis": {...},
        "context_pack_fingerprint": "<ContextPack.fingerprint>",
        "audit_path": "runs/critic_audit/ch01_sc01_01_....json",
    },
    output_hash=parsed.output_sha,
    mode=None,
    rubric_version=self.rubric.rubric_version,  # TOP-LEVEL Phase-1 field
    checkpoint_sha=None,
    extra={
        "filled_axes": ["metaphysics"] if any filled else [],
        "invariant_fixed": False,  # True if overall_pass was corrected
        "scores_per_axis": {...},
        "severities": {axis: "none"|"low"|"mid"|"high" per issue roll-up},
        "request_rubric_version_mismatch": True,  # only present if mismatched
    },
)
```

Failure path (tenacity-exhaustion or parse failure):

```python
Event(
    ...,
    role="critic",
    input_tokens=0,
    cached_tokens=0,
    output_tokens=0,
    output_hash="",
    rubric_version=self.rubric.rubric_version,
    extra={
        "status": "error",
        "error_type": "APIConnectionError",
        "error_message": str(exc),
        "attempts_made": 5,
        "request_rubric_version_mismatch": <bool>,
    },
)
```

Plan 03-06 regenerator reads the role='critic' event stream filtered by `caller_context.scene_id` to reconstruct attempt history; the `audit_path` field gives it the local-disk pointer for post-mortem.

## System prompt template variables

`SystemPromptBuilder.render()` binds these Jinja2 variables:

| Variable | Type | Source |
|---|---|---|
| `rubric` | `RubricConfig` | `RubricConfig()` — loads `config/rubric.yaml` |
| `axes_ordered` | `list[str]` | `AXES_ORDERED = ("historical","metaphysics","entity","arc","donts")` |
| `few_shot_bad` | `dict` | `yaml.safe_load(scene_fewshot.yaml)["bad"]` |
| `few_shot_good` | `dict` | `yaml.safe_load(scene_fewshot.yaml)["good"]` |

Phase 4 CRIT-02 (chapter-level critic) can reuse the SAME `SystemPromptBuilder` + `system.j2` template pair — only the few-shot yaml needs to change (chapter-level examples will show arc-function consistency across 9-scene chapter blocks, not per-scene historical alignment).

## Audit record shape (CRIT-04)

```json
{
  "event_id": "<xxh64 hex 16 chars>",
  "scene_id": "ch01_sc01",
  "attempt_number": 1,
  "timestamp_iso": "2026-04-22T14:30:05.123456Z",
  "rubric_version": "v1",
  "model_id": "claude-opus-4-7",
  "opus_model_id_response": "claude-opus-4-7",  // null on failure path
  "caching_cache_control_applied": true,
  "cached_input_tokens": 3000,
  "system_prompt_sha": "<xxh64 hex>",
  "user_prompt_sha": "<xxh64 hex>",
  "context_pack_fingerprint": "<ContextPack.fingerprint>",
  "raw_anthropic_response": { ...SDK model_dump... },  // or {error, error_type, attempts_made} on failure
  "parsed_critic_response": { ...CriticResponse.model_dump()... }  // null on failure
}
```

Phase 6 OBS-02 ingester reads these files chronologically, joins against `runs/events.jsonl` via `event_id`, and aggregates `scores_per_axis` × `rubric_version` × `scene_id` into the metric ledger. Rubric version bumps (`v1` → `v2`) are filterable: the ingester keeps parallel trend lines rather than mixing regimes.

## cache_control semantics

```python
self._system_blocks = [{
    "type": "text",
    "text": self._system_prompt,          # ~3000 tokens (rubric + few-shot)
    "cache_control": {"type": "ephemeral", "ttl": "1h"},
}]
```

- The pre-rendered `self._system_prompt` is identical across `review()` calls within a `SceneCritic` instance's lifetime (Test H verifies object-identity equality of `system_blocks` across two calls).
- First `messages.parse` call: `cache_read_input_tokens=0`, `cache_creation_input_tokens=~3000` (Anthropic stores the prefix).
- Second+ call within 1h: `cache_read_input_tokens=~3000`, `cache_creation_input_tokens=0` — the discount is ~90% of input-token cost for the cached portion.
- Event.cached_tokens is wired to `response.usage.cache_read_input_tokens` so Phase 6's cost-tracker sees the savings directly.

**Composition guidance for Plan 03-07 orchestrator:** construct `SceneCritic` ONCE per `book-pipeline draft` CLI invocation; reuse it across every scene in the run. Re-constructing per scene rebuilds the `system_blocks` list identity, but Anthropic's cache key is byte-stable so cost stays the same — however the per-scene overhead of `SystemPromptBuilder.render()` (fewshot yaml read + Jinja2 compile) is ~5ms, worth eliding with a single instance.

## Token-count expectations

| Segment | Tokens | Notes |
|---|---|---|
| System prompt (rubric + fewshot) | ~2,800-3,200 | Cached on 1h TTL after first call |
| User prompt (scene_text + retrievals) | ~2,000-4,000 | NOT cached (varies per scene) |
| CriticResponse output | ~1,000-2,000 | Scales with `issues` list length |
| **Total input** | 4,800-7,200 | First call: all uncached; 2nd+: ~3000 discounted |
| **Total output** | 1,000-2,000 | |
| **Est. cost / scene** | $0.08-0.12 | Opus 4.7 pricing as of 2026-04; cached prefix ~$0.01 saved/scene |

At 243 scenes × 1-3 attempts, Phase 3 + Phase 4 scene-critic spend is ~$30-90 for the whole 27-chapter draft. OBS-04 mode-B escape rate + per-scene cost cap come online in Phase 5 REGEN-02.

## Plan 03-06 composition signature

```python
from anthropic import Anthropic
from book_pipeline.config.rubric import RubricConfig
from book_pipeline.critic import SceneCritic
from book_pipeline.observability import JsonlEventLogger

rubric = RubricConfig()                    # reads config/rubric.yaml
event_logger = JsonlEventLogger()          # writes runs/events.jsonl
critic = SceneCritic(
    anthropic_client=Anthropic(),          # reads ANTHROPIC_API_KEY from env
    event_logger=event_logger,
    rubric=rubric,
)
# Per-scene in the regen loop:
response = critic.review(CriticRequest(
    scene_text=draft.scene_text,
    context_pack=pack,
    rubric_id="scene.v1",
    rubric_version=rubric.rubric_version,   # typically matches — W-6 Test I
    chapter_context={"attempt_number": N},
))
# On SceneCriticError → persist HARD_BLOCKED with exc.context.
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] anthropic SDK keyword is `output_format=`, not `response_format=`.**

- **Found during:** Task 2 GREEN — plan text specifies `client.messages.parse(response_format=CriticResponse, ...)` but live inspection of `anthropic.resources.messages.Messages.parse` in v0.96.0 shows the signature takes `output_format: Optional[type[ResponseFormatT]]` (merged into `output_config`). Passing `response_format=` would raise `TypeError: messages.parse() got an unexpected keyword argument 'response_format'`.
- **Fix:** Used `output_format=CriticResponse` in `SceneCritic._call_opus_inner`. No behavioral difference — Pydantic schema is converted to JSONSchema for Anthropic via either channel; the SDK plumbs this to the same wire format.
- **Files modified:** `src/book_pipeline/critic/scene.py`.
- **Commit:** `b7035b7` (Task 2 GREEN).
- **Scope:** Plan text was written against an SDK draft; Rule 3 applies (blocking — the plan literal would not compile).

**2. [Rule 3 — Blocking] ParsedMessage attribute is `.parsed_output`, not `.parsed`.**

- **Found during:** Task 2 GREEN — plan text says "response.parsed (CriticResponse instance from messages.parse)". Live inspection: `anthropic.types.ParsedMessage.parsed_output` (property returning `Optional[ResponseFormatT]`).
- **Fix:** Used `response.parsed_output` in `SceneCritic.review`. Same content — a `CriticResponse` instance populated by the SDK — different access path.
- **Files modified:** `src/book_pipeline/critic/scene.py`, `tests/critic/fixtures.py` (FakeParsedMessage exposes `.parsed_output`).
- **Commit:** `b7035b7` (Task 2 GREEN).
- **Scope:** Plan text drift; Rule 3 applies.

**3. [Rule 3 — Blocking] tenacity retry-wait monkeypatch requires patching the decorated method's `retry.wait` attribute, not `wait_exponential.__init__`.**

- **Found during:** Task 2 GREEN — initial implementation of `_patch_tenacity_wait_fast` monkeypatched `tenacity.wait_exponential.__init__` hoping new instances would pick up the fast config. But `@tenacity.retry(wait=wait_exponential(...))` captures the `wait_exponential` instance at decoration (import) time, so Test E ran with the real 2→4→8→16s waits and took ~30s.
- **Fix:** `monkeypatch.setattr(SceneCritic._call_opus_inner.retry, "wait", tenacity.wait_fixed(0))` reaches into the captured `Retrying` object and replaces its `wait` attribute directly. Test E drops from 30s to <1s; production config (`wait_exponential(multiplier=2, min=2, max=30)`) unchanged. T-03-05-05 DoS mitigation (total wall time bounded at ~90s over 5 attempts) preserved.
- **Files modified:** `tests/critic/test_scene_critic.py`.
- **Commit:** `b7035b7` (Task 2 GREEN).
- **Scope:** Plan spec said "Monkeypatch tenacity.wait_exponential to wait=0.01 in tests to avoid slowing the suite" — the approach doesn't work due to the decoration-time capture. Rule 3 applies (test suite timing regression).

**4. [Rule 2 — Missing critical] `runs/critic_audit/` added to `.gitignore`.**

- **Found during:** Plan `<verification>` §12 explicitly requires this addition — noticed while drafting the commit.
- **Issue:** CRIT-04 audit records are local-truth (ADR-003) same as `runs/events.jsonl`. Without the gitignore entry, per-scene audits would be accidentally staged with every `git add -A` — and each audit can carry the full raw Anthropic payload including the scene_text (unpublished prose). T-03-05-07 threat register flag.
- **Fix:** Added `runs/critic_audit/` to the "Runtime artifacts" section of `.gitignore` alongside `runs/*.jsonl`.
- **Files modified:** `.gitignore`.
- **Commit:** `b7035b7` (Task 2 GREEN).
- **Scope:** Plan explicitly required this. Rule 2 applies (correctness — missing gitignore entry would leak prose via git history).

**5. [Rule 2 — Missing critical] Mypy strict-mode fallout: `response.parsed_output` types as `Any` via generic SDK; `chapter_context.get(...)` returns `object`.**

- **Found during:** Task 2 GREEN lint gate — `bash scripts/lint_imports.sh` reported `Returning Any from function declared to return CriticResponse` on `SceneCritic.review` and `No overload variant of int() matches argument type object` on `_derive_attempt_number`.
- **Fix:** (a) Pinned `parsed: CriticResponse = parsed_raw` after the None-check in `review()` so mypy sees the narrowed type. (b) Rewrote `_derive_attempt_number` to `isinstance(raw, int)` → return directly; `isinstance(raw, str)` → try `int(raw)` with ValueError fallback; else return 1. Cleaner than the plan's `int(raw) + type: ignore` because it actually handles the runtime shape.
- **Files modified:** `src/book_pipeline/critic/scene.py`.
- **Commit:** `b7035b7` (Task 2 GREEN).
- **Scope:** Plan spec had `int(raw)` + `# type: ignore[arg-type]` which mypy 1.x flags as `unused-ignore` because it can tell `raw: object` fails overload resolution, not just arg-type. Rule 2 applies (correctness: the original would crash on `chapter_context={"attempt_number": 2.5}` float input).

**Total deviations:** 5 auto-fixed. Deviations 1-3 are plan-vs-SDK / plan-vs-runtime drift — the plan was written against an older mental model of the anthropic SDK and tenacity; the code shipped is the version that actually works. Deviations 4-5 are plan-required content that the GREEN shots surfaced as necessary for lint+gitignore cleanliness. None changed the Protocol signature, the Event shape, the audit-record shape, or the cache_control semantics.

## Authentication Gates

**None.** Plan 03-05 lands the SceneCritic class + the CLI composition surface; it does NOT make a real Anthropic API call. Tests use a FakeAnthropicClient that captures messages.parse call args in-memory. The REAL Opus 4.7 round-trip will land in Plan 03-07 (`book-pipeline draft` CLI) or Plan 03-06 (end-to-end scene loop), at which point `ANTHROPIC_API_KEY` presence becomes a real auth gate (SecretsConfig.is_anthropic_present() check is already in `validate-config` from Plan 01-03).

## Deferred Issues

1. **Audit rotation / compression.** T-03-05-08 accepted: audit dir grows unbounded (~10MB/scene × 243 × R). Phase 6 ingester (OBS-02) can rotate + compress; Plan 03-05 ships write-path only.
2. **Mode-B-specific few-shot yaml.** Phase 5 Mode-B drafter may want a different few-shot regime in the critic (frontier-vs-frontier self-preference C-1 in PITFALLS). Plan 03-05's `SceneCritic` accepts a `fewshot_path` kwarg so Phase 5 can swap without touching the kernel; only the yaml file changes.
3. **Cross-family critic audit (CRIT-03, Phase 6).** Reads this plan's events + audit records; re-scores with Anthropic-independent judge (e.g. OpenAI GPT-5). Plan 03-05's `rubric_version` stamping makes cross-regime comparison clean.
4. **Audit record shape change will bump rubric_version implicitly.** Currently audit JSON schema is 1:1 with CriticResponse fields. If Phase 4 adds a new axis or severity value, `rubric_version` MUST bump per REQUIREMENTS CRIT-04 — the ingester sees the discontinuity and keeps separate series. Documented as a Phase 4 Plan 04-xx convention rather than a Plan 03-05 change.
5. **Anthropic SDK `cache_creation_input_tokens` telemetry.** The Event uses `cached_tokens = cache_read_input_tokens` only; `cache_creation_input_tokens` (the one-time cost of seeding the cache) is visible in the audit raw_anthropic_response but NOT bubbled up to the Event. Phase 6 cost-tracker can read from audits for the first-call tax; Phase 3 Events focus on steady-state cost per scene (what Plan 03-07's CLI digest surfaces).

## Known Stubs

**None.** SceneCritic is production-ready: real `anthropic.messages.parse` call, real tenacity retry, real audit log, real Event emission. The only test-only stub is `tests/critic/fixtures.py::FakeAnthropicClient` (pure in-memory mock), intentionally not imported by production code.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All 10 threats (T-03-05-01 through T-03-05-10) are covered as planned:

- **T-03-05-01** (rubric.yaml edited mid-run): MITIGATED. SceneCritic reads RubricConfig() at __init__ and reuses self.rubric.rubric_version across every Event + CriticResponse. Plan 03-06 CLI constructs ONE SceneCritic per `book-pipeline draft` run.
- **T-03-05-03** (repudiation, critic response not audited): MITIGATED. CRIT-04 audit written on EVERY call (W-7: success AND failure). Atomic tmp+os.replace via `write_audit_record`.
- **T-03-05-04** (ANTHROPIC_API_KEY leak): MITIGATED. anthropic.Anthropic() reads env directly; SceneCritic never touches the key; Event.extra never includes auth headers (verified via Test G's Event round-trip — only the plan-specified fields are present).
- **T-03-05-05** (DoS unbounded retries): MITIGATED. tenacity 5x exp backoff capped at 30s per attempt; total wall-time ≤~90s; exhaust → SceneCriticError.
- **T-03-05-06** (overall_pass invariant silently accepted): MITIGATED. Step-8 invariant fix + Event.extra['invariant_fixed']=True.
- **T-03-05-07** (scene_text prose in audit): ACCEPTED + MITIGATED via .gitignore `runs/critic_audit/`. Prose stays local-disk only.
- **T-03-05-09** (critic → book_specifics): MITIGATED. `grep -c "book_specifics" src/book_pipeline/critic/*.py` = 0. Import-linter contract 1 green.
- **T-03-05-10** (few-shot bias): ACCEPTED + documented. rubric_version should bump when few-shot content changes; this SUMMARY flags the convention for Phase 4.

## Verification Evidence

Plan `<success_criteria>` + task `<acceptance_criteria>` coverage:

| Criterion | Status | Evidence |
|---|---|---|
| SceneCritic structurally satisfies Critic Protocol | PASS | Test A: `isinstance(c, Critic)` True; `level == 'scene'`. |
| Every review() writes audit record | PASS | Test B: exactly 1 json file under `audit_dir/` after review. Test E: 1 file on failure path too. |
| CRIT-04 audit has all 11 required keys + indented JSON | PASS | Test J: assert set(record.keys()) >= required_keys. |
| cache_control={'type':'ephemeral','ttl':'1h'} applied | PASS | Test F: `call_kwargs['system'][0]['cache_control']` matches. |
| Events emitted with rubric_version top-level field | PASS | Test G + B: ev.rubric_version matches RubricConfig().rubric_version. |
| CriticResponse.rubric_version stamped == rubric.yaml | PASS | Test B: response.rubric_version == expected_rubric_version (read from yaml). |
| All 5 REQUIRED_AXES enforced post-process | PASS | Test C: 'metaphysics' filled pass=True, score=75.0; Event.extra['filled_axes']=['metaphysics']. |
| overall_pass invariant | PASS | Test D: inconsistent response corrected; Event.extra['invariant_fixed']=True. |
| Tenacity 5x exponential on transient errors | PASS | Test E: 5× APIConnectionError → SceneCriticError. |
| Failure-path audit written (W-7) | PASS | Test E: parsed_critic_response=null, error_type='APIConnectionError', attempts_made=5. |
| Two reviews send identical system_blocks (cache-stable) | PASS | Test H: `calls[0]['system'] == calls[1]['system']`. |
| rubric_version mismatch between request and critic (W-6) | PASS | Test I: Event.extra['request_rubric_version_mismatch']=True. |
| Kernel cleanliness | PASS | `grep -c "book_specifics" src/book_pipeline/critic/*.py` = 0. |
| Few-shot curation (B-2) | PASS | Test 5a+5b: bad has 7 real entities / 173 words; good has 5 real entities / 192 words. Test 5c: both Pydantic-validate. |
| System prompt deterministic SHA | PASS | Test 4: two builder renders produce byte-identical strings + SHAs. |
| `bash scripts/lint_imports.sh` green | PASS | Import-linter 2 contracts kept; ruff clean; mypy clean on 91 source files. |
| Full test suite increases | PASS | 340 passed (+20 from 320 baseline). |

## Self-Check: PASSED

Artifact verification (files on disk at `/home/admin/Source/our-lady-book-pipeline/`):

- FOUND: `src/book_pipeline/critic/audit.py`
- FOUND: `src/book_pipeline/critic/scene.py` (576 lines)
- FOUND: `src/book_pipeline/critic/templates/system.j2`
- FOUND: `src/book_pipeline/critic/templates/scene_fewshot.yaml` (173+192-word curated scenes)
- FOUND: `tests/critic/__init__.py`
- FOUND: `tests/critic/fixtures.py`
- FOUND: `tests/critic/test_audit.py`
- FOUND: `tests/critic/test_rubric_version_stamping.py`
- FOUND: `tests/critic/test_scene_critic.py`
- FOUND: `.gitignore` (with `runs/critic_audit/` line added)
- FOUND: `src/book_pipeline/critic/__init__.py` (exports updated)

Commit verification on `main` branch (git log --oneline):

- FOUND: `e6f599c test(03-05): RED — failing tests for audit.py + scene_fewshot.yaml + SystemPromptBuilder`
- FOUND: `d073a30 feat(03-05): GREEN — audit.py + scene_fewshot.yaml + SystemPromptBuilder`
- FOUND: `ae5a1b6 test(03-05): RED — failing tests A-J for SceneCritic (CRIT-01 + CRIT-04)`
- FOUND: `b7035b7 feat(03-05): GREEN — SceneCritic (CRIT-01 Anthropic Opus 4.7 + CRIT-04 audit)`

All 4 per-task commits landed on `main`. Aggregate gate green. Full non-slow test suite: 340 passed.

---

*Phase: 03-mode-a-drafter-scene-critic-basic-regen*
*Plan: 05*
*Completed: 2026-04-22*
