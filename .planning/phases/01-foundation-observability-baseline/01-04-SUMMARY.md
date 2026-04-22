---
phase: 01-foundation-observability-baseline
plan: 04
subsystem: orchestration
tags: [openclaw, cron, drafter, gateway, cli, bootstrap, phase1-stub]
dependency_graph:
  requires:
    - phase: 01-foundation-observability-baseline/01
      provides: "CLI dispatcher + SUBCOMMAND_IMPORTS extension point (openclaw_cmd pre-listed)"
  provides:
    - "openclaw.json at repo root (port 18790, vLLM baseUrl http://127.0.0.1:8002/v1)"
    - "workspaces/drafter/ agent workspace skeleton (SOUL/AGENTS/USER/BOOT.md + memory/)"
    - "book_pipeline.openclaw.bootstrap module (BootstrapReport, bootstrap(), register_placeholder_cron())"
    - "`book-pipeline openclaw {bootstrap, status, register-cron}` subcommand group"
    - "Manual-command fallback diagnostic when the openclaw CLI is not on PATH"
  affects:
    - "Phase 3 DRAFT-01/02 (drafter workspace fills with real Mode-A loop; SOUL pre-declares the seam)"
    - "Phase 5 ORCH-01 (replaces the placeholder cron with the real nightly scene-generation loop)"
    - "Phase 1 Plan 05 OBS-01 (event-logger will land alongside drafter calls that originate from this workspace)"
tech_stack:
  added:
    - "openclaw project config (v2026.4.5 schema) — first consumer in this repo"
  patterns:
    - "argv-list subprocess invocation of `openclaw cron add` (shell=False, static args; injection-proof)"
    - "BootstrapReport dataclass + .ok property — structured diagnostic return (no exceptions for expected config problems)"
    - "2.0s socket.create_connection timeout for loopback gateway probe (DoS guard T-04-04)"
    - "Manual-command fallback text when subprocess target is absent (graceful degradation for cold installs)"
key_files:
  created:
    - "openclaw.json"
    - "workspaces/drafter/AGENTS.md"
    - "workspaces/drafter/SOUL.md"
    - "workspaces/drafter/USER.md"
    - "workspaces/drafter/BOOT.md"
    - "workspaces/drafter/memory/.gitkeep"
    - "src/book_pipeline/openclaw/__init__.py"
    - "src/book_pipeline/openclaw/bootstrap.py"
    - "src/book_pipeline/cli/openclaw_cmd.py"
    - "tests/test_openclaw.py"
  modified: []
key-decisions:
  - "openclaw.json lives at repo ROOT, never in a .openclaw/ subdir — .openclaw/ is openclaw-the-tool's global state at ~/.openclaw/ (per-user, NOT per-project). STACK.md flagged this as the #1 common misconception."
  - "Port assignments chosen to not collide with the running wipe-haus-state install: gateway 18790 (vs 18789), vLLM 8002 (vs 8000). Future installs should increment from here."
  - "Model id in openclaw.json is `paul-voice-latest` (aspirational Phase-3 pin) rather than today's V6 checkpoint — voice_pin.yaml is authoritative for the actual SHA once Phase 3 lands, and this id is a stable alias the cron script will dereference."
  - "register-cron shells out to `openclaw cron add` rather than installing a systemd timer (D-03 in CONTEXT.md explicitly forbids shadowing openclaw's built-in persistent cron)."
  - "bootstrap() returns a dataclass (BootstrapReport), not an exception on config defects — the CLI needs to print both errors AND warnings. Only genuinely missing/corrupt state raises at read time (JSONDecodeError in one arm)."
  - "`status` is wired as a read-only alias for `bootstrap` today. The split exists so future plans can attach side effects to `bootstrap` (e.g., creating drafts/scene_buffer dirs) without breaking `status`."
patterns-established:
  - "Subprocess safety: argv list, not shell=True, never string-interpolate external input into the command"
  - "Loopback port probe with explicit timeout (copy-pasteable for future health-check endpoints in other plans)"
  - "Dataclass-based diagnostic reports over exception-for-config-error (fits the CLI printing model)"
requirements-completed: [FOUND-03]
metrics:
  duration_minutes: 3
  completed_date: 2026-04-22
  tasks_completed: 2
  files_created: 10
  files_modified: 0
  tests_added: 5
  tests_passing: 5
