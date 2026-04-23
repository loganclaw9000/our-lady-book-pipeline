"""Tests for OpusRetrospectiveWriter (Plan 04-03 Task 2 — TEST-01 retro).

Covers tests A-F per plan <behavior>:
  A — Protocol conformance (isinstance(w, RetrospectiveWriter) True).
  B — Lint pass first try: 1 Event, lint_retries=0, lint_pass=True.
  C — Lint fail-then-pass: Fake returns bad markdown then good; 1 Event
      with lint_retries=1, lint_pass=True, extra.first_fail_reasons != [].
  D — Lint fail twice: Fake returns bad both times; writer RETURNS retro
      anyway; WARNING logged; 1 Event lint_retries=1, lint_pass=False.
  E — Markdown parse shape: retro.chapter_num, what_worked, what_didnt,
      pattern, candidate_theses all populated.
  F — Generation failure ungated: 3x APIConnectionError -> stub Retrospective
      returned (NOT raised); 1 error Event; WARNING logged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pytest
import tenacity
from anthropic import APIConnectionError

from book_pipeline.interfaces.retrospective_writer import RetrospectiveWriter
from book_pipeline.interfaces.types import Event, Retrospective
from book_pipeline.retrospective.opus import OpusRetrospectiveWriter


# --------------------------------------------------------------------- #
# Fakes                                                                 #
# --------------------------------------------------------------------- #


@dataclass
class _Usage:
    input_tokens: int = 500
    output_tokens: int = 1200
    cache_read_input_tokens: int = 0

    def model_dump(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _CreateResponse:
    content: list[_TextBlock]
    id: str = "msg_fake_retro_01"
    type: str = "message"
    role: str = "assistant"
    model: str = "claude-opus-4-7"
    stop_reason: str = "end_turn"
    usage: _Usage = field(default_factory=_Usage)

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "role": self.role,
            "model": self.model,
            "stop_reason": self.stop_reason,
            "usage": self.usage.model_dump(),
            "content": [{"type": b.type, "text": b.text} for b in self.content],
        }


class _FakeMessages:
    def __init__(self, side_effect: list[Any]) -> None:
        self._side_effect = list(side_effect)
        self.call_args_list: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.call_args_list)

    def create(self, **kwargs: Any) -> _CreateResponse:
        self.call_args_list.append(kwargs)
        effect = self._side_effect.pop(0)
        if isinstance(effect, Exception):
            raise effect
        if isinstance(effect, str):
            return _CreateResponse(content=[_TextBlock(text=effect)])
        return effect  # type: ignore[return-value]


class _FakeAnthropicClient:
    def __init__(self, side_effect: list[Any]) -> None:
        self.messages = _FakeMessages(side_effect=side_effect)


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


# --------------------------------------------------------------------- #
# Helpers                                                               #
# --------------------------------------------------------------------- #


GOOD_MARKDOWN = """---
chapter_num: 1
candidate_theses:
  - id: t1
    description: Opening chapters reward dense metaphysical framing.
---

# Chapter 01 Retrospective

## What Worked
ch01_sc01 landed the historical beats cleanly; the "auspices" framing
paid off without dragging pace.

## What Drifted
ch01_sc02 drifted on the metaphysics axis — the engine-tier reference
crept back in despite the critic's earlier flag.

## Emerging Patterns
ch01_sc03 shows a reusable transition: when the POV shifts, lead with
a sensory anchor before advancing entity state.

## Open Questions for Next Chapter
Should ch02 leverage the pattern from ch01_sc03? Or let it rest and
return in ch03?
"""

BAD_MARKDOWN_NO_ARTIFACT = """---
chapter_num: 1
candidate_theses:
  - id: t1
    description: Generic finding.
---

# Chapter 01 Retrospective

## What Worked
ch01_sc01 went fine overall.

## What Drifted
ch01_sc02 went a bit off at points.

## Emerging Patterns
ch01_sc03 was interesting.

