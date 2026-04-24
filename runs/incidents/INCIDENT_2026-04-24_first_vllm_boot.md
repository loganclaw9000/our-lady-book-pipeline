# INCIDENT 2026-04-24 — first vLLM boot attempt

**Status:** Resolved (no OOM, no wedge, no GPU touch)
**Severity:** Low — caught by systemd restart loop, no resource damage
**Author:** scribe (book-pipeline)
**Counterpart:** forge (paul-thinkpiece-pipeline)

## What happened

First live `book-pipeline vllm-bootstrap --start --enable` after Forge handoff + dry-run gate v1.1 greenlight. Service started, hit `ModuleNotFoundError: No module named 'vllm'` at every restart, looped 6 times in 90s before bootstrap CLI timed out polling /v1/models for ready.

## What did NOT happen (good)

- **No OOM.** Memory stayed at 5.5G used / 116G available throughout. vLLM never loaded weights — it crashed at module import before reaching any GPU allocation.
- **No GPU touch.** nvidia-smi shows 0% util throughout. No VRAM consumed.
- **No wedge.** Spark unified-memory wedge risk (which Forge HANDOFF flagged at high gpu_memory_utilization) never materialized.
- **No co-resident damage.** FT process was idle (Forge confirmed pre-boot); restart loop wasted CPU briefly but didn't compete for GPU.

## Root cause

Service unit's `ExecStart` defaulted to `/home/admin/finetuning/venv_cu130/bin/python` per book-pipeline's `vllm-bootstrap --venv-python` default constant. vLLM 0.17.0 is installed in `/usr/bin/python3` (system Python), NOT in `venv_cu130/`. venv_cu130 was the right home for paul-thinkpiece-pipeline's training stack but vLLM serving lives system-wide.

Forge's STATUS.json.serve_command correctly used `/usr/bin/python3` — book-pipeline default never picked up that signal.

## Resolution

Stop + disable the unit. Re-run bootstrap with `--venv-python /usr/bin/python3`. Make this the default in `vllm_bootstrap.py` so future boots don't repeat.

```bash
systemctl --user stop vllm-paul-voice.service
systemctl --user disable vllm-paul-voice.service
# then:
uv run book-pipeline vllm-bootstrap --start --enable --venv-python /usr/bin/python3
```

## Prevention

1. Update `_default_venv_python` constant in `book_pipeline/cli/vllm_bootstrap.py` to `/usr/bin/python3`.
2. Add a pre-flight check inside dry-run gate v1.1: assert `<venv_python> -c 'import vllm'` exits 0 before rendering. Catches python/vllm-location drift pre-boot at the same gate that catches SHA drift.
3. Forge HANDOFF + STATUS.json should remain authoritative on serve_command — when scribe diverges, scribe is wrong by default.

## Memory pointer

Add to scribe memory: "vllm lives in system python (/usr/bin/python3), NOT venv_cu130. Always pass --venv-python /usr/bin/python3 OR rely on default once fixed."
