"""Tests for Plan 07-03 Task 2: ModeADrafter physics pre-flight + canonical stamp + beat directive.

Tests 1-9 from PLAN.md <behavior>:
- 1: ctor accepts new optional kwargs (backward-compat preserved)
- 2: physics_pre_flight=None -> identical pre-Phase-7 behavior
- 3: physics_pre_flight returning [GateResult(...pass)] -> normal vLLM flow
- 4: physics_pre_flight raising GateError -> ModeADrafterBlocked('physics_pre_flight_fail')
- 5: rendered template contains "CANONICAL:" before voice_description (top-of-prompt)
- 6: rendered template contains "<beat>...</beat>" fenced block
- 7: empty canonical_stamp -> NO "CANONICAL:" line
- 8: ModeADrafterBlocked('physics_pre_flight_fail', ...) constructs cleanly
- 9: ModeADrafterBlocked('bogus_reason') raises ValueError
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import jinja2
import numpy as np
import pytest

from book_pipeline.config.voice_pin import VllmServeConfig, VoicePinData
from book_pipeline.drafter.sampling_profiles import SamplingProfiles
from book_pipeline.interfaces.types import (
    ContextPack,
    DraftRequest,
    Event,
    RetrievalHit,
    RetrievalResult,
    SceneRequest,
)
from book_pipeline.physics.gates.base import GateError, GateResult

EMBEDDING_DIM = 1024


# --- Test doubles -----------------------------------------------------------


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class _FakeVllmClient:
    """vLLM client stub that accepts the full Plan 03-03 + min_tokens signature."""

    def __init__(
        self,
        *,
        scene_text: str = "The room was quiet. A single candle burned. Andres watched.",
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
    def __init__(self, *, sha: str = "deadbeef" * 8) -> None:
        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        vec[0] = 1.0
        self._centroid = vec
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


def _context_pack(chapter: int = 15, scene_index: int = 2) -> ContextPack:
    scene_request = SceneRequest(
        chapter=chapter,
        scene_index=scene_index,
        pov="Andres",
        date_iso="1519-10-18",
        location="Cempoala fortress courtyard",
        beat_function="warning",
        preceding_scene_summary=None,
    )
    hist = RetrievalResult(
        retriever_name="historical",
        hits=[
            RetrievalHit(
                text="In October 1519, the Spanish were at Cholula.",
                source_path="canon/historical/1519.md",
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
        fingerprint=f"ctxfp-{chapter}-{scene_index}",
    )


def _build_drafter(
    *,
    vllm_client: Any | None = None,
    physics_pre_flight: Any | None = None,
    physics_canonical_stamp_factory: Any | None = None,
    physics_beat_directive_factory: Any | None = None,
) -> tuple[Any, _FakeEventLogger]:
    from book_pipeline.drafter.mode_a import ModeADrafter

    logger = _FakeEventLogger()
    client = vllm_client if vllm_client is not None else _FakeVllmClient()
    drafter = ModeADrafter(
        vllm_client=client,
        event_logger=logger,
        voice_pin=_pin(),
        anchor_provider=_FakeAnchorProvider(),
        memorization_gate=None,
        sampling_profiles=SamplingProfiles(),
        embedder_for_fidelity=None,
        physics_pre_flight=physics_pre_flight,
        physics_canonical_stamp_factory=physics_canonical_stamp_factory,
        physics_beat_directive_factory=physics_beat_directive_factory,
    )
    return drafter, logger


# --- Test 1: ctor accepts new kwargs (backward-compat) --------------------


def test_mode_a_drafter_ctor_accepts_new_physics_kwargs() -> None:
    """ModeADrafter accepts the 3 new optional physics kwargs."""
    drafter, _ = _build_drafter(
        physics_pre_flight=lambda req: [],
        physics_canonical_stamp_factory=lambda req: "CANONICAL: test",
        physics_beat_directive_factory=lambda req: "<beat>test</beat>",
    )
    assert drafter.physics_pre_flight is not None
    assert drafter.physics_canonical_stamp_factory is not None
    assert drafter.physics_beat_directive_factory is not None


def test_mode_a_drafter_ctor_omitting_physics_kwargs_preserves_backward_compat() -> None:
    """Omitting the 3 new kwargs -> attributes are None (Phase 1 freeze additive-optional)."""
    from book_pipeline.drafter.mode_a import ModeADrafter

    drafter = ModeADrafter(
        vllm_client=_FakeVllmClient(),
        event_logger=_FakeEventLogger(),
        voice_pin=_pin(),
        anchor_provider=_FakeAnchorProvider(),
        memorization_gate=None,
        sampling_profiles=SamplingProfiles(),
    )
    assert drafter.physics_pre_flight is None
    assert drafter.physics_canonical_stamp_factory is None
    assert drafter.physics_beat_directive_factory is None


# --- Test 2: physics_pre_flight=None -> identical pre-Phase-7 behavior ----


def test_drafter_with_no_physics_pre_flight_drafts_normally() -> None:
    """physics_pre_flight=None -> drafter renders + calls vLLM (no pre-flight call)."""
    pre_flight_calls: list[Any] = []

    def _spy_pre_flight(request: Any) -> list[GateResult]:
        pre_flight_calls.append(request)
        return []

    # Build with NO physics hooks
    client = _FakeVllmClient()
    drafter, _ = _build_drafter(vllm_client=client)
    request = DraftRequest(context_pack=_context_pack())
    response = drafter.draft(request)

    assert response.scene_text  # normal flow ran
    assert pre_flight_calls == []  # spy was never wired


# --- Test 3: pre-flight passing all gates -> normal vLLM flow continues ---


def test_drafter_with_passing_pre_flight_continues_to_vllm() -> None:
    """All gates pass -> vLLM is called, response returned."""
    pre_flight_calls: list[Any] = []

    def _passing_pre_flight(request: Any) -> list[GateResult]:
        pre_flight_calls.append(request)
        return [
            GateResult(gate_name="pov_lock", passed=True, severity="pass"),
            GateResult(gate_name="motivation", passed=True, severity="pass"),
        ]

    client = _FakeVllmClient()
    drafter, _ = _build_drafter(
        vllm_client=client, physics_pre_flight=_passing_pre_flight
    )
    request = DraftRequest(context_pack=_context_pack())
    response = drafter.draft(request)

    assert len(pre_flight_calls) == 1  # called exactly once
    assert pre_flight_calls[0] is request
    assert response.scene_text  # vLLM was called too
    assert len(client.calls) == 1


# --- Test 4: pre-flight GateError -> ModeADrafterBlocked('physics_pre_flight_fail')


def test_drafter_with_failing_pre_flight_raises_blocked() -> None:
    """GateError from pre-flight -> ModeADrafterBlocked('physics_pre_flight_fail')."""
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked

    def _failing_pre_flight(request: Any) -> list[GateResult]:
        err = GateError("physics pre-flight FAIL: gate=pov_lock reason=pov_lock_breach")
        err.failed_gate = "pov_lock"  # type: ignore[attr-defined]
        err.results = [  # type: ignore[attr-defined]
            GateResult(
                gate_name="pov_lock",
                passed=False,
                severity="high",
                reason="pov_lock_breach",
                detail={"breaches": ["Andres: declared 3rd_close but lock pins 1st_person"]},
            ),
        ]
        raise err

    client = _FakeVllmClient()
    drafter, logger = _build_drafter(
        vllm_client=client, physics_pre_flight=_failing_pre_flight
    )
    request = DraftRequest(context_pack=_context_pack())

    with pytest.raises(ModeADrafterBlocked) as exc_info:
        drafter.draft(request)

    assert exc_info.value.reason == "physics_pre_flight_fail"
    assert exc_info.value.context.get("failed_gate") == "pov_lock"
    # vLLM was NOT called (pre-flight short-circuits before render)
    assert len(client.calls) == 0
    # An error Event was emitted (drafter._emit_error_event)
    drafter_events = [e for e in logger.events if e.role == "drafter"]
    assert len(drafter_events) == 1
    assert drafter_events[0].extra.get("error") == "physics_pre_flight_fail"


# --- Test 5-7: Jinja2 template rendering ---------------------------------


def _render_template(
    *,
    canonical_stamp: str = "",
    beat_directive: str = "",
    scene_chapter: int = 15,
    scene_index: int = 2,
) -> str:
    """Render the mode_a.j2 template with synthetic kwargs."""
    template_dir = Path(__file__).parent.parent.parent / "src" / "book_pipeline" / "drafter" / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tpl = env.get_template("mode_a.j2")
    pack = _context_pack(scene_chapter, scene_index)
    return tpl.render(
        voice_description="Voice description body here.",
        rubric_awareness="Rubric awareness body here.",
        retrievals=pack.retrievals,
        scene_request=pack.scene_request,
        prior_scenes=[],
        word_target=1000,
        scene_type="prose",
        canonical_stamp=canonical_stamp,
        beat_directive=beat_directive,
    )


def test_template_renders_canonical_stamp_at_top() -> None:
    """canonical_stamp appears in the rendered system body BEFORE voice_description."""
    rendered = _render_template(
        canonical_stamp="CANONICAL: Andres age=23 | La Nina=55ft | Cholula=Oct 18 1519"
    )
    assert "CANONICAL:" in rendered
    canonical_idx = rendered.find("CANONICAL:")
    voice_idx = rendered.find("Voice description body here.")
    assert canonical_idx >= 0
    assert voice_idx >= 0
    assert canonical_idx < voice_idx, "canonical_stamp must precede voice_description"


def test_template_renders_beat_directive_fenced_block() -> None:
    """beat_directive renders the fenced <beat>...</beat> block in the system body."""
    rendered = _render_template(
        beat_directive="<beat>OWNS: ch15_sc02_warning. DO NOT renarrate ch15_sc01_arrival.</beat>"
    )
    assert "<beat>" in rendered
    assert "</beat>" in rendered
    open_idx = rendered.find("<beat>")
    close_idx = rendered.find("</beat>")
    assert open_idx < close_idx


def test_template_with_empty_canonical_stamp_omits_canonical_line() -> None:
    """Empty canonical_stamp -> NO 'CANONICAL:' line in the rendered output."""
    rendered = _render_template(canonical_stamp="", beat_directive="")
    assert "CANONICAL:" not in rendered


# --- Test 8-9: ModeADrafterBlocked _ACCEPTED_REASONS frozenset enforcement


def test_mode_a_drafter_blocked_accepts_physics_pre_flight_fail_at_runtime() -> None:
    """ModeADrafterBlocked('physics_pre_flight_fail', ...) constructs without ValueError."""
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked

    err = ModeADrafterBlocked(
        "physics_pre_flight_fail", scene_id="ch15_sc02", attempt_number=1
    )
    assert err.reason == "physics_pre_flight_fail"


def test_mode_a_drafter_blocked_rejects_unknown_reason() -> None:
    """ModeADrafterBlocked('bogus_reason', ...) raises ValueError listing known reasons."""
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked

    with pytest.raises(ValueError, match=r"unknown ModeADrafterBlocked reason"):
        ModeADrafterBlocked("bogus_reason", scene_id="x")


def test_mode_a_drafter_blocked_pov_lock_violated_reserved_for_phase7_plan04() -> None:
    """'pov_lock_violated' is in the accepted-reasons set (Plan 07-04 critic-axis reservation)."""
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked

    err = ModeADrafterBlocked("pov_lock_violated", scene_id="ch15_sc02")
    assert err.reason == "pov_lock_violated"


def test_mode_a_drafter_blocked_runtime_subprocess_smoke() -> None:
    """Subprocess parallel: covers the standalone-import path (BLOCKER #4 acceptance)."""
    code = (
        "from book_pipeline.drafter.mode_a import ModeADrafterBlocked; "
        "ModeADrafterBlocked('physics_pre_flight_fail', scene_id='ch15_sc02', attempt_number=1); "
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "ok" in result.stdout