## Open Questions for Next Chapter
What next?
"""


def _patch_tenacity_wait_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    fast = tenacity.wait_fixed(0)
    monkeypatch.setattr(
        OpusRetrospectiveWriter._call_opus_inner.retry, "wait", fast
    )


# --------------------------------------------------------------------- #
# Tests                                                                 #
# --------------------------------------------------------------------- #


def test_A_protocol_conformance() -> None:
    fake = _FakeAnthropicClient(side_effect=[GOOD_MARKDOWN])
    logger = _FakeEventLogger()
    writer = OpusRetrospectiveWriter(anthropic_client=fake, event_logger=logger)
    assert isinstance(writer, RetrospectiveWriter)


def test_B_lint_pass_first_try() -> None:
    fake = _FakeAnthropicClient(side_effect=[GOOD_MARKDOWN])
    logger = _FakeEventLogger()
    writer = OpusRetrospectiveWriter(anthropic_client=fake, event_logger=logger)
    retro = writer.write(
        chapter_text="ch01 committed body",
        chapter_events=[],
        prior_retros=[],
    )
    assert isinstance(retro, Retrospective)
    assert retro.chapter_num == 1
    assert len(logger.events) == 1
    event = logger.events[0]
    assert event.role == "retrospective_writer"
    assert event.caller_context["lint_retries"] == 0
    assert event.caller_context["lint_pass"] is True


def test_C_lint_fail_then_pass_on_retry() -> None:
    fake = _FakeAnthropicClient(
        side_effect=[BAD_MARKDOWN_NO_ARTIFACT, GOOD_MARKDOWN]
    )
    logger = _FakeEventLogger()
    writer = OpusRetrospectiveWriter(anthropic_client=fake, event_logger=logger)
    retro = writer.write(
        chapter_text="ch01 committed body",
        chapter_events=[],
        prior_retros=[],
    )
    assert isinstance(retro, Retrospective)
    assert fake.messages.call_count == 2
    assert len(logger.events) == 1
    event = logger.events[0]
    assert event.caller_context["lint_retries"] == 1
    assert event.caller_context["lint_pass"] is True
    first_fail_reasons = event.extra.get("first_fail_reasons")
    assert isinstance(first_fail_reasons, list)
    assert "missing_critic_artifact" in first_fail_reasons


def test_D_lint_fail_twice_logs_and_commits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = _FakeAnthropicClient(
        side_effect=[BAD_MARKDOWN_NO_ARTIFACT, BAD_MARKDOWN_NO_ARTIFACT]
    )
    logger = _FakeEventLogger()
    writer = OpusRetrospectiveWriter(anthropic_client=fake, event_logger=logger)
    with caplog.at_level(logging.WARNING):
        retro = writer.write(
            chapter_text="ch01 committed body",
            chapter_events=[],
            prior_retros=[],
        )
    assert isinstance(retro, Retrospective)
    assert fake.messages.call_count == 2
    assert len(logger.events) == 1
    event = logger.events[0]
    assert event.caller_context["lint_retries"] == 1
    assert event.caller_context["lint_pass"] is False
    lint_reasons = event.extra.get("lint_reasons_if_failed")
    assert isinstance(lint_reasons, list)
    assert lint_reasons
    assert any(
        "retrospective lint failed twice" in rec.message for rec in caplog.records
    )


def test_E_markdown_parse_shape() -> None:
    fake = _FakeAnthropicClient(side_effect=[GOOD_MARKDOWN])
    logger = _FakeEventLogger()
    writer = OpusRetrospectiveWriter(anthropic_client=fake, event_logger=logger)
    retro = writer.write(
        chapter_text="ch01 body",
        chapter_events=[],
        prior_retros=[],
    )
    assert retro.chapter_num == 1
    assert retro.what_worked != ""
    assert retro.what_didnt != ""
    assert retro.pattern != ""
    assert len(retro.candidate_theses) >= 1


def test_F_generation_failure_ungated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_tenacity_wait_fast(monkeypatch)
    import httpx

    req = httpx.Request("POST", "https://fake/claude")
    exc = APIConnectionError(message="fake network error", request=req)
    fake = _FakeAnthropicClient(side_effect=[exc, exc, exc])
    logger = _FakeEventLogger()
    writer = OpusRetrospectiveWriter(anthropic_client=fake, event_logger=logger)
    with caplog.at_level(logging.WARNING):
        retro = writer.write(
            chapter_text="ch01 body",
            chapter_events=[],
            prior_retros=[],
        )
    assert isinstance(retro, Retrospective)
    assert retro.what_worked == "(generation failed)"
    assert "fake network error" in retro.what_didnt
    assert retro.candidate_theses == []
    assert len(logger.events) == 1
    event = logger.events[0]
    assert event.role == "retrospective_writer"
    assert event.extra.get("status") == "error"
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)
