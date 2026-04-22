"""Tests for book_pipeline.drafter.mode_a.ModeADrafter (Plan 03-04 Task 2).

Protocol conformance + end-to-end draft flow + error-path Event emission +
voice-fidelity classification + scene_type dispatch.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from book_pipeline.config.voice_pin import VllmServeConfig, VoicePinData
from book_pipeline.drafter.memorization_gate import (
    MemorizationHit,
    TrainingBleedGate,
)
from book_pipeline.drafter.sampling_profiles import SamplingProfiles
from book_pipeline.drafter.vllm_client import VllmClient, VllmUnavailable
from book_pipeline.interfaces.drafter import Drafter
from book_pipeline.interfaces.types import (
    ContextPack,
    DraftRequest,
    Event,
    RetrievalHit,
    RetrievalResult,
    SceneRequest,
)

EMBEDDING_DIM = 1024


# --- Test doubles -----------------------------------------------------------


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class _FakeVllmClient:
    """VllmClient drop-in returning a canned chat_completion response.

    May be configured to raise VllmUnavailable on demand.
    """

    def __init__(
        self,
        *,
        scene_text: str = "The room was quiet. A single candle burned.",
        raise_on_completion: Exception | None = None,
    ) -> None:
        self.scene_text = scene_text
        self.raise_on_completion = raise_on_completion
        self.calls: list[dict[str, Any]] = []

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        temperature: float,
        top_p: float,
        max_tokens: int,
        repetition_penalty: float | None = None,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "repetition_penalty": repetition_penalty,
                "stop": stop,
            }
        )
        if self.raise_on_completion is not None:
            raise self.raise_on_completion
        return {
            "choices": [
                {"message": {"content": self.scene_text}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 42,
                "completion_tokens": 128,
                "total_tokens": 170,
            },
            "model": model,
        }


class _FakeAnchorProvider:
    """AnchorSetProvider drop-in that returns a fixed centroid."""

    def __init__(self, *, centroid: np.ndarray | None = None, sha: str = "deadbeef" * 8) -> None:
        if centroid is None:
            vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
            vec[0] = 1.0
            centroid = vec
        self._centroid = centroid
        self._sha = sha

    def load(self) -> tuple[np.ndarray, str, Any]:
        from book_pipeline.config.mode_thresholds import VoiceFidelityConfig

        vf = VoiceFidelityConfig(
            anchor_set_sha=self._sha,
            pass_threshold=0.78,
            flag_band_min=0.75,
            flag_band_max=0.78,
            fail_threshold=0.75,
            memorization_flag_threshold=0.95,
        )
        return self._centroid, self._sha, vf


class _FakeEmbedder:
    """Embedder that returns a deterministic vector given a pre-set score.

    For tests that need a specific voice_fidelity_score, we set `target_cos`
    to the desired cosine-vs-centroid[0] and the embedder returns a vector
    with dot == target_cos on unit-e0 centroid.
    """

    def __init__(self, target_cos: float = 0.82) -> None:
        self.target_cos = target_cos

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        for i in range(len(texts)):
            # Vector: (cos, sqrt(1-cos^2), 0, ..., 0). Dot with e0 = cos.
            cos = self.target_cos
            sin = float(np.sqrt(max(1.0 - cos * cos, 0.0)))
            out[i, 0] = cos
            if EMBEDDING_DIM > 1:
                out[i, 1] = sin
        return out


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


def _context_pack(chapter: int = 1, scene_index: int = 1) -> ContextPack:
    scene_request = SceneRequest(
        chapter=chapter,
        scene_index=scene_index,
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
        fingerprint="ctxfp-" + str(chapter) + "-" + str(scene_index),
    )


def _build_drafter(
    *,
    vllm_client: Any | None = None,
    memorization_gate: Any | None = None,
    embedder_for_fidelity: Any | None = None,
    anchor_provider: Any | None = None,
    event_logger: Any | None = None,
) -> tuple[Any, _FakeEventLogger]:
    from book_pipeline.drafter.mode_a import ModeADrafter

    logger = event_logger if event_logger is not None else _FakeEventLogger()
    provider = anchor_provider if anchor_provider is not None else _FakeAnchorProvider()
    client = vllm_client if vllm_client is not None else _FakeVllmClient()
    drafter = ModeADrafter(
        vllm_client=client,
        event_logger=logger,
        voice_pin=_pin(),
        anchor_provider=provider,
        memorization_gate=memorization_gate,
        sampling_profiles=SamplingProfiles(),
        embedder_for_fidelity=embedder_for_fidelity,
    )
    return drafter, logger


# --- Test A: Protocol conformance ------------------------------------------

def test_mode_a_drafter_is_drafter_protocol() -> None:
    drafter, _ = _build_drafter()
    assert isinstance(drafter, Drafter)
    assert drafter.mode == "A"


# --- Test B: happy path emits one drafter Event ----------------------------

def test_draft_happy_path_emits_one_drafter_event() -> None:
    scene_text = "The hill was still. Tonantzin paused. A rose bloomed out of season."
    client = _FakeVllmClient(scene_text=scene_text)
    drafter, logger = _build_drafter(vllm_client=client, embedder_for_fidelity=_FakeEmbedder(0.82))

    request = DraftRequest(context_pack=_context_pack())
    response = drafter.draft(request)

    assert response.scene_text == scene_text
    assert response.mode == "A"
    assert response.model_id == "paul-voice"
    assert response.voice_pin_sha == _pin().checkpoint_sha
    assert response.tokens_in == 42
    assert response.tokens_out == 128
    assert response.latency_ms >= 1
    assert response.attempt_number == 1

    # Exactly one drafter Event emitted.
    drafter_events = [e for e in logger.events if e.role == "drafter"]
    assert len(drafter_events) == 1
    evt = drafter_events[0]
    assert evt.mode == "A"
    assert evt.checkpoint_sha == _pin().checkpoint_sha
    assert evt.caller_context["voice_pin_sha"] == _pin().checkpoint_sha
    assert evt.caller_context["anchor_set_sha"] == "deadbeef" * 8
    assert "voice_fidelity_score" in evt.caller_context
    # scene_type defaulted to 'prose' → temperature=0.85.
    assert client.calls[0]["temperature"] == 0.85
    assert client.calls[0]["top_p"] == 0.92


# --- Test C: generation_config override resolves dialogue_heavy ------------

def test_draft_scene_type_override_dispatches_dialogue_heavy() -> None:
    client = _FakeVllmClient()
    drafter, _ = _build_drafter(vllm_client=client)
    request = DraftRequest(
        context_pack=_context_pack(),
        generation_config={"scene_type": "dialogue_heavy"},
    )
    drafter.draft(request)
    assert client.calls[0]["temperature"] == 0.7


# --- Test D: heuristic detects dialogue-heavy via paired quotes -----------

def test_draft_scene_type_heuristic_quotes_triggers_dialogue_heavy() -> None:
    client = _FakeVllmClient()
    drafter, _ = _build_drafter(vllm_client=client)
    prior = ['"Yes." "No." "Perhaps." "Then we go." she said.']
    request = DraftRequest(context_pack=_context_pack(), prior_scenes=prior)
    drafter.draft(request)
    assert client.calls[0]["temperature"] == 0.7


# --- Test E: memorization gate hit raises ModeADrafterBlocked --------------

def test_draft_memorization_gate_hit_raises_and_emits_error_event(tmp_path: Path) -> None:
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked

    # Build a fake gate by subclassing TrainingBleedGate to bypass file I/O.
    class _FakeGate(TrainingBleedGate):
        def __init__(self) -> None:  # no super()
            self.ngram = 12
            self._hashes = set()
            self.row_count = 0
            self.ngram_count = 0

        def scan(self, scene_text: str) -> list[MemorizationHit]:
            return [MemorizationHit(ngram="fake hit phrase", position=0)]

    client = _FakeVllmClient(scene_text="some scene text " * 20)
    drafter, logger = _build_drafter(vllm_client=client, memorization_gate=_FakeGate())
    request = DraftRequest(context_pack=_context_pack())

    with pytest.raises(ModeADrafterBlocked) as exc_info:
        drafter.draft(request)
    assert exc_info.value.reason == "training_bleed"
    # One error Event emitted.
    drafter_events = [e for e in logger.events if e.role == "drafter"]
    assert len(drafter_events) == 1
    assert drafter_events[0].extra.get("status") == "error"
    assert drafter_events[0].extra.get("error") == "training_bleed"


# --- Test F: VllmUnavailable → ModeADrafterBlocked(mode_a_unavailable) ------

def test_draft_vllm_unavailable_raises_blocked_and_emits_error_event() -> None:
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked

    client = _FakeVllmClient(raise_on_completion=VllmUnavailable("no vllm"))
    drafter, logger = _build_drafter(vllm_client=client)
    request = DraftRequest(context_pack=_context_pack())

    with pytest.raises(ModeADrafterBlocked) as exc_info:
        drafter.draft(request)
    assert exc_info.value.reason == "mode_a_unavailable"
    drafter_events = [e for e in logger.events if e.role == "drafter"]
    assert len(drafter_events) == 1
    assert drafter_events[0].extra.get("error") == "mode_a_unavailable"


# --- Test G: empty scene_text → ModeADrafterBlocked(empty_completion) ------

def test_draft_empty_completion_raises_blocked() -> None:
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked

    client = _FakeVllmClient(scene_text="   \n\t  ")
    drafter, logger = _build_drafter(vllm_client=client)
    request = DraftRequest(context_pack=_context_pack())

    with pytest.raises(ModeADrafterBlocked) as exc_info:
        drafter.draft(request)
    assert exc_info.value.reason == "empty_completion"
    drafter_events = [e for e in logger.events if e.role == "drafter"]
    assert len(drafter_events) == 1
    assert drafter_events[0].extra.get("error") == "empty_completion"


# --- Test H: voice_fidelity_status classification per Plan 03-02 thresholds

@pytest.mark.parametrize(
    "cos,expected_status",
    [
        (0.82, "pass"),
        (0.76, "flag_low"),
        (0.70, "fail"),
        (0.97, "flag_memorization"),
    ],
)
def test_draft_voice_fidelity_status_classification(cos: float, expected_status: str) -> None:
    embedder = _FakeEmbedder(target_cos=cos)
    client = _FakeVllmClient(scene_text="a valid scene text content")
    drafter, logger = _build_drafter(vllm_client=client, embedder_for_fidelity=embedder)
    request = DraftRequest(context_pack=_context_pack())
    drafter.draft(request)
    evt = [e for e in logger.events if e.role == "drafter"][0]
    assert evt.caller_context["voice_fidelity_status"] == expected_status


# --- Test I: Event schema round-trip ---------------------------------------

def test_draft_event_schema_roundtrip() -> None:
    client = _FakeVllmClient(scene_text="scene body text")
    drafter, logger = _build_drafter(vllm_client=client)
    drafter.draft(DraftRequest(context_pack=_context_pack()))
    evt = [e for e in logger.events if e.role == "drafter"][0]
    # model_validate round-trip succeeds.
    dumped = evt.model_dump()
    restored = Event.model_validate(dumped)
    assert restored.role == "drafter"
    assert restored.mode == "A"
    assert restored.schema_version == "1.0"
    # All 18 Phase-1 fields present (default-provided or populated).
    expected_fields = {
        "schema_version", "event_id", "ts_iso", "role", "model", "prompt_hash",
        "input_tokens", "cached_tokens", "output_tokens", "latency_ms",
        "temperature", "top_p", "caller_context", "output_hash", "mode",
        "rubric_version", "checkpoint_sha", "extra",
    }
    assert expected_fields.issubset(set(dumped.keys()))


# --- Test J: AnchorSetDrift at construction raises --------------------------

def test_drafter_init_raises_on_anchor_set_drift() -> None:
    from book_pipeline.voice_fidelity.pin import AnchorSetDrift

    class _DriftProvider:
        def load(self) -> tuple[np.ndarray, str, Any]:
            raise AnchorSetDrift(
                expected_sha="a" * 64,
                actual_sha="b" * 64,
                yaml_path=Path("fake.yaml"),
            )

    with pytest.raises(AnchorSetDrift):
        _build_drafter(anchor_provider=_DriftProvider())
