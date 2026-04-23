"""Tests for book_pipeline.drafter.mode_b.ModeBDrafter (Plan 05-01 Task 2).

D-01: Clone-not-abstract — no import from mode_a.py.
D-02: Opus 4.7 + cache_control.ttl='1h' on preserved _system_blocks.
D-03: Voice-samples validation (>=3 passages, 400-600 words / slack 300-700).
D-04: Protocol conformance + B-3 voice_pin_sha passthrough invariant.

All tests use FakeAnthropicClient from tests/conftest.py — no real Anthropic.
Tenacity wait monkeypatched to wait_fixed(0) to keep wall-time <1s.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
import tenacity

from book_pipeline.config.voice_pin import VllmServeConfig, VoicePinData
from book_pipeline.interfaces.drafter import Drafter
from book_pipeline.interfaces.types import (
    ContextPack,
    DraftRequest,
    Event,
    RetrievalHit,
    RetrievalResult,
    SceneRequest,
)

# --- fakes ------------------------------------------------------------ #


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


@dataclass
class _FakeVoicePin:
    checkpoint_sha: str = "f" * 64


def _pin() -> VoicePinData:
    return VoicePinData(
        source_repo="paul-thinkpiece-pipeline",
        source_commit_sha="abc123",
        ft_run_id="v6_qwen3_32b",
        checkpoint_path="/tmp/fake-adapter",
        checkpoint_sha="f" * 64,
        base_model="Qwen/Qwen3-32B",
        trained_on_date="2026-04-14",
        pinned_on_date="2026-04-22",
        pinned_reason="test",
        vllm_serve_config=VllmServeConfig(
            port=8002, max_model_len=8192, dtype="bfloat16", tensor_parallel_size=1
        ),
    )


def _context_pack() -> ContextPack:
    scene_request = SceneRequest(
        chapter=1,
        scene_index=2,
        pov="Tonantzin",
        date_iso="1531-12-09",
        location="Tepeyac hill",
        beat_function="discovery",
        preceding_scene_summary=None,
    )
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
        scene_request=scene_request,
        retrievals={"historical": hist},
        total_bytes=80,
        assembly_strategy="round_robin",
        fingerprint="ctxfp-1-2",
    )


def _valid_voice_samples() -> list[str]:
    """3 passages, each ~500 words (within 400-600 band)."""
    return [
        " ".join(["voiceword"] * 500),
        " ".join(["toneword"] * 500),
        " ".join(["essayword"] * 500),
    ]


def _patch_tenacity_wait_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap tenacity wait on ModeBDrafter._call_opus_inner for wait_fixed(0).

    Clones Plan 03-06 pattern from tests/regenerator/test_scene_local.py.
    """
    from book_pipeline.drafter.mode_b import ModeBDrafter

    fast = tenacity.wait_fixed(0)
    monkeypatch.setattr(
        ModeBDrafter._call_opus_inner.retry, "wait", fast
    )


def _build_drafter(
    *,
    anthropic_client: Any | None = None,
    event_logger: Any | None = None,
    voice_samples: list[str] | None = None,
) -> tuple[Any, _FakeEventLogger]:
    from book_pipeline.drafter.mode_b import ModeBDrafter
    from tests.conftest import FakeAnthropicClient

    client = anthropic_client if anthropic_client is not None else FakeAnthropicClient()
    logger = event_logger if event_logger is not None else _FakeEventLogger()
    samples = voice_samples if voice_samples is not None else _valid_voice_samples()
    drafter = ModeBDrafter(
        anthropic_client=client,
        event_logger=logger,
        voice_pin=_pin(),
        voice_samples=samples,
    )
    return drafter, logger


# --- Tests ------------------------------------------------------------ #


def test_protocol_conformance(monkeypatch: pytest.MonkeyPatch) -> None:
    """ModeBDrafter satisfies Drafter Protocol + mode class attr == 'B'."""
    _patch_tenacity_wait_fast(monkeypatch)
    drafter, _ = _build_drafter()
    assert isinstance(drafter, Drafter)
    assert drafter.mode == "B"


def test_system_blocks_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """_system_blocks is the same Python list object across draft() calls.

    Byte-identical cache prefix → Anthropic 1h ephemeral cache hits on
    request #2+ (Pitfall 1)."""
    from tests.conftest import FakeAnthropicClient

    _patch_tenacity_wait_fast(monkeypatch)
    client = FakeAnthropicClient(text="A scene.")
    drafter, _ = _build_drafter(anthropic_client=client)
    req = DraftRequest(context_pack=_context_pack())
    first_id = id(drafter._system_blocks)
    drafter.draft(req)
    assert id(drafter._system_blocks) == first_id
    drafter.draft(req)
    assert id(drafter._system_blocks) == first_id


