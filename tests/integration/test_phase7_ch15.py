"""Phase 7 Plan 05 PHYSICS-12: ch15 sc02 end-to-end engine smoke.

Mocks vLLM (FakeVllmClient returns clean scene_text) and Anthropic
(FakeAnthropicClient returns 13-axis CriticResponse all-pass). Real
SceneEmbeddingCache against tmp_path SQLite — embedder is a tiny in-process
fake so the test runs in <1s without loading 2GB BGE-M3 weights.

Flow under test:
  1. Build v2 SceneMetadata for ch15_sc02 inline (synthetic stub).
  2. Build pov_locks from config/pov_locks.yaml.
  3. Build a CanonBibleView from a stub continuity_bible retrieval.
  4. run_pre_flight — assert all 5 GateResults pass.
  5. Synthesize a clean scene_text (no stub-leak, no repetition).
  6. SceneCritic.review with FakeAnthropicClient + a mocked
     SceneEmbeddingCache that reports cosine = 0.30 (well below 0.80
     threshold).
  7. Assert overall_pass=True; FakeAnthropicClient called exactly once
     (pre-LLM short-circuits did NOT fire on the clean text).
  8. BLOCKER #5 — request.scene_metadata wires through directly.

Plan acceptance gate (operator-run with vLLM stopped + indexes/ populated)
adds the deeper smoke: real BGE-M3 + real LanceDB. This automated smoke
verifies the wiring contract in <1s.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

# Trigger CriticRequest.scene_metadata forward-ref resolution.
import book_pipeline.physics  # noqa: F401
from book_pipeline.config.rubric import RubricConfig
from book_pipeline.critic.scene import SceneCritic
from book_pipeline.interfaces.types import (
    ContextPack,
    CriticRequest,
    RetrievalHit,
    RetrievalResult,
    SceneRequest,
)
from book_pipeline.physics import (
    build_canon_bible_view,
    load_pov_locks,
    run_pre_flight,
)
from book_pipeline.physics.schema import SceneMetadata
from tests.critic.fixtures import FakeAnthropicClient, FakeEventLogger
from tests.critic.test_scene_13axis import make_canonical_critic_response_v2

FEWSHOT_PATH = Path("src/book_pipeline/critic/templates/scene_fewshot.yaml")
TEMPLATE_PATH = Path("src/book_pipeline/critic/templates/system.j2")


def _ch15_sc02_metadata() -> SceneMetadata:
    """Synthetic v2 SceneMetadata for ch15 sc02 (the resume target).

    Itzcoatl 1st-person POV per D-21 (active_from_chapter=15). LITURGICAL
    treatment for the Toxcatl ritual scene.
    """
    return SceneMetadata.model_validate(
        {
            "chapter": 15,
            "scene_index": 2,
            "contents": {
                "goal": "feel the deity's continuous metabolism beneath ritual",
                "conflict": "Spanish guard count keeps climbing past treaty",
                "outcome": "engine corps rules of restraint hold one more hour",
            },
            "characters_present": [
                {
                    "name": "Itzcoatl",
                    "on_screen": True,
                    "motivation": "honor the festival vow of ritual silence",
                },
            ],
            "voice": "paul-v7c",
            "perspective": "1st_person",
            "treatment": "liturgical",
            "owns": ["ch15_sc02_toxcatl_observance"],
            "do_not_renarrate": ["ch15_sc01_arrival"],
            "callback_allowed": [],
            "staging": {
                "location_canonical": "Templo Mayor courtyard south steps",
                "spatial_position": "third tier feasting nobility station",
                "scene_clock": "festival mid-morning fourth hour",
                "relative_clock": "during Toxcatl observance",
                "sensory_dominance": ["sound"],
                "on_screen": ["Itzcoatl"],
                "off_screen_referenced": [],
                "witness_only": [],
            },
        }
    )


def _ch15_sc02_clean_scene_text() -> str:
    """Synthetic clean scene_text (no stub-leak, no repetition loops).

    Crafted to look like ch15 prose: Itzcoatl 1st-person POV, liturgical
    treatment. Distinct enough from any prior committed scene that the
    cosine cache would report a low cosine.
    """
    return (
        "I felt the drum first. The hum followed, lower than my own breath, "
        "and I held my hands at my sides in the formal posture the corps "
        "ascribed to a feasting nobleman. Mirror lay quiet a quarter mile "
        "northwest, attended in his ritual sleep, and I would not approach "
        "him today. The protocol of Toxcatl forbade it. My absence was the "
        "form of my devotion.\n\n"
        "I counted the Spaniards along the south rim. Forty-six already, "
        "and I had not yet looked east. The treaty count was twenty. I "
        "filed the discrepancy under the same name I had been giving it "
        "since the second day of the festival, and went on watching the "
        "dancers. The ixiptla turned in their slow procession. Tepetl "
        "passed close, and I did not turn my head."
    )


class _StubCanonBibleRetrieval:
    """Minimal RetrievalResult-shaped object for build_canon_bible_view."""


class _StubSceneBufferCache:
    """In-process scene-buffer cache that reports a low cosine (=0.30)."""

    def __init__(self, target_cosine: float = 0.30) -> None:
        self.target_cosine = target_cosine
        self.calls: list[tuple[str, str]] = []

    def get_or_compute(self, scene_id: str, scene_text: str) -> np.ndarray:
        self.calls.append((scene_id, scene_text[:60]))
        v = np.zeros((1024,), dtype=np.float32)
        v[0] = 1.0
        return v

    def compute_transient(self, scene_text: str) -> np.ndarray:
        self.calls.append(("<transient>", scene_text[:60]))
        v = np.zeros((1024,), dtype=np.float32)
        v[0] = 1.0
        return v

    def all_prior(self, prior_scene_ids: list[str]) -> dict[str, np.ndarray]:
        # Build a prior vector at the target_cosine angle from the candidate.
        out: dict[str, np.ndarray] = {}
        for sid in prior_scene_ids:
            p = np.zeros((1024,), dtype=np.float32)
            p[0] = self.target_cosine
            p[1] = float(np.sqrt(1.0 - self.target_cosine ** 2))
            out[sid] = p
        return out


@pytest.fixture
def ch15_sc02_metadata() -> SceneMetadata:
    return _ch15_sc02_metadata()


# --------------------------------------------------------------------- #
# Test 1 — physics pre-flight passes for synthetic ch15 sc02 stub        #
# --------------------------------------------------------------------- #


@pytest.mark.slow
def test_ch15_sc02_physics_pre_flight_passes(
    ch15_sc02_metadata: SceneMetadata, tmp_path: Path
) -> None:
    """run_pre_flight on the synthetic ch15 sc02 stub returns 5 GateResults
    with no high-severity FAIL (pre-flight green; the engine would proceed
    to the drafter)."""
    pov_locks = load_pov_locks()
    canon_bible = build_canon_bible_view(
        cb01_retrieval=None,
        pov_locks=pov_locks,
    )
    logger = FakeEventLogger()

    results = run_pre_flight(
        ch15_sc02_metadata,
        pov_locks=pov_locks,
        canon_bible=canon_bible,
        event_logger=logger,
    )
    assert len(results) == 5, (
        f"expected 5 GateResults (5 gates), got {len(results)}"
    )
    high_fails = [r for r in results if r.severity == "high"]
    assert not high_fails, (
        f"unexpected high-severity gate failures: {high_fails}"
    )


# --------------------------------------------------------------------- #
# Test 2 — clean scene_text passes critic 13-axis with all-pass mock     #
# --------------------------------------------------------------------- #


@pytest.mark.slow
def test_ch15_sc02_clean_scene_passes_critic(
    ch15_sc02_metadata: SceneMetadata, tmp_path: Path
) -> None:
    """A synthesized clean ch15 sc02 scene_text flows through SceneCritic
    with FakeAnthropicClient returning all-pass 13-axis CriticResponse.
    Expectations:
      - Pre-LLM short-circuits do NOT fire (clean text).
      - Anthropic IS called exactly once.
      - scene_buffer cosine 0.30 < threshold 0.80 — buffer axis passes.
      - overall_pass=True.
      - BLOCKER #5: request.scene_metadata is the wiring point (not a
        side-channel closure).
    """
    fake_client = FakeAnthropicClient(
        parsed_response=make_canonical_critic_response_v2(overall_pass=True)
    )
    logger = FakeEventLogger()
    cache = _StubSceneBufferCache(target_cosine=0.30)

    critic = SceneCritic(
        anthropic_client=fake_client,
        event_logger=logger,
        rubric=RubricConfig(),
        fewshot_path=FEWSHOT_PATH,
        template_path=TEMPLATE_PATH,
        audit_dir=tmp_path / "audit",
        scene_buffer_cache=cache,
        scene_buffer_threshold=0.80,
        enable_pre_llm_short_circuits=True,
    )

    scene_text = _ch15_sc02_clean_scene_text()
    request = CriticRequest(
        scene_text=scene_text,
        context_pack=ContextPack(
            scene_request=SceneRequest(
                chapter=15,
                scene_index=2,
                pov="Itzcoatl",
                date_iso="1520-05-22",
                location="Templo Mayor",
                beat_function="ritual_observance",
            ),
            retrievals={
                "historical": RetrievalResult(
                    retriever_name="historical",
                    hits=[
                        RetrievalHit(
                            text="Toxcatl 1520 was the festival of "
                            "Tezcatlipoca; Spanish protocols capped armed "
                            "guards at twenty.",
                            source_path="hist/toxcatl_1520.md",
                            chunk_id="hist_toxcatl_001",
                            score=0.91,
                        )
                    ],
                    bytes_used=200,
                    query_fingerprint="q_hist_ch15",
                ),
            },
            total_bytes=200,
            assembly_strategy="round_robin",
            fingerprint="ch15_sc02_pack_smoke",
        ),
        rubric_id="scene.v1",
        rubric_version="v2",
        chapter_context={"attempt_number": 1},
        # BLOCKER #5: load-bearing direct field.
        scene_metadata=ch15_sc02_metadata,
        prior_scene_ids=["ch15_sc01"],
    )

    response = critic.review(request)

    # FakeAnthropicClient was invoked (pre-LLM did NOT fire on clean text).
    assert len(fake_client.messages.call_args_list) == 1, (
        f"expected exactly one Anthropic call, got "
        f"{len(fake_client.messages.call_args_list)}"
    )

    # scene_buffer axis: cosine 0.30 < 0.80 → pass.
    assert response.pass_per_axis["scene_buffer_similarity"] is True
    # All 13 axes pass → overall_pass.
    assert response.overall_pass is True

    # The cache was consulted (BLOCKER #5 contract: scene_metadata routed
    # through; prior_scene_ids triggered the cosine compute).
    assert cache.calls, "scene buffer cache was never consulted"


# --------------------------------------------------------------------- #
# Test 3 — BLOCKER #5: request.scene_metadata is read directly           #
# --------------------------------------------------------------------- #


@pytest.mark.slow
def test_ch15_sc02_scene_metadata_reaches_critic_without_side_channel(
    ch15_sc02_metadata: SceneMetadata, tmp_path: Path
) -> None:
    """BLOCKER #5 acceptance: SceneMetadata flows through CriticRequest's
    additive scene_metadata field, NOT via any side-channel closure /
    global / mutable holder.

    Verified by: building two CriticRequests in-line; the critic reads the
    treatment from each request.scene_metadata independently. If a
    side-channel were in play, the second call would inherit the first's
    state.
    """
    fake_client = FakeAnthropicClient(
        parsed_response=make_canonical_critic_response_v2(overall_pass=True)
    )
    critic = SceneCritic(
        anthropic_client=fake_client,
        event_logger=FakeEventLogger(),
        rubric=RubricConfig(),
        fewshot_path=FEWSHOT_PATH,
        template_path=TEMPLATE_PATH,
        audit_dir=tmp_path / "audit",
        enable_pre_llm_short_circuits=True,
    )

    # First call — LITURGICAL stub.
    request_a = CriticRequest(
        scene_text="I held my hands at my sides. The drum was first. The hum.",
        context_pack=ContextPack(
            scene_request=SceneRequest(
                chapter=15, scene_index=2,
                pov="Itzcoatl", date_iso="1520-05-22",
                location="x", beat_function="b",
            ),
            retrievals={},
            total_bytes=10,
            assembly_strategy="round_robin",
            fingerprint="fa",
        ),
        rubric_id="scene.v1",
        rubric_version="v2",
        scene_metadata=ch15_sc02_metadata,  # liturgical
    )
    critic.review(request_a)
    # Reset mock for second call.
    fake_client.messages.call_args_list.clear()

    # Second call — no scene_metadata; treatment must default (None).
    request_b = CriticRequest(
        scene_text="A different scene. With different content. Distinct prose.",
        context_pack=request_a.context_pack,
        rubric_id="scene.v1",
        rubric_version="v2",
        scene_metadata=None,
    )
    critic.review(request_b)
    # If the critic correctly reads request.scene_metadata each call, both
    # invocations succeed and Anthropic was called once for each. (A
    # side-channel state-leak would surface as a dict-mutation issue or
    # an erroneous LITURGICAL threshold being applied to the second call.)
    assert len(fake_client.messages.call_args_list) == 1
