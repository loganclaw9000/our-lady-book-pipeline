#!/usr/bin/env bash
# v7d_redeploy_preview.sh — read forge V7D ship artifacts and print the
# redeploy_voice_pin.sh invocation that WOULD pin V7D.
#
# This script does NOT modify state. Operator-review gated per protocol.
# Once SHIP=True comes through and operator approves, run the printed cmd.
#
# Reads:
#   /home/admin/finetuning/output/paul-v7d-qwen35-27b-merged/MANIFEST.json
#     -> manifest_digest, adapter_digest, ft_run_id (or derive from path)
#   /home/admin/finetuning/output/paul-v7d-qwen35-27b-lora/
#     -> verifies adapter dir exists with required files
#   /home/admin/paul-thinkpiece-pipeline/eval/v7d_vs_v7c_comparison.md
#     -> prints comparison summary if present
#
# Exits 0 if MANIFEST.json present + adapter dir verified; non-zero if
# anything missing (V7D not yet shipped or path differs).

set -euo pipefail

MERGED_DIR="${MERGED_DIR:-/home/admin/finetuning/output/paul-v7d-qwen35-27b-merged}"
ADAPTER_DIR="${ADAPTER_DIR:-/home/admin/finetuning/output/paul-v7d-qwen35-27b-lora}"
COMPARISON_MD="${COMPARISON_MD:-/home/admin/paul-thinkpiece-pipeline/eval/v7d_vs_v7c_comparison.md}"
FT_RUN_ID="${FT_RUN_ID:-v7d_qwen35_27b}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== V7D redeploy preview ==="
echo

# 1. MANIFEST ----------------------------------------------------------------
MANIFEST="$MERGED_DIR/MANIFEST.json"
if [[ ! -f "$MANIFEST" ]]; then
    echo "FAIL: MANIFEST.json not present at $MANIFEST" >&2
    echo "      V7D not yet shipped. Re-run after forge SHIP=True alert." >&2
    exit 10
fi
echo "MANIFEST.json present:"
python3 -c "
import json, sys
m = json.load(open('$MANIFEST'))
keys = ('manifest_digest', 'adapter_digest', 'base_model', 'ft_run_id', 'trained_at', 'epochs', 'final_eval_loss')
for k in keys:
    v = m.get(k)
    if v is not None:
        print(f'  {k}: {v}')
"
echo

# Pull manifest_digest + adapter_digest into shell vars (best effort).
MANIFEST_DIGEST="$(python3 -c "import json; print(json.load(open('$MANIFEST')).get('manifest_digest',''))")"
ADAPTER_DIGEST="$(python3 -c "import json; print(json.load(open('$MANIFEST')).get('adapter_digest',''))")"

# 2. adapter dir + V-3 sha ---------------------------------------------------
if [[ ! -d "$ADAPTER_DIR" ]]; then
    echo "FAIL: adapter dir missing: $ADAPTER_DIR" >&2
    exit 11
fi
if [[ ! -f "$ADAPTER_DIR/adapter_model.safetensors" ]] || [[ ! -f "$ADAPTER_DIR/adapter_config.json" ]]; then
    echo "FAIL: adapter dir incomplete (missing safetensors or config.json): $ADAPTER_DIR" >&2
    exit 12
fi
COMPUTED_SHA="$(
    cd "$ADAPTER_DIR" && sha256sum adapter_model.safetensors adapter_config.json | sort | sha256sum | awk '{print $1}'
)"
echo "Adapter dir verified: $ADAPTER_DIR"
echo "  V-3 manifest sha (recomputed): $COMPUTED_SHA"
if [[ -n "$ADAPTER_DIGEST" ]] && [[ "$COMPUTED_SHA" != "$ADAPTER_DIGEST" ]]; then
    echo "  WARN: MANIFEST.adapter_digest=$ADAPTER_DIGEST does NOT match recomputed sha"
    echo "        Will fail redeploy_voice_pin.sh pre-flight."
fi
echo

# 3. Comparison report (if present) -----------------------------------------
if [[ -f "$COMPARISON_MD" ]]; then
    echo "Comparison report: $COMPARISON_MD"
    echo "  -- first 30 lines --"
    sed -n '1,30p' "$COMPARISON_MD"
    echo
else
    echo "Comparison report not yet present at $COMPARISON_MD"
    echo
fi

# 4. Print invocation -------------------------------------------------------
echo "=== READY-TO-FIRE COMMAND (operator review gated) ==="
echo
echo "$REPO_ROOT/scripts/redeploy_voice_pin.sh \\"
echo "    $FT_RUN_ID \\"
echo "    $ADAPTER_DIR \\"
echo "    $COMPUTED_SHA \\"
echo "    $MANIFEST_DIGEST"
echo
echo "(append REINDEX=1 env to also re-ingest RAG)"
