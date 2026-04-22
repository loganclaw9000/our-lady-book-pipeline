"""Shared fixtures for tests/critic/* (Plan 03-05 Task 2).

Provides a FakeAnthropicClient that mimics anthropic.Anthropic().messages.parse
semantics (.parsed_output, .usage, model_dump()) without hitting the network,
plus a canonical CriticResponse fixture used across SceneCritic tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from book_pipeline.interfaces.types import (
    ContextPack,
    CriticIssue,
    CriticRequest,
    CriticResponse,
    RetrievalResult,
    SceneRequest,
)


def make_canonical_critic_response(
    *,
    overall_pass: bool = True,
    include_all_axes: bool = True,
    rubric_version: str = "v1",
    model_id: str = "claude-opus-4-7",
) -> CriticResponse:
    """Return a canonical CriticResponse for tests."""
    if include_all_axes:
        pass_per_axis = {
            "historical": overall_pass,
            "metaphysics": True,
            "entity": True,
            "arc": True,
            "donts": True,
        }
        scores_per_axis = {
            "historical": 92.0 if overall_pass else 45.0,
            "metaphysics": 88.0,
            "entity": 90.0,
            "arc": 89.0,
            "donts": 94.0,
        }
    else:
        # Omit 'metaphysics' to exercise the fill-in path.
        pass_per_axis = {
            "historical": True,
            "entity": True,
            "arc": True,
            "donts": True,
        }
        scores_per_axis = {
            "historical": 92.0,
            "entity": 90.0,
            "arc": 89.0,
            "donts": 94.0,
        }

    issues: list[CriticIssue] = []
    if not overall_pass:
        issues.append(
            CriticIssue(
                axis="historical",
                severity="high",
                location="paragraph 1",
                claim="date error",
                evidence="corpus hist_brief_042",
                citation="hist_brief_042",
            )
        )

    return CriticResponse(
        pass_per_axis=pass_per_axis,
        scores_per_axis=scores_per_axis,
        issues=issues,
        overall_pass=overall_pass,
        model_id=model_id,
        rubric_version=rubric_version,
        output_sha="will-be-overwritten",
    )


def make_scene_request(chapter: int = 1, scene_index: int = 1) -> SceneRequest:
    return SceneRequest(
        chapter=chapter,
        scene_index=scene_index,
        pov="Cortés",
        date_iso="1519-08-16",
        location="Cempoala",
        beat_function="first diplomatic contact",
    )


def make_context_pack(chapter: int = 1, scene_index: int = 1) -> ContextPack:
    return ContextPack(
        scene_request=make_scene_request(chapter, scene_index),
        retrievals={
            "historical": RetrievalResult(
                retriever_name="historical",
                hits=[],
                bytes_used=0,
                query_fingerprint="q_hist",
            ),
        },
        total_bytes=100,
        assembly_strategy="round_robin",
        fingerprint="ctxpack_fingerprint_1234",
    )


def make_critic_request(
    *,
    chapter: int = 1,
    scene_index: int = 1,
    rubric_version: str = "v1",
    attempt: int = 1,
) -> CriticRequest:
    return CriticRequest(
        scene_text="A curated scene about Malintzin translating at Cempoala.",
        context_pack=make_context_pack(chapter, scene_index),
        rubric_id="scene.v1",
        rubric_version=rubric_version,
        chapter_context={"attempt_number": attempt},
    )


@dataclass
class FakeUsage:
    input_tokens: int = 3500
    output_tokens: int = 900
    cache_read_input_tokens: int = 3000
    cache_creation_input_tokens: int = 0

    def model_dump(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
        }


@dataclass
class FakeParsedMessage:
    """Mimics anthropic.types.ParsedMessage enough for SceneCritic."""

    _parsed: CriticResponse
    id: str = "msg_fake_01"
    type: str = "message"
    role: str = "assistant"
    model: str = "claude-opus-4-7"
    stop_reason: str = "end_turn"
    usage: FakeUsage = field(default_factory=FakeUsage)

    @property
    def parsed_output(self) -> CriticResponse:
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


class FakeMessages:
    """Captures messages.parse call args; returns a canned FakeParsedMessage."""

    def __init__(
        self,
        parsed_response: CriticResponse | None = None,
        side_effect: list[Any] | None = None,
        usage: FakeUsage | None = None,
    ) -> None:
        self._parsed_response = parsed_response or make_canonical_critic_response()
        self._side_effect = list(side_effect) if side_effect is not None else None
        self._usage = usage or FakeUsage()
        self.call_args_list: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> FakeParsedMessage:
        self.call_args_list.append(kwargs)
        if self._side_effect is not None:
            effect = self._side_effect.pop(0)
            if isinstance(effect, Exception):
                raise effect
            if isinstance(effect, CriticResponse):
                return FakeParsedMessage(_parsed=effect, usage=self._usage)
            return effect
        return FakeParsedMessage(_parsed=self._parsed_response, usage=self._usage)


class FakeAnthropicClient:
    """Mimics anthropic.Anthropic() surface used by SceneCritic."""

    def __init__(
        self,
        parsed_response: CriticResponse | None = None,
        side_effect: list[Any] | None = None,
        usage: FakeUsage | None = None,
    ) -> None:
        self.messages = FakeMessages(
            parsed_response=parsed_response,
            side_effect=side_effect,
            usage=usage,
        )


class FakeEventLogger:
    """Captures emitted Events for test assertions."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)
