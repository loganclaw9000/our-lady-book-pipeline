# Phase 5: Mode-B Escape + Regen Budget + Alerting + Nightly Orchestration — Context

**Gathered:** 2026-04-23 (auto mode — recommended defaults)
**Status:** Ready for planning

<domain>
## Phase Boundary

Every failure path in the scene loop terminates in either a successful commit (Mode-A pass, Mode-B escalation, or regen success) or a deduplicated Telegram alert — **never a silent wedge**. Nightly openclaw cron drives the full loop unattended. Budget caps prevent Mode-B cost blowouts. Pre-flagged structurally complex beats (Cholula stir, two-thirds reveal, siege climax) route to Mode-B from the start.

In scope: DRAFT-03 (Mode-B Opus drafter), DRAFT-04 (Mode-B preflags), REGEN-02 (R-cap + spend cap), REGEN-03 (auto-escalate to Mode-B), REGEN-04 (oscillation detector + hard-block), LOOP-01 (end-to-end scene loop autonomous), ORCH-01 (nightly cron), ALERT-01 (Telegram alerts), ALERT-02 (alert dedup + cooldown). Plus 2 Phase 4 deferrals: SC4 surgical scene-kick routing on CHAPTER_FAIL + SC6 bundler stale-card flag.

Out of scope: First-draft 27-chapter production run (Phase 6 FIRST-01), thesis registry + matcher (Phase 6 TEST-02), ablation harness extensions (Phase 6), cross-family critic (Phase 6 CRIT-03), weekly digest (Phase 6 ORCH-02).

</domain>

<decisions>
## Implementation Decisions

### Mode-B Drafter (DRAFT-03 / DRAFT-04)

- **D-01:** Mode-B drafter is a NEW concrete under `src/book_pipeline/drafter/mode_b.py`, satisfying the existing frozen `Drafter` Protocol with `mode='B'`. Clone-not-abstract pattern per ADR-004 — ModeADrafter stays untouched; shared helpers (Jinja2 template sentinel split, word-count target, Event emission shape) paraphrased.
- **D-02:** Backbone = Anthropic SDK `anthropic>=0.96` with `claude-opus-4-7` (no `claude-sonnet-4-6` fallback in v1 — cost predictability beats flex; re-evaluate at Phase 6 ablation). Ephemeral prompt cache `cache_control.ttl="1h"` around the voice-samples block so repeat drafts within an hour hit cache. Single workspace API key — cache hits held across all Mode-B calls per ADR-003.
- **D-03:** Voice samples prefix = 3-5 curated paragraphs from paul-thinkpiece training corpus (NOT the FT anchor set — different use case). Curation CLI `book-pipeline curate-voice-samples` ships alongside; output to `config/voice_samples.yaml`; cached once then reloaded per call. Selection rule: same ANALYTIC + ESSAY + NARRATIVE balance as anchor curator (Plan 03-02 precedent) but longer passages (400-600 words each). Stored under `book_specifics/` because selection is book-authored; kernel drafter reads opaque sample list via DI.
- **D-04:** Mode-B preflags live in `config/mode_preflags.yaml` (new). Shape: `preflagged_beats: [ch01_b1_beat01, ch08_b2_beat02, ch14_b3_beat03, ...]`. Reader: `book_pipeline/drafter/preflag.py` pure function `is_preflagged(scene_id: str, preflag_set: frozenset[str]) -> bool`. Outline-parser deps already land the canonical beat_id shape (Phase 2 Plan 04). Demotion to Mode-A requires explicit removal from the YAML + logged via pre-commit audit — never silent.

### Regen Budget + Escalation (REGEN-02 / REGEN-03 / REGEN-04)

- **D-05:** R-cap per scene = 3 Mode-A regen attempts (configurable `config/mode_thresholds.yaml` new key `regen.r_cap_mode_a`). Mirrors Plan 03-07 SceneStateMachine `R=3` assumption (4 total attempts: 1 initial + 3 regens). Attempt #4's critic-fail is the trigger for Mode-B escalation (REGEN-03).
- **D-06:** Per-scene spend cap (USD) = $0.75 hard cap (configurable `regen.spend_cap_usd_per_scene`). Enforced by tracking cumulative `tokens_in + tokens_out` per scene across Events, converted to USD via pricing lookup table. HARD abort on breach → scene HARD_BLOCKED('spend_cap_exceeded') + mid-run Telegram alert (not end-of-week surprise per SC3).
- **D-07:** Oscillation detector = per-scene-attempt axis-set comparison. If attempts N and N-2 fail on IDENTICAL axis+severity tuples (e.g., both `historical:high`) → oscillation flag → immediate Mode-B escalation (skip remaining Mode-A budget). Detector lives in `src/book_pipeline/regenerator/oscillation.py` as pure function over the Event trail; state is read-only.
- **D-08:** Escalation event is a new `role='mode_escalation'` Event with `extra={from_mode, to_mode, trigger: 'r_cap_exhausted'|'spend_cap_exceeded'|'oscillation'|'preflag', issue_ids: [...]}`. Written ONCE per escalation; both the ModeADrafter-exhaust path and the pre-loop Mode-B-preflag path emit this so Phase 6 OBS-04 has one canonical signal.

