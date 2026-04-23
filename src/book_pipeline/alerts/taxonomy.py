"""Hard-block alert taxonomy + terse unblock-hint message templates.

CONTEXT.md D-12: exactly 8 hard-block conditions. Every condition MUST have a
corresponding ``MESSAGE_TEMPLATES`` entry so ``.format(**detail)`` at alert
time cannot raise KeyError.

Per ``<specifics>`` ("Paul reads on a phone; terse is a feature"):
templates lead with a single unicode glyph + include a 1-line "how to
unblock" hint.

Detail-dict whitelist (``ALLOWED_DETAIL_KEYS``) is the T-05-03-01 mitigation:
only known-safe keys are ever interpolated into the Telegram message body.
Caller-supplied dicts may carry secrets (bot tokens / API keys) — the
whitelist strips them before ``.format()``.
"""

from __future__ import annotations

HARD_BLOCK_CONDITIONS: frozenset[str] = frozenset(
    {
        "spend_cap_exceeded",
        "regen_stuck_loop",
        "rubric_conflict",
        "voice_drift_over_threshold",
        "checkpoint_sha_mismatch",
        "vllm_health_failed",
        "stale_cron_detected",
        "mode_b_exhausted",
    }
)


# Keys = condition; values = f-string templates receiving a whitelisted
# detail dict. `{scene_id}` is always available (synthesized from detail
# scene_id / chapter_num / "global" by TelegramAlerter.send_alert).
MESSAGE_TEMPLATES: dict[str, str] = {
    "spend_cap_exceeded": (
        "🛑 Scene {scene_id}: spend cap hit at ${spent_usd:.2f}. "
        "Unblock: raise regen.spend_cap_usd_per_scene in "
        "config/mode_thresholds.yaml."
    ),
    "regen_stuck_loop": (
        "🔁 Scene {scene_id}: oscillation detected on {axes}. "
        "Unblock: escalated to Mode-B automatically; investigate rubric "
        "if it repeats."
    ),
    "rubric_conflict": (
        "⚠️ Scene {scene_id}: critic rubric returned contradictory axes. "
        "Unblock: inspect runs/critic_audit/{scene_id}_*.json."
    ),
    "voice_drift_over_threshold": (
        "📉 Scene {scene_id}: voice fidelity {cosine:.3f} below fail "
        "threshold. Unblock: check voice_pin.yaml + anchor set; consider "
        "re-curating anchors."
    ),
    "checkpoint_sha_mismatch": (
        "🔒 Scene {scene_id}: vLLM checkpoint SHA != voice_pin.yaml. "
        "Unblock: run `book-pipeline pin-voice` or restart vLLM with "
        "correct LoRA."
    ),
    "vllm_health_failed": (
        "🩺 Scene {scene_id}: vLLM health probe failed on port {port}. "
        "Unblock: `systemctl --user restart vllm-book-voice.service`."
    ),
    "stale_cron_detected": (
        "⏰ Scene {scene_id}: no nightly-run Event in {hours_since}h "
        "(>36h threshold). Unblock: run `book-pipeline nightly-run` "
        "manually; check gateway + cron."
    ),
    "mode_b_exhausted": (
        "💀 Scene {scene_id}: Mode-B drafter tenacity-exhausted. "
        "Unblock: inspect runs/events.jsonl for role='drafter' mode='B' "
        "errors."
    ),
}


# Payload whitelist — the T-05-03-01 "no secret leak into Telegram body"
# mitigation. Only these keys survive into the `.format()` step. Any
# caller-supplied extras (bot_token, api_key, stack_trace, etc.) are
# silently dropped before the message is rendered.
ALLOWED_DETAIL_KEYS: frozenset[str] = frozenset(
    {
        "scene_id",
        "chapter_num",
        "spent_usd",
        "axes",
        "cosine",
        "port",
        "hours_since",
    }
)


__all__ = [
    "ALLOWED_DETAIL_KEYS",
    "HARD_BLOCK_CONDITIONS",
    "MESSAGE_TEMPLATES",
]
