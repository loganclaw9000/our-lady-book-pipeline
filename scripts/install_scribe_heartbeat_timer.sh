#!/usr/bin/env bash
# install_scribe_heartbeat_timer.sh — installs scribe-heartbeat-tier systemd timer
# (mirrors forge install_heartbeat_timer.sh; idempotent).
set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
USER_SYSTEMD="$HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD"

ln -sf "$REPO/systemd/scribe-heartbeat-tier.service" "$USER_SYSTEMD/scribe-heartbeat-tier.service"
ln -sf "$REPO/systemd/scribe-heartbeat-tier.timer"   "$USER_SYSTEMD/scribe-heartbeat-tier.timer"

systemctl --user daemon-reload
systemctl --user enable --now scribe-heartbeat-tier.timer
systemctl --user list-timers scribe-heartbeat-tier.timer || true
echo "[install] scribe-heartbeat-tier timer enabled."
echo "[install] Verify: journalctl --user -u scribe-heartbeat-tier.service -f"