### Scene Loop + Chapter-Fail Routing (LOOP-01 + deferred SC4)

- **D-09:** Scene loop remains the existing `cli/draft.py` composition root (Plan 03-07). Phase 5 extends it with: (a) `preflag` check before first drafter call; (b) oscillation check at each regen attempt; (c) spend-cap check at each attempt; (d) Mode-B escalation path.
- **D-10:** Surgical scene-kick routing on CHAPTER_FAIL (Phase 4 SC4 deferral): extract `implicated_scene_ids: set[str]` from `CriticResponse.issues` by parsing `issue.location` — each issue cites `ch{NN}_sc{II}` prefix. Map to scene IDs, reset those scenes' SceneStateRecord → PENDING, emit `role='scene_kick'` Event with `extra={kicked_scenes, chapter_num, issue_refs}`. Scenes NOT implicated stay COMMITTED. Non-specific chapter-level issues (no scene reference) → fall back to "full chapter fail" → CHAPTER_FAIL terminal + Mode-B re-draft preflag (future phase hook).
- **D-11:** Stale-card flag (Phase 4 SC6 deferral): entity_state retriever extension adds `source_chapter_sha` to each RetrievalHit.metadata (read from the card JSON `source_chapter_sha` field via `rag/reindex.py`). Bundler post-retrieval scan: for each entity_state hit, shell out `git rev-parse HEAD:canon/chapter_{last_seen_chapter:02d}.md` and compare. Mismatch → push into `conflicts` list with dimension='stale_card', keeps the hit in the pack but Phase 3 critic sees the conflict. Regression test mutates canon by one byte, asserts bundler surfaces stale flag.

### Alerting (ALERT-01 / ALERT-02)

- **D-12:** Telegram alert backbone = the existing `claude-config/telegram-channel` skill's bot (user already configured per memory). Hard-block condition taxonomy (derive from codebase grep): `['spend_cap_exceeded', 'regen_stuck_loop', 'rubric_conflict', 'voice_drift_over_threshold', 'checkpoint_sha_mismatch', 'vllm_health_failed', 'stale_cron_detected', 'mode_b_exhausted']`. New module `src/book_pipeline/alerts/telegram.py` with `class TelegramAlerter` + `send_alert(condition: str, detail: dict) -> None`.
- **D-13:** Dedup + cooldown = in-memory per-alerter LRU cache keyed on `(condition, scene_id_or_chapter_num)` with 1h TTL (spec requires 1-hour cooldown before re-alerting same condition). Persistence across process restarts = `runs/alert_cooldowns.json` (gitignored) read at alerter `__init__`, written after every successful send. T-05-alert threat mitigation: no secrets in payload (detail dict whitelist at send time), rate-limit on Telegram API surface (5 req/min).
- **D-14:** Stale-cron detector = `book-pipeline check-cron-freshness` CLI that inspects `runs/events.jsonl` last-cron-run timestamp. If >36h old: emit hard-block alert. Runs as its own openclaw cron at 08:00 daily (independent of nightly loop to avoid self-silencing).

### Orchestration (ORCH-01)