commits:
  - hash: c997cee
    type: feat
    summary: add openclaw.json + drafter workspace skeleton
  - hash: ad7ca74
    type: feat
    summary: add book-pipeline openclaw CLI + bootstrap module
---

# Phase 1 Plan 4: openclaw Bootstrap + Drafter Workspace Summary

**One-liner:** openclaw.json at repo root on port 18790 + `workspaces/drafter/` stub + `book-pipeline openclaw {bootstrap, status, register-cron}` CLI that validates config, probes the gateway over a 2s loopback socket, and shells out to `openclaw cron add` for a Phase 1 no-op nightly placeholder.

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-22T03:03:39Z
- **Completed:** 2026-04-22T03:06:37Z
- **Tasks:** 2
- **Files created:** 10
- **Files modified:** 0

## Accomplishments

- **openclaw.json at repo root** with gateway port 18790 and vLLM baseUrl `http://127.0.0.1:8002/v1` (both chosen to avoid collision with the running wipe-haus-state install at 18789/8000). One agent declared: `drafter` on `vllm/paul-voice-latest`.
- **Drafter workspace skeleton** — `workspaces/drafter/{SOUL,AGENTS,USER,BOOT}.md` + `memory/.gitkeep`. SOUL.md pre-declares the seam: "You draft, and nothing else. The critic is a separate agent." AGENTS.md flags Phase 1 status as a stub explicitly so Phase 3 has a clean slot to fill.
- **Bootstrap module** (`book_pipeline.openclaw.bootstrap`) — `bootstrap()` returns a structured `BootstrapReport` with ok/warnings/errors; `register_placeholder_cron()` invokes `openclaw cron add` via a static argv list (no shell interpolation, T-04-02 mitigated) with a 30s timeout, and gracefully prints the exact manual command when the `openclaw` CLI is missing.
- **CLI surface** registered via plan 01-01's `SUBCOMMAND_IMPORTS` extension point — zero edit to `main.py` needed. Three actions: `bootstrap` / `status` (alias) / `register-cron`.
- **Five tests pass, mypy strict clean, ruff clean.** Full suite 86/86 green. `uv run book-pipeline openclaw bootstrap` exits 0 against the committed config (warnings for not-yet-running gateway + missing env token, both allowed in Phase 1).

## The port-collision decision rationale

| System | Gateway | vLLM |
|---|---|---|
| wipe-haus-state | 18789 | 8000 (Gemma-4-26B NVFP4) |
| our-lady-book-pipeline | **18790** | **8002** (paul-voice-latest, Phase 3 onward) |

Two systemd --user-owned openclaw gateways may eventually run in parallel (the user keeps wipe-haus-state active for another project); picking different ports lets them coexist on the same Spark. The vLLM port split is more deferred — in Phase 3 we either spin up a dedicated `vllm-book-voice.service` on 8002 or re-point to 8000 if we reuse the Gemma instance — but the openclaw.json commits us to 8002 as the *intended* voice-model port, consistent with STACK.md's stack-patterns section.

## How Phase 5 ORCH-01 will replace the placeholder cron

Today's `register-cron` installs:

```
openclaw cron add \
  --name "book-pipeline:phase1-placeholder" \
  --cron "0 2 * * *" \
  --tz "America/New_York" \
  --session isolated \
  --session-agent drafter \
  --system-event "Phase 1 placeholder. No-op tick. Phase 5 ORCH-01 replaces." \
  --wake now
```

Phase 5 ORCH-01 will:
1. Delete the `book-pipeline:phase1-placeholder` job (`openclaw cron rm ...`).
2. Add `book-pipeline:nightly-draft` whose `--system-event` is the real scene-loop instruction (RAG → Mode A drafter → critic → regen/escalate → commit scene), pointing at `workspaces/drafter/AGENTS.md` for the full spec, which will no longer be a stub by then.
3. The cron key name (`book-pipeline:*`) is a convention so any future `openclaw cron ls | grep book-pipeline` lists all pipeline-owned jobs cleanly.

The Phase 1 placeholder is intentionally a no-op (`--session isolated` + a `--system-event` string that just narrates itself) — it proves the wiring without touching the repo.

## Task Commits

1. **Task 1: openclaw.json + drafter workspace skeleton** — `c997cee` (feat)
2. **Task 2: openclaw bootstrap/status/register-cron CLI + tests** — `ad7ca74` (feat)

