"""pytest configuration and shared fixtures.

WR-03: Close and evict all cached FileHandler objects after each test so that
pytest's tmp_path cleanup can remove temporary directories without hitting
open file descriptors.  The handler cache (_HANDLERS_BY_PATH) is designed for
a long-running production process with exactly one log path; in tests each
tmp_path call produces a unique directory, so without teardown the process
accumulates O(N) open FDs across the suite.

This fixture also prevents test_handler_idempotent from passing spuriously
because a leftover cached handler from a prior test happens to share the same
path key (unlikely with tmp_path, but not impossible with manually constructed
paths).

Plan 05-01 extension: FakeAnthropicClient + pricing_fixture for Mode-B
drafter + pricing tests. No real network I/O; cache_read_input_tokens is
configurable so tests can assert cached_tokens flows through into Events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

import book_pipeline.observability.event_logger as _el


@pytest.fixture(autouse=True)
def _clear_handler_cache() -> object:
    yield
    with _el._HANDLER_LOCK:
        for handler in _el._HANDLERS_BY_PATH.values():
            handler.close()
        _el._HANDLERS_BY_PATH.clear()


# --- Plan 05-01 fakes ---------------------------------------------------- #


@dataclass
class FakeAnthropicUsage:
    """Mimics anthropic.types.Usage shape used by ModeBDrafter."""

    input_tokens: int = 150
    output_tokens: int = 600
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeAnthropicTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeAnthropicMessage:
    content: list[FakeAnthropicTextBlock]
    usage: FakeAnthropicUsage = field(default_factory=FakeAnthropicUsage)
    id: str = "msg_fake_01"
    model: str = "claude-opus-4-7"
    role: str = "assistant"
    type: str = "message"
    stop_reason: str = "end_turn"


class FakeAnthropicMessages:
    """Captures call args; optionally raises N times before succeeding."""

    def __init__(
        self,
        *,
        text: str = "A drafted scene.",
        usage: FakeAnthropicUsage | None = None,
        fail_n_times: int = 0,
        failure_exc: Exception | None = None,
    ) -> None:
        self._text = text
        self._usage = usage or FakeAnthropicUsage()
        self._fail_remaining = fail_n_times
        self._failure_exc = failure_exc
        self.call_args_list: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeAnthropicMessage:
        self.call_args_list.append(kwargs)
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            if self._failure_exc is not None:
                raise self._failure_exc
            # default: simulate a transient APIConnectionError
            from anthropic import APIConnectionError

            raise APIConnectionError(request=None)  # type: ignore[arg-type]
        return FakeAnthropicMessage(
            content=[FakeAnthropicTextBlock(text=self._text)],
            usage=self._usage,
        )


class FakeAnthropicClient:
    """Top-level Anthropic client stub — exposes `.messages.create`."""

    def __init__(
        self,
        *,
        text: str = "A drafted scene.",
        usage: FakeAnthropicUsage | None = None,
        fail_n_times: int = 0,
        failure_exc: Exception | None = None,
    ) -> None:
        self.messages = FakeAnthropicMessages(
            text=text,
            usage=usage,
            fail_n_times=fail_n_times,
            failure_exc=failure_exc,
        )


@pytest.fixture
def fake_anthropic_factory() -> Any:
    """Factory fixture: returns a callable (**kwargs) -> FakeAnthropicClient.

    Tests pass text / usage / fail_n_times / failure_exc to control the fake.
    """

    def _make(**kwargs: Any) -> FakeAnthropicClient:
        usage_kwargs: dict[str, Any] = {}
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            if k in kwargs:
                usage_kwargs[k] = kwargs.pop(k)
        usage = FakeAnthropicUsage(**usage_kwargs) if usage_kwargs else None
        return FakeAnthropicClient(usage=usage, **kwargs)

    return _make


@pytest.fixture
def pricing_fixture() -> Any:
    """Return a PricingConfig loaded from the shipped config/pricing.yaml.

    Consumers: test_pricing.py + Plan 05-02 spend-cap tests.
    """
    from book_pipeline.config.pricing import PricingConfig

    return PricingConfig()
