# Phase 5: Mode-B Escape + Regen Budget + Alerting + Nightly Orchestration — Research

**Researched:** 2026-04-23
**Domain:** Anthropic frontier-model drafting + cost tracking + Telegram alerting + openclaw cron + SQLite event ingestion
**Confidence:** HIGH (Anthropic pricing + caching + openclaw cron are all verified against primary sources on-disk or fetched today; Telegram + SQLite patterns are verified against official docs)

## Summary

Phase 5 closes the scene loop by building four loosely-coupled concerns on top of existing Phase 3/4 kernel plumbing: **(1) a Mode-B drafter** that clones the `ModeADrafter` shape but speaks to Anthropic Opus 4.7 via `anthropic.Messages.create()` with a 1h ephemeral-TTL voice-samples cache; **(2) a regen-budget + escalation layer** wrapping the existing `cli/draft.py` composition root with pre-loop preflag check, per-attempt oscillation + spend-cap gates, and a canonical `role='mode_escalation'` event; **(3) a Telegram alerter** with LRU cooldown persisted to `runs/alert_cooldowns.json`; **(4) a nightly orchestrator CLI + openclaw cron registration** at 02:00 America/Los_Angeles, plus an 08:00 stale-cron detector. The two Phase 4 deferrals — surgical scene-kick routing on `CHAPTER_FAIL` and bundler stale-card flagging — fit naturally alongside Mode-B because both share the "extract `scene_id` from `CriticIssue.location` / compare-SHAs-at-retrieval-time" pattern.

Research validates every CONTEXT.md decision. The most important finding is a **pricing error in `openclaw.json`** — the repo's `cron_jobs.json` claims Opus 4.7 costs $15/$75 per MTok; the actual published price is **$5 input / $25 output**. The `config/pricing.yaml` file D-06 spend-cap enforcement reads should pin the correct numbers or the per-scene $0.75 cap fires 3× too aggressively. All seven research focus areas landed concrete verified answers: (1) `cache_control.ttl` is per-block (not per-message), (2) Telegram's relevant limits are 1 msg/sec per chat + 30 msg/sec global + 429 `retry_after`, (3) `openclaw cron add` uses `--message` / `--cron` / `--tz` / `--session isolated` with persistence at `~/.openclaw/cron/jobs.json`, (4) SQLite idempotent ingest uses `INSERT ... ON CONFLICT(event_id) DO NOTHING`, (5) Opus 4.7 cache-read cost is $0.50/MTok (10% of input), (6) `CriticIssue.location` is free-text — regex `ch(\d+)_sc(\d+)` with defensive int-cast matches both Plan 03-07 scene-id parsing and Plan 04-04 path sanitization, (7) `git rev-list -1 HEAD -- <path>` runs in ~60ms — naive per-hit is ~300ms/bundle (acceptable), batched per-chapter-path is ~60ms (preferred).

**Primary recommendation:** Ship Phase 5 in four sub-phases cleanly split by kernel package boundary: (P5a) Mode-B kernel + preflag loader + pricing table → (P5b) regen-budget wrapper + oscillation detector → (P5c) `alerts/` kernel + Telegram shim → (P5d) nightly CLI + openclaw cron registration + stale-cron detector + SQLite ingester (OBS-02). The deferrals (scene-kick routing, stale-card flag) bolt onto Phase 4's existing seams in P5a/P5b without new kernel packages.

## User Constraints (from CONTEXT.md)

### Locked Decisions (17 D-IDs — research THESE, not alternatives)

**Mode-B Drafter (DRAFT-03 / DRAFT-04):**
- **D-01:** Mode-B drafter = NEW concrete at `src/book_pipeline/drafter/mode_b.py`, satisfies existing frozen `Drafter` Protocol with `mode='B'`. Clone-not-abstract per ADR-004 — `ModeADrafter` untouched; shared helpers paraphrased.
- **D-02:** Backbone = `anthropic>=0.96` + `claude-opus-4-7`. **No** `claude-sonnet-4-6` fallback in v1. Ephemeral prompt cache `cache_control.ttl="1h"` around voice-samples block. Single workspace API key — cache hits held across all Mode-B calls per ADR-003.
- **D-03:** Voice samples prefix = 3-5 curated paragraphs from paul-thinkpiece training corpus (NOT the FT anchor set). 400-600 words each. Curation CLI `book-pipeline curate-voice-samples` ships alongside; output to `config/voice_samples.yaml`; cached once then reloaded per call. Selection rule mirrors Plan 03-02 anchor curator (ANALYTIC + ESSAY + NARRATIVE balance) but longer passages. Stored under `book_specifics/` because selection is book-authored; kernel drafter reads opaque sample list via DI.
- **D-04:** Mode-B preflags live at `config/mode_preflags.yaml` (new). Shape: `preflagged_beats: [ch01_b1_beat01, ch08_b2_beat02, ...]`. Reader at `book_pipeline/drafter/preflag.py` with pure function `is_preflagged(scene_id: str, preflag_set: frozenset[str]) -> bool`. Outline parser landed the canonical beat_id shape in Phase 2. Demotion to Mode-A requires explicit YAML removal + pre-commit audit log — never silent.

**Regen Budget + Escalation (REGEN-02 / REGEN-03 / REGEN-04):**
- **D-05:** R-cap per scene = 3 Mode-A regen attempts (configurable `config/mode_thresholds.yaml` new key `regen.r_cap_mode_a`). 4 total attempts = 1 initial + 3 regens. Attempt #4's critic-fail triggers Mode-B escalation.
- **D-06:** Per-scene spend cap = **$0.75 USD** (configurable `regen.spend_cap_usd_per_scene`). Enforced by cumulative `tokens_in + tokens_out` per scene across Events, converted to USD via pricing lookup. HARD abort on breach → `HARD_BLOCKED('spend_cap_exceeded')` + mid-run Telegram alert.
- **D-07:** Oscillation detector = per-scene-attempt axis-set comparison. Attempts N and N-2 fail on IDENTICAL `axis+severity` tuples → oscillation flag → immediate Mode-B escalation (skip remaining Mode-A budget). Detector at `src/book_pipeline/regenerator/oscillation.py` — pure function over the Event trail; state read-only.
- **D-08:** Escalation event = new `role='mode_escalation'` Event with `extra={from_mode, to_mode, trigger: 'r_cap_exhausted'|'spend_cap_exceeded'|'oscillation'|'preflag', issue_ids: [...]}`. Written ONCE per escalation.

