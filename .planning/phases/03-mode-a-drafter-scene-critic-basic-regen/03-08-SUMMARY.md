---
phase: 03-mode-a-drafter-scene-critic-basic-regen
plan: 08
type: execute-summary
status: deferred
wave: 7
completed_at: 2026-04-22
operator_action_required: true
---

# Plan 03-08 Summary — Real-World Smoke (DEFERRED to operator)

## Outcome

**Status: deferred_pending_operator_preflight**

Plan 03-08 is a `checkpoint:human-verify` task that requires operator secrets + live
GPU + ~$0.6 Anthropic spend. Autonomous session could not complete the smoke because
mandatory preconditions are not met on this host:

| Precondition | State | Blocker |
|--------------|-------|---------|
| `ANTHROPIC_API_KEY` env var | **NOT SET** | Hard-block. Required for CRIT-01 Opus 4.7 call + REGEN-01. |
| `.env` file in repo with Anthropic key | **NOT PRESENT** | Would satisfy via pydantic-settings `.env` loader. |
| `vllm-paul-voice` systemd unit | **NOT STARTED** | Plan 03-03 shipped generator + bootstrap CLI; `book-pipeline vllm-bootstrap --enable --start` was never run (awaits operator). |
| Port 8002 open | **UNUSED** | Confirms vLLM not yet serving V6 adapter. |
| GB10 GPU | **AVAILABLE** | `vllm-qwen122.service` is inactive; no port/VRAM conflict. |
| RAG indexes populated | **YES** | 5 LanceDB tables at `ingestion_run_id=ing_20260422T082448725590Z_2264c687` (Phase 2). |
| `config/voice_pin.yaml` V6 SHA | **PINNED** | Plan 03-01 wrote real SHA `3f0ac5e2...d094`. |
| `config/voice_anchors/anchor_set_v1.yaml` | **PINNED** | Plan 03-02 wrote `anchor_set_sha=28fd890bc4c8...df31` (22 anchors). |
| `scenes/ch01/ch01_sc01.yaml` stub | **PRESENT** | Plan 03-07 landed the stub. |

Phase 3 kernel + CLI are proven against mocked dependencies (11 integration tests in
`tests/cli/test_draft_loop.py` — all green). The outstanding work is the live-infra
forcing function documented in Plan 03-08.

## Operator runbook to complete 03-08

From `/home/admin/Source/our-lady-book-pipeline`:

```bash
# 1) Set Anthropic credentials (one of):
export ANTHROPIC_API_KEY="sk-ant-..."
# OR write to .env at repo root:
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
chmod 600 .env

# 2) Pre-flight gates
uv run book-pipeline validate-config
bash scripts/lint_imports.sh
nvidia-smi
systemctl --user status vllm-qwen122  # confirm inactive — avoid VRAM collision

# 3) Start vLLM paul-voice on port 8002
uv run book-pipeline vllm-bootstrap --enable --start
sleep 60  # vLLM LoRA load + warmup
curl -s http://127.0.0.1:8002/v1/models | head -5  # health check

# 4) Boot handshake (SHA verify against V6 pin)
uv run python -c "from book_pipeline.drafter.vllm_client import VllmClient; from book_pipeline.config.voice_pin import VoicePinConfig; import asyncio; c = VllmClient('http://127.0.0.1:8002'); asyncio.run(c.boot_handshake(VoicePinConfig()))"

# 5) Real smoke (expect ~3-10 min wall, ~$0.6 spend)
PYTHONUNBUFFERED=1 uv run book-pipeline draft ch01_sc01 2>&1 | tee runs/smoke_03_08.log

# 6) Document outcome
#   - If COMMITTED: cat drafts/ch01/ch01_sc01.md  (verify 9 frontmatter keys)
#   - If HARD_BLOCKED: cat drafts/scene_buffer/ch01/ch01_sc01.state.json
#   - Either way: runs/events.jsonl has role='drafter', 'critic', (maybe) 'regenerator' Events
#     with caller_context carrying scene_id, attempt_number, voice_pin_sha, rubric_version
#     and extra.voice_fidelity_score
#   - runs/critic_audit/ch01_sc01_*.json has the Opus payload

# 7) After the smoke lands, edit this file to fill in the Observed Outcome section below
#    and commit with: git commit -m "docs(03-08): real smoke completed — <outcome>"
```

Acceptable smoke outcomes (per plan's must_haves):
- **PASS-COMMIT** — `drafts/ch01/ch01_sc01.md` produced with all 9 frontmatter keys.
- **PASS-HARDBLOCK-FAIL-CRITIC** — `state.json` HARD_BLOCKED, reason `failed_critic_after_R_attempts`. Expected for V6 on complex beat.
- **PASS-HARDBLOCK-TRAINING-BLEED** — `state.json` HARD_BLOCKED, reason `training_bleed`. V-2 mitigation live on real corpus.

FAIL outcomes (require fix before Phase 4):
- HARD_BLOCKED('mode_a_unavailable') → vLLM issue.
- HARD_BLOCKED('critic_blocked:anthropic_unavailable') → auth/rate.
- HARD_BLOCKED('anchor_set_drift') → Plan 03-02 state out of sync.
- Unhandled traceback outside HARD_BLOCKED taxonomy → integration gap; fix in gap-closure plan.

## Observed Outcome

*(operator fills this in after running the smoke)*

- Timestamp: —
- Outcome: —
- Wall time: —
- Token counts (draft / critic / regen): —
- Anthropic spend: —
- 12-gram gate triggered: —
- voice_fidelity_score: —
- Events landed in runs/events.jsonl: —
- Audit files in runs/critic_audit/: —
- Notes / deferred issues for Phase 4: —

## Phase 3 Exit State

8/8 plans shipped (6 kernel + 1 CLI + 1 smoke-deferred). All 6 Phase 3 REQs closed at
the kernel+CLI layer:

| REQ | Status | Evidence |
|-----|--------|----------|
| DRAFT-01 | Complete | Plan 03-01 pin + 03-03 vLLM boot_handshake + 03-04 ModeADrafter |
| DRAFT-02 | Complete | Plan 03-04 SamplingProfiles per scene_type |
| CRIT-01 | Complete | Plan 03-05 SceneCritic with Opus 4.7 + messages.parse |
| CRIT-04 | Complete | Plan 03-05 audit on every invocation (success + failure) |
| REGEN-01 | Complete | Plan 03-06 SceneLocalRegenerator + 03-07 SceneStateMachine R=3 loop |
| OBS-03 | Complete | Plan 03-02 anchor centroid + 03-04 voice_fidelity_score on Event |

**REGEN-01 note:** Kernel + CLI are complete. The live-infra validation (that regen
actually produces improved output on a real failing critic report) is the Plan 03-08
smoke — deferred as documented above.

Phase-level test count: 396 passing tests (up from 261 Phase-2-exit baseline; +135 net
new in Phase 3 across 7 executed plans). Zero regressions against Phase 1 + 2 suites.
`bash scripts/lint_imports.sh` green across 98 source files.
