"""Tests for OpusEntityExtractor (Plan 04-03 Task 1 — CORPUS-02).

Covers tests A-H per plan <behavior>:
  A — Protocol conformance (isinstance(e, EntityExtractor) True).
  B — source_chapter_sha stamping (defense-in-depth override).
  C — Incremental filter: unchanged prior entity is NOT re-returned.
  D — Incremental flag: changed prior entity IS re-returned.
  E — Exactly 1 Event emitted per extract() call (success XOR error).
  F — Empty chapter_text raises EntityExtractorBlocked WITHOUT calling Fake.
  G — Tenacity 3x exhaustion fast (<1s) with wait patch; 1 error Event.
  H — Prior-cards summary injected into the Opus user prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import tenacity
from anthropic import APIConnectionError

from book_pipeline.entity_extractor.opus import (
    EntityExtractorBlocked,
    OpusEntityExtractor,
)
from book_pipeline.entity_extractor.schema import EntityExtractionResponse
from book_pipeline.interfaces.entity_extractor import EntityExtractor
from book_pipeline.interfaces.types import EntityCard

# --------------------------------------------------------------------- #
# Fakes                                                                 #
# --------------------------------------------------------------------- #


@dataclass
class _Usage:
    input_tokens: int = 500
    output_tokens: int = 200
    cache_read_input_tokens: int = 0

    def model_dump(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }


@dataclass
class _FakeParsedMessage:
    _parsed: EntityExtractionResponse
    id: str = "msg_fake_entity_01"
    type: str = "message"
    role: str = "assistant"
    model: str = "claude-opus-4-7"
    stop_reason: str = "end_turn"
    usage: _Usage = field(default_factory=_Usage)

    @property
    def parsed_output(self) -> EntityExtractionResponse:
        return self._parsed

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "role": self.role,
            "model": self.model,
            "stop_reason": self.stop_reason,
            "usage": self.usage.model_dump(),
            "parsed_output_dump": self._parsed.model_dump(),
        }


class _FakeMessages:
    def __init__(
        self,
        parsed_response: EntityExtractionResponse | None = None,
        side_effect: list[Any] | None = None,
    ) -> None:
        self._parsed_response = parsed_response
        self._side_effect = list(side_effect) if side_effect is not None else None
        self.call_args_list: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.call_args_list)

    def parse(self, **kwargs: Any) -> _FakeParsedMessage:
        self.call_args_list.append(kwargs)
        if self._side_effect is not None:
            effect = self._side_effect.pop(0)
            if isinstance(effect, Exception):
                raise effect
            if isinstance(effect, EntityExtractionResponse):
                return _FakeParsedMessage(_parsed=effect)
            return effect  # type: ignore[return-value]
        assert self._parsed_response is not None
        return _FakeParsedMessage(_parsed=self._parsed_response)


class _FakeAnthropicClient:
    def __init__(
        self,
        parsed_response: EntityExtractionResponse | None = None,
        side_effect: list[Any] | None = None,
    ) -> None:
        self.messages = _FakeMessages(
            parsed_response=parsed_response,
            side_effect=side_effect,
        )


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


# --------------------------------------------------------------------- #
# Helpers                                                               #
# --------------------------------------------------------------------- #


def _card(
    *,
    name: str,
    chapter: int = 1,
    state: dict[str, object] | None = None,
    source_chapter_sha: str = "placeholder_sha",
) -> EntityCard:
    return EntityCard(
        entity_name=name,
        last_seen_chapter=chapter,
        state=state or {},
        evidence_spans=[],
        source_chapter_sha=source_chapter_sha,
    )


def _response(
    *,
    entities: list[EntityCard],
    chapter_num: int = 1,
    extraction_timestamp: str = "2026-04-23T00:00:00Z",
) -> EntityExtractionResponse:
    return EntityExtractionResponse(
        entities=entities,
        chapter_num=chapter_num,
        extraction_timestamp=extraction_timestamp,
    )


def _patch_tenacity_wait_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    fast = tenacity.wait_fixed(0)
    monkeypatch.setattr(
        OpusEntityExtractor._call_opus_inner.retry, "wait", fast
    )


# --------------------------------------------------------------------- #
# Tests                                                                 #
# --------------------------------------------------------------------- #


def test_A_protocol_conformance() -> None:
    fake = _FakeAnthropicClient(parsed_response=_response(entities=[]))
    logger = _FakeEventLogger()
    extractor = OpusEntityExtractor(
        anthropic_client=fake,
        event_logger=logger,
    )
    assert isinstance(extractor, EntityExtractor)


def test_B_source_chapter_sha_stamped() -> None:
    """Defense-in-depth: every returned card has source_chapter_sha == arg."""
    fake = _FakeAnthropicClient(
        parsed_response=_response(
            entities=[
                _card(name="Cortes", source_chapter_sha="WRONG_SHA"),
                _card(name="Motecuhzoma", source_chapter_sha=""),
            ]
        )
    )
    logger = _FakeEventLogger()
    extractor = OpusEntityExtractor(anthropic_client=fake, event_logger=logger)
    out = extractor.extract(
        chapter_text="chapter 1 body",
        chapter_num=1,
        chapter_sha="abc123",
        prior_cards=[],
    )
    assert len(out) == 2
    for card in out:
        assert card.source_chapter_sha == "abc123"


def test_C_incremental_filters_unchanged() -> None:
    """Prior Cortes (in Havana); Opus returns same Cortes + new Motecuhzoma.
    Result: only Motecuhzoma (new) is returned."""
    prior_cards = [
        _card(
            name="Cortes",
            state={"current_state": "in Havana"},
            source_chapter_sha="ch01_sha",
        )
    ]
    fake = _FakeAnthropicClient(
        parsed_response=_response(
            entities=[
                _card(name="Cortes", state={"current_state": "in Havana"}),
                _card(
                    name="Motecuhzoma",
                    state={"first_mentioned_chapter": 2},
                ),
            ],
            chapter_num=2,
        )
    )
    logger = _FakeEventLogger()
    extractor = OpusEntityExtractor(anthropic_client=fake, event_logger=logger)
    out = extractor.extract(
        chapter_text="chapter 2 body",
        chapter_num=2,
        chapter_sha="ch02_sha",
        prior_cards=prior_cards,
    )
    assert [c.entity_name for c in out] == ["Motecuhzoma"]


def test_D_incremental_flags_updated() -> None:
    """Prior Cortes (in Havana); Opus returns Cortes (in Veracruz).
    Result: 1 card — updated Cortes."""
    prior_cards = [
        _card(
            name="Cortes",
            state={"current_state": "in Havana"},
            source_chapter_sha="ch01_sha",
        )
    ]
    fake = _FakeAnthropicClient(
        parsed_response=_response(
            entities=[
                _card(name="Cortes", state={"current_state": "in Veracruz"}),
            ],
            chapter_num=2,
        )
    )
    logger = _FakeEventLogger()
    extractor = OpusEntityExtractor(anthropic_client=fake, event_logger=logger)
    out = extractor.extract(
        chapter_text="chapter 2 body",
        chapter_num=2,
        chapter_sha="ch02_sha",
        prior_cards=prior_cards,
    )
    assert len(out) == 1
    assert out[0].entity_name == "Cortes"
    assert out[0].state.get("current_state") == "in Veracruz"
    assert out[0].source_chapter_sha == "ch02_sha"


def test_E_one_event_emitted() -> None:
    """Success path: exactly 1 event, role='entity_extractor', caller_context
    has chapter_num + new_cards + updated_cards summing to len(out)."""
    fake = _FakeAnthropicClient(
        parsed_response=_response(
            entities=[
                _card(name="Cortes", state={"current_state": "in Veracruz"}),
                _card(name="Motecuhzoma", state={"first_mentioned_chapter": 2}),
            ],
            chapter_num=2,
        )
    )
    prior_cards = [
        _card(
            name="Cortes",
            state={"current_state": "in Havana"},
            source_chapter_sha="ch01_sha",
        )
    ]
    logger = _FakeEventLogger()
    extractor = OpusEntityExtractor(anthropic_client=fake, event_logger=logger)
    out = extractor.extract(
        chapter_text="chapter 2 body",
        chapter_num=2,
        chapter_sha="ch02_sha",
        prior_cards=prior_cards,
    )
    assert len(logger.events) == 1
    event = logger.events[0]
    assert event.role == "entity_extractor"
    assert event.caller_context["chapter_num"] == 2
    new_cards = event.caller_context["new_cards"]
    updated_cards = event.caller_context["updated_cards"]
    assert isinstance(new_cards, int)
    assert isinstance(updated_cards, int)
    assert new_cards + updated_cards == len(out)
    assert event.caller_context["prior_cards_count"] == 1
    assert event.caller_context["chapter_sha"] == "ch02_sha"


def test_F_empty_chapter_raises() -> None:
    """Empty/whitespace-only chapter_text raises EntityExtractorBlocked before
    Opus is called."""
    fake = _FakeAnthropicClient(parsed_response=_response(entities=[]))
    logger = _FakeEventLogger()
    extractor = OpusEntityExtractor(anthropic_client=fake, event_logger=logger)
    with pytest.raises(EntityExtractorBlocked) as exc_info:
        extractor.extract(
            chapter_text="\n\n",
            chapter_num=3,
            chapter_sha="ch03_sha",
            prior_cards=[],
        )
    assert exc_info.value.reason == "empty_chapter"
    assert fake.messages.call_count == 0


def test_G_tenacity_exhaustion_3x_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake raises APIConnectionError on every call; 3 retries; <1s with
    wait patch; 1 error Event emitted; EntityExtractorBlocked raised."""
    _patch_tenacity_wait_fast(monkeypatch)
    fake_request_response_req = __import__("httpx").Request(
        "POST", "https://fake/claude"
    )
    exc = APIConnectionError(
        message="fake connection error",
        request=fake_request_response_req,
    )
    fake = _FakeAnthropicClient(side_effect=[exc, exc, exc])
    logger = _FakeEventLogger()
    extractor = OpusEntityExtractor(anthropic_client=fake, event_logger=logger)
    import time

    start = time.monotonic()
    with pytest.raises(EntityExtractorBlocked) as exc_info:
        extractor.extract(
            chapter_text="chapter body",
            chapter_num=1,
            chapter_sha="ch01_sha",
            prior_cards=[],
        )
    elapsed = time.monotonic() - start
    assert exc_info.value.reason == "entity_extraction_failed"
    assert elapsed < 1.0
    assert fake.messages.call_count == 3
    # 1 error Event.
    assert len(logger.events) == 1
    event = logger.events[0]
    assert event.role == "entity_extractor"
    assert event.extra["status"] == "error"
    assert event.extra["attempts_made"] == 3


def test_H_prior_cards_injected_into_prompt() -> None:
    """Prior Cortes (in Havana); assert 'Cortes' AND 'in Havana' appear in
    the Opus user prompt — proves prior-summary injection."""
    prior_cards = [
        _card(
            name="Cortes",
            state={"current_state": "in Havana"},
            source_chapter_sha="ch01_sha",
        )
    ]
    fake = _FakeAnthropicClient(parsed_response=_response(entities=[]))
    logger = _FakeEventLogger()
    extractor = OpusEntityExtractor(anthropic_client=fake, event_logger=logger)
    extractor.extract(
        chapter_text="chapter 2 body",
        chapter_num=2,
        chapter_sha="ch02_sha",
        prior_cards=prior_cards,
    )
    assert fake.messages.call_count == 1
    kwargs = fake.messages.call_args_list[0]
    messages = kwargs["messages"]
    assert len(messages) == 1
    user_prompt = messages[0]["content"]
    assert "Cortes" in user_prompt
    assert "in Havana" in user_prompt
