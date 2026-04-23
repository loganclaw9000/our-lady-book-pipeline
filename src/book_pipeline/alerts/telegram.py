"""TelegramAlerter — POST to Telegram Bot API via httpx with tenacity retry.

ALERT-01 / ALERT-02 / D-12 / D-13. Emits role='telegram_alert' Events for
forensic trail (T-05-03-07 repudiation mitigation).

Retry semantics (Pitfall 3 mitigation):
  - 429 responses read ``parameters.retry_after`` from body and raise
    ``TelegramRetryAfter`` → tenacity retries.
  - 4xx non-429 (bad token, bad chat_id, malformed payload) raises
    ``TelegramPermanentError`` — tenacity does NOT retry (prevents storm on a
    permanently-broken config).
  - Transient transport errors (``httpx.TransportError``) retry.

Detail-dict whitelist (T-05-03-01 mitigation): caller-supplied ``detail``
dicts may carry secrets; only keys in ``ALLOWED_DETAIL_KEYS`` reach the
``.format()`` call that builds the message body.

Cooldown integration (ALERT-02): ``CooldownCache`` checked before send,
recorded after successful send. Scope = ``detail["scene_id"]`` or
``detail["chapter_num"]`` or literal string ``"global"``. Key = (condition,
scope).

DI seam: ``http_post`` parameter defaults to ``httpx.post`` but tests inject a
stub; ``now_fn`` similarly for deterministic cooldown time control.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
import tenacity

from book_pipeline.alerts.cooldown import CooldownCache
from book_pipeline.alerts.taxonomy import (
    ALLOWED_DETAIL_KEYS,
    HARD_BLOCK_CONDITIONS,
    MESSAGE_TEMPLATES,
)
from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.types import Event
from book_pipeline.observability.hashing import event_id, hash_text

_TELEGRAM_BASE_URL = "https://api.telegram.org"
_DEFAULT_TIMEOUT_S = 10.0


class TelegramRetryAfter(Exception):
    """Raised when Telegram returns 429 — tenacity retries on this exception."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Telegram 429 retry_after={retry_after}s")


class TelegramPermanentError(Exception):
    """Raised on 4xx non-429 — tenacity does NOT retry (bad token/chat_id).

    Pitfall 3: permanent errors must not trigger exponential-backoff retry
    storms; the API rejection is definitive (bot token banned, chat deleted,
    etc.) so the caller must surface to the operator immediately.
    """


def _is_retryable(exc: BaseException) -> bool:
    """tenacity retry predicate: 429 + transient httpx transport errors only.

    TelegramPermanentError is intentionally excluded — we never retry on a
    bad-token / bad-chat_id response.
    """
    return isinstance(exc, (TelegramRetryAfter, httpx.TransportError))


