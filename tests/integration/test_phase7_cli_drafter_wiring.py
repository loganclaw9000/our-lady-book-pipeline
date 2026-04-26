"""Phase 7 verifier-2026-04-26 gap closure: cli/draft.py drafter wiring.

Drives the SAME physics-factory composition path that production
``cli/draft.py::_build_composition_root`` uses (extracted into
``cli.draft.build_physics_factories``) through ``ModeADrafter`` and asserts
that a stub with deliberately-bad SceneMetadata surfaces
``ModeADrafterBlocked('physics_pre_flight_fail')`` BEFORE any vLLM call —
proving D-24 ("Physics gates fire at drafter pre-flight ONLY") is enforced
at production grain (NOT just via standalone ``run_pre_flight`` calls).

This test fills the verifier gap:

  ModeADrafter at cli/draft.py:1304 must receive physics_pre_flight,
  physics_canonical_stamp_factory, physics_beat_directive_factory; the
  integration smoke must drive cli/draft.py through ModeADrafter (NOT
  bypass it via run_pre_flight directly).

The factories are constructed via the exact production helper
``build_physics_factories``; the test injects a mock vLLM (so the gate is
the only thing under test) and a fake anchor provider (BGE-M3 weights would
load otherwise).

Marked ``@pytest.mark.slow`` because it loads ``config/pov_locks.yaml`` from
the repo, which is fast in practice but consistent with the other Phase 7
integration tests' slow-mark policy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

# Trigger DraftRequest forward-ref resolution.
import book_pipeline.physics  # noqa: F401
from book_pipeline.cli.draft import build_physics_factories
from book_pipeline.config.voice_pin import VllmServeConfig, VoicePinData
from book_pipeline.drafter.mode_a import ModeADrafter, ModeADrafterBlocked
from book_pipeline.drafter.sampling_profiles import SamplingProfiles
from book_pipeline.interfaces.types import (
    ContextPack,
    DraftRequest,
    Event,
    SceneRequest,
)
from book_pipeline.physics.schema import (
    CharacterPresence,
    Contents,
    Perspective,
    SceneMetadata,
    Staging,
    Treatment,
)

EMBEDDING_DIM = 1024


# --- Test doubles -----------------------------------------------------------


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class _FakeVllmClient:
    """vLLM client stub. If draft() reaches it, physics_pre_flight DID NOT
    fire — that's the failure mode the wiring test catches."""

    def __init__(self) -> None:
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
        min_tokens: int | None = None,
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
                "min_tokens": min_tokens,
            }
        )
        return {
            "choices": [
                {
                    "message": {"content": "should never be returned"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
            "model": model,
        }


class _FakeAnchorProvider:
    def __init__(self) -> None:
        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        vec[0] = 1.0
        self._centroid = vec
        self._sha = "f" * 64

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


def _voice_pin() -> VoicePinData:
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
            port=8002,
            max_model_len=8192,
            dtype="bfloat16",
            tensor_parallel_size=1,
        ),
    )


def _ch15_sc02_bad_metadata() -> SceneMetadata:
    """SceneMetadata with stub-leak vocabulary in motivation.

    Pydantic schema enforces motivation has >= 3 words; the motivation gate
    is the runtime safety belt that catches operator-pasted stub
    scaffolding. ``Beat:`` at line-start is in the gate's stub-leak
    keyword set (motivation.py: Establish | Resolve | Set up | Setup |
    Beat | Function | Disaster | Reaction | Dilemma | Decision) and fires
    severity='high' → run_pre_flight raises GateError → ModeADrafter
    surfaces ModeADrafterBlocked('physics_pre_flight_fail') BEFORE any
    vLLM call.

    chapter=15 + 1st_person Itzcoatl matches the active pov_lock window so
    the gate-event trail covers a realistic ch15+ ordering. The motivation
    gate is index 1 in run_pre_flight, so it short-circuits AFTER pov_lock
    pass but BEFORE ownership/treatment/quantity.
    """
    return SceneMetadata(
        chapter=15,
        scene_index=2,
        contents=Contents(
            goal="feel the deity's continuous metabolism",
            conflict="spanish guard count keeps climbing",
            outcome="engine corps rules of restraint hold",
        ),
        characters_present=[
            CharacterPresence(
                name="Itzcoatl",
                on_screen=True,
                # Stub-leak vocabulary at motivation line-start. Passes
                # Pydantic min-words validator (3 words) but fires the
                # motivation gate's stub-leak guard.
                motivation="Beat: honor the festival",
            ),
        ],
        voice="paul-v7c",
        perspective=Perspective.FIRST_PERSON,
        treatment=Treatment.LITURGICAL,
        owns=["ch15_sc02_toxcatl_observance"],
        do_not_renarrate=["ch15_sc01_arrival"],
        callback_allowed=[],
        staging=Staging(
            location_canonical="Templo Mayor courtyard",
            spatial_position="third tier station",
            scene_clock="festival mid-morning",
            relative_clock="during Toxcatl observance",
            sensory_dominance=["sound"],
            on_screen=["Itzcoatl"],
            off_screen_referenced=[],
            witness_only=[],
        ),
    )


def _stub_context_pack(chapter: int = 15, scene_index: int = 2) -> ContextPack:
    sr = SceneRequest(
        chapter=chapter,
        scene_index=scene_index,
        pov="Itzcoatl",
        date_iso="1520-05-22",
        location="Templo Mayor",
        beat_function="ritual_observance",
        preceding_scene_summary=None,
    )
    return ContextPack(
        scene_request=sr,
        retrievals={},  # CB-01 absent; canon_bible degrades to empty
        total_bytes=0,
        assembly_strategy="round_robin",
        fingerprint=f"ctxfp-wiring-{chapter}-{scene_index}",
    )


# --------------------------------------------------------------------------- #
# Test 1 — production composition path: ModeADrafter receives the 3 physics  #
# factories built by build_physics_factories; bad metadata surfaces as       #
# ModeADrafterBlocked('physics_pre_flight_fail') BEFORE the vLLM call.       #
# --------------------------------------------------------------------------- #


@pytest.mark.slow
def test_cli_drafter_wiring_blocks_on_bad_metadata_before_vllm() -> None:
    """ModeADrafter wired via build_physics_factories rejects a bad-metadata
    DraftRequest with ModeADrafterBlocked('physics_pre_flight_fail') BEFORE
    invoking the (mocked) vLLM client. Production grain for D-24."""
    event_logger = _FakeEventLogger()
    fake_vllm = _FakeVllmClient()

    # Use the EXACT production helper to build the closures.
    factories = build_physics_factories(
        event_logger=event_logger,
        pov_locks_yaml_path=Path("config/pov_locks.yaml"),
    )
    assert set(factories.keys()) == {
        "physics_pre_flight",
        "physics_canonical_stamp_factory",
        "physics_beat_directive_factory",
    }

    drafter = ModeADrafter(
        vllm_client=fake_vllm,
        event_logger=event_logger,
        voice_pin=_voice_pin(),
        anchor_provider=_FakeAnchorProvider(),
        memorization_gate=None,
        sampling_profiles=SamplingProfiles(),
        embedder_for_fidelity=None,
        physics_pre_flight=factories["physics_pre_flight"],
        physics_canonical_stamp_factory=factories[
            "physics_canonical_stamp_factory"
        ],
        physics_beat_directive_factory=factories[
            "physics_beat_directive_factory"
        ],
    )

    # All 3 factories MUST be live — verifier acceptance.
    assert drafter.physics_pre_flight is not None
    assert drafter.physics_canonical_stamp_factory is not None
    assert drafter.physics_beat_directive_factory is not None

    request = DraftRequest(
        context_pack=_stub_context_pack(),
        prior_scenes=[],
        generation_config={"attempt_number": 1},
        scene_metadata=_ch15_sc02_bad_metadata(),
    )

    with pytest.raises(ModeADrafterBlocked) as exc_info:
        drafter.draft(request)

    # Reason must be physics_pre_flight_fail (NOT some other ModeADrafter
    # block reason like 'invalid_scene_type' or 'training_bleed').
    assert exc_info.value.reason == "physics_pre_flight_fail", (
        f"unexpected ModeADrafterBlocked reason: {exc_info.value.reason!r}"
    )
    # The failed gate name must be present in context for downstream routing.
    assert exc_info.value.context.get("failed_gate") == "motivation"
    # Critical: vLLM must NOT have been called — pre-flight is a cheap-first
    # gate per D-24. If this assertion fires, the wiring is broken (the
    # exact verifier-2026-04-26 failure mode).
    assert len(fake_vllm.calls) == 0, (
        "vLLM was invoked despite physics_pre_flight FAIL — D-24 "
        "production-grain wiring is broken"
    )

    # At least one role='physics_gate' Event was emitted by the gate
    # composer (one per checked gate up to the failing motivation gate).
    gate_events = [
        e for e in event_logger.events if getattr(e, "role", "") == "physics_gate"
    ]
    assert gate_events, "no physics_gate Event emitted; pre-flight skipped"


# --------------------------------------------------------------------------- #
# Test 2 — backward compat: scene_metadata=None preserves pre-Phase-7 path.   #
# --------------------------------------------------------------------------- #


@pytest.mark.slow
def test_cli_drafter_wiring_no_op_when_scene_metadata_absent() -> None:
    """Legacy ch01-04 stubs lack v2 SceneMetadata. With scene_metadata=None
    the closures degrade to no-op so the drafter proceeds to the (mocked)
    vLLM call — preserving the pre-Phase-7 path (D-21 forward-only)."""
    event_logger = _FakeEventLogger()
    fake_vllm = _FakeVllmClient()

    factories = build_physics_factories(
        event_logger=event_logger,
        pov_locks_yaml_path=Path("config/pov_locks.yaml"),
    )

    # When scene_metadata is None, all 3 closures must return no-op values
    # without raising (so the drafter proceeds to vLLM normally for legacy
    # stubs).
    legacy_request = DraftRequest(
        context_pack=_stub_context_pack(chapter=1, scene_index=1),
        prior_scenes=[],
        generation_config={"attempt_number": 1},
        scene_metadata=None,
    )

    assert factories["physics_pre_flight"](legacy_request) == []
    assert factories["physics_canonical_stamp_factory"](legacy_request) == ""
    assert factories["physics_beat_directive_factory"](legacy_request) == ""

    # Silence unused-fixture warning — fake_vllm is here to ensure
    # drafter construction is a viable production-shape exercise even when
    # we don't dispatch through it on the no-op path.
    _ = fake_vllm

    # No physics_gate Event should have been emitted — pre-flight no-op'd.
    gate_events = [
        e for e in event_logger.events if getattr(e, "role", "") == "physics_gate"
    ]
    assert not gate_events, (
        f"unexpected physics_gate Events on no-metadata path: {gate_events}"
    )