- **D-15:** Nightly cron = single openclaw cron at 02:00 America/Los_Angeles: `book-pipeline nightly-run --max-scenes 10`. 10-scene cap prevents runaway cost on a bad night; chapter assembly + DAG remain unrate-limited (kicks only after 3 scenes per beat fill the chapter buffer per outline_scene_counts.py). Persistent via `~/.openclaw/cron/jobs.json`. Gateway-token gate already deferred from Phase 2 — document in CONTEXT as prerequisite operator action; cron registration skill `book-pipeline openclaw register-cron --nightly` present but emits a clear "needs `OPENCLAW_GATEWAY_TOKEN`" message if unset.
- **D-16:** Nightly run CLI composes: (a) vllm-bootstrap (SHA-verify + lora-load); (b) `/scene` loop until buffer filled or max-scenes reached; (c) trigger chapter DAG if buffer full; (d) emit completion Event. On any HARD_BLOCK: send Telegram alert + STOP (don't cascade). Exit codes: 0 scene-loop-progressed, 2 vllm-bootstrap-failed, 3 hard-block-fired, 4 max-scenes-reached-with-no-progress (no-op nights).

### SQLite Metric Ledger (OBS-02)

- **D-17:** Ledger lives at `runs/metrics.sqlite3` (gitignored; rebuildable from events.jsonl per OBS-02 idempotency). Schema: one row per (event_id, axis) with `scene_id, chapter_num, attempt_number, score, severity, mode_tag, voice_fidelity, cost_usd, ts_iso`. Ingester `book-pipeline ingest-events` scans events.jsonl tail-ward since last persisted event_id. Schema-version column for OBS-04 migration. LanceDB not used here — SQLite adequate + stdlib-only.

### Claude's Discretion

- Python module shape for `alerts/` kernel package (likely single-file per ADR-004).
- Exact spend-cap USD-per-token pricing table structure (Opus 4.7 pricing locked in `config/pricing.yaml`).
- Exact regex / parsing shape for `CriticIssue.location` → scene_id (defensive int-cast like chapter path sanitization).
- Specific Telegram message template text.

</decisions>

<canonical_refs>
## Canonical References

### Hard Constraints (MUST read before planning)

- `.planning/PROJECT.md` — vision, principles, non-negotiables (budget tracking, human-touch <1 per scene, Telegram hard-block alerts only)
- `.planning/REQUIREMENTS.md` — v1 requirements table; phase 5 covers DRAFT-03/04, REGEN-02/03/04, LOOP-01, ORCH-01, ALERT-01/02, OBS-02/04 plus Phase 4 deferrals CORPUS-02 (read-side) and LOOP-04 (scene-kick).
- `.planning/ROADMAP.md §Phase 5` — 6 numbered success criteria.
- `.planning/phases/04-chapter-assembly-post-commit-dag/04-VERIFICATION.md §deferrals` — SC4 + SC6 rescope rationale.
- `docs/ADRs/ADR-003.md` (observability-is-load-bearing) — every LLM call emits Event; Mode-B cache semantics workspace-scoped.
- `docs/ADRs/ADR-004.md` (kernel extraction hygiene) — Mode-B drafter clones ModeADrafter shape, does not subclass.

### Existing concretes this phase composes

- `src/book_pipeline/drafter/mode_a.py` (Plan 03-04) — reference for drafter-Protocol concrete shape
- `src/book_pipeline/drafter/vllm_client.py` (Plan 03-03) — Mode-A IO layer (Mode-B uses Anthropic SDK, not vLLM)
- `src/book_pipeline/critic/scene.py` + `critic/chapter.py` — CriticResponse + CriticIssue shapes drive D-10 scene-kick extraction
- `src/book_pipeline/regenerator/scene_local.py` (Plan 03-06) — regen call shape; R-cap + spend-cap wrap this at Plan 03-07 composition root
- `src/book_pipeline/chapter_assembler/dag.py` (Plan 04-04) — CHAPTER_FAIL terminal state + blocker-tag audit entry points for D-10
- `src/book_pipeline/rag/bundler.py` (Plan 02-05) + `rag/reindex.py` (Plan 04-04) — extension seam for D-11 stale-card flag
- `src/book_pipeline/observability/event_logger.py` (Plan 01-03) — emission target for D-08 mode_escalation + D-11 scene_kick events
- `openclaw.json` + `~/.npm-global/lib/node_modules/openclaw/docs/automation/cron-jobs.md` — nightly cron registration pattern (already exercised in Plans 02-06 ingest-cron)

### External references

- Anthropic SDK prompt caching docs — [cache_control.ttl](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- Telegram Bot API — [sendMessage](https://core.telegram.org/bots/api#sendmessage) + rate limits
- SQLite stdlib module — [sqlite3](https://docs.python.org/3/library/sqlite3.html) for ledger (OBS-02)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `ModeADrafter` cache-identity pattern (Plan 03-04 `_system_blocks` pre-rendered once at `__init__`) directly transfers to Mode-B — Anthropic cache key is byte-identical prefix, so pre-render + reuse the voice-samples block the same way.
- `SceneCritic` tenacity config (`wait_exponential(multiplier=2, min=2, max=30)`, 5 attempts, `retry_if_exception_type((APIConnectionError, APIStatusError))`) clones verbatim to Mode-B drafter API boundary.
- `SceneLocalRegenerator` tenacity-retry-wait monkeypatch pattern from `tests/regenerator/test_scene_local.py` reused for Mode-B drafter tests — drops Mode-B integration test wall time from ~60s to <1s.
- `cli/draft.py::_build_composition_root` (Plan 03-07) is the hook for wiring the Mode-B escalation path; `_FakeDrafter` / `_FakeCritic` / `_FakeRegenerator` test fakes extend by Protocol for Phase 5 tests.
- Existing atomic-tmp-rename `_persist(record, state_path)` helper used for SceneStateRecord — same pattern for `runs/alert_cooldowns.json` + `runs/metrics.sqlite3` checkpoint marker.

### Established Patterns

- **Clone-not-abstract** (ADR-004): every Phase 4 critic / extractor / retrospective writer cloned its sibling. Phase 5 continues: Mode-B clones Mode-A, chapter-DAG-style orchestration clones scene-loop-style orchestration, alerter clones event-emitter shape.
- **Import-linter contracts 1+2** are the architectural guardrails. New kernel packages (`alerts/`, possibly `preflag/`, `spend_tracker/`) land at plan start with pyproject.toml + scripts/lint_imports.sh extensions (precedent: Plan 04-01).
- **Fresh-pack invariant** for ChapterCritic (Plan 04-02 C-4 mitigation via `context_pack_fingerprint` in audit) generalizes: every Mode-B drafter call gets a fresh SceneRequest bundle, not a recycled pack. Enforce via audit fingerprint comparison.
- **Event-emission-at-shim-boundary** — every CLI-level composition root emits exactly one wrap-up Event per run (Plan 03-07 precedent). `nightly-run` CLI follows: one role='nightly_run' Event per invocation.

### Integration Points

- `cli/main.py` subcommand registration (Plan 04-05 precedent: 3 new subcommands land via `SUBCOMMAND_IMPORTS += N`; pyproject.toml import-linter exemptions for each).
- `openclaw.json` workspace definitions: new `workspaces/nightly-runner/` with AGENTS/SOUL/USER markdown (mirrors `workspaces/drafter/` shape).
- Telegram bot token stored via existing `telegram:configure` skill (per-user keychain); alert module reads via env var `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (documented prerequisite).

</code_context>

<specifics>
## Specific Ideas

- Mode-B voice samples should be LONGER than anchor set passages (400-600 words vs 150-250) — anchor is for cosine-scoring, samples are for in-context voice priming. Different job, different length.
- Alert messages must include a 1-line "how to unblock" hint when possible (e.g., `spend_cap_exceeded: increase spend_cap_usd_per_scene in config/mode_thresholds.yaml`). Paul reads these on a phone; terse is a feature.
- Oscillation detector is a SIGNAL, not a GATE. It fires on 2 identical axis+severity tuples in history, BUT Mode-B escalation only fires when history >= 2 (attempts 2+). Attempt 1 oscillation impossible.
- Per-scene metric export (for Phase 6 digest) reads from events.jsonl via the OBS-02 ingester — we never persist authoritative state in the sqlite ledger; it's always rebuildable.
- CHAPTER_FAIL scene-kick is surgical: it only kicks scenes IMPLICATED by issues. If ch01 fails with all issues citing sc02, only sc02 resets; sc01 + sc03 stay COMMITTED (already in canon/chapter_01.md? NO — chapter_01.md is already committed as FAIL target, rolled back via `git revert`; sc01/sc03 scene markdown files in drafts/ch01/ stay valid for next assembly).

</specifics>

<deferred>
## Deferred Ideas

- Mode-B voice-sample *selection rule* refinement (contrasting sample genres per scene type — Paul-narrative for dialogue-heavy, Paul-essay for structural) — pushed to Phase 6 ablation (TEST-03 compares selection rules).
- Sonnet 4.6 fallback for cost-sensitive Mode-B — pushed to Phase 6 ablation (TEST-03 variant).
- Multi-tier alert routing (hard-block → Telegram, warning → email digest, info → ledger only) — v1 ships Telegram-only per PROJECT.md.
- Anthropic Batch API for nightly Mode-B regens (cheaper but non-realtime) — pushed to Phase 6 cost optimization.
- Cross-machine cron resilience (run-lock file, dual-host deployment) — single-host (DGX Spark) is v1; multi-host deferred.

</deferred>

---

*Phase: 05-mode-b-escape-regen-budget-alerting-nightly-orchestration*
*Context gathered: 2026-04-23 via auto mode (all gray areas auto-resolved to recommended defaults)*