class TelegramAlerter:
    """Send hard-block alerts to Telegram with 1h cooldown dedup.

    Args:
        bot_token: Telegram bot API token (read from env by composition root).
        chat_id: Target chat id.
        cooldown_path: Path to ``runs/alert_cooldowns.json`` (gitignored).
        cooldown_ttl_s: 1h per ALERT-02.
        event_logger: Optional EventLogger for ``role='telegram_alert'`` emits.
        now_fn: Test seam for deterministic time control.
        http_post: Test seam for injecting a fake httpx.post (signature:
            ``(url, *, json, timeout) -> response``).
    """

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        cooldown_path: Path | str,
        cooldown_ttl_s: int = 3600,
        event_logger: EventLogger | None = None,
        now_fn: Callable[[], float] = time.time,
        http_post: Callable[..., Any] = httpx.post,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.event_logger = event_logger
        self._now = now_fn
        self._http_post = http_post
        self._cooldown = CooldownCache(
            Path(cooldown_path), ttl_s=cooldown_ttl_s, now_fn=now_fn
        )

    def send_alert(self, condition: str, detail: Mapping[str, Any]) -> bool:
        """Send a hard-block alert. Returns True if actually sent, False on dedup.

        Raises:
            ValueError: `condition` is not in HARD_BLOCK_CONDITIONS (fail fast).
            TelegramPermanentError: 4xx non-429 response — do not retry.
        """
        if condition not in HARD_BLOCK_CONDITIONS:
            raise ValueError(f"unknown hard-block condition: {condition}")

        scope = str(
            detail.get("scene_id")
            or detail.get("chapter_num")
            or "global"
        )

        if self._cooldown.is_suppressed(condition, scope):
            self._emit_event(
                condition, scope, dict(detail), sent=False, deduped=True, error=None
            )
            return False

        # Whitelist detail keys — T-05-03-01 mitigation.
        safe_detail: dict[str, Any] = {
            k: v for k, v in detail.items() if k in ALLOWED_DETAIL_KEYS
        }
        # Ensure scene_id always available for MESSAGE_TEMPLATES.format() —
        # every template references {scene_id}. Use the synthesized scope.
        safe_detail.setdefault("scene_id", scope)

        template = MESSAGE_TEMPLATES[condition]
        try:
            text = template.format(**safe_detail)
        except (KeyError, ValueError, IndexError) as exc:
            # Missing required template field — operator bug, not an API
            # failure. Surface with a placeholder so alerts degrade gracefully.
            text = f"[{condition}] alert (template format error: {exc})"

        try:
            self._post_with_retry(text)
        except TelegramPermanentError as exc:
            self._emit_event(
                condition, scope, safe_detail,
                sent=False, deduped=False, error=str(exc),
            )
            raise

        self._cooldown.record(condition, scope)
        self._emit_event(
            condition, scope, safe_detail,
            sent=True, deduped=False, error=None,
        )
        return True

    # --- Internal -----------------------------------------------------------

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=30),
        retry=tenacity.retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _post_with_retry(self, text: str) -> dict[str, Any]:
        """POST sendMessage; translate 429 → TelegramRetryAfter, 4xx → permanent."""
        url = f"{_TELEGRAM_BASE_URL}/bot{self.bot_token}/sendMessage"
        r = self._http_post(
            url,
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_notification": False,
            },
            timeout=_DEFAULT_TIMEOUT_S,
        )
        if r.status_code == 429:
            retry_after = 1
            try:
                body = r.json() or {}
                retry_after = int(body.get("parameters", {}).get("retry_after", 1))
            except (ValueError, TypeError, AttributeError):
                pass
            raise TelegramRetryAfter(retry_after)
        if 400 <= r.status_code < 500:
            raise TelegramPermanentError(
                f"Telegram {r.status_code}: bad token / chat_id / payload"
            )
        r.raise_for_status()
        body = r.json() if callable(getattr(r, "json", None)) else {}
        return body if isinstance(body, dict) else {}

    def _emit_event(
        self,
        condition: str,
        scope: str,
        safe_detail: dict[str, Any],
        *,
        sent: bool,
        deduped: bool,
        error: str | None,
    ) -> None:
        if self.event_logger is None:
            return
        ts_iso = _now_iso(self._now)
        caller = "alerts.telegram.send_alert"
        prompt_hash = hash_text(f"{condition}|{scope}")
        extra: dict[str, Any] = {
            "condition": condition,
            "scope": scope,
            "sent": sent,
            "deduped": deduped,
            "detail": safe_detail,
        }
        if error is not None:
            extra["error"] = error
        event = Event(
            event_id=event_id(ts_iso, "telegram_alert", caller, prompt_hash),
            ts_iso=ts_iso,
            role="telegram_alert",
            model="telegram-bot-api",
            prompt_hash=prompt_hash,
            input_tokens=0,
            output_tokens=0,
            latency_ms=1,
            caller_context={
                "module": "alerts.telegram",
                "function": "send_alert",
                "scene_id": scope,
            },
            output_hash=hash_text(
                f"{condition}|{scope}|{sent}|{deduped}|{error or ''}"
            ),
            extra=extra,
        )
        self.event_logger.emit(event)


def _now_iso(now_fn: Callable[[], float]) -> str:
    """RFC3339-ish UTC timestamp from an injected now_fn (float epoch)."""
    ns = int(now_fn() * 1_000_000_000)
    s = ns // 1_000_000_000
    us = (ns // 1_000) % 1_000_000
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(s))
        + f".{us:06d}Z"
    )


__all__ = [
    "TelegramAlerter",
    "TelegramPermanentError",
    "TelegramRetryAfter",
]
