"""Tests for SceneLocalRegenerator (Plan 03-06, REGEN-01).

Task 1 (Tests 1-4): Jinja2 template render + exception shapes — no Anthropic
call path exercised (SceneLocalRegenerator.regenerate() is filled in Task 2;
Task 1 lands the skeleton + template + exceptions).

Task 2 (Tests 5-12): SceneLocalRegenerator.regenerate() end-to-end with
FakeAnthropicClient, covering success, word-count guard boundary, issue
severity grouping, tenacity exhaustion, empty regen, Protocol conformance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import tenacity
from anthropic import APIConnectionError
from jinja2 import Environment, FileSystemLoader

from book_pipeline.interfaces.regenerator import Regenerator
from book_pipeline.interfaces.types import (
    ContextPack,
    CriticIssue,
    DraftResponse,
    Event,
    RegenRequest,
    RetrievalHit,
    RetrievalResult,
    SceneRequest,
)
from book_pipeline.regenerator import (
    RegeneratorUnavailable,
    RegenWordCountDrift,
    SceneLocalRegenerator,
)

TEMPLATE_PATH = Path("src/book_pipeline/regenerator/templates/regen.j2")


# --- shared fixtures --------------------------------------------------- #


def _render_template(**kwargs: Any) -> str:
    """Render the regen.j2 template directly (no SceneLocalRegenerator needed)."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_PATH.parent)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(TEMPLATE_PATH.name)
    return template.render(**kwargs)


def _issue(
    axis: str = "historical",
    severity: str = "high",
    location: str = "paragraph 1",
    claim: str = "date error",
    evidence: str = "corpus hist_brief_042",
    citation: str | None = "hist_brief_042",
) -> CriticIssue:
    return CriticIssue(
        axis=axis,
        severity=severity,
        location=location,
        claim=claim,
        evidence=evidence,
        citation=citation,
    )


def _scene_request(chapter: int = 1, scene_index: int = 1) -> SceneRequest:
    return SceneRequest(
        chapter=chapter,
        scene_index=scene_index,
        pov="Tonantzin",
        date_iso="1531-12-09",
        location="Tepeyac hill",
        beat_function="discovery",
    )


def _context_pack(chapter: int = 1, scene_index: int = 1) -> ContextPack:
    hist = RetrievalResult(
        retriever_name="historical",
        hits=[
            RetrievalHit(
                text="In December 1531, Spanish friars were consolidating in Mexico City.",
                source_path="canon/historical/1531.md",
                chunk_id="hist:001",
                score=0.8,
                metadata={},
            )
        ],
        bytes_used=80,
        query_fingerprint="qfp1",
    )
    return ContextPack(
        scene_request=_scene_request(chapter, scene_index),
        retrievals={"historical": hist},
        total_bytes=80,
        assembly_strategy="round_robin",
        fingerprint="ctxfp-" + str(chapter) + "-" + str(scene_index),
    )


def _make_prior_draft(*, word_count: int = 500) -> DraftResponse:
    """Build a DraftResponse with a scene_text of exactly `word_count` tokens."""
    words = ["lorem"] * word_count
    scene_text = " ".join(words)
    return DraftResponse(
        scene_text=scene_text,
        mode="A",
        model_id="paul-voice",
        voice_pin_sha="f" * 64,
        tokens_in=100,
        tokens_out=500,
        latency_ms=100,
        output_sha="deadbeef",
        attempt_number=1,
    )


def _make_regen_request(
    *,
    prior_draft: DraftResponse | None = None,
    issues: list[CriticIssue] | None = None,
    attempt_number: int = 2,
    max_attempts: int = 3,
) -> RegenRequest:
    return RegenRequest(
        prior_draft=prior_draft if prior_draft is not None else _make_prior_draft(),
        context_pack=_context_pack(),
        issues=issues if issues is not None else [_issue()],
        attempt_number=attempt_number,
        max_attempts=max_attempts,
    )


# --- FakeAnthropicClient ---------------------------------------------- #


