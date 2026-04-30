"""Adaptive tier (TCP-backoff) for scribe heartbeat.

TCP-backoff model:
  - Each tick, recompute tier from observable signals before emit:
      forge heartbeat staleness, inbox unread (from counterparty),
      pending ack-required messages we've sent.
  - On signs of liveness (fresh forge hb OR new inbox msg) -> step UP
    (lower tier_index = higher cadence).
  - On silence (stale forge hb, empty inbox) -> step DOWN
    (higher tier_index = lower cadence).
  - Bounded T0..T3 per tiers.json contract.

Step rules (TCP-style multiplicative on success/loss):
  +1 step (more responsive) on liveness signal: forge_hb_age_s < cadence*2
                                              OR inbox_unread > 0
                                              OR fresh ack to our pending msg
  -1 step (back off) on silence: forge_hb_age_s > cadence*4
                              AND inbox_unread == 0
                              AND no pending ack arrived

Idempotent: writes new tier into state-file then exits. Heartbeat module
reads tier on next tick. Run BEFORE forge.coordination.heartbeat in the
systemd ExecStart chain.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

TIER_ORDER: list[str] = ["T0_HEADS_DOWN", "T1_active", "T2_idle", "T3_long_idle"]
TIER_CADENCE_S: dict[str, int] = {
    "T0_HEADS_DOWN": 30,
    "T1_active": 90,
    "T2_idle": 270,
    "T3_long_idle": 1200,
}


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _parse_iso(ts: str) -> _dt.datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(ts).astimezone(_dt.UTC)
    except (ValueError, TypeError):
        return None


def _hb_age_s(state: dict) -> float | None:
    parsed = _parse_iso(state.get("last_heartbeat", ""))
    if parsed is None:
        return None
    return (_now_utc() - parsed).total_seconds()


def _read_counterparty_state(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _count_unread_msgs(channel: Path, since: _dt.datetime, from_handle: str) -> int:
    """Count messages in channel (one JSON per line) from `from_handle` after `since`."""
    if not channel.exists():
        return 0
    count = 0
    for line in channel.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("from") != from_handle:
            continue
        ts = _parse_iso(msg.get("timestamp", ""))
        if ts is None:
            continue
        if ts > since:
            count += 1
    return count


def compute_next_tier(
    *,
    current_tier: str,
    forge_hb_age_s: float | None,
    inbox_unread: int,
) -> str:
    """Pure decision function. TCP-backoff style step ±1.

    Liveness => move toward T0 (more responsive).
    Silence  => move toward T3 (back off).
    """
    if current_tier not in TIER_ORDER:
        current_tier = "T1_active"
    cur_idx = TIER_ORDER.index(current_tier)
    cadence = TIER_CADENCE_S[current_tier]

    has_liveness = inbox_unread > 0 or (
        forge_hb_age_s is not None and forge_hb_age_s < cadence * 2
    )
    is_silent = inbox_unread == 0 and (
        forge_hb_age_s is None or forge_hb_age_s > cadence * 4
    )

    # T0_HEADS_DOWN reserved for explicit operator/protocol set per tiers.json
    # ("active bilateral conflict or mid-multi-edit cycle"). Auto-step floor = T1.
    auto_min_idx = TIER_ORDER.index("T1_active")
    if has_liveness and cur_idx > auto_min_idx:
        return TIER_ORDER[cur_idx - 1]
    if is_silent and cur_idx < len(TIER_ORDER) - 1:
        return TIER_ORDER[cur_idx + 1]
    return current_tier


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--state-file", required=True, type=Path)
    p.add_argument("--counterparty-state", required=True, type=Path)
    p.add_argument("--inbound-channel", required=True, type=Path,
                   help="JSONL channel where counterparty messages arrive (e.g. voice_to_novel.jsonl)")
    p.add_argument("--counterparty-handle", default="forge")
    args = p.parse_args(argv)

    state = json.loads(args.state_file.read_text())
    cp_state = _read_counterparty_state(args.counterparty_state) or {}

    cp_hb_age = _hb_age_s(cp_state)
    last_emit = _parse_iso(state.get("last_heartbeat", "")) or _now_utc()
    inbox_unread = _count_unread_msgs(
        args.inbound_channel,
        since=last_emit,
        from_handle=args.counterparty_handle,
    )

    current_tier = state.get("tier", "T1_active")
    next_tier = compute_next_tier(
        current_tier=current_tier,
        forge_hb_age_s=cp_hb_age,
        inbox_unread=inbox_unread,
    )

    state["inbox_unread_count"] = inbox_unread
    if next_tier != current_tier:
        state["tier"] = next_tier
        state["_adaptive_tier_last_change"] = _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
        print(
            f"[adaptive_tier] {current_tier}->{next_tier} "
            f"cp_hb_age={cp_hb_age} inbox_unread={inbox_unread}",
            file=sys.stderr,
        )
    else:
        print(
            f"[adaptive_tier] hold {current_tier} "
            f"cp_hb_age={cp_hb_age} inbox_unread={inbox_unread}",
            file=sys.stderr,
        )

    args.state_file.write_text(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
