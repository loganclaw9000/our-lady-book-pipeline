#!/usr/bin/env bash
# redeploy_voice_pin.sh — atomically re-pin voice_pin.yaml to a new FT checkpoint
# and run downstream re-ingest steps. Idempotent (re-running with same SHA = no-op).
#
# Usage:
#   scripts/redeploy_voice_pin.sh <ft_run_id> <checkpoint_path> <checkpoint_sha> [merged_digest]
#
# Example (V7D ship):
#   scripts/redeploy_voice_pin.sh \
#     v7d_qwen35_27b \
#     /home/admin/finetuning/output/paul-v7d-qwen35-27b-lora \
#     <adapter_sha> \
#     <merged_digest>
#
# Pre-flight checks:
#   - checkpoint_path exists + adapter_model.safetensors present
#   - checkpoint_sha matches sha256(sorted sha256(adapter_model.safetensors + adapter_config.json))
#   - vllm-paul-voice service exists in systemd --user
#
# Steps:
#   1. Sanity-check args + checkpoint
#   2. Stop vllm-paul-voice (yields GPU)
#   3. Atomically rewrite config/voice_pin.yaml (write to .new + mv)
#   4. RAG re-ingest if --reindex flag passed (expensive)
#   5. Restart vllm-paul-voice
#   6. Smoke-test /v1/models endpoint
#   7. Print summary

set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "Usage: $0 <ft_run_id> <checkpoint_path> <checkpoint_sha> [merged_digest]" >&2
    echo "  ft_run_id: e.g. v7d_qwen35_27b" >&2
    echo "  checkpoint_path: absolute path to LoRA adapter dir" >&2
    echo "  checkpoint_sha: sha256 hex computed by V-3 algorithm" >&2
    echo "  merged_digest: optional sha256 of merged-dir for documentation" >&2
    exit 2
fi

FT_RUN_ID="$1"
CHECKPOINT_PATH="$2"
CHECKPOINT_SHA="$3"
MERGED_DIGEST="${4:-unknown}"
REINDEX="${REINDEX:-0}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIN_FILE="$REPO_ROOT/config/voice_pin.yaml"

# 1. Pre-flight ---------------------------------------------------------------
echo "[redeploy] pre-flight: ft_run_id=$FT_RUN_ID"
if [[ ! -d "$CHECKPOINT_PATH" ]]; then
    echo "[redeploy] FATAL: checkpoint dir not found: $CHECKPOINT_PATH" >&2
    exit 3
fi
if [[ ! -f "$CHECKPOINT_PATH/adapter_model.safetensors" ]]; then
    echo "[redeploy] FATAL: adapter_model.safetensors missing in $CHECKPOINT_PATH" >&2
    exit 3
fi
if [[ ! -f "$CHECKPOINT_PATH/adapter_config.json" ]]; then
    echo "[redeploy] FATAL: adapter_config.json missing in $CHECKPOINT_PATH" >&2
    exit 3
fi

# Recompute sha (V-3 algo per src/book_pipeline/voice_fidelity/sha.py):
#   cd <adapter_dir> && sha256sum adapter_model.safetensors adapter_config.json | sort | sha256sum
# Must preserve "two spaces + basename" sha256sum format; sort alphabetically;
# hash the sorted concatenation.
COMPUTED_SHA="$(
    cd "$CHECKPOINT_PATH" && sha256sum adapter_model.safetensors adapter_config.json | sort | sha256sum | awk '{print $1}'
)"
if [[ "$COMPUTED_SHA" != "$CHECKPOINT_SHA" ]]; then
    echo "[redeploy] FATAL: computed sha mismatch" >&2
    echo "[redeploy]   expected: $CHECKPOINT_SHA" >&2
    echo "[redeploy]   actual:   $COMPUTED_SHA" >&2
    exit 4
fi
echo "[redeploy] sha verified: $CHECKPOINT_SHA"

# Idempotency: skip if pin already matches.
CURRENT_SHA="$(grep -E '^\s*checkpoint_sha:' "$PIN_FILE" | awk '{print $2}' | head -1)"
if [[ "$CURRENT_SHA" == "$CHECKPOINT_SHA" ]]; then
    echo "[redeploy] noop: pin already at $CHECKPOINT_SHA"
    exit 0
fi

# 2. Stop vllm ---------------------------------------------------------------
echo "[redeploy] stopping vllm-paul-voice..."
if systemctl --user is-active --quiet vllm-paul-voice.service; then
    systemctl --user stop vllm-paul-voice.service
fi