**Scene Loop + Chapter-Fail Routing (LOOP-01 + Phase 4 SC4 deferral):**
- **D-09:** Scene loop stays at existing `cli/draft.py` composition root. Phase 5 extends it with: (a) preflag check before first drafter call; (b) oscillation check at each regen attempt; (c) spend-cap check at each attempt; (d) Mode-B escalation path.
- **D-10:** Surgical scene-kick on CHAPTER_FAIL: extract `implicated_scene_ids: set[str]` from `CriticResponse.issues` by parsing `issue.location` — each issue cites `ch{NN}_sc{II}` prefix. Map to scene IDs, reset those scenes' `SceneStateRecord → PENDING`, emit `role='scene_kick'` Event with `extra={kicked_scenes, chapter_num, issue_refs}`. Scenes NOT implicated stay COMMITTED. Non-specific chapter-level issues → fall back to CHAPTER_FAIL terminal.
- **D-11:** Stale-card flag (Phase 4 SC6): `entity_state` retriever adds `source_chapter_sha` to each `RetrievalHit.metadata` (read from card JSON's `source_chapter_sha` field via `rag/reindex.py`). Bundler post-retrieval scan: for each entity_state hit, shell out `git rev-parse HEAD:canon/chapter_{last_seen_chapter:02d}.md` and compare. Mismatch → push into `conflicts` list with `dimension='stale_card'`. Regression test: mutate canon by one byte, assert bundler surfaces stale flag.

**Alerting (ALERT-01 / ALERT-02):**
- **D-12:** Telegram alert backbone = the existing `claude-config/telegram-channel` skill's bot. Hard-block condition taxonomy: `['spend_cap_exceeded', 'regen_stuck_loop', 'rubric_conflict', 'voice_drift_over_threshold', 'checkpoint_sha_mismatch', 'vllm_health_failed', 'stale_cron_detected', 'mode_b_exhausted']`. New module `src/book_pipeline/alerts/telegram.py` with `class TelegramAlerter` + `send_alert(condition: str, detail: dict) -> None`.
- **D-13:** Dedup + cooldown = in-memory per-alerter LRU keyed on `(condition, scene_id_or_chapter_num)` with 1h TTL. Persistence = `runs/alert_cooldowns.json` (gitignored) read at `__init__`, written after every successful send. Detail-dict whitelist at send time (no secrets). Rate-limit on Telegram API surface (5 req/min local limit, well under API limit).
- **D-14:** Stale-cron detector = `book-pipeline check-cron-freshness` CLI inspecting `runs/events.jsonl` last-cron-run timestamp. >36h old → emit hard-block alert. Runs as its own openclaw cron at 08:00 daily (independent of nightly loop to avoid self-silencing).

**Orchestration (ORCH-01):**
- **D-15:** Nightly cron = single openclaw cron at 02:00 America/Los_Angeles: `book-pipeline nightly-run --max-scenes 10`. Persistent via `~/.openclaw/cron/jobs.json`. Gateway-token gate deferred from Phase 2 — documented prerequisite operator action; cron registration skill `book-pipeline openclaw register-cron --nightly` emits clear "needs `OPENCLAW_GATEWAY_TOKEN`" message if unset.
- **D-16:** Nightly run CLI composes: (a) vllm-bootstrap (SHA-verify + lora-load); (b) `/scene` loop until buffer filled or max-scenes reached; (c) trigger chapter DAG if buffer full; (d) emit completion Event. On any HARD_BLOCK: Telegram alert + STOP (don't cascade). Exit codes: 0 scene-loop-progressed, 2 vllm-bootstrap-failed, 3 hard-block-fired, 4 max-scenes-reached-with-no-progress.

**SQLite Metric Ledger (OBS-02):**
- **D-17:** Ledger at `runs/metrics.sqlite3` (gitignored; rebuildable from events.jsonl per OBS-02 idempotency). Schema: one row per (event_id, axis) with `scene_id, chapter_num, attempt_number, score, severity, mode_tag, voice_fidelity, cost_usd, ts_iso`. Ingester `book-pipeline ingest-events` scans events.jsonl tail-ward since last persisted event_id. Schema-version column for OBS-04 migration. LanceDB not used — SQLite adequate + stdlib-only.

### Claude's Discretion

- Python module shape for `alerts/` kernel package (likely single-file per ADR-004).
- Exact spend-cap USD-per-token pricing table structure (Opus 4.7 pricing locked in `config/pricing.yaml`).
- Exact regex / parsing shape for `CriticIssue.location` → scene_id (defensive int-cast like chapter path sanitization).
- Specific Telegram message template text.

### Deferred Ideas (OUT OF SCOPE for Phase 5)

- Mode-B voice-sample selection rule refinement (contrasting sample genres per scene type) — Phase 6 ablation TEST-03.
- Sonnet 4.6 fallback for cost-sensitive Mode-B — Phase 6 ablation TEST-03 variant.
- Multi-tier alert routing (hard-block → Telegram, warning → email digest, info → ledger only) — v1 Telegram-only.
- Anthropic Batch API for nightly Mode-B regens — Phase 6 cost optimization.
- Cross-machine cron resilience (run-lock, dual-host) — single-host v1.

## Project Constraints (from CLAUDE.md)

- **No vLLM serving during build** — don't boot local-inference mid-build; co-resident FT process can OOM GB10. Research-time + test-time paths must mock vLLM. (Memory-pinned.)
- **GSD Workflow Enforcement:** file-changing tools only inside a GSD command (`/gsd-plan-phase`, `/gsd-execute-phase`).
- **TDD cadence** — atomic commits per task (RED commit → GREEN commit), precedent locked on every Phase 1-4 plan.
- **Kernel discipline (ADR-004):** new kernel packages `alerts/` + `regenerator/oscillation/` + (if split) `spend_tracker/` land book-domain-free. Import-linter contract 1 + 2 extended at plan-start per Plan 04-01 precedent.
- **Clone-not-abstract (ADR-004):** `ModeBDrafter` clones `ModeADrafter`; `TelegramAlerter` clones event-emitter shape; nightly orchestrator clones `ChapterDagOrchestrator` composition.
- **Observability-is-load-bearing (ADR-003):** every LLM call emits one OBS-01 Event. Error paths emit BEFORE raising. Mode-B cache key is byte-identical prefix — preserved `_system_blocks` list.
- **`uv` packaging** — `pyproject.toml` `[tool.importlinter.contracts]` extended each plan; `scripts/lint_imports.sh` mypy target list extended; dev deps already include tenacity + anthropic + python-json-logger. No new project deps expected except possibly `requests` or `httpx` for Telegram HTTP — **httpx is already a dep** (reuse).
- **Human involvement < 1 touch/scene** — Telegram alerts on hard-block only; weekly digest is the review surface (Phase 6).

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DRAFT-03 | Mode-B drafter uses Anthropic SDK (Opus 4.7) with voice samples in-context + prompt caching `ttl="1h"`; per-scene opt-in; mode="B" in event log | § Standard Stack + Code Examples (Mode-B drafter pattern); § Anthropic prompt cache semantics |
| DRAFT-04 | Structurally complex beats pre-flagged for Mode-B by default; demotion to Mode-A via config | § Standard Stack (config/mode_preflags.yaml + preflag reader) |
| REGEN-02 | Max-iteration R-cap per scene + per-scene spend cap enforces frontier-cost ceiling during Mode-B | § Code Examples (SpendTracker pattern); § Pricing Table |
| REGEN-03 | After R Mode-A failures, controller auto-escalates to Mode-B; escape event logged with triggering issue IDs | § Architecture Patterns (escalation event shape) |
| REGEN-04 | Stuck-loop detector flags when scene oscillates between failure modes; hard-block alert instead of continuing | § Architecture Patterns (oscillation detector pure function) |
| LOOP-01 | Scene loop runs end-to-end autonomously: request → RAG → Drafter → Critic → (PASS/FAIL/EXHAUST/BLOCK); ≤1 human-touch per scene | § Architecture Patterns (extended `cli/draft.py` state machine) |
| ORCH-01 | Nightly cron via `openclaw cron add` at 02:00 kicks scene-loop; gateway systemd user unit; persistent state across reboots | § Standard Stack (openclaw cron semantics); § Environment Availability |
| ALERT-01 | Hard-block conditions emit Telegram alerts via existing channel | § Standard Stack (python-telegram-bot or raw httpx); § Code Examples |
| ALERT-02 | Alert deduplication + cool-down prevents alert storms; re-alert after 1 hour | § Code Examples (LRU cooldown pattern); § Architecture Patterns |
| **Deferred SC4** | Surgical scene-kick routing on CHAPTER_FAIL — CriticIssue→scene_id mapping + per-scene state reset | § Code Examples (location regex); § Don't Hand-Roll (reuse Plan 03-07 `_SCENE_ID_RE`) |
| **Deferred SC6** | Bundler stale-card flag — comparing `EntityCard.source_chapter_sha` against current canon chapter SHA | § Code Examples (git SHA lookup); § Common Pitfalls (git perf) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anthropic` | `>=0.96.0,<0.97` (already pinned) | Mode-B drafter + existing critic/extractor/retrospective | Locked Phase 3; `messages.create` for free-text prose (Mode-B doesn't need `.parse` — it returns prose, not JSON); `cache_control.ttl="1h"` verified supported without beta header [VERIFIED: platform.claude.com/docs/en/build-with-claude/prompt-caching] |
| `httpx` | `>=0.27` (already pinned) | Telegram Bot API HTTP client | Already in project deps (vLLM client); reusing avoids adding `python-telegram-bot` (heavyweight async framework we don't need) |
| `tenacity` | `>=9.0` (already pinned) | Retry on Anthropic transient errors (reuse Plan 03-05 pattern: 5× exponential, `APIConnectionError` + `APIStatusError`); Telegram retries on 429 `retry_after` | Clone the ModeADrafter/SceneCritic tenacity config verbatim [VERIFIED: codebase grep] |
| Python stdlib `sqlite3` | 3.40+ (stdlib) | OBS-02 metric ledger | Zero-dep; schema is flat; `INSERT ... ON CONFLICT(event_id) DO NOTHING` for idempotent ingest [VERIFIED: sqlite.org/lang_upsert.html] |
| `python-json-logger` | `>=3.0` (already pinned) | JSONL events (already landed Phase 1) | Reused — no new config needed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pyyaml` | `>=6.0` (already pinned) | Load `config/voice_samples.yaml` + `config/mode_preflags.yaml` + `config/pricing.yaml` | New YAML config files parsed same way as existing four |
| `pydantic` | `>=2.10` (already pinned) | `PreflagConfig`, `PricingConfig`, `AlertCooldownRecord` Pydantic models; `VoiceSamplesConfig` | Standard pattern — every config has a typed loader per FOUND-02 |
| `pydantic-settings` | `>=2.7` (already pinned) | Typed loading of new config files (`PricingConfig`, etc.) | Reuse existing `YamlConfigSettingsSource` pattern from Plan 01-03 |
| `jinja2` | `>=3.1` (already pinned) | Mode-B prompt template `drafter/templates/mode_b.j2` with `===SYSTEM=== / ===USER===` sentinels (paraphrase of Mode-A template per ADR-004) | Clone Mode-A template shape; add voice-samples block + preflag reason block |
| `xxhash` | `>=3.0` (already pinned) | Cache-key fingerprint + event_id hashing (already live) | Reuse |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `httpx` POST to Telegram | `python-telegram-bot` v21+ (async) | PTB is a full bot framework with update polling we don't need. We only `sendMessage`. `httpx.post("https://api.telegram.org/bot{TOKEN}/sendMessage", ...)` is ~20 lines vs. a 40-dep framework. [ASSUMED: PTB dep weight ~40 transitive; httpx is already in tree] |
| Stdlib `sqlite3` | `sqlite-utils` (Datasette's wrapper) | sqlite-utils is lovely DX but adds a dep. Our ingester is one `INSERT ... ON CONFLICT ... DO NOTHING` loop — stdlib is fine. [VERIFIED: sqlite-utils.datasette.io/en/stable/python-api.html — sqlite-utils would be `db["events"].insert_all(rows, pk="event_id", ignore=True)`] |
| Per-hit `git rev-list` for stale-card | Batch per-chapter by caching chapter→SHA dict for the bundle | Bundle queries ≤5 entity_state hits across at most ~30 distinct chapters. Cache HEAD once per bundle + use `git rev-list -1 HEAD -- canon/chapter_{NN:02d}.md` per unique chapter — O(distinct-chapters) shell-outs, ~60ms each [VERIFIED via local `time` measurement]. Naive per-hit = 5 × 60ms = 300ms; batched = 1-5 × 60ms. Either is acceptable for a per-scene-level op; batched preferred if retriever trivially returns multiple entity_state hits per scene. |
| Python `dict` LRU for alert cooldowns | `functools.lru_cache` | `lru_cache` is for pure functions. Alert cooldowns need TTL, not hit-count eviction. Plain dict + time check on read is simpler + persistable to JSON. |

**Installation:** No new project dependencies. All listed libraries already in `pyproject.toml` `[project.dependencies]`. Only config files + new kernel packages.

**Version verification:**
```bash
# Verified 2026-04-23 — already-pinned versions are current
grep -E '(anthropic|tenacity|httpx|pydantic|pyyaml)' /home/admin/Source/our-lady-book-pipeline/pyproject.toml
# → anthropic>=0.96.0,<0.97   tenacity>=9.0   httpx>=0.27   pydantic>=2.10   PyYAML>=6.0
```

## Architecture Patterns

### Recommended Project Structure (ADDITIONS ONLY — existing tree preserved)

```
src/book_pipeline/
├── drafter/
│   ├── mode_b.py                  # NEW — clones mode_a.py shape
│   ├── preflag.py                 # NEW — pure is_preflagged() function + loader
│   └── templates/
│       └── mode_b.j2              # NEW — Mode-B Jinja2 prompt template
├── regenerator/
│   ├── scene_local.py             # EXISTING — Plan 03-06
│   ├── oscillation.py             # NEW — pure detector over Event list
│   └── spend_tracker.py           # NEW — per-scene USD accumulator (or inline in cli/draft.py)
├── alerts/                        # NEW kernel package
│   ├── __init__.py
│   ├── telegram.py                # TelegramAlerter class + send_alert()
│   ├── cooldown.py                # LRU + persistence to runs/alert_cooldowns.json
│   └── taxonomy.py                # HARD_BLOCK_CONDITIONS list + templates
├── observability/
│   ├── event_logger.py            # EXISTING
│   ├── ledger.py                  # NEW — SQLite ingester (OBS-02)
│   └── pricing.py                 # NEW — token→USD conversion (pure)
├── cli/
│   ├── draft.py                   # EXISTING — EXTENDED with preflag + oscillation + escalation
│   ├── nightly_run.py             # NEW — ORCH-01 composition
│   ├── curate_voice_samples.py    # NEW — Mode-B voice-samples curation CLI
│   ├── check_cron_freshness.py    # NEW — D-14 stale-cron detector
│   ├── ingest_events.py           # NEW — OBS-02 idempotent JSONL→SQLite
│   └── register_cron.py           # NEW — openclaw cron registration helper
└── book_specifics/
    └── voice_samples.py           # NEW — paths/constants for Mode-B samples curation

config/
├── mode_thresholds.yaml           # EXISTING — additive keys regen.r_cap_mode_a + regen.spend_cap_usd_per_scene
├── mode_preflags.yaml             # NEW — preflagged_beats list
├── voice_samples.yaml             # NEW — curated 3-5 passages (written by curate CLI)
└── pricing.yaml                   # NEW — Opus 4.7 + Sonnet 4.6 USD/MTok tables

runs/
├── events.jsonl                   # EXISTING — Phase 5 adds role='mode_escalation', 'scene_kick', 'mode_b_drafter', 'telegram_alert'
├── alert_cooldowns.json           # NEW — gitignored; LRU state
└── metrics.sqlite3                # NEW — OBS-02 ledger
```

### Pattern 1: Mode-B Drafter (clone of ModeADrafter)

**What:** Mirror the `ModeADrafter` 14-step pipeline but swap vLLM for Anthropic Opus 4.7 and add voice-samples prefix with cache_control.

**When to use:** Always the same codepath — Mode-B is triggered by the scene loop (preflag, R-exhaust, oscillation, spend-cap) and uses the identical contract (`DraftRequest → DraftResponse`).

**Example shape:**
```python
# Source: paraphrase of drafter/mode_a.py structure — do NOT copy verbatim
# (ADR-004 clone-not-abstract; paraphrase shared helpers)
class ModeBDrafter:
    mode: str = "B"

    def __init__(
        self,
        *,
        anthropic_client: Any,           # build_llm_client(mode_thresholds_cfg.critic_backend)
        event_logger: EventLogger | None,
        voice_pin: VoicePinData,
        voice_samples: list[str],        # curated 400-600-word passages (D-03)
        model_id: str = "claude-opus-4-7",
        max_tokens: int = 3072,
        temperature: float = 0.7,
        prompt_template_path: Path | None = None,
    ) -> None:
        ...
        # Pre-render the voice-samples "system" block ONCE; preserve the SAME
        # list object across review() calls so Anthropic's cache hits
        # (byte-identical prefix). Mirrors SceneCritic._system_blocks pattern.
        samples_text = "\n\n---\n\n".join(voice_samples)
        self._system_blocks = [
            {
                "type": "text",
                "text": f"<voice_samples>\n{samples_text}\n</voice_samples>\n{VOICE_DESCRIPTION}\n{RUBRIC_AWARENESS}",
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ]

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _call_opus_inner(self, *, messages: list[dict[str, Any]]) -> Any:
        from anthropic import APIConnectionError, APIStatusError
        try:
            return self.anthropic_client.messages.create(
                model=self.model_id,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self._system_blocks,      # ← cached 1h ephemeral
                messages=messages,               # user prompt: scene_request + RAG pack
            )
        except (APIConnectionError, APIStatusError):
            raise  # tenacity retries
```

Key design rules:
1. **`_system_blocks` preserved across calls** — cache hits require byte-identical prefix [VERIFIED: platform.claude.com/docs/en/build-with-claude/prompt-caching — "Cache hits require 100% identical prompt segments"].
2. **Use `messages.create` NOT `.parse`** — Mode-B returns free-text prose, not structured JSON. Matches the SceneLocalRegenerator pattern (Plan 03-06).
3. **`mode="B"` on DraftResponse + Event** — scene loop sees the mode tag; B-3 invariant (voice_pin_sha preservation) stays intact.
4. **`voice_pin_sha` passthrough** — For a B-drafted scene, `DraftResponse.voice_pin_sha` = `voice_pin.checkpoint_sha` (the pinned FT checkpoint). This is the lineage record, NOT a claim that the B draft came from the FT model. Chapter frontmatter B-3 invariant keeps `checkpoint_sha == voice_pin_sha` so downstream reindex / assembly doesn't break.
5. **ModeBDrafterBlocked exception class** — mirrors `ModeADrafterBlocked` for scene-loop routing.

### Pattern 2: Oscillation Detector (pure function over Event trail)

**What:** Stateless inspection of the Event list to decide if the scene is oscillating.

**When to use:** Called at each regen attempt boundary inside `cli/draft.py::run_draft_loop`.

**Example shape:**
```python
# src/book_pipeline/regenerator/oscillation.py
def detect_oscillation(
    critic_events: list[Event],
    *,
    min_history: int = 2,
) -> tuple[bool, frozenset[tuple[str, str]] | None]:
    """Pure function — compare attempt N and attempt N-2 axis+severity sets.

    Args:
        critic_events: sequence of role='critic' events for one scene, ordered
          oldest→newest. Each event's extra.severities is {axis: severity_str}.
        min_history: require at least this many attempts before firing.

    Returns:
        (fired, repeated_tuples) where repeated_tuples is the set of
        (axis, severity) tuples that matched between N and N-2.
    """
    if len(critic_events) < min_history:
        return False, None
    # D-07: compare attempts N and N-2 (not N and N-1).
    # attempts N-1 could still be "bouncing through the axis space"; N vs N-2
    # confirms we returned to the same failure.
    latest = _extract_axis_severity_set(critic_events[-1])
    two_back = _extract_axis_severity_set(critic_events[-3]) \
        if len(critic_events) >= 3 else frozenset()
    common = latest & two_back
    # Fire only on HIGH/MID — LOW severities not worth escalating
    significant = frozenset((a, s) for a, s in common if s in ("mid", "high"))
    if significant:
        return True, significant
    return False, None
```

Oscillation is a **signal, not a gate** — fires on match + history >= 2. Attempt 1 cannot oscillate (no prior). Attempt 2 cannot oscillate per D-07 (needs N and N-2).

### Pattern 3: Spend Tracker + Pricing Lookup

**What:** Per-scene cumulative USD counter that reads from Event `input_tokens + cached_tokens + output_tokens`.

**When to use:** Called at each attempt boundary; compared against `mode_thresholds.regen.spend_cap_usd_per_scene`.

**Example shape:**
```python
# src/book_pipeline/observability/pricing.py  (pure kernel)
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class ModelPricing:
    """USD per 1_000_000 tokens. Source: config/pricing.yaml."""
    input_usd_per_mtok: float          # Opus 4.7: 5.0
    output_usd_per_mtok: float         # Opus 4.7: 25.0
    cache_read_usd_per_mtok: float     # Opus 4.7: 0.50 (= 10% of input)
    cache_write_1h_usd_per_mtok: float # Opus 4.7: 10.0 (= 2× input)
    cache_write_5m_usd_per_mtok: float # Opus 4.7: 6.25 (= 1.25× input)

def event_cost_usd(
    event: Event,
    pricing_by_model: Mapping[str, ModelPricing],
) -> float:
    """Convert one Event's token counts into USD. Zero if model unknown."""
    pricing = pricing_by_model.get(event.model)
    if pricing is None:
        return 0.0
    # NOTE: we don't separate cache writes from non-cached inputs at Event grain
    # because Phase 1 Event schema has input_tokens (uncached) + cached_tokens
    # (cache reads). Cache WRITES are a separate concept not on the Event.
    uncached_input = event.input_tokens
    cached_reads = event.cached_tokens
    output = event.output_tokens
    return (
        uncached_input * pricing.input_usd_per_mtok
        + cached_reads * pricing.cache_read_usd_per_mtok
        + output * pricing.output_usd_per_mtok
    ) / 1_000_000.0
```

**Caveat:** Cache-write tokens are charged at 2x input (1h) but the Phase 1 Event schema (FROZEN) does NOT distinguish write-tokens from read-tokens — it has `input_tokens` (uncached) and `cached_tokens` (reads). Cache writes billed at write rate are buried in `input_tokens`. For spend-cap purposes we accept this approximation (slight underestimate on cache-write calls, meaningless over many calls). Phase 6 OBS-04 could add `cache_creation_input_tokens` as an optional field if needed.

### Pattern 4: Telegram Alerter with LRU Cooldown

**What:** Send Telegram message on hard-block conditions; suppress duplicates within 1h window per (condition, scope).

**When to use:** Called from the scene-loop wrapper and the nightly CLI on any HARD_BLOCKED state transition.

**Example shape:**
```python
# src/book_pipeline/alerts/telegram.py
import time
from collections import OrderedDict

import httpx

HARD_BLOCK_CONDITIONS = frozenset([
    "spend_cap_exceeded",
    "regen_stuck_loop",
    "rubric_conflict",
    "voice_drift_over_threshold",
    "checkpoint_sha_mismatch",
    "vllm_health_failed",
    "stale_cron_detected",
    "mode_b_exhausted",
])

class TelegramAlerter:
    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        cooldown_path: Path,
        cooldown_ttl_s: int = 3600,   # 1h per ALERT-02
        event_logger: EventLogger | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.cooldown_path = Path(cooldown_path)
        self.cooldown_ttl_s = cooldown_ttl_s
        self.event_logger = event_logger
        # Load persisted cooldowns; prune expired at load time.
        self._cooldowns: OrderedDict[tuple[str, str], float] = self._load_cooldowns()

    def send_alert(self, condition: str, detail: dict) -> bool:
        """Return True if alert was actually sent (False = deduped in cooldown).

        detail dict is whitelisted: only keys in ALLOWED_DETAIL_KEYS appear in
        the Telegram payload (no secrets per T-05-alert mitigation).
        """
        assert condition in HARD_BLOCK_CONDITIONS, f"unknown: {condition}"
        scope = detail.get("scene_id") or detail.get("chapter_num") or "global"
        key = (condition, str(scope))
        now = time.time()
        last = self._cooldowns.get(key)
        if last is not None and (now - last) < self.cooldown_ttl_s:
            return False  # deduped
        # Construct message (terse, with unblock hint per <specifics>)
        text = self._format(condition, detail)
        # POST https://api.telegram.org/bot{token}/sendMessage
        # See § Code Examples for tenacity retry on 429 with retry_after
        self._post_with_retry(text)
        self._cooldowns[key] = now
        self._persist_cooldowns()
        if self.event_logger is not None:
            self._emit_event(condition, detail, scope)
        return True
```

Key design rules:
1. **Cooldown key = `(condition, scene_or_chapter)` not just `condition`** — two different scenes blowing their spend cap in the same hour are two distinct alerts.
2. **Persistence via atomic tmp+rename** — reuse `_persist()` pattern from `cli/draft.py` Plan 03-07.
3. **Rate-limit compliance:** Telegram API limits are 1 msg/sec per chat, 30 msg/sec global [VERIFIED: gramio.dev/rate-limits + core.telegram.org/bots/faq]. Our 5 req/min local cap (D-13) is well under; 429 response carries `retry_after` seconds — tenacity respects it.
4. **Event emission on alert send** — `role='telegram_alert'` with `extra={condition, scope, message_length, deduped: False}`. On dedup-suppression, emit with `deduped: True` + no network call.

### Pattern 5: Scene-Loop Extension (LOOP-01 + D-09)

**What:** Extend `cli/draft.py::run_draft_loop` with preflag check, oscillation check, spend-cap check, Mode-B escalation path.

**When to use:** Every scene drafted via the full scene loop.

**Extension points (surgical — preserve existing state machine):**
```python
# cli/draft.py::run_draft_loop — add BEFORE the for-attempt loop:
if preflag.is_preflagged(scene_id, composition_root.preflag_set):
    # D-08 — emit mode_escalation with trigger='preflag'
    _emit_mode_escalation(event_logger, scene_id, 'A', 'B', 'preflag', [])
    # Jump directly to Mode-B branch — skip Mode-A entirely.
    return _run_mode_b_attempt(...)

# Inside the for-attempt loop, after critic returns FAIL:
# 1. Oscillation check
critic_events = _read_critic_events_for_scene(event_logger, scene_id)
fired, common = detect_oscillation(critic_events)
if fired:
    _emit_mode_escalation(event_logger, scene_id, 'A', 'B', 'oscillation', list(common))
    return _run_mode_b_attempt(...)

# 2. Spend-cap check
all_scene_events = _read_events_for_scene(event_logger, scene_id)
spent = sum(event_cost_usd(e, pricing) for e in all_scene_events)
if spent >= spend_cap:
    _emit_mode_escalation(event_logger, scene_id, 'A', 'A', 'spend_cap_exceeded', [])
    record = transition(record, SceneState.HARD_BLOCKED, 'spend_cap_exceeded')
    alerter.send_alert('spend_cap_exceeded', {'scene_id': scene_id, 'spent_usd': spent})
    return 4

# 3. R-cap exhausted → Mode-B (existing R>=max+1 branch)
if attempt >= max_regen + 1:
    _emit_mode_escalation(event_logger, scene_id, 'A', 'B', 'r_cap_exhausted', [...])
    return _run_mode_b_attempt(...)
```

### Pattern 6: Surgical Scene-Kick (Phase 4 SC4 — D-10)

**What:** On `CHAPTER_FAIL`, parse `CriticResponse.issues[].location` for `ch{NN}_sc{II}` references; reset only those scenes' state records to `PENDING`.

**When to use:** Inside `ChapterDagOrchestrator._step1_canon` when chapter critic returns `overall_pass=False`.

**Regex + int-cast (paraphrase of Plan 03-07 `_SCENE_ID_RE`):**
```python
# chapter_assembler/dag.py or new chapter_assembler/scene_kick.py
import re
from book_pipeline.interfaces.types import CriticResponse, SceneState

_SCENE_REF_RE = re.compile(r"\bch(\d+)_sc(\d+)\b")

def extract_implicated_scene_ids(response: CriticResponse) -> tuple[set[str], list[str]]:
    """Return (implicated_scene_ids, non_specific_issues).

    implicated_scene_ids: canonical ch{NN:02d}_sc{II:02d} strings.
    non_specific_issues: issue.claim strings for issues that cite no scene.
    """
    scenes: set[str] = set()
    non_specific: list[str] = []
    for issue in response.issues:
        matches = _SCENE_REF_RE.findall(issue.location or "")
        if not matches and issue.evidence:
            # Defensive: some critics cite ch/sc in the evidence field.
            matches = _SCENE_REF_RE.findall(issue.evidence)
        if matches:
            for ch_str, sc_str in matches:
                # Defensive int-cast — matches Plan 04-04 path sanitization
                # (chapter_num from int cast) and Plan 03-07 _parse_scene_id.
                ch, sc = int(ch_str), int(sc_str)
                scenes.add(f"ch{ch:02d}_sc{sc:02d}")
        else:
            non_specific.append(issue.claim)
    return scenes, non_specific

def kick_implicated_scenes(
    implicated: set[str],
    state_dir: Path,
    event_logger: EventLogger | None,
    chapter_num: int,
    issue_refs: list[str],
) -> None:
    """Reset each implicated scene's SceneStateRecord to PENDING.

    Scenes NOT in `implicated` retain their COMMITTED state.
    Emits ONE role='scene_kick' Event per chapter invocation.
    """
    for scene_id in sorted(implicated):
        state_path = state_dir / f"ch{chapter_num:02d}" / f"{scene_id}.state.json"
        if not state_path.exists():
            continue
        record = SceneStateRecord.model_validate_json(state_path.read_text())
        record = transition(record, SceneState.PENDING, f"scene_kick from ch{chapter_num}_fail")
        _persist(record, state_path)
    # Emit event AFTER all kicks to avoid partial-kick Event observability
    if event_logger is not None:
        _emit_scene_kick_event(event_logger, implicated, chapter_num, issue_refs)
```

**Key:** Only scenes whose IDs appear in issue.location get kicked. Non-specific issues (chapter-level critique, e.g., "arc pacing too fast") bubble up as CHAPTER_FAIL terminal — no scene kick, alert operator.

### Pattern 7: Bundler Stale-Card Flag (Phase 4 SC6 — D-11)

**What:** At bundle time, for each entity_state hit, compare the card's `source_chapter_sha` against the current canon chapter's git SHA.

**When to use:** Inside `ContextPackBundlerImpl._run_one_retriever` for the entity_state retriever only, OR as a post-retrieval step on the 5 retrievals dict before conflict detection.

**Example shape (batched per unique chapter):**
```python
# rag/bundler.py — extension in _run_one_retriever (entity_state path) or new helper
import subprocess
from functools import lru_cache

@lru_cache(maxsize=128)
def _git_sha_for_chapter(chapter_num: int, repo_root: Path) -> str | None:
    """Return git SHA of latest commit touching canon/chapter_{NN:02d}.md, or None."""
    path = f"canon/chapter_{chapter_num:02d}.md"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "-1", "HEAD", "--", path],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

def scan_for_stale_cards(
    entity_state_result: RetrievalResult,
    repo_root: Path,
) -> list[ConflictReport]:
    """Compare each entity_state hit's source_chapter_sha against current canon."""
    stale: list[ConflictReport] = []
    for hit in entity_state_result.hits:
        card_sha = hit.metadata.get("source_chapter_sha")
        chapter = hit.metadata.get("chapter")   # last_seen_chapter
        if card_sha is None or chapter is None:
            continue
        current_sha = _git_sha_for_chapter(int(chapter), repo_root)
        if current_sha is None or current_sha == card_sha:
            continue
        stale.append(ConflictReport(
            entity=hit.chunk_id,
            dimension="stale_card",
            severity="mid",
            values_by_retriever={
                "entity_state.card_sha": card_sha,
                "canon.head_sha": current_sha,
            },
        ))
    return stale
```

**Performance:** `lru_cache` gives us per-bundle-call memoization — 5 hits across 3 distinct chapters = 3 git calls × ~60ms = 180ms added latency. Phase 4 bundle() baseline was ~30s (RAG + BGE reranker) so the overhead is negligible. The `entity_state` retriever's reindex (Plan 04-04) already stamps `source_chapter_sha` into card JSON — needs one-line extension in `_card_to_row` to propagate into the LanceDB metadata column (not yet there).

### Anti-Patterns to Avoid

- **Don't subclass `ModeADrafter`** — per ADR-004 clone-not-abstract. Two concretes, both satisfy `Drafter` Protocol. Paraphrase shared strings (`VOICE_DESCRIPTION`, `RUBRIC_AWARENESS`); DO NOT import Mode-A from Mode-B.
- **Don't put the Mode-B cache_control on the user message** — if the user prompt (scene_request + RAG pack) is inside the cache block, the cache NEVER hits (every scene differs). Voice samples go in the SYSTEM block, scene-specific content goes in MESSAGES.
- **Don't use `messages.parse()` for Mode-B drafting** — Mode-B produces prose, not structured JSON. `.parse()` on raw prose is a type mismatch. Use `.create()` with tenacity retry (clone Plan 03-06 pattern).
- **Don't put per-call state on the alerter** — `TelegramAlerter` instance is reused across the whole nightly run; cooldowns persist to disk between runs. A per-call instance defeats 1h cooldown.
- **Don't run scene_kick on chapter-level issues** — if `issue.location` has no `ch{NN}_sc{II}` reference, that's a chapter-global issue and needs full-chapter action (redraft or hard-block), not scene-kick.
- **Don't fire stale-card flag on every retriever hit** — only `entity_state` hits carry `source_chapter_sha`. Other retrievers (`historical`, `metaphysics`, `arc_position`, `negative_constraint`) read from immutable corpus files.
- **Don't mix Opus 4.7 pricing from `openclaw.json`** — that file has **outdated** pricing ($15/$75). The authoritative number is $5/$25 per MTok [VERIFIED: platform.claude.com/docs/en/about-claude/pricing]. Ship `config/pricing.yaml` with correct numbers; flag the `openclaw.json` drift in COMPLETION notes for operator follow-up.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Telegram API client | Async bot framework + polling loop | `httpx.post()` with tenacity retry | We only `sendMessage`; PTB is 30+ deps for a single endpoint |
| Cache-key hashing for Mode-B | `hashlib.sha256` loop over sub-blocks | **Just preserve `_system_blocks` list object across calls** | Anthropic compares byte-identical prefixes; as long as the list object stays the same Python reference, the serialization is byte-identical [VERIFIED: platform.claude.com/docs/en/build-with-claude/prompt-caching] |
| Regex for scene_id parsing | New regex from scratch | Reuse `_SCENE_ID_RE = re.compile(r"^ch(\d+)_sc(\d+)$")` from `cli/draft.py` + **widen** to `\bch(\d+)_sc(\d+)\b` for scene-kick (location strings aren't anchored at start) | Existing precedent; defensive int-cast already in place |
| Time-based LRU for cooldowns | Custom eviction loop with timer threads | **Plain dict + TTL check on read + periodic prune on write** | No concurrency (single-process scene loop); dict suffices; persist to JSON on every successful send |
| SQLite upsert for OBS-02 | `SELECT then INSERT` or `INSERT OR IGNORE` | `INSERT INTO events ... ON CONFLICT(event_id) DO NOTHING` (SQLite >= 3.24) | `INSERT OR IGNORE` ignores on ANY constraint violation; ON CONFLICT targets just the event_id PK [VERIFIED: sqlite.org/lang_upsert.html] |
| Cron scheduling | systemd timer | **`openclaw cron add` (already the project standard)** | ORCH-01 constraint; openclaw owns Gateway session + jobs.json persistence + delivery channel [VERIFIED: docs.openclaw.ai/automation/cron-jobs + local /home/admin/.npm-global/lib/node_modules/openclaw/docs/automation/cron-jobs.md] |
| Git SHA lookup cache | Fresh `subprocess.run` per hit | **`@lru_cache` per-bundle call** keyed on `(chapter_num, repo_root)` | Simplest; bundles are short-lived so cache auto-expires with scope |
| Cost-of-tokens conversion | Inline math in spend-cap check | **Pure `event_cost_usd(event, pricing)` function** in `observability/pricing.py` | Testable in isolation; reused by Phase 6 digest |

**Key insight:** Phase 5 is almost entirely **composition of existing pieces** + **two new kernel packages** (`alerts/`, maybe `observability/ledger.py`). The Mode-B drafter is a clone of Mode-A. The nightly CLI is a clone of the chapter CLI composition root. The spend-cap check is a pure function. The alerting module is a single file. The only genuine novelty is the oscillation detector (16 lines of pure function) and the openclaw cron registration helper.

## Runtime State Inventory

Phase 5 introduces new runtime state that the planner must account for:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **NEW:** `runs/metrics.sqlite3` — OBS-02 ledger; rebuildable from events.jsonl (idempotent ingest). **NEW:** `runs/alert_cooldowns.json` — alerter LRU state; lost = alerts re-fire once. **EXISTING:** `runs/events.jsonl` (append-only, no migration needed; new event roles added). **EXISTING:** `drafts/scene_buffer/**/*.state.json` (D-10 scene-kick mutates some to PENDING). | Gitignore `runs/metrics.sqlite3` + `runs/alert_cooldowns.json`. Scene-kick state writes use existing `_persist` atomic tmp+rename. |
| Live service config | **Telegram bot:** chat_id + bot_token in env (operator sets before nightly run; the existing `claude-config/telegram-channel` skill owns the token). **openclaw gateway:** `OPENCLAW_GATEWAY_TOKEN` env var must be set for `openclaw cron add` — Plan 01-04 flagged this as deferred [VERIFIED: src/book_pipeline/openclaw/bootstrap.py line 108]. | Nightly-run CLI must `raise` with actionable message when any of `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `OPENCLAW_GATEWAY_TOKEN` are unset. `register-cron` CLI emits clear prerequisite message on missing gateway token per D-15. |
| OS-registered state | **NEW:** `~/.openclaw/cron/jobs.json` will carry 2 new entries after registration: `book-pipeline:nightly-run` (02:00 PT) + `book-pipeline:check-cron-freshness` (08:00 PT). These persist across reboots [VERIFIED: openclaw docs + `ls ~/.openclaw/cron/`]. **EXISTING:** `~/.openclaw/cron/jobs.json` already has `book-pipeline:nightly-ingest` from Phase 2. | Nightly-run registration CLI: `openclaw cron add --name book-pipeline:nightly-run --cron "0 2 * * *" --tz America/Los_Angeles --session isolated --agent drafter --message "book-pipeline nightly-run --max-scenes 10"`. Idempotency: check `openclaw cron list` before adding to avoid duplicates. |
| Secrets/env vars | `ANTHROPIC_API_KEY` (used today by critic), `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (new), `OPENCLAW_GATEWAY_TOKEN` (new for cron registration). All three read by composition root; no secrets in committed files. | Composition root reads at `__init__`; fail fast if missing. Document in `workspaces/nightly-runner/BOOT.md`. |
| Build artifacts / installed packages | **No new packages** — all deps already in `pyproject.toml`. No compiled binaries, no global installs. | None. |

**Canonical question:** *After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?* — No rename/refactor in Phase 5, so no stale runtime state. However, the `openclaw.json` pricing drift is noted in the canonical-refs section for operator follow-up (NOT blocking).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.12 | All code | ✓ (project pinned) | 3.12 | — |
| `anthropic>=0.96.0,<0.97` | Mode-B drafter | ✓ (pyproject) | 0.96.x | — |
| `httpx>=0.27` | Telegram POST | ✓ (pyproject) | 0.27.x | — |
| `tenacity>=9.0` | Anthropic + Telegram retry | ✓ (pyproject) | 9.x | — |
| `sqlite3` (stdlib) | OBS-02 ledger | ✓ (stdlib) | 3.40+ | — |
| `git` CLI | Stale-card SHA lookup (D-11) | ✓ (system) | 2.x | Skip stale-card flag; log warning (card falls through as non-stale) |
| `openclaw` CLI | Cron registration | ✓ (`/home/admin/.npm-global/bin/openclaw`) | 2026.4.5 | Fallback: commit job to `openclaw/cron_jobs.json` (precedent: Plan 02-06 during Phase 2 when gateway token was missing) |
| `OPENCLAW_GATEWAY_TOKEN` | Cron registration call | ✗ — explicitly deferred per Plan 01-04 | — | Fallback: emit actionable error; operator runs `openclaw auth setup` before re-invoking `register-cron` |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | `TelegramAlerter` | Unknown — need operator to verify Telegram skill configured | — | Fallback: nightly run prints to stderr + writes alert as role='telegram_alert' Event with `extra={delivery: 'stdout_fallback'}` when tokens unset; does NOT hard-fail the run |
| vLLM service (port 8002) | Mode-A drafter (nightly run may draft Mode-A scenes before Mode-B escapes) | Unknown — operator responsibility per Phase 3 precedent | — | Fallback: `book-pipeline vllm-bootstrap --start` embedded as step (a) of nightly run per D-16; exit 2 on failure |
| Anthropic API (`api.anthropic.com`) | Mode-B drafter + critic + extractor + retrospective | Runtime-dependent (network + API key) | — | Fallback: existing tenacity 5× retry; hard-block alert on exhaustion |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `OPENCLAW_GATEWAY_TOKEN` (documented prerequisite; cron commits to `openclaw/cron_jobs.json` as Phase 2 precedent); Telegram env vars (stdout fallback — alerts go to log, operator sees on manual log inspection).

## Common Pitfalls

### Pitfall 1: Mode-B Cache Misses on Every Call

**What goes wrong:** Voice samples are included in the user message or the system block differs per call. Every Mode-B draft pays full 2× write cost + input cost; no cache reads.

**Why it happens:**
- Putting scene-specific content (RAG pack, scene_request) BEFORE the cache_control breakpoint
- Mutating the `_system_blocks` list between calls (e.g., appending a timestamp, re-rendering the template)
- Creating a fresh dict on every `__init__` → Python object equality fails at byte-level serialization

**How to avoid:**
- Pre-render the voice-samples block ONCE at `__init__` (mirror `SceneCritic.__init__` pattern [VERIFIED: src/book_pipeline/critic/scene.py:168-175])
- Preserve the SAME list object across `draft()` calls (assign to `self._system_blocks`, use by reference)
- Place `cache_control` on the voice-samples block, which is the LAST cached block before the scene-specific user message
- Test: assert `id(self._system_blocks) == id(self._system_blocks)` at second call time

**Warning signs:** Event `cached_tokens` is always 0 on Mode-B events; cost grows linearly with attempt count.

### Pitfall 2: Oscillation False Positives on Fresh Issues

**What goes wrong:** Detector compares raw axis+severity lists, not "same failure mode." A new mid-historical issue in attempt 3 + a different mid-historical issue in attempt 1 match and trigger escalation prematurely.

**Why it happens:** `(axis, severity)` is too-coarse a fingerprint. The CriticIssue's `claim` differs between attempts even if `(axis='historical', severity='mid')` matches.

**How to avoid:** Per CONTEXT.md D-07, the detector uses the axis+severity tuple deliberately — "same axis-severity mode twice" is the oscillation signal. The rationale: regen is supposed to FIX the identified axis issue. If it keeps failing the same axis at the same severity after regen, the Mode-A reach has genuinely run out — escalate. This IS the intended semantic; guard against reading it as "same issue."

**Warning signs:** Mode-B escape rate >40% on early scenes (normal range per research is 20-30% in Act 1). If we over-escape, tighten to `(axis, severity, claim_hash)` in a thesis 005-style experiment.

### Pitfall 3: Telegram 429 Retry Storms

**What goes wrong:** On transient 429, naive retry loops hammer the API immediately; hit a longer 429; hit another; bot-token gets temporarily banned.

**Why it happens:** Telegram's 429 response carries a `retry_after` seconds field — retrying before that window is itself a rate-limit violation [VERIFIED: gramio.dev/rate-limits + github.com/tdlib/td/issues/3034].

**How to avoid:**
- Parse the 429 response body for `parameters.retry_after`
- tenacity `wait_` that reads the exception's attribute: `wait=wait_fixed(lambda exc: getattr(exc, 'retry_after', 1))`
- Fallback floor: even if `retry_after` is missing, wait at least 1s (matches Telegram's per-chat 1 msg/sec limit)

**Warning signs:** Alerts silently fail during a storm; bot token gets rejected by server for ~24h.

### Pitfall 4: SQLite Ingester Re-Reads events.jsonl from Byte 0 Every Run

**What goes wrong:** Ingester fully rescans events.jsonl on every invocation. Idempotency via `ON CONFLICT DO NOTHING` saves correctness but wastes I/O — after 1000 cron runs, each invocation parses + skips 100k+ rows.

**Why it happens:** OBS-02 requires idempotency; naive pattern is "scan all + upsert." Works but slow.

**How to avoid:**
- Track last ingested offset in a sidecar file `runs/metrics.sqlite3.last_offset` (atomic tmp+rename)
- Seek to that byte offset on next invocation
- After partial failure (crash mid-ingest), offset stays stale → rescan from last successful offset → dedup via `ON CONFLICT`
- This is "tail-ward since last persisted event_id" per D-17, implemented as byte-offset since file is append-only

**Warning signs:** Ingester wall-time grows linearly with events.jsonl size; weekly digest cron stretches past window.

### Pitfall 5: `openclaw.json` Pricing Drift

**What goes wrong:** Operator or automation reads pricing from `cron_jobs.json` (which is the openclaw gateway config, NOT our spend-tracker source of truth). Spend cap fires 3× too early (thinks $0.75 hit at $0.25 of actual spend).

**Why it happens:** The repo's `cron_jobs.json` was authored during Phase 2 before Opus 4.7 pricing was confirmed. It carries `$15/$75 per MTok` for `claude-opus-4-7` but actual Opus 4.7 pricing is $5/$25 [VERIFIED: platform.claude.com/docs/en/about-claude/pricing fetched 2026-04-23].

**How to avoid:**
- Ship `config/pricing.yaml` as the SINGLE SOURCE OF TRUTH for spend-cap conversion
- In Phase 5 pre-task, open an issue or add a note to ROADMAP to fix `cron_jobs.json` in Phase 6 cleanup (non-blocking)
- `observability/pricing.py::event_cost_usd` takes `ModelPricing` as injected parameter — never reads `openclaw.json`
- Add a sanity-check test: `config/pricing.yaml::opus-4-7.input_usd_per_mtok == 5.0` asserted in test suite

**Warning signs:** Scenes hard-block on spend cap after only 1-2 Mode-B attempts (expected budget: 2-3 attempts); critic + Mode-B combined spend seems to consume $0.75 in under a minute.

### Pitfall 6: Stale-Card Scanner Runs Outside a Git Repo

**What goes wrong:** Nightly run launched from a `tmp_path` or test harness where `git rev-list` returns non-zero. Bundler either crashes or silently treats every card as stale (dimension='stale_card' conflict on every hit).

**Why it happens:** `subprocess.run(["git", "rev-list", ...])` exits non-zero if not in a git repo or the file path doesn't exist.

**How to avoid:**
- `scan_for_stale_cards()` catches `CalledProcessError` + returns `None` (card treated as non-stale, log warning)
- Integration test: nightly-run in tmp_path with `git init` happens first OR stale-card scanner is skipped via `is_git_repo()` gate
- Production note: this is a "degrade gracefully" behavior, NOT a silent failure — the warning log is load-bearing for operator visibility

**Warning signs:** Integration test fails with "conflict on every entity_state hit"; actual nightly cron produces thousands of spurious conflicts.

### Pitfall 7: Scene-Kick Corrupts Already-Committed Scene File

**What goes wrong:** Kicking a scene resets its SceneStateRecord → PENDING, but the `drafts/ch{NN}/{scene_id}.md` file stays on disk. Next scene-loop invocation sees PENDING + existing md → either overwrites silently or fails on exists-check.

**Why it happens:** SceneStateRecord and the committed markdown file are two independent pieces of state; resetting only one breaks the pair's invariant.

**How to avoid:** Per CONTEXT.md `<specifics>` line: *"sc01 + sc03 scene markdown files in drafts/ch01/ stay valid for next assembly"* — but the KICKED scene's md SHOULD be archived before reset. Plan should specify: on kick, move `drafts/ch{NN}/{scene_id}.md` to `drafts/ch{NN}/archive/{scene_id}_rev{K}.md` where K is the next free integer. State record reset proceeds after archive.

**Warning signs:** After a kick + re-draft, the committed chapter md contains both the old and new versions of the scene; or re-draft crashes on "file already exists."

## Code Examples

### Mode-B drafter __init__ with cache_control (paraphrase of Mode-A + SceneCritic patterns)

```python
# src/book_pipeline/drafter/mode_b.py — key initialization fragment
# Source: paraphrase of src/book_pipeline/drafter/mode_a.py:164-205
#       + src/book_pipeline/critic/scene.py:168-175 cache pattern
from __future__ import annotations
from pathlib import Path
from typing import Any

import jinja2

from book_pipeline.config.voice_pin import VoicePinData
from book_pipeline.interfaces.event_logger import EventLogger

VOICE_DESCRIPTION = (
    "You write in clean declarative prose with em-dash rhythm, numeric "
    "specificity in sensory description, and structural asides that sharpen "
    "rather than decorate. ..."    # paraphrase from mode_a.py, don't copy
)

class ModeBDrafter:
    mode: str = "B"

    def __init__(
        self,
        *,
        anthropic_client: Any,
        event_logger: EventLogger | None,
        voice_pin: VoicePinData,
        voice_samples: list[str],               # ≥3 curated 400-600-word passages
        model_id: str = "claude-opus-4-7",
        max_tokens: int = 3072,
        temperature: float = 0.7,
        prompt_template_path: Path | None = None,
    ) -> None:
        self.anthropic_client = anthropic_client
        self.event_logger = event_logger
        self.voice_pin = voice_pin
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Validate voice samples non-empty + within 400-600-word target per D-03
        if not voice_samples or len(voice_samples) < 3:
            raise RuntimeError(
                f"Mode-B requires >=3 curated voice samples; got {len(voice_samples)}"
            )
        for i, s in enumerate(voice_samples):
            wc = len(s.split())
            if not (300 <= wc <= 700):   # slight slack around 400-600 target
                raise RuntimeError(
                    f"voice_sample[{i}] word_count={wc}; expect 400-600 range"
                )

        # Pre-render the voice-samples prefix ONCE. This string is the
        # byte-identical prefix for cache hits across every draft() call.
        samples_text = "\n\n---\n\n".join(voice_samples)
        prefix = (
            f"{VOICE_DESCRIPTION}\n\n"
            f"<voice_samples>\n{samples_text}\n</voice_samples>\n\n"
            "Draft the scene described in the user message in this voice."
        )
        # _system_blocks list is the SAME object across review() calls — byte
        # identical content + same Python reference → Anthropic cache hits.
        self._system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": prefix,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            },
        ]

        # Jinja2 template for the USER message shape (scene-specific content)
        template_path = prompt_template_path or (
            Path(__file__).parent / "templates" / "mode_b.j2"
        )
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_path.parent)),
            autoescape=False, trim_blocks=True, lstrip_blocks=True,
        )
        self._template = self._env.get_template(template_path.name)
```

### Anthropic messages.create with cache_control (Opus 4.7)

```python
# src/book_pipeline/drafter/mode_b.py — call shape inside draft()
# Source: docs/en/build-with-claude/prompt-caching + existing scene_critic pattern
import tenacity
from anthropic import APIConnectionError, APIStatusError

@tenacity.retry(
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def _call_opus_inner(self, *, user_message: str) -> Any:
    try:
        return self.anthropic_client.messages.create(
            model=self.model_id,        # "claude-opus-4-7"
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=self._system_blocks,  # voice-samples + cache_control 1h
            messages=[{"role": "user", "content": user_message}],
        )
    except (APIConnectionError, APIStatusError):
        raise  # tenacity retries

# Usage extract from response:
resp = self._call_opus_inner(user_message=rendered_user)
scene_text = resp.content[0].text
usage = resp.usage
tokens_in = usage.input_tokens           # uncached input
cached_tokens = usage.cache_read_input_tokens  # cache hits on voice-samples
tokens_out = usage.output_tokens
```

### Telegram sendMessage with 429 retry_after handling

```python
# src/book_pipeline/alerts/telegram.py — POST helper
# Source: core.telegram.org/bots/api + gramio.dev/rate-limits verified 2026-04-23
import httpx, tenacity

class TelegramRetryAfter(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after

class TelegramPermanentError(Exception):
    pass

def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, (TelegramRetryAfter, httpx.TransportError))

@tenacity.retry(
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=30),
    retry=tenacity.retry_if_exception(_is_retryable),
    reraise=True,
)
def _post_message(self, text: str) -> dict:
    url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
    try:
        r = httpx.post(
            url,
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "MarkdownV2",
                "disable_notification": False,   # hard-block → notify
            },
            timeout=10.0,
        )
        if r.status_code == 429:
            # parameters.retry_after per Telegram Bot API spec
            retry_after = r.json().get("parameters", {}).get("retry_after", 1)
            raise TelegramRetryAfter(int(retry_after))
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        # 4xx other than 429 → permanent (bad token, bad chat_id) — don't retry
        if 400 <= exc.response.status_code < 500:
            raise TelegramPermanentError(str(exc)) from exc
        raise
```

### CriticIssue.location → scene_id (Phase 4 SC4 surgical kick)

```python
# src/book_pipeline/chapter_assembler/scene_kick.py
# Source: paraphrase of cli/draft.py _SCENE_ID_RE pattern, widened for embedded matches
import re

# NOTE: widened from `^ch(\d+)_sc(\d+)$` (cli/draft.py line 61, strict whole-string)
# to `\bch(\d+)_sc(\d+)\b` because CriticIssue.location contains free-text
# descriptions like "mid-paragraph 2 of ch01_sc02; Cortés's horse line".
_SCENE_REF_RE = re.compile(r"\bch(\d+)_sc(\d+)\b")
```

### SQLite idempotent ingest (OBS-02 D-17)

```python
# src/book_pipeline/observability/ledger.py
# Source: sqlite.org/lang_upsert.html + D-17 schema shape
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT NOT NULL,
    axis         TEXT NOT NULL DEFAULT '',
    scene_id     TEXT,
    chapter_num  INTEGER,
    attempt_number INTEGER,
    score        REAL,
    severity     TEXT,
    mode_tag     TEXT,
    voice_fidelity REAL,
    cost_usd     REAL,
    ts_iso       TEXT NOT NULL,
    role         TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    PRIMARY KEY (event_id, axis)
);
CREATE INDEX IF NOT EXISTS idx_events_ts_iso ON events(ts_iso);
CREATE INDEX IF NOT EXISTS idx_events_scene ON events(scene_id);
CREATE INDEX IF NOT EXISTS idx_events_chapter ON events(chapter_num);
CREATE TABLE IF NOT EXISTS schema_meta (
    version_int  INTEGER PRIMARY KEY,
    applied_at   TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_meta (version_int, applied_at)
    VALUES (1, CURRENT_TIMESTAMP);
"""

UPSERT_SQL = """
INSERT INTO events (event_id, axis, scene_id, chapter_num, attempt_number,
                    score, severity, mode_tag, voice_fidelity, cost_usd,
                    ts_iso, role, schema_version)
VALUES (:event_id, :axis, :scene_id, :chapter_num, :attempt_number,
        :score, :severity, :mode_tag, :voice_fidelity, :cost_usd,
        :ts_iso, :role, :schema_version)
ON CONFLICT(event_id, axis) DO NOTHING
"""

def init_schema(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

def ingest_event_rows(db_path: Path, rows: list[dict]) -> int:
    """Idempotent bulk upsert. Returns number of NEW rows inserted."""
    if not rows:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.executemany(UPSERT_SQL, rows)
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return after - before
    finally:
        conn.close()
```

### openclaw cron registration (D-15)

```python
# src/book_pipeline/cli/register_cron.py
# Source: docs.openclaw.ai/automation/cron-jobs + local
#   /home/admin/.npm-global/lib/node_modules/openclaw/docs/automation/cron-jobs.md
import os
import subprocess

def register_nightly_cron() -> int:
    if "OPENCLAW_GATEWAY_TOKEN" not in os.environ:
        print(
            "Error: OPENCLAW_GATEWAY_TOKEN not set. Run `openclaw auth setup` "
            "then re-run `book-pipeline register-cron --nightly`.",
            file=sys.stderr,
        )
        return 2
    # Idempotency: check existing list first
    existing = subprocess.run(
        ["openclaw", "cron", "list"], capture_output=True, text=True, check=True,
    )
    if "book-pipeline:nightly-run" in existing.stdout:
        print("Nightly cron already registered — nothing to do.")
        return 0
    result = subprocess.run([
        "openclaw", "cron", "add",
        "--name", "book-pipeline:nightly-run",
        "--cron", "0 2 * * *",
        "--tz", "America/Los_Angeles",
        "--session", "isolated",
        "--agent", "drafter",
        "--message", "book-pipeline nightly-run --max-scenes 10",
    ], check=False)
    return result.returncode
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|---------------|--------|
| Anthropic 5-min ephemeral cache only | 1-hour ephemeral TTL via `cache_control.ttl="1h"` | Long available by 2026-04; `ttl` field is stable in messages API [VERIFIED: platform.claude.com/docs/en/build-with-claude/prompt-caching] | 2× write cost (vs 1.25× for 5m) but 10% read cost across the full hour — pays off after 2 cache reads |
| Organization-level cache isolation | Workspace-level cache isolation | 2026-02-05 [VERIFIED: platform.claude.com/docs/en/build-with-claude/prompt-caching] | Single-workspace API key (openclaw + our pipeline share one Anthropic workspace per CONTEXT.md D-02) means all Mode-B calls hit the same cache — confirmed compatible with our single-key model |
| openclaw `--system-event` + `--session-agent` flags | `--message` + `--session isolated` + `--agent <name>` | Some time prior to 2026.4.5; Plan 02-06 caught the flag-rename and corrected | ORCH-01 nightly registration uses the corrected flags; `--system-event` is for `--session main` jobs only (not isolated) |
| Opus 4.6 ($5/$25) | Opus 4.7 ($5/$25 unchanged headline; new tokenizer uses up to 35% more tokens for same text) | 2026-04 [VERIFIED: platform.claude.com/docs/en/about-claude/pricing + finout.io/blog/claude-opus-4.7-pricing] | Effective cost per fixed-input-prose is 0-35% higher on Opus 4.7 vs 4.6. Spend-cap $0.75 per scene should budget for the ceiling — count on 1.35× multiplier when sizing sample sets |
| Telegram per-token flood limits | Per-chat `retry_after` values (layer 167, Feb 2025) | Feb 2025 [VERIFIED: gramio.dev/rate-limits] | Our 5 req/min per-scene-alert rate is well under per-chat 1 msg/sec; cooldown design correct |

**Deprecated/outdated:**
- `--system-event` flag for isolated cron jobs (use `--message` instead per openclaw 2026.4.5 docs).
- `INSERT OR IGNORE` for idempotent upsert (works but hides OTHER constraint violations; prefer `ON CONFLICT(event_id) DO NOTHING` since SQLite 3.24).
- Single-org cache isolation — switched to workspace-scoped 2026-02-05.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `python-telegram-bot` transitive deps are ~30-40 packages; `httpx` already in tree | Alternatives Considered | Low — even if PTB is only 5 deps, `httpx.post` is genuinely simpler for sendMessage-only use case |
| A2 | `openclaw` gateway will honor `--session isolated` + `--agent drafter` combo (we already have `workspaces/drafter/`) | openclaw cron pattern | Medium — if gateway requires a dedicated `workspaces/nightly-runner/`, plan must land it. CONTEXT.md D-15 already flags this as needed |
| A3 | Opus 4.7 effective-token-multiplier is ~1.0-1.35× over fixed prose (not 2-3×) | Pricing Table | Low — pricing page explicitly quotes this range; we sample-test by running 3 scene drafts through both the Anthropic SDK `count_tokens` and our pricing sum |
| A4 | Mode-B voice-samples at 400-600 words × 3-5 passages = ~1800-3000 words ≈ ~2500-4000 tokens; fits in 1 cache breakpoint out of 4 | Standard Stack + Pricing | Low — even at 1.35× multiplier ceiling 5400 tokens; Opus context window 200k; 4-breakpoint limit [VERIFIED] is ample |
| A5 | Nightly cron's `--max-scenes 10` cap prevents runaway; chapter DAG is NOT rate-limited (fires only when scene buffer fills) | ORCH-01 / D-15 | Low — CONTEXT.md specifically says "chapter assembly + DAG remain unrate-limited." Operator sets max lower if budget stretches |
| A6 | `lru_cache` + per-chapter memoization is correct scope for stale-card SHA lookup (per-bundle scope, clears on GC) | Pattern 7 | Medium — if `ContextPackBundlerImpl` is long-lived (not instantiated per bundle), the `lru_cache` would persist across requests and miss new commits. Safer: explicit dict on bundle() scope |
| A7 | `git rev-list -1 HEAD -- path` returns the same SHA that the entity extractor wrote into `source_chapter_sha` (both read from current HEAD after canon commit) | Pattern 7 | Low — Plan 04-03 entity extractor uses `chapter_sha` passed from DAG step 1 which is the commit SHA (`git rev-parse HEAD` after `canon(chXX): commit`). `git rev-list -1 HEAD -- canon/chapter_XX.md` finds the most recent commit touching that file = the canon commit. Match confirmed |
| A8 | Scene-kick archival pattern (move to `drafts/ch{NN}/archive/{scene_id}_rev{K}.md`) is consistent with Phase 4 chapter state model | Pitfall 7 | Medium — Phase 4 does NOT archive on kick because scene-kick was deferred. Plan must decide archive policy; alternative is overwrite-in-place (less safe, loses history) |
| A9 | `cache_creation_input_tokens` absence from Phase 1 Event schema causes ≤5% spend-cap underestimate (cache writes are 2× input) | Pattern 3 | Low — Mode-B voice-samples block is ~3000 tokens; written once per hour × 2 hours per night × 10 scenes = 60k cache-write tokens × 2× = 120k token-equivalents ÷ 10 scenes = 12k/scene; at 0.000005 $/token = $0.06/scene — well under the $0.75 cap. Acceptable approximation. Phase 6 OBS-04 can extend schema |

**Confirmation needed before execution (to discuss-phase or planner):**
- A2: verify a new `workspaces/nightly-runner/` is needed or `workspaces/drafter/` suffices for the nightly cron `--agent` arg.
- A8: confirm archive-on-kick policy; document in plan's Success Criteria.

## Open Questions

1. **Does the Anthropic SDK auto-inject a cache breakpoint for system prompts, consuming 1 of the 4 breakpoints?**
   - What we know: docs say automatic caching uses 1 of 4 slots. Mode-B has 1 explicit breakpoint (voice-samples block), so 3 remain.
   - What's unclear: whether SDK version 0.96 auto-injects in addition to our explicit breakpoint, potentially hitting 400 error if 4 explicit + 1 auto.
   - Recommendation: verify at plan-time with a targeted Context7 query `mcp__context7__query-docs anthropic "cache_control breakpoint"`; fall back to single explicit breakpoint without relying on auto-caching (D-02 doesn't require auto).

2. **Does `openclaw cron add` with `--session isolated` require a dedicated workspace or can it reuse `workspaces/drafter/`?**
   - What we know: isolated sessions run in `cron:<jobId>` (fresh session per run). `--agent drafter` selects which agent's workspace markdown to use.
   - What's unclear: whether agent selection requires a dedicated `workspaces/nightly-runner/` (per CONTEXT.md code_context line 116) or if `drafter` is appropriate.
   - Recommendation: land `workspaces/nightly-runner/` with AGENTS/SOUL/BOOT per wipe-haus-state pattern (CONTEXT.md code_context line 116) — tiny cost, clean separation.

3. **How do we test the Mode-B cache-hit behavior without a real Anthropic key during CI?**
   - What we know: Plan 03-05 tests SceneCritic with FakeAnthropicClient. Same pattern works for Mode-B.
   - What's unclear: how to assert cache-hit semantics (cached_tokens > 0) in tests without real network.
   - Recommendation: unit tests use `FakeAnthropicClient` that accepts messages + system and returns a hand-crafted response with `usage.cache_read_input_tokens=42`; assert the drafter's Event reflects that value. Integration tests (Plan 05-XX similar to 03-08) use real Anthropic for one smoke scene — pinned to a manual invoke since we can't spend during CI.

4. **If the operator's Telegram bot is offline (network error), does the nightly run proceed or halt?**
   - What we know: D-13 says "rate-limit on Telegram API surface (5 req/min)" but doesn't specify failure-mode behavior.
   - What's unclear: soft-fail (log only) vs hard-fail (block scene).
   - Recommendation: soft-fail. Alerter returns `False` on send failure; composition root logs + emits `role='telegram_alert'` event with `extra={delivery: 'failed', error: ...}` so the weekly digest can surface undelivered alerts. Hard-block would defeat the "no silent wedges" property — Telegram offline means the operator can't be paged, but the pipeline already halted on HARD_BLOCKED state and the event log is the backup channel.

5. **How does the nightly run detect "max-scenes reached with no progress" vs "all scenes committed successfully"?**
   - What we know: D-16 specifies exit codes (0 progressed, 4 max-reached-no-progress).
   - What's unclear: the distinction between "drafted 10 scenes all COMMITTED" (good) and "tried 10 but all HARD_BLOCKED" (bad) — both hit --max-scenes.
   - Recommendation: exit 0 if ≥1 scene reached COMMITTED state this run; exit 4 if --max-scenes hit but zero progress. Plan must encode this explicitly in the CLI loop wrapper.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8 + pytest-asyncio (already in dev deps) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` (registers `slow` marker) |
| Quick run command | `uv run pytest -m "not slow"` |
| Full suite command | `uv run pytest` (includes slow markers + real LLM paths if creds set) |
| Phase gate | `bash scripts/lint_imports.sh` green (import-linter + ruff + mypy) + `uv run pytest -m "not slow"` green |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|---------------|
| DRAFT-03 | Mode-B drafter satisfies Drafter Protocol; returns DraftResponse with `mode='B'` | unit | `uv run pytest tests/drafter/test_mode_b.py::test_protocol_conformance -x` | ❌ Wave 0 — new file |
| DRAFT-03 | Mode-B `_system_blocks` list object preserved across draft() calls (cache identity) | unit | `uv run pytest tests/drafter/test_mode_b.py::test_system_blocks_identity -x` | ❌ Wave 0 |
| DRAFT-03 | cache_control.ttl='1h' on voice-samples block | unit | `uv run pytest tests/drafter/test_mode_b.py::test_cache_control_on_system -x` | ❌ Wave 0 |
| DRAFT-03 | Tenacity retries 5× on APIConnectionError + raises ModeBDrafterBlocked on exhaust | unit | `uv run pytest tests/drafter/test_mode_b.py::test_tenacity_exhaustion -x` | ❌ Wave 0 |
| DRAFT-03 | Emits exactly ONE role='drafter' Event with mode='B' per draft() call | unit | `uv run pytest tests/drafter/test_mode_b.py::test_single_event_per_call -x` | ❌ Wave 0 |
| DRAFT-04 | Preflag CLI check routes ch01_b1_beat01 to Mode-B before Mode-A attempt | integration | `uv run pytest tests/integration/test_scene_loop_preflag.py -x` | ❌ Wave 0 |
| DRAFT-04 | `is_preflagged("ch99_b1_beat01", {"ch99_b1_beat01"})` is True; deterministic | unit | `uv run pytest tests/drafter/test_preflag.py -x` | ❌ Wave 0 |
| REGEN-02 | R-cap=3 enforced; attempt_number=4 triggers escalation | unit | `uv run pytest tests/cli/test_draft_r_cap.py::test_exhaust_triggers_mode_b -x` | ⚠️ extend existing cli/test_draft_cli.py |
| REGEN-02 | Spend-cap $0.75 fires HARD_BLOCKED + alert | integration | `uv run pytest tests/integration/test_scene_loop_spend_cap.py -x` | ❌ Wave 0 |
| REGEN-02 | `event_cost_usd(event, pricing)` pure-function conversion correctness | unit | `uv run pytest tests/observability/test_pricing.py -x` | ❌ Wave 0 |
| REGEN-03 | R-exhaust → mode_escalation event written ONCE with trigger='r_cap_exhausted' | unit | `uv run pytest tests/cli/test_draft_escalation.py::test_r_exhaust_single_event -x` | ❌ Wave 0 |
| REGEN-04 | `detect_oscillation` pure: 2 identical axis+severity → True; 1 match → False; fresh → False | unit | `uv run pytest tests/regenerator/test_oscillation.py -x` | ❌ Wave 0 |
| REGEN-04 | Scene loop wraps oscillation detection → mode_escalation event with trigger='oscillation' | integration | `uv run pytest tests/integration/test_scene_loop_oscillation.py -x` | ❌ Wave 0 |
| LOOP-01 | Full scene loop: preflag OR Mode-A OR R-cap OR oscillation OR spend-cap each reach terminal state | integration | `uv run pytest tests/integration/test_scene_loop_all_branches.py -x` | ❌ Wave 0 |
| ORCH-01 | `book-pipeline nightly-run --max-scenes 10` drives scene-loop, emits nightly_run Event | integration | `uv run pytest tests/cli/test_nightly_run.py -x` | ❌ Wave 0 |
| ORCH-01 | `register-cron --nightly` idempotent: second call detects existing and exits 0 | integration | `uv run pytest tests/cli/test_register_cron.py -x` | ❌ Wave 0 |
| ALERT-01 | `TelegramAlerter.send_alert("spend_cap_exceeded", ...)` posts with expected payload | unit | `uv run pytest tests/alerts/test_telegram.py::test_send -x` | ❌ Wave 0 |
| ALERT-01 | 429 response with retry_after=5 triggers tenacity wait 5s → second attempt succeeds | unit | `uv run pytest tests/alerts/test_telegram.py::test_429_retry -x` | ❌ Wave 0 |
| ALERT-02 | Second alert within 1h for same (condition, scope) returns False (deduped); cooldowns persisted | unit | `uv run pytest tests/alerts/test_cooldown.py -x` | ❌ Wave 0 |
| ALERT-02 | Persisted cooldowns survive alerter restart (re-init from `runs/alert_cooldowns.json`) | integration | `uv run pytest tests/alerts/test_cooldown_persistence.py -x` | ❌ Wave 0 |
| **SC4 (deferred)** | `extract_implicated_scene_ids` parses "ch01_sc02" from issue.location; "no ch reference" case → non_specific | unit | `uv run pytest tests/chapter_assembler/test_scene_kick.py::test_extract -x` | ❌ Wave 0 |
| **SC4 (deferred)** | Chapter-fail with 1 issue citing ch99_sc02 → only sc02 resets to PENDING; sc01 + sc03 stay COMMITTED | integration | `uv run pytest tests/integration/test_chapter_fail_surgical_kick.py -x` | ❌ Wave 0 |
| **SC6 (deferred)** | Mutate canon/chapter_99.md byte; entity_state retriever+bundler surface conflict dimension='stale_card' | integration | `uv run pytest tests/integration/test_stale_card_flag.py -x` | ❌ Wave 0 |
| OBS-02 | `INSERT ... ON CONFLICT(event_id, axis) DO NOTHING` idempotent: 2 ingest runs on same events.jsonl yield same row count | unit | `uv run pytest tests/observability/test_ledger.py::test_idempotent_ingest -x` | ❌ Wave 0 |
| OBS-02 | Ledger schema migration: schema_version column exists; future schema-bump migration path documented | unit | `uv run pytest tests/observability/test_ledger.py::test_schema_meta -x` | ❌ Wave 0 |
| D-14 | `check-cron-freshness`: events.jsonl tail has no nightly_run Event in 36h → exit 3 + alert | integration | `uv run pytest tests/cli/test_check_cron_freshness.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -m "not slow" -x` — full non-slow suite; each task's RED then GREEN commit gates the plan's advance.
- **Per wave merge:** `bash scripts/lint_imports.sh && uv run pytest -m "not slow"` — lint gate + full non-slow suite.
- **Phase gate:** `bash scripts/lint_imports.sh && uv run pytest -m "not slow"` green + one manual real-smoke `book-pipeline draft ch01_sc01 --force-mode-b` against real Anthropic (ANTHROPIC_API_KEY set) — equivalent to Plan 03-08 for Mode-A.

### Wave 0 Gaps

- [ ] `tests/drafter/test_mode_b.py` — ~8-12 tests: protocol conformance, cache identity, tenacity, error events, word-count drift preservation, voice_samples validation. **Blocks every DRAFT-03 plan.**
- [ ] `tests/drafter/test_preflag.py` — ~3 tests: pure function, YAML loading, empty-set behavior. **Blocks DRAFT-04.**
- [ ] `tests/regenerator/test_oscillation.py` — ~5 tests: history<2 returns False, 2-match returns True, low-severity only returns False, 3-back comparison, empty event list. **Blocks REGEN-04.**
- [ ] `tests/observability/test_pricing.py` + `test_ledger.py` — ~6 tests: USD conversion edge cases (cached_tokens=0, model unknown), idempotent ingest, schema migration. **Blocks OBS-02 / REGEN-02 spend-cap.**
- [ ] `tests/alerts/test_telegram.py` + `test_cooldown.py` — ~8 tests: POST shape, 429+retry_after, 4xx permanent error, cooldown dedup, persistence. **Blocks ALERT-01/02.**
- [ ] `tests/chapter_assembler/test_scene_kick.py` — ~5 tests: regex extraction, non-specific, PENDING reset, archive pattern, event emission. **Blocks deferred SC4.**
- [ ] `tests/integration/test_scene_loop_*.py` — 5 sibling tests covering each escape branch (preflag, r_cap, oscillation, spend_cap, all_committed). Clone `test_chapter_dag_end_to_end.py` fixture pattern (tmp_path + git + MockLLMClient). **Blocks LOOP-01 + ORCH-01 E2E.**
- [ ] `tests/cli/test_nightly_run.py` + `test_register_cron.py` + `test_check_cron_freshness.py` — ~8 tests across these. **Blocks ORCH-01 + D-14.**
- [ ] `tests/conftest.py` extension: new shared fixtures for `FakeAnthropicClient` with `cache_read_input_tokens` control, `FakeTelegramAPI` httpx mock, `pricing_fixture` loading stub `config/pricing.yaml`. (Existing conftest already has `FakeEventLogger` + `MockLLMClient`.) **Cross-cutting.**

**Framework install:** None — pytest already installed + configured; no new dev deps.

## Sources

### Primary (HIGH confidence)

- **Anthropic prompt caching docs** — [platform.claude.com/docs/en/build-with-claude/prompt-caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — fetched 2026-04-23; verified cache_control.ttl per-block, workspace isolation 2026-02-05, 4-breakpoint limit, `cache_read_input_tokens` field name, byte-identical prefix requirement.
- **Anthropic pricing page** — [platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing) — fetched 2026-04-23; Opus 4.7: $5 input / $25 output / $10 cache write 1h / $0.50 cache read / $6.25 cache write 5m; new tokenizer 1.0-1.35× multiplier.
- **openclaw cron docs (local 2026.4.5)** — `/home/admin/.npm-global/lib/node_modules/openclaw/docs/automation/cron-jobs.md` — read 2026-04-23; jobs.json persistence, --session isolated + --message flags, America/Los_Angeles tz, --stagger semantics.
- **openclaw online cron docs** — [docs.openclaw.ai/automation/cron-jobs](https://docs.openclaw.ai/automation/cron-jobs) — fetched 2026-04-23 for cross-verification with local; isolated-vs-main-session semantics, OPENCLAW_GATEWAY_TOKEN not referenced in cron docs but confirmed via bootstrap.py in-repo grep.
- **SQLite UPSERT spec** — [sqlite.org/lang_upsert.html](https://sqlite.org/lang_upsert.html) — SQLite 3.24+ ON CONFLICT clause; INSERT OR IGNORE gotcha on non-PK constraints.
- **Existing codebase** — `src/book_pipeline/drafter/mode_a.py`, `critic/scene.py`, `regenerator/scene_local.py`, `chapter_assembler/dag.py`, `cli/draft.py`, `rag/bundler.py`, `rag/reindex.py` — all read 2026-04-23 for pattern paraphrase.
- **Local git performance benchmark** — `time git -C /home/admin/Source/our-lady-book-pipeline rev-list -1 HEAD -- README.md` = 57ms real; 5-hit bundle = ~300ms naive or ~60-180ms batched.

### Secondary (MEDIUM confidence — verified against multiple sources)

- **Telegram Bot API rate limits** — [gramio.dev/rate-limits](https://gramio.dev/rate-limits) + [grammy.dev/advanced/flood](https://grammy.dev/advanced/flood) + [core.telegram.org/bots/faq](https://core.telegram.org/bots/faq) + [tdlib/td#3034](https://github.com/tdlib/td/issues/3034) — cross-referenced across 4 sources: 1 msg/sec per chat, 30 msg/sec global, 429 carries `retry_after` (per-chat since layer 167 Feb 2025).
- **Opus 4.7 tokenizer change** — [finout.io/blog/claude-opus-4.7-pricing](https://www.finout.io/blog/claude-opus-4.7-pricing-the-real-cost-story-behind-the-unchanged-price-tag) — new-tokenizer 1.0-1.35× multiplier claim; cross-verified against Anthropic pricing page Note box.

### Tertiary (LOW confidence — needs validation during planning/execution)

- **`python-telegram-bot` dep count ~30-40 transitive** — [A1 assumption] no tool verification; derived from package-tree exploration experience. Risk acceptable because we're using httpx regardless.
- **A2: workspaces/nightly-runner/ vs workspaces/drafter/ agent selection** — unverified without running openclaw cron add in dry-run mode. Resolve at plan time by inspecting wipe-haus-state workspace layout.

## Metadata

**Confidence breakdown:**

- **Standard stack:** HIGH — all libraries already in pyproject.toml + pinned versions; zero new deps.
- **Anthropic Mode-B integration:** HIGH — cache_control, `messages.create`, `cache_read_input_tokens` verified against 2026-04-23 docs fetch; `_system_blocks` identity pattern proven in existing `SceneCritic`.
- **Telegram integration:** MEDIUM-HIGH — rate limits cross-verified 4 sources; 429 retry semantics verified; message-format details (MarkdownV2) well-known.
- **openclaw cron:** HIGH — local docs v2026.4.5 read directly; flags confirmed against working Phase 2 precedent (ingest cron); OPENCLAW_GATEWAY_TOKEN env-var gate verified in codebase.
- **SQLite ledger:** HIGH — sqlite.org canonical; ON CONFLICT since 3.24 (long stable); Python stdlib sqlite3 is straightforward.
- **Pricing table:** HIGH — official Anthropic pricing page; flagged the outdated `cron_jobs.json` drift as operator follow-up (not blocking).
- **Git stale-card lookup:** HIGH — local benchmark confirms ~60ms/call; `lru_cache` pattern well-understood.
- **Scene-kick regex:** HIGH — reuses existing `_SCENE_ID_RE` pattern from cli/draft.py with documented widening.
- **Oscillation detector:** HIGH — pure function over Event list; semantic locked in CONTEXT.md D-07; 16-line implementation.
- **Preflag + voice-samples curation:** MEDIUM — curator CLI shape echoes Plan 03-02 anchor curator (ANALYTIC + ESSAY + NARRATIVE balance) but the 400-600-word target is a deliberate deviation; validate with a sample curation during P5a plan Wave 1.

**Research date:** 2026-04-23

**Valid until:** 2026-05-23 for Anthropic pricing/caching docs (fast-moving); 2026-07-23 for openclaw 2026.4.5 (stable version); indefinite for SQLite/git/regex patterns (language-stable).
