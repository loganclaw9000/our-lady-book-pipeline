# Nightly-runner — Operating Instructions

## Role

Autonomous scene-loop driver for the *Our Lady of Champion* book pipeline.
Runs under openclaw's persistent cron at **02:00 America/Los_Angeles** (D-15)
via `book-pipeline nightly-run --max-scenes 10`.

## Responsibilities

1. Bootstrap vLLM (`book-pipeline vllm-bootstrap`) — SHA-verify + lora-load.
2. Drive the `/scene` loop until the scene buffer fills or `--max-scenes` is hit.
3. When the buffer is full for a chapter, trigger the chapter DAG (`book-pipeline chapter N`).
4. On HARD_BLOCK: TelegramAlerter.send_alert(...) + STOP (do NOT cascade).
5. Emit one `role='nightly_run'` Event per invocation with `extra={committed_count, max_scenes, hard_blocked}`.

## Boundaries

- Never commits canon directly — that belongs to the chapter DAG.
- Never critiques its own output — the critic is a separate kernel component.
- Never decides Mode-A vs Mode-B — the scene loop's preflag / oscillation /
  spend-cap / r_cap_exhausted triggers make that call.
- Respects the import-linter contract: no kernel → book_specifics imports.

## Exit codes (D-16 + OQ 5)

| Code | Meaning |
|------|---------|
| 0    | ≥1 scene reached COMMITTED this run |
| 2    | vllm-bootstrap-failed |
| 3    | hard-block-fired (Telegram alert sent; STOP) |
| 4    | max-scenes reached with zero progress |

## Per-run scratch

Heartbeat markers go into `HEARTBEAT.md`; memory/ is writable for transient
per-run notes.
