"""Tests for book_pipeline.alerts.telegram.TelegramAlerter (Plan 05-03 Task 2).

Behavior (D-12 / D-13 + Pitfall 3):
  - Success path: 200 → alert sent, cooldown recorded, Event emitted with
    role='telegram_alert', sent=True, deduped=False.
  - Dedup: second send() immediately after first returns False and does NOT
    invoke httpx.post (call_count stays at 1); Event logged with deduped=True.
  - 429 retry_after honored via tenacity; underlying post retried after the
    retry_after window; wall-time kept <1s via tenacity wait_none monkeypatch.
  - 4xx non-429 (e.g. 403 bad token) raises TelegramPermanentError; cooldown
    NOT recorded; Event logged with extra.error set.
  - Detail-dict whitelist: bot_token / api_key / stack_trace keys stripped
    before .format() — Telegram body never contains those secrets.
  - Unknown condition raises ValueError (fail fast, not silent drop).

All tests use a plain monkeypatch-based http_post stub — no real network I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


# --- Test fake for httpx.post -----------------------------------------------


@dataclass
class _FakeHttpResponse:
    status_code: int
    _json: dict[str, Any]

    def json(self) -> dict[str, Any]:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 500:
            raise RuntimeError(f"simulated {self.status_code}")


@dataclass
class _FakeHttpPost:
    """Programmable httpx.post stub. Returns responses[i] on call i; after the
    list is exhausted, returns the last response repeatedly (useful when the
    test only wants to observe the first-call dedup behavior)."""

    responses: list[_FakeHttpResponse]
    calls: list[dict[str, Any]] = field(default_factory=list)
    call_count: int = 0

    def __call__(self, url: str, *, json: dict[str, Any], timeout: float = 10.0) -> _FakeHttpResponse:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        self.call_count += 1
        idx = min(self.call_count - 1, len(self.responses) - 1)
        return self.responses[idx]


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


@pytest.fixture
def fake_telegram_api() -> Any:
    """Return a factory for _FakeHttpPost parameterized by (status, body)
    tuples.  Tests use this to configure the HTTP response sequence."""

    def _make(*responses: tuple[int, dict[str, Any]]) -> _FakeHttpPost:
        return _FakeHttpPost(
            responses=[
                _FakeHttpResponse(status_code=status, _json=body)
                for status, body in responses
            ]
        )

    return _make


def _disable_retry_wait(alerter: Any) -> None:
    """Monkeypatch tenacity retry.wait to wait_none so 429 tests complete in
    sub-second wall time without skipping the retry behavior itself."""
    import tenacity

    # tenacity decorator attaches .retry on the bound method; wait is part of
    # the Retrying controller.
    alerter._post_with_retry.retry.wait = tenacity.wait_none()


# --- Tests ------------------------------------------------------------------


def test_send_alert_success_path(tmp_path: Path, fake_telegram_api: Any) -> None:
    from book_pipeline.alerts.telegram import TelegramAlerter

    http = fake_telegram_api((200, {"ok": True, "result": {"message_id": 1}}))
    logger = _FakeEventLogger()
    alerter = TelegramAlerter(
        bot_token="tok",
        chat_id="chat",
        cooldown_path=tmp_path / "cooldowns.json",
        event_logger=logger,
        http_post=http,
    )
    _disable_retry_wait(alerter)

    sent = alerter.send_alert(
        "spend_cap_exceeded",
        {"scene_id": "ch01_sc02", "spent_usd": 0.80},
    )
    assert sent is True
    assert http.call_count == 1
    # URL hits the Telegram Bot API.
    assert "api.telegram.org/bot" in http.calls[0]["url"]
    assert http.calls[0]["json"]["chat_id"] == "chat"
    # Message body carries the scene_id + spent_usd from the template.
    text = http.calls[0]["json"]["text"]
    assert "ch01_sc02" in text
    assert "0.80" in text
    # Cooldown recorded.
    assert alerter._cooldown.is_suppressed("spend_cap_exceeded", "ch01_sc02")
    # Event logged with role='telegram_alert'.
    assert len(logger.events) == 1
    evt = logger.events[0]
    assert evt.role == "telegram_alert"
    assert evt.extra.get("sent") is True
    assert evt.extra.get("deduped") is False


def test_send_alert_deduped(tmp_path: Path, fake_telegram_api: Any) -> None:
    from book_pipeline.alerts.telegram import TelegramAlerter

    http = fake_telegram_api((200, {"ok": True}))
    logger = _FakeEventLogger()
    alerter = TelegramAlerter(
        bot_token="tok",
        chat_id="chat",
        cooldown_path=tmp_path / "cooldowns.json",
        event_logger=logger,
        http_post=http,
    )
    _disable_retry_wait(alerter)

    assert alerter.send_alert(
        "spend_cap_exceeded", {"scene_id": "ch01_sc02", "spent_usd": 0.80}
    ) is True
    assert alerter.send_alert(
        "spend_cap_exceeded", {"scene_id": "ch01_sc02", "spent_usd": 0.80}
    ) is False
    # Exactly one HTTP POST — dedup prevented the second send.
    assert http.call_count == 1
    # Two events logged — one sent, one deduped.
    assert len(logger.events) == 2
    assert logger.events[0].extra["sent"] is True
    assert logger.events[0].extra["deduped"] is False
    assert logger.events[1].extra["sent"] is False
    assert logger.events[1].extra["deduped"] is True


def test_send_alert_429_retry_after_honored(
    tmp_path: Path, fake_telegram_api: Any
) -> None:
    from book_pipeline.alerts.telegram import TelegramAlerter

    http = fake_telegram_api(
        (429, {"ok": False, "parameters": {"retry_after": 2}}),
        (200, {"ok": True}),
    )
    logger = _FakeEventLogger()
    alerter = TelegramAlerter(
        bot_token="tok",
        chat_id="chat",
        cooldown_path=tmp_path / "cooldowns.json",
        event_logger=logger,
        http_post=http,
    )
    _disable_retry_wait(alerter)

    import time as _time

    t0 = _time.monotonic()
    sent = alerter.send_alert(
        "spend_cap_exceeded", {"scene_id": "ch01_sc02", "spent_usd": 0.80}
    )
    elapsed = _time.monotonic() - t0
    assert sent is True
    # tenacity retried on 429 and succeeded on the second call.
    assert http.call_count == 2
    # Wall time stayed <1s (tenacity wait_none) — retry logic itself exercised
    # without paying real wall time.
    assert elapsed < 1.0


def test_send_alert_4xx_non_429_raises_permanent(
    tmp_path: Path, fake_telegram_api: Any
) -> None:
    from book_pipeline.alerts.telegram import (
        TelegramAlerter,
        TelegramPermanentError,
    )

    http = fake_telegram_api(
        (403, {"ok": False, "description": "Forbidden: bot was blocked"})
    )
    logger = _FakeEventLogger()
    alerter = TelegramAlerter(
        bot_token="bad-tok",
        chat_id="chat",
        cooldown_path=tmp_path / "cooldowns.json",
        event_logger=logger,
        http_post=http,
    )
    _disable_retry_wait(alerter)

    with pytest.raises(TelegramPermanentError):
        alerter.send_alert(
            "spend_cap_exceeded",
            {"scene_id": "ch01_sc02", "spent_usd": 0.80},
        )
    # Exactly one POST — no retry storm on 4xx non-429 (Pitfall 3).
    assert http.call_count == 1
    # Cooldown NOT recorded (alert failed).
    assert not alerter._cooldown.is_suppressed("spend_cap_exceeded", "ch01_sc02")
    # Event logged with error surface.
    assert len(logger.events) == 1
    assert logger.events[0].extra.get("sent") is False
    assert logger.events[0].extra.get("error")


def test_send_alert_detail_whitelist_enforced(
    tmp_path: Path, fake_telegram_api: Any
) -> None:
    from book_pipeline.alerts.telegram import TelegramAlerter

    http = fake_telegram_api((200, {"ok": True}))
    alerter = TelegramAlerter(
        bot_token="tok",
        chat_id="chat",
        cooldown_path=tmp_path / "cooldowns.json",
        http_post=http,
    )
    _disable_retry_wait(alerter)

    alerter.send_alert(
        "spend_cap_exceeded",
        {
            "scene_id": "ch01_sc02",
            "spent_usd": 0.80,
            # Secrets that MUST be stripped before .format():
            "bot_token": "SECRET_BOT_TOKEN_xyz",
            "api_key": "SECRET_API_KEY_abc",
            "stack_trace": "Traceback ... SECRET_LEAKED",
        },
    )
    body = http.calls[0]["json"]["text"]
    assert "SECRET_BOT_TOKEN_xyz" not in body
    assert "SECRET_API_KEY_abc" not in body
    assert "SECRET_LEAKED" not in body
    # Whitelisted keys DID land in the body.
    assert "ch01_sc02" in body
    assert "0.80" in body


def test_send_alert_unknown_condition_raises(
    tmp_path: Path, fake_telegram_api: Any
) -> None:
    from book_pipeline.alerts.telegram import TelegramAlerter

    http = fake_telegram_api((200, {"ok": True}))
    alerter = TelegramAlerter(
        bot_token="tok",
        chat_id="chat",
        cooldown_path=tmp_path / "cooldowns.json",
        http_post=http,
    )
    _disable_retry_wait(alerter)

    with pytest.raises(ValueError, match="unknown"):
        alerter.send_alert(
            "bogus_condition_not_in_taxonomy",
            {"scene_id": "ch01_sc02"},
        )
    # No POST made.
    assert http.call_count == 0