# 3. Atomic pin rewrite ------------------------------------------------------
PIN_NEW="${PIN_FILE}.new"
TODAY="$(date -u +%Y-%m-%d)"
PINNED_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$PIN_NEW" <<EOF
# voice_pin.yaml — pins the voice-FT checkpoint consumed by Mode-A drafter.
# Auto-rewritten by scripts/redeploy_voice_pin.sh on $PINNED_TS.
# FT run: $FT_RUN_ID
# Adapter SHA (V-3 algo): $CHECKPOINT_SHA
# Merged digest: $MERGED_DIGEST
voice_pin:
  source_repo: paul-thinkpiece-pipeline
  source_commit_sha: unknown
  ft_run_id: $FT_RUN_ID
  checkpoint_path: $CHECKPOINT_PATH
  checkpoint_sha: $CHECKPOINT_SHA
  base_model: Qwen/Qwen3.5-27B
  trained_on_date: '$TODAY'
  pinned_on_date: '$TODAY'
  pinned_reason: "$FT_RUN_ID — auto-pinned via redeploy_voice_pin.sh at $PINNED_TS. Adapter SHA verified V-3. Merged digest $MERGED_DIGEST."
  vllm_serve_config:
    port: 8003
    max_model_len: 16384
    dtype: bfloat16
    tensor_parallel_size: 1
    quantization: bitsandbytes
    gpu_memory_utilization: 0.40
    safety_ceiling_max_gpu_util: 0.60
EOF
mv "$PIN_NEW" "$PIN_FILE"
echo "[redeploy] pin rewritten: $PIN_FILE"

# 4. Optional RAG re-ingest --------------------------------------------------
if [[ "$REINDEX" == "1" ]]; then
    echo "[redeploy] running RAG re-ingest (REINDEX=1)..."
    cd "$REPO_ROOT"
    if [[ -x ".venv/bin/python3" ]]; then
        .venv/bin/python3 -m book_pipeline ingest 2>&1 | tail -20
    else
        echo "[redeploy] WARN: .venv missing, skipping ingest" >&2
    fi
fi

# 5. Re-render systemd unit + restart vllm -----------------------------------
# IMPORTANT (2026-04-30 incident): bare `systemctl --user start` reuses the
# existing unit which has the OLD --lora-modules path hardcoded. Must call
# `book-pipeline vllm-bootstrap --start` so the unit is re-rendered from the
# Jinja2 template using the freshly-rewritten voice_pin.yaml.
echo "[redeploy] re-rendering systemd unit + starting vllm via vllm-bootstrap..."
cd "$REPO_ROOT"
if [[ ! -x ".venv/bin/python3" ]]; then
    echo "[redeploy] FATAL: .venv missing — cannot run book-pipeline vllm-bootstrap" >&2
    exit 5
fi
# Stop is already done in step 2. vllm-bootstrap --start does daemon-reload +
# unit write + start + V-3 SHA boot handshake.
.venv/bin/python3 -m book_pipeline vllm-bootstrap --enable --start 2>&1 | tail -10
BOOTSTRAP_RC="${PIPESTATUS[0]}"
if [[ "$BOOTSTRAP_RC" -ne 0 ]]; then
    echo "[redeploy] FATAL: vllm-bootstrap exited $BOOTSTRAP_RC" >&2
    systemctl --user status vllm-paul-voice.service | tail -10 >&2
    exit 5
fi

# Final health check (vllm-bootstrap already polls /v1/models internally, but
# double-check from outside its process).
echo "[redeploy] verifying /v1/models health..."
for i in $(seq 1 36); do
    if curl -sf http://127.0.0.1:8003/v1/models > /dev/null; then
        echo "[redeploy] vllm healthy after ${i}*5s"
        break
    fi
    sleep 5
    if [[ $i -eq 36 ]]; then
        echo "[redeploy] FATAL: vllm not healthy after 180s" >&2
        exit 5
    fi
done

# Verify the running vllm now points at the NEW adapter path.
RUNNING_LORA="$(ps aux | grep -E 'vllm.entrypoints' | grep -v grep | grep -oE 'paul-voice=[^ ]+' | head -1 | cut -d= -f2)"
if [[ -n "$RUNNING_LORA" ]] && [[ "$RUNNING_LORA" != "$CHECKPOINT_PATH" ]]; then
    echo "[redeploy] FATAL: vllm running lora path ($RUNNING_LORA) != pinned ($CHECKPOINT_PATH)" >&2
    echo "[redeploy] systemd unit may not have been re-rendered correctly" >&2
    exit 6
fi
echo "[redeploy] verified vllm serving $RUNNING_LORA"

# 6. Summary -----------------------------------------------------------------
echo "[redeploy] ========================================"
echo "[redeploy] DONE"
echo "[redeploy]   ft_run_id:       $FT_RUN_ID"
echo "[redeploy]   checkpoint_path: $CHECKPOINT_PATH"
echo "[redeploy]   checkpoint_sha:  $CHECKPOINT_SHA"
echo "[redeploy]   merged_digest:   $MERGED_DIGEST"
echo "[redeploy]   reindexed:       $REINDEX"
echo "[redeploy] ========================================"