def test_cache_control_on_system() -> None:
    """The one-and-only system block carries cache_control ephemeral 1h."""
    drafter, _ = _build_drafter()
    assert len(drafter._system_blocks) == 1
    block = drafter._system_blocks[0]
    assert block["type"] == "text"
    assert block["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_voice_samples_validation_rejects_few() -> None:
    """D-03: <3 passages → RuntimeError mentioning >=3."""
    from book_pipeline.drafter.mode_b import ModeBDrafter
    from tests.conftest import FakeAnthropicClient

    with pytest.raises(RuntimeError, match=r">=3 curated voice samples"):
        ModeBDrafter(
            anthropic_client=FakeAnthropicClient(),
            event_logger=_FakeEventLogger(),
            voice_pin=_pin(),
            voice_samples=[
                " ".join(["w"] * 500),
                " ".join(["w"] * 500),
            ],
        )


def test_voice_samples_validation_rejects_short() -> None:
    """D-03: sample with <300 words → RuntimeError mentioning word_count + 400-600."""
    from book_pipeline.drafter.mode_b import ModeBDrafter
    from tests.conftest import FakeAnthropicClient

    with pytest.raises(RuntimeError, match=r"word_count"):
        ModeBDrafter(
            anthropic_client=FakeAnthropicClient(),
            event_logger=_FakeEventLogger(),
            voice_pin=_pin(),
            voice_samples=[
                " ".join(["w"] * 50),  # 50 words — way under
                " ".join(["w"] * 500),
                " ".join(["w"] * 500),
            ],
        )


def test_tenacity_exhaustion_raises_ModeBDrafterBlocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After 5 tenacity retries, Mode-B raises ModeBDrafterBlocked(anthropic_transient_exhausted)."""
    from book_pipeline.drafter.mode_b import ModeBDrafterBlocked
    from tests.conftest import FakeAnthropicClient

    _patch_tenacity_wait_fast(monkeypatch)
    # fail_n_times=10 → tenacity will see APIConnectionError every call, exhaust 5 attempts.
    client = FakeAnthropicClient(fail_n_times=10)
    drafter, _ = _build_drafter(anthropic_client=client)
    req = DraftRequest(context_pack=_context_pack())
    with pytest.raises(ModeBDrafterBlocked) as exc_info:
        drafter.draft(req)
    assert exc_info.value.reason == "anthropic_transient_exhausted"


def test_single_event_per_call_mode_b(monkeypatch: pytest.MonkeyPatch) -> None:
    """One draft() → 1 Event with role='drafter', mode='B', model='claude-opus-4-7',
    cached_tokens from resp.usage.cache_read_input_tokens."""
    from tests.conftest import FakeAnthropicClient, FakeAnthropicUsage

    _patch_tenacity_wait_fast(monkeypatch)
    usage = FakeAnthropicUsage(
        input_tokens=150,
        output_tokens=600,
        cache_read_input_tokens=42,
    )
    client = FakeAnthropicClient(text="A scene.", usage=usage)
    drafter, logger = _build_drafter(anthropic_client=client)
    drafter.draft(DraftRequest(context_pack=_context_pack()))
    drafter_events = [e for e in logger.events if e.role == "drafter"]
    assert len(drafter_events) == 1
    ev = drafter_events[0]
    assert ev.mode == "B"
    assert ev.model == "claude-opus-4-7"
    assert ev.cached_tokens == 42
    assert ev.input_tokens == 150
    assert ev.output_tokens == 600


def test_voice_pin_sha_passthrough_B3(monkeypatch: pytest.MonkeyPatch) -> None:
    """B-3 invariant: DraftResponse.voice_pin_sha == voice_pin.checkpoint_sha."""
    _patch_tenacity_wait_fast(monkeypatch)
    drafter, _ = _build_drafter()
    response = drafter.draft(DraftRequest(context_pack=_context_pack()))
    assert response.voice_pin_sha == _pin().checkpoint_sha
    assert response.mode == "B"


def test_error_event_emitted_on_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenacity exhaustion → 1 error Event emitted BEFORE raising (ADR-003)."""
    from book_pipeline.drafter.mode_b import ModeBDrafterBlocked
    from tests.conftest import FakeAnthropicClient

    _patch_tenacity_wait_fast(monkeypatch)
    client = FakeAnthropicClient(fail_n_times=10)
    drafter, logger = _build_drafter(anthropic_client=client)
    with pytest.raises(ModeBDrafterBlocked):
        drafter.draft(DraftRequest(context_pack=_context_pack()))
    error_events = [
        e for e in logger.events
        if e.role == "drafter" and e.extra.get("status") == "error"
    ]
    assert len(error_events) == 1
    assert error_events[0].mode == "B"
    assert error_events[0].extra["error_reason"] == "anthropic_transient_exhausted"
