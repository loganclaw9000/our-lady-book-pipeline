# Nightly-runner — Heartbeat

This file receives per-run completion markers written by the openclaw
session when the nightly cron fires. The `check-cron-freshness` CLI
inspects `runs/events.jsonl` for the last `role='nightly_run'` Event
timestamp (not this file) — this file is advisory, not authoritative.

## Format

One line per run (most recent last):

```
<ISO-8601 ts> <exit_code> committed=<N> hard_blocked=<bool>
```

Example:

```
2026-04-23T02:00:03Z 0 committed=2 hard_blocked=false
2026-04-24T02:00:04Z 3 committed=0 hard_blocked=true
```

If this file falls silent for >36h while `runs/events.jsonl` still shows
activity, the nightly cron itself has drifted — `check-cron-freshness`
at 08:00 PT (D-14 independent cron) catches that and sends a
`stale_cron_detected` Telegram alert.