_(Plan-metadata commit follows in final_commit step below.)_

## Files Created/Modified

- `openclaw.json` — openclaw v2026.4.5 project config; gateway 18790, vLLM baseUrl 8002, single agent `drafter`
- `workspaces/drafter/SOUL.md` — persona; "you are the drafter; your only job is scene-level voice-faithful prose"
- `workspaces/drafter/AGENTS.md` — operating instructions (Phase 1 stub; Phase 3 fills)
- `workspaces/drafter/USER.md` — user-interaction model (Paul; weekly spot-checks)
- `workspaces/drafter/BOOT.md` — boot checklist placeholder (vLLM reachability, SHA match, hard-block on failure)
- `workspaces/drafter/memory/.gitkeep` — keeps openclaw memory dir tracked
- `src/book_pipeline/openclaw/__init__.py` — package marker with docstring
- `src/book_pipeline/openclaw/bootstrap.py` — `BootstrapReport`, `bootstrap()`, `register_placeholder_cron()`
- `src/book_pipeline/cli/openclaw_cmd.py` — `openclaw` subcommand group with three actions
- `tests/test_openclaw.py` — 5 tests (valid-config probe, repo-layout assertion, missing-workspace error path, CLI stdout, manual-command fallback)

## Decisions Made

See the `key-decisions` frontmatter block — all 6 decisions are captured there with the reasoning embedded in the bullet text. Summary:

1. **openclaw.json at repo root** (not `.openclaw/`) — STACK.md #1 common misconception, blocked explicitly in the test_openclaw.py assertion `assert not Path(".openclaw/openclaw.json").exists()`.
2. **Ports 18790/8002** to avoid collision with wipe-haus-state (18789/8000).
3. **`paul-voice-latest` as the model id** — stable alias, not tied to V6 or the specific next checkpoint; `voice_pin.yaml` remains authoritative for the SHA.
4. **`openclaw cron add`, not systemd timer** — CONTEXT.md D-03 and STACK.md both forbid shadowing.
5. **Dataclass diagnostic return, not exceptions** — keeps CLI-printing model clean; only genuinely corrupt JSON raises.
6. **`status` as a read-only alias for `bootstrap`** — future-proof split so plans can add side effects to `bootstrap` without breaking `status`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed unused variable lint warning in test_openclaw.py**
- **Found during:** Post-Task-2 ruff check
- **Issue:** `ok, out, err = register_placeholder_cron()` — `out` was unused, triggering RUF059. Test asserts only on `ok` and `err`; the empty stdout in the fallback path is already implied by the function contract.
- **Fix:** Renamed to `_out` (underscore dummy-variable pattern, per the ruff hint).
- **Files modified:** `tests/test_openclaw.py`
- **Verification:** `uv run ruff check` — All checks passed; `uv run pytest tests/test_openclaw.py -q` — 5 passed.
- **Committed in:** `ad7ca74` (Task 2 commit — the fix was made before the Task 2 commit was finalized, so it's bundled with the rest of Task 2's changes).

---

**Total deviations:** 1 auto-fixed (1 bug fix / lint)
**Impact on plan:** Trivial. No scope creep. Maintains the zero-warnings posture the plan established.

## Authentication Gates

None encountered. The openclaw gateway was not listening during bootstrap (warned, not errored — allowed in Phase 1), and `OPENCLAW_GATEWAY_TOKEN` was not exported (also warned, not errored — the bootstrap probe is loopback-only and does not exercise gateway auth yet; Phase 5 ORCH-01 will tighten this).

The `openclaw` CLI IS on PATH (`/home/admin/.npm-global/bin/openclaw`), so `register-cron` would actually install the placeholder cron if invoked — but the plan's `<verify>` block only requires that `register_placeholder_cron()` *works when the CLI is present* and *returns the manual-command diagnostic when it is not*. Both are covered by the test suite; the real cron was not installed as part of plan execution (no plan step asked for that), leaving the decision with the user.

## Deferred Issues

None. All acceptance criteria pass on first run after the one-line ruff fix.

## Known Stubs

The following are **intentional Phase 1 stubs**, all explicitly marked as such in the file contents themselves. They do NOT block the plan's goal (FOUND-03) because FOUND-03's goal is "openclaw.json recognized by the gateway + drafter workspace skeleton exists + bootstrap CLI works" — the content of the stub markdown is not part of that goal.

