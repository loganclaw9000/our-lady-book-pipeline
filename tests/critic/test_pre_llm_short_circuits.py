"""Tests for SceneCritic pre-LLM short-circuits (Plan 07-05 PHYSICS-08/09/10).

Coverage:
  Test 8  — stub_leak hit short-circuits without Anthropic call;
            non-failed axes set to None sentinel (Warning #4).
  Test 9  — repetition_loop hit short-circuits + emits role='scene_critic'
            Event with extra={'pre_llm_short_circuit': True, ...}.
  Test 10 — scene_buffer cosine ≥ threshold sets axis pass=False (override).
  Test 12 — CriticResponse with one None pass value validates (Warning #4
            schema-side bump).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

# Force forward-ref resolution on CriticRequest.scene_metadata.
import book_pipeline.physics  # noqa: F401  — triggers model_rebuild
from book_pipeline.config.rubric import RubricConfig
from book_pipeline.critic.scene import SceneCritic
from book_pipeline.interfaces.types import (
    ContextPack,
    CriticRequest,
    CriticResponse,
    RetrievalResult,
    SceneRequest,
)
from book_pipeline.physics.schema import SceneMetadata, Treatment
from tests.critic.fixtures import (
    FakeAnthropicClient,
    FakeEventLogger,
)
from tests.critic.test_scene_13axis import make_canonical_critic_response_v2

FEWSHOT_PATH = Path("src/book_pipeline/critic/templates/scene_fewshot.yaml")
TEMPLATE_PATH = Path("src/book_pipeline/critic/templates/system.j2")


def _make_request(
    scene_text: str,
    *,
    scene_metadata: SceneMetadata | None = None,
    prior_scene_ids: list[str] | None = None,
) -> CriticRequest:
    return CriticRequest(
        scene_text=scene_text,
        context_pack=ContextPack(
            scene_request=SceneRequest(
                chapter=15,
                scene_index=2,
                pov="Andrés",
                date_iso="1519-08-16",
                location="Cempoala",
                beat_function="warning",
            ),
            retrievals={
                "historical": RetrievalResult(
                    retriever_name="historical",
                    hits=[],
                    bytes_used=0,
                    query_fingerprint="q",
                ),
            },
            total_bytes=100,
            assembly_strategy="round_robin",
            fingerprint="ctxpack_test",
        ),
        rubric_id="scene.v1",
        rubric_version="v2",
        chapter_context={"attempt_number": 1},
        scene_metadata=scene_metadata,
        prior_scene_ids=prior_scene_ids or [],
    )


def _make_critic(
    *,
    anthropic_client: Any,
    event_logger: Any | None = None,
    scene_buffer_cache: Any | None = None,
    scene_buffer_threshold: float = 0.80,
    enable_pre_llm_short_circuits: bool = True,
    audit_dir: Path,
) -> SceneCritic:
    return SceneCritic(
        anthropic_client=anthropic_client,
        event_logger=event_logger,
        rubric=RubricConfig(),
        fewshot_path=FEWSHOT_PATH,
        template_path=TEMPLATE_PATH,
        audit_dir=audit_dir,
        scene_buffer_cache=scene_buffer_cache,
        scene_buffer_threshold=scene_buffer_threshold,
        enable_pre_llm_short_circuits=enable_pre_llm_short_circuits,
    )


# ----------------------------------------------------------------- #
# Test 8 — stub_leak short-circuit                                  #
# ----------------------------------------------------------------- #


def test_8_stub_leak_short_circuits_without_anthropic_call(tmp_path: Path) -> None:
    """When scene_text contains a stub directive (`Establish: ...`),
    SceneCritic.review() returns a synthetic CriticResponse with stub_leak=False
    and ALL OTHER 12 axes set to None (Warning #4 sentinel) WITHOUT calling
    Anthropic."""
    fake_client = FakeAnthropicClient(
        parsed_response=make_canonical_critic_response_v2(overall_pass=True)
    )
    logger = FakeEventLogger()
    critic = _make_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "audit",
    )

    scene_text = (
        "Establish: the friendship that will become Bernardo's death-witness.\n\n"
        "Andrés walked the beach at dawn."
    )
    request = _make_request(scene_text)
    response = critic.review(request)

    # Anthropic was NOT called.
    assert fake_client.messages.call_args_list == [], (
        "pre-LLM short-circuit must not invoke Anthropic"
    )

    # stub_leak axis is False; other 12 axes are None sentinel.
    assert response.pass_per_axis["stub_leak"] is False
    assert response.overall_pass is False
    none_axes = [
        a for a, v in response.pass_per_axis.items() if v is None
    ]
    assert len(none_axes) == 12, (
        f"expected 12 unverified axes (None sentinel), got {len(none_axes)}: "
        f"{none_axes}"
    )
    # Issues populated with stub-leak hit.
    assert response.issues
    assert response.issues[0].axis == "stub_leak"


# ----------------------------------------------------------------- #
# Test 9 — repetition_loop short-circuit + Event marker             #
# ----------------------------------------------------------------- #


def test_9_repetition_loop_short_circuit_emits_event_marker(tmp_path: Path) -> None:
    """When repetition_loop fires, SceneCritic.review() returns a synthetic
    CriticResponse + emits role='scene_critic' Event with
    extra={'pre_llm_short_circuit': True, 'unverified_axes': [12 names]}."""
    fake_client = FakeAnthropicClient(
        parsed_response=make_canonical_critic_response_v2(overall_pass=True)
    )
    logger = FakeEventLogger()
    critic = _make_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "audit",
    )

    # 4 distinct identical lines > default threshold of 2.
    scene_text = "\n".join(
        [
            "He waited.",
            "He waited.",
            "He waited.",
            "He waited.",
        ]
        * 1
    )
    request = _make_request(scene_text)
    response = critic.review(request)

    assert fake_client.messages.call_args_list == [], (
        "pre-LLM short-circuit must not invoke Anthropic on repetition_loop hit"
    )
    assert response.pass_per_axis["repetition_loop"] is False
    assert response.overall_pass is False

    # Event marker present.
    assert logger.events, "expected at least one emitted Event"
    pre_llm_events = [
        e
        for e in logger.events
        if getattr(e, "extra", {}).get("pre_llm_short_circuit") is True
    ]
    assert len(pre_llm_events) == 1, (
        f"expected exactly one pre_llm_short_circuit Event, got {len(pre_llm_events)}"
    )
    ev = pre_llm_events[0]
    assert ev.role == "scene_critic"
    assert ev.extra["failed_axis"] == "repetition_loop"
    unverified = ev.extra["unverified_axes"]
    assert len(unverified) == 12, (
        f"expected 12 unverified axes in Event extra, got {len(unverified)}: "
        f"{unverified}"
    )


# ----------------------------------------------------------------- #
# Test — repetition_loop with LITURGICAL treatment is more lenient  #
# ----------------------------------------------------------------- #


def test_repetition_loop_liturgical_threshold(tmp_path: Path) -> None:
    """LITURGICAL treatment raises identical_line_max from 2 to 5 — 4 identical
    lines should NOT short-circuit; the Anthropic call proceeds normally."""
    fake_client = FakeAnthropicClient(
        parsed_response=make_canonical_critic_response_v2(overall_pass=True)
    )
    critic = _make_critic(
        anthropic_client=fake_client,
        audit_dir=tmp_path / "audit",
    )

    # 4 short identical lines diluted by surrounding distinct prose so the
    # trigram rate stays under the LITURGICAL ceiling (0.40). Identical-line
    # max for LITURGICAL is 5 (>=6 fails) — 4 identical lines are below it.
    scene_text = (
        "The drum first. Always the drum first. The note rolled down the steps "
        "of the south pyramid like a slow tide and the priests on the upper "
        "platform raised the brazier copal-smoke into the morning air.\n"
        "He felt the hum. He felt it in his teeth and in the small bones "
        "behind his ears.\n"
        "The hum.\n"
        "The hum.\n"
        "The hum.\n"
        "The hum.\n"
        "Itzcoatl stood in his formal posture and watched the dancers turn "
        "the courtyard into a slow vortex around the central platform of the "
        "feasting nobility today this morning."
    )
    payload = {
        "chapter": 15,
        "scene_index": 2,
        "contents": {
            "goal": "feel the deity's continuous metabolism",
            "conflict": "the city's pitch must hold",
            "outcome": "ritual is fully observed",
        },
        "characters_present": [
            {
                "name": "Andres",
                "on_screen": True,
                "motivation": "stand in the corps formal posture",
            }
        ],
        "voice": "paul-v7c",
        "perspective": "3rd_close",
        "treatment": "liturgical",
        "owns": ["ch15_sc02_ritual_sustain"],
        "do_not_renarrate": [],
        "callback_allowed": [],
        "staging": {
            "location_canonical": "Templo Mayor courtyard",
            "spatial_position": "south steps third tier",
            "scene_clock": "festival mid-morning",
            "relative_clock": "during Toxcatl observance",
            "sensory_dominance": ["sound"],
            "on_screen": ["Andres"],
            "off_screen_referenced": [],
            "witness_only": [],
        },
    }
    sm = SceneMetadata.model_validate(payload)
    assert sm.treatment == Treatment.LITURGICAL
    request = _make_request(scene_text, scene_metadata=sm)
    critic.review(request)

    # Anthropic WAS called (LITURGICAL exempts these 4 identical lines).
    assert len(fake_client.messages.call_args_list) == 1


# ----------------------------------------------------------------- #
# Test 10 — scene_buffer override                                   #
# ----------------------------------------------------------------- #


class _StubSceneBufferCache:
    """Mock SceneEmbeddingCache that returns canned cosine values."""

    def __init__(self, candidate: np.ndarray, prior: dict[str, np.ndarray]) -> None:
        self._candidate = candidate
        self._prior = prior
        self.calls: list[tuple[str, str]] = []

    def get_or_compute(self, scene_id: str, scene_text: str) -> np.ndarray:
        self.calls.append((scene_id, scene_text[:50]))
        return self._candidate.copy()

    def compute_transient(self, scene_text: str) -> np.ndarray:
        self.calls.append(("<transient>", scene_text[:50]))
        return self._candidate.copy()

    def all_prior(self, prior_scene_ids: list[str]) -> dict[str, np.ndarray]:
        return {sid: self._prior[sid].copy() for sid in prior_scene_ids if sid in self._prior}


def test_10_scene_buffer_cosine_above_threshold_overrides_to_fail(tmp_path: Path) -> None:
    """scene_buffer cosine ≥ threshold overrides pass_per_axis['scene_buffer_similarity']
    to False AND forces overall_pass=False."""
    # Build a candidate + prior with cosine = 0.85 (above 0.80 threshold).
    candidate = np.zeros((1024,), dtype=np.float32)
    candidate[0] = 1.0
    prior_high = np.zeros((1024,), dtype=np.float32)
    prior_high[0] = 0.85
    prior_high[1] = float(np.sqrt(1.0 - 0.85 * 0.85))  # unit-norm

    cache = _StubSceneBufferCache(candidate, {"sc01": prior_high})

    fake_client = FakeAnthropicClient(
        parsed_response=make_canonical_critic_response_v2(overall_pass=True)
    )
    critic = _make_critic(
        anthropic_client=fake_client,
        scene_buffer_cache=cache,
        scene_buffer_threshold=0.80,
        audit_dir=tmp_path / "audit",
    )

    request = _make_request(
        "Andrés walked the beach at dawn.",
        prior_scene_ids=["sc01"],
    )
    response = critic.review(request)

    # Anthropic WAS called (override is post-LLM).
    assert len(fake_client.messages.call_args_list) == 1
    # Override fired.
    assert response.pass_per_axis["scene_buffer_similarity"] is False
    assert response.overall_pass is False


def test_10b_scene_buffer_cosine_below_threshold_passes(tmp_path: Path) -> None:
    """scene_buffer cosine < threshold leaves pass_per_axis['scene_buffer_similarity']
    True and overall_pass remains True."""
    candidate = np.zeros((1024,), dtype=np.float32)
    candidate[0] = 1.0
    prior_low = np.zeros((1024,), dtype=np.float32)
    prior_low[0] = 0.40
    prior_low[1] = float(np.sqrt(1.0 - 0.40 * 0.40))

    cache = _StubSceneBufferCache(candidate, {"sc01": prior_low})

    fake_client = FakeAnthropicClient(
        parsed_response=make_canonical_critic_response_v2(overall_pass=True)
    )
    critic = _make_critic(
        anthropic_client=fake_client,
        scene_buffer_cache=cache,
        scene_buffer_threshold=0.80,
        audit_dir=tmp_path / "audit",
    )

    request = _make_request(
        "Andrés walked the beach at dawn.",
        prior_scene_ids=["sc01"],
    )
    response = critic.review(request)
    assert response.pass_per_axis["scene_buffer_similarity"] is True
    assert response.overall_pass is True


# ----------------------------------------------------------------- #
# Test 12 — CriticResponse schema bump (Warning #4)                  #
# ----------------------------------------------------------------- #


def test_12_critic_response_accepts_none_sentinel_in_pass_per_axis() -> None:
    """CriticResponse.pass_per_axis is dict[str, bool | None]; None values
    validate. Existing pure-bool maps still validate (backward-compat)."""
    # With None sentinel.
    r1 = CriticResponse(
        pass_per_axis={"historical": True, "metaphysics": None, "entity": False},
        scores_per_axis={"historical": 92.0, "metaphysics": 0.0, "entity": 30.0},
        issues=[],
        overall_pass=False,
        model_id="x",
        rubric_version="v2",
        output_sha="abc",
    )
    assert r1.pass_per_axis["metaphysics"] is None
    # Without None (legacy shape).
    r2 = CriticResponse(
        pass_per_axis={"historical": True, "metaphysics": True},
        scores_per_axis={"historical": 92.0, "metaphysics": 88.0},
        issues=[],
        overall_pass=True,
        model_id="x",
        rubric_version="v2",
        output_sha="def",
    )
    assert r2.pass_per_axis["metaphysics"] is True


# ----------------------------------------------------------------- #
# Backward-compat: enable_pre_llm_short_circuits=False               #
# ----------------------------------------------------------------- #


def test_short_circuits_disabled_anthropic_still_called(tmp_path: Path) -> None:
    """With enable_pre_llm_short_circuits=False, even a stub-leak scene_text
    proceeds to the Anthropic call (legacy behavior)."""
    fake_client = FakeAnthropicClient(
        parsed_response=make_canonical_critic_response_v2(overall_pass=True)
    )
    critic = _make_critic(
        anthropic_client=fake_client,
        enable_pre_llm_short_circuits=False,
        audit_dir=tmp_path / "audit",
    )
    request = _make_request("Establish: the friendship.\n\nAndrés walked.")
    critic.review(request)
    assert len(fake_client.messages.call_args_list) == 1