@dataclass
class _FakeUsage:
    input_tokens: int = 1500
    output_tokens: int = 600

    def model_dump(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[_FakeTextBlock]
    usage: _FakeUsage = field(default_factory=_FakeUsage)
    id: str = "msg_regen_01"
    model: str = "claude-opus-4-7"
    role: str = "assistant"
    type: str = "message"
    stop_reason: str = "end_turn"

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {
            "id": self.id,
            "model": self.model,
            "role": self.role,
            "type": self.type,
            "stop_reason": self.stop_reason,
            "usage": self.usage.model_dump(),
            "content": [{"type": b.type, "text": b.text} for b in self.content],
        }


class _FakeMessages:
    """Captures messages.create call args; returns a canned _FakeMessage."""

    def __init__(
        self,
        *,
        text: str | None = None,
        side_effect: list[Any] | None = None,
        usage: _FakeUsage | None = None,
    ) -> None:
        self._text = text
        self._side_effect = list(side_effect) if side_effect is not None else None
        self._usage = usage or _FakeUsage()
        self.call_args_list: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.call_args_list.append(kwargs)
        if self._side_effect is not None:
            effect = self._side_effect.pop(0)
            if isinstance(effect, Exception):
                raise effect
            if isinstance(effect, _FakeMessage):
                return effect
            # Treat a plain str as the regen text for that call.
            if isinstance(effect, str):
                return _FakeMessage(
                    content=[_FakeTextBlock(text=effect)], usage=self._usage
                )
            return effect
        text = self._text if self._text is not None else ""
        return _FakeMessage(content=[_FakeTextBlock(text=text)], usage=self._usage)


class _FakeAnthropicClient:
    def __init__(
        self,
        *,
        text: str | None = None,
        side_effect: list[Any] | None = None,
        usage: _FakeUsage | None = None,
    ) -> None:
        self.messages = _FakeMessages(
            text=text, side_effect=side_effect, usage=usage
        )


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


@dataclass
class _FakeVoicePin:
    checkpoint_sha: str = "f" * 64


def _patch_tenacity_wait_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reach into the retry instance attr on SceneLocalRegenerator._call_opus_inner
    to swap out the production exp-backoff for wait_fixed(0). Same mechanism as
    Plan 03-05's test_scene_critic._patch_tenacity_wait_fast."""
    fast = tenacity.wait_fixed(0)
    monkeypatch.setattr(
        SceneLocalRegenerator._call_opus_inner.retry, "wait", fast
    )


def _build_regenerator(
    *,
    anthropic_client: Any | None = None,
    event_logger: Any | None = None,
    voice_pin: Any | None = None,
) -> tuple[SceneLocalRegenerator, _FakeEventLogger]:
    client = anthropic_client if anthropic_client is not None else _FakeAnthropicClient()
    logger = event_logger if event_logger is not None else _FakeEventLogger()
    pin = voice_pin if voice_pin is not None else _FakeVoicePin()
    regenerator = SceneLocalRegenerator(
        anthropic_client=client,
        event_logger=logger,
        voice_pin=pin,
    )
    return regenerator, logger


# ============================================================ #
# Task 1 tests — template render + exception shapes            #
# ============================================================ #


def test_regen_template_renders() -> None:
    """Test 1: Jinja2 render of regen.j2 with HIGH + MID issues (no LOW)
    produces expected sections."""
    prior_scene_text = "The quiet hill stood above the valley. Paul thought about it."
    severity_grouped_issues = {
        "high": [_issue(severity="high", claim="high claim A")],
        "mid": [_issue(severity="mid", claim="mid claim B")],
        "low": [],
    }
    rendered = _render_template(
        prior_scene_text=prior_scene_text,
        severity_grouped_issues=severity_grouped_issues,
        word_count_target=500,
        scene_request=_scene_request(),
        voice_description="Paul writes in clean declarative prose.",
        retrievals=_context_pack().retrievals,
    )
    assert "===SYSTEM===" in rendered
    assert "===USER===" in rendered
    assert prior_scene_text in rendered
    assert "high claim A" in rendered
    assert "mid claim B" in rendered
    assert "Low-severity context" not in rendered


def test_regen_template_low_severity_block() -> None:
    """Test 2: Jinja2 render WITH low-severity issues produces
    the 'Low-severity context' block."""
    severity_grouped_issues = {
        "high": [_issue(severity="high", claim="high claim A")],
        "mid": [],
        "low": [_issue(severity="low", claim="low claim C")],
    }
    rendered = _render_template(
        prior_scene_text="short prior scene",
        severity_grouped_issues=severity_grouped_issues,
        word_count_target=500,
        scene_request=_scene_request(),
        voice_description="vd",
        retrievals=_context_pack().retrievals,
    )
    assert "Low-severity context (don't chase):" in rendered
    assert "low claim C" in rendered


def test_regen_word_count_drift_exception() -> None:
    """Test 3: RegenWordCountDrift carries prior/new/drift attrs and __str__
    is informative (grep-able in logs)."""
    exc = RegenWordCountDrift(1000, 200, 0.8)
    assert exc.prior_word_count == 1000
    assert exc.new_word_count == 200
    assert exc.drift_pct == pytest.approx(0.8)
    message = str(exc)
    assert "1000" in message
    assert "200" in message
    assert "0.8" in message or "0.800" in message


def test_regenerator_unavailable_exception() -> None:
    """Test 4: RegeneratorUnavailable surfaces reason + sorted context keys."""
    exc = RegeneratorUnavailable(
        "anthropic_unavailable",
        scene_id="ch01_sc01",
        cause="connection reset",
    )
    assert exc.reason == "anthropic_unavailable"
    assert exc.context == {"scene_id": "ch01_sc01", "cause": "connection reset"}
    message = str(exc)
    assert "anthropic_unavailable" in message
    assert "cause" in message
    assert "scene_id" in message


# ============================================================ #
# Task 2 tests — regenerate() end-to-end + Protocol conformance
# ============================================================ #


def _scene_text_with_wc(wc: int) -> str:
    return " ".join(["word"] * wc)


def test_regenerate_happy_path_preserves_voice_pin_and_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 5: regenerate() returns a DraftResponse with voice_pin_sha
    preserved from prior_draft + attempt_number == request.attempt_number."""
    _patch_tenacity_wait_fast(monkeypatch)
    prior = _make_prior_draft(word_count=500)
    new_text = _scene_text_with_wc(505)  # 1% drift, within ±10%
    client = _FakeAnthropicClient(text=new_text)
    regenerator, _ = _build_regenerator(anthropic_client=client)

    request = _make_regen_request(prior_draft=prior, attempt_number=2)
    response = regenerator.regenerate(request)

    assert isinstance(response, DraftResponse)
    assert response.scene_text == new_text
    assert response.mode == "A"
    assert response.model_id == "claude-opus-4-7"
    assert response.voice_pin_sha == prior.voice_pin_sha
    assert response.attempt_number == 2
    assert response.latency_ms >= 1
    assert response.tokens_in == 1500
    assert response.tokens_out == 600


def test_regenerate_emits_one_regenerator_event_with_expected_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 6: regenerate() emits exactly 1 role='regenerator' Event with
    mode='A', checkpoint_sha=prior.voice_pin_sha, issue_count counts ONLY
    mid+high (excludes low)."""
    _patch_tenacity_wait_fast(monkeypatch)
    prior = _make_prior_draft(word_count=500)
    new_text = _scene_text_with_wc(500)
    client = _FakeAnthropicClient(text=new_text)
    regenerator, logger = _build_regenerator(anthropic_client=client)

    issues = [
        _issue(axis="historical", severity="high"),
        _issue(axis="entity", severity="mid"),
        _issue(axis="metaphysics", severity="mid"),
        _issue(axis="arc", severity="low"),
        _issue(axis="donts", severity="low"),
    ]
    request = _make_regen_request(prior_draft=prior, issues=issues, attempt_number=3)
    regenerator.regenerate(request)

    regen_events = [e for e in logger.events if e.role == "regenerator"]
    assert len(regen_events) == 1
    ev = regen_events[0]
    assert ev.mode == "A"
    assert ev.checkpoint_sha == prior.voice_pin_sha
    assert ev.caller_context["attempt_number"] == 3
    # Only mid+high (1 high + 2 mid = 3) — not the 2 low.
    assert ev.caller_context["issue_count"] == 3
    assert ev.caller_context["voice_pin_sha"] == prior.voice_pin_sha
    assert ev.caller_context["scene_id"] == "ch01_sc01"
    assert "word_count_drift_pct" in ev.caller_context
    assert "regen_token_count" in ev.caller_context
    assert ev.caller_context["regen_token_count"] == 600


def test_regenerate_word_count_drift_over_limit_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 7: word-count drift > 10% (200 new vs 1000 prior = 80% drift)
    raises RegenWordCountDrift AND emits an error Event with
    extra.status='error' + extra.error='word_count_drift' + drift_pct ≈ 0.8."""
    _patch_tenacity_wait_fast(monkeypatch)
    prior = _make_prior_draft(word_count=1000)
    new_text = _scene_text_with_wc(200)  # 80% drift
    client = _FakeAnthropicClient(text=new_text)
    regenerator, logger = _build_regenerator(anthropic_client=client)
    request = _make_regen_request(prior_draft=prior, attempt_number=2)

    with pytest.raises(RegenWordCountDrift) as exc_info:
        regenerator.regenerate(request)

    assert exc_info.value.prior_word_count == 1000
    assert exc_info.value.new_word_count == 200
    assert exc_info.value.drift_pct == pytest.approx(0.8)

    error_events = [
        e for e in logger.events
        if e.role == "regenerator" and e.extra.get("status") == "error"
    ]
    assert len(error_events) == 1
    err_ev = error_events[0]
    assert err_ev.extra["error"] == "word_count_drift"
    assert err_ev.extra["drift_pct"] == pytest.approx(0.8)
    assert err_ev.extra["prior_wc"] == 1000
    assert err_ev.extra["new_wc"] == 200


def test_regenerate_word_count_drift_within_boundary_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 8: 5% drift (1050 new vs 1000 prior) is WITHIN the ±10% band →
    no raise; DraftResponse returned normally."""
    _patch_tenacity_wait_fast(monkeypatch)
    prior = _make_prior_draft(word_count=1000)
    new_text = _scene_text_with_wc(1050)  # 5% drift
    client = _FakeAnthropicClient(text=new_text)
    regenerator, _ = _build_regenerator(anthropic_client=client)

    response = regenerator.regenerate(_make_regen_request(prior_draft=prior))
    assert isinstance(response, DraftResponse)
    assert len(response.scene_text.split()) == 1050


def test_regenerate_issues_grouped_correctly_in_prompt_and_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 9: 1 high + 2 mid + 3 low → prompt rendered with all high+mid
    issues in their sections; low issues appear in 'Low-severity context';
    Event.caller_context.issue_count == 3 (high+mid only)."""
    _patch_tenacity_wait_fast(monkeypatch)
    prior = _make_prior_draft(word_count=500)
    new_text = _scene_text_with_wc(500)
    client = _FakeAnthropicClient(text=new_text)
    regenerator, logger = _build_regenerator(anthropic_client=client)

    issues = [
        _issue(axis="historical", severity="high", claim="HIGH-A"),
        _issue(axis="entity", severity="mid", claim="MID-B"),
        _issue(axis="arc", severity="mid", claim="MID-C"),
        _issue(axis="metaphysics", severity="low", claim="LOW-D"),
        _issue(axis="donts", severity="low", claim="LOW-E"),
        _issue(axis="historical", severity="low", claim="LOW-F"),
    ]
    request = _make_regen_request(prior_draft=prior, issues=issues)
    regenerator.regenerate(request)

    # Inspect the rendered prompt that Opus was shown.
    call_kwargs = client.messages.call_args_list[0]
    system_text = call_kwargs["system"]
    user_text = call_kwargs["messages"][0]["content"]
    combined = system_text + "\n" + user_text

    for claim in ("HIGH-A", "MID-B", "MID-C"):
        assert claim in combined, f"{claim} missing from regen prompt"
    assert "Low-severity context (don't chase):" in combined
    for claim in ("LOW-D", "LOW-E", "LOW-F"):
        assert claim in combined, f"{claim} missing from low-severity block"

    regen_event = next(e for e in logger.events if e.role == "regenerator")
    assert regen_event.caller_context["issue_count"] == 3


def test_regenerate_anthropic_connection_error_exhausts_tenacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 10: APIConnectionError x5 → tenacity exhausts →
    RegeneratorUnavailable('anthropic_unavailable') raised; error Event emitted;
    no success Event; no DraftResponse."""
    _patch_tenacity_wait_fast(monkeypatch)
    side_effect = [APIConnectionError(request=None) for _ in range(5)]  # type: ignore[arg-type]
    client = _FakeAnthropicClient(side_effect=side_effect)
    regenerator, logger = _build_regenerator(anthropic_client=client)

    with pytest.raises(RegeneratorUnavailable) as exc_info:
        regenerator.regenerate(_make_regen_request())
    assert exc_info.value.reason == "anthropic_unavailable"

    # Success events: 0. Error events: 1.
    success_events = [
        e for e in logger.events
        if e.role == "regenerator" and e.extra.get("status") != "error"
    ]
    assert success_events == []
    error_events = [
        e for e in logger.events
        if e.role == "regenerator" and e.extra.get("status") == "error"
    ]
    assert len(error_events) == 1
    assert error_events[0].extra["error"] == "anthropic_unavailable"


def test_regenerate_empty_response_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 11: empty response.content[0].text → RegeneratorUnavailable
    ('empty_regen_response'); error Event emitted."""
    _patch_tenacity_wait_fast(monkeypatch)
    client = _FakeAnthropicClient(text="")
    regenerator, logger = _build_regenerator(anthropic_client=client)

    with pytest.raises(RegeneratorUnavailable) as exc_info:
        regenerator.regenerate(_make_regen_request())
    assert exc_info.value.reason == "empty_regen_response"

    error_events = [
        e for e in logger.events
        if e.role == "regenerator" and e.extra.get("status") == "error"
    ]
    assert len(error_events) == 1
    assert error_events[0].extra["error"] == "empty_regen_response"


def test_regenerator_is_regenerator_protocol() -> None:
    """Test 12: isinstance(r, Regenerator) True (FROZEN Protocol conformance)."""
    regenerator, _ = _build_regenerator()
    assert isinstance(regenerator, Regenerator)
    assert hasattr(regenerator, "regenerate")