| Stub | File | Resolved by |
|---|---|---|
| Drafter AGENTS.md body | `workspaces/drafter/AGENTS.md` | Phase 3 DRAFT-01/02 (real Mode-A drafter loop spec) |
| Drafter BOOT.md checks | `workspaces/drafter/BOOT.md` | Phase 3 DRAFT-01 (real vLLM reachability + SHA match enforcement) |
| `paul-voice-latest` model id | `openclaw.json` | Phase 3 (voice_pin.yaml becomes authoritative; the alias is either remapped or replaced with the concrete checkpoint id) |
| Placeholder cron `--system-event` | installed via `register-cron` | Phase 5 ORCH-01 (replaces with real scene-loop instruction) |

Each stub is self-labeled (grep for "Phase 1 stub" or "placeholder" in the files). No stub flows to a code path that would silently produce wrong output — the drafter workspace is not yet invoked by any code in the repo.

## Threat Flags

No new threat surface introduced beyond the plan's `<threat_model>` declared register:

- T-04-01 (Spoofing — fake openclaw.json) — mitigated: bootstrap() only reads repo-root openclaw.json via `Path.cwd() / "openclaw.json"` (or an explicit `repo_root` arg for tests); workspaces/drafter/*.md existence is explicitly checked.
- T-04-02 (Tampering — subprocess injection) — mitigated: `subprocess.run` with a static list argv, `shell=False`, no string interpolation from external input.
- T-04-03 (Information Disclosure — token in logs) — mitigated: bootstrap() only checks env-var presence via `"OPENCLAW_GATEWAY_TOKEN" in os.environ`, never reads the value; openclaw.json embeds `${OPENCLAW_GATEWAY_TOKEN}` for gateway-side expansion.
- T-04-04 (DoS — port probe hangs) — mitigated: `socket.create_connection(..., timeout=2.0)` in `_probe_port`.
- T-04-05 (EoP — cron installs arbitrary command) — accepted: Phase 1 installs only the no-op `--system-event` placeholder; Phase 5 ORCH-01 diff will be reviewed before landing.

## Next Phase Readiness

Ready for Plan 01-05 (OBS-01 EventLogger + smoke-event CLI). The openclaw integration is structurally complete — Plan 5 can assume the `drafter` workspace exists and emits events through the same `book_pipeline.observability.event_logger` that Plan 5 will build.

After Plan 5 lands, Phase 1 is complete (six plans: packaging, protocols + Event schema, typed configs, openclaw bootstrap, observability). Phase 2 (CORPUS-01/02) becomes the next phase target.

## Self-Check: PASSED

Verified post-write:

**Files on disk (10 FOUND):**
- FOUND: openclaw.json
- FOUND: workspaces/drafter/AGENTS.md, SOUL.md, USER.md, BOOT.md
- FOUND: workspaces/drafter/memory/.gitkeep
- FOUND: src/book_pipeline/openclaw/__init__.py, bootstrap.py
- FOUND: src/book_pipeline/cli/openclaw_cmd.py
- FOUND: tests/test_openclaw.py

**Commits reachable (2 FOUND):**
- FOUND: c997cee (Task 1 — openclaw.json + drafter workspace skeleton)
- FOUND: ad7ca74 (Task 2 — CLI + bootstrap module + tests)

**Acceptance criteria (all PASS):**
- openclaw.json at repo root; `test ! -d .openclaw/project_state` passes
- `python3 -c "import json; json.load(open('openclaw.json'))"` clean
- `jq '.gateway.port' openclaw.json` = 18790
- `jq '.models.providers.vllm.baseUrl' openclaw.json` = "http://127.0.0.1:8002/v1"
- `jq '.agents.list | length' openclaw.json` = 1; id = "drafter"
- `uv run book-pipeline openclaw bootstrap` exit 0, prints report with port 18790
- `uv run book-pipeline --help` lists `openclaw`
- `uv run mypy src/book_pipeline/openclaw/` — no issues
- `uv run ruff check src/book_pipeline/openclaw/ src/book_pipeline/cli/openclaw_cmd.py tests/test_openclaw.py` — all passed
- `uv run pytest tests/test_openclaw.py` — 5 passed
- Full suite: 86/86 green

---
*Phase: 01-foundation-observability-baseline*
*Completed: 2026-04-22*
