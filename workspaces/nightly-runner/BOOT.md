# Nightly-runner — BOOT checklist

Required environment (read by `_build_nightly_alerter` + scene-loop composition):

1. `ANTHROPIC_API_KEY` — for critic / extractor / retrospective / Mode-B drafter.
2. `TELEGRAM_BOT_TOKEN` — Telegram Bot API token. Absence degrades to
   stderr-only alerts (OQ 4 soft-fail) but does NOT block the run.
3. `TELEGRAM_CHAT_ID` — target chat id. Absence → same soft-fail.
4. `OPENCLAW_GATEWAY_TOKEN` — required only for `book-pipeline register-cron`
   (one-shot; not per-run).

vLLM health:

- Step (a) of the nightly run is `book-pipeline vllm-bootstrap`: SHA-verify
  + lora-load. On failure → exit 2 + Telegram alert `vllm_health_failed`.
- The drafter unit is `vllm-paul-voice.service` under `systemctl --user`.
- Port: 8002 (per config/voice_pin.yaml → `vllm_serve_config.port`).

Operator pre-flight (one-time, before the first real nightly):

```
# 1. Set secrets (these live in ~/.claude env, systemd user drop-ins, or .env).
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
export OPENCLAW_GATEWAY_TOKEN=...
export ANTHROPIC_API_KEY=...

# 2. Populate voice samples (once).
book-pipeline curate-voice-samples --out config/voice_samples.yaml \
  --source-dir /home/admin/paul-thinkpiece-pipeline/...

# 3. Register crons.
book-pipeline register-cron --nightly
book-pipeline register-cron --cron-freshness
```
