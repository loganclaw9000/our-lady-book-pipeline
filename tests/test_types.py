"""Tests for book_pipeline.interfaces.types — OBS-01 Event schema + cross-Protocol Pydantic models.

Covers:
- Test 1: every Pydantic model instantiates with minimal valid args
- Test 2: Event model has all 18 OBS-01 fields
- Test 3: Event defaults (mode=None, checkpoint_sha=None, cached_tokens=0, extra={})
- Test 4: SceneState Enum has exactly 9 members
- Test 5: ContextPack.fingerprint and RetrievalResult.query_fingerprint are required str
- Test 6: top-level imports succeed
"""
from __future__ import annotations

import pytest

from book_pipeline.interfaces import (
    ContextPack,
    CriticIssue,
    CriticRequest,
    CriticResponse,
    DraftRequest,
    DraftResponse,
    EntityCard,
    Event,
    RegenRequest,
    RetrievalHit,
    RetrievalResult,
    Retrospective,
    SceneRequest,
    SceneState,
    SceneStateRecord,
    ThesisEvidence,
    transition,
)


def test_event_has_all_obs01_fields() -> None:
    """OBS-01 acceptance: Event model carries every field listed in CONTEXT.md D-06."""
    e = Event(
        event_id="abc",
        ts_iso="2026-04-21T00:00:00Z",
        role="drafter",
        model="vllm/paul-voice",
        prompt_hash="p1",
        input_tokens=100,
        output_tokens=500,
        latency_ms=1234,
        output_hash="o1",
    )
    # mandatory fields
    for f in (
        "schema_version",
        "event_id",
        "ts_iso",
        "role",
        "model",
        "prompt_hash",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "output_hash",
    ):
        assert hasattr(e, f), f"Event is missing mandatory field {f}"
    # optional/defaulted fields
    assert e.mode is None
    assert e.checkpoint_sha is None
    assert e.cached_tokens == 0
    assert e.rubric_version is None
    assert e.extra == {}
    assert e.temperature is None
    assert e.top_p is None
    assert e.caller_context == {}
    assert e.schema_version == "1.0"


def test_event_has_18_fields_total() -> None:
    """OBS-01 freeze: Event has exactly the 18 fields enumerated in the plan."""
    expected = {
        "schema_version",
        "event_id",
        "ts_iso",
        "role",
        "model",
        "prompt_hash",
        "input_tokens",
        "cached_tokens",
        "output_tokens",
        "latency_ms",
        "temperature",
        "top_p",
        "caller_context",
        "output_hash",
        "mode",
        "rubric_version",
        "checkpoint_sha",
        "extra",
    }
    assert set(Event.model_fields.keys()) == expected


def test_scene_state_has_9_members() -> None:
    """SceneState Enum has exactly 9 members per ARCHITECTURE.md §4.1."""
    assert len(list(SceneState)) == 9
    for name in (
        "PENDING",
        "RAG_READY",
        "DRAFTED_A",
        "CRITIC_PASS",
        "CRITIC_FAIL",
        "REGENERATING",
        "ESCALATED_B",
        "COMMITTED",
        "HARD_BLOCKED",
    ):
        assert hasattr(SceneState, name), f"SceneState missing member {name}"


def test_scene_state_values_are_snake_case() -> None:
    """SceneState values are snake_case strings (serialization contract)."""
    assert SceneState.PENDING.value == "pending"
    assert SceneState.RAG_READY.value == "rag_ready"
    assert SceneState.DRAFTED_A.value == "drafted_a"
    assert SceneState.CRITIC_PASS.value == "critic_pass"
    assert SceneState.CRITIC_FAIL.value == "critic_fail"
    assert SceneState.REGENERATING.value == "regenerating"
    assert SceneState.ESCALATED_B.value == "escalated_b"
    assert SceneState.COMMITTED.value == "committed"
    assert SceneState.HARD_BLOCKED.value == "hard_blocked"


def test_scene_request_minimal() -> None:
    r = SceneRequest(
        chapter=1,
        scene_index=1,
        pov="Andres",
        date_iso="1519-04-21",
        location="Cempoala",
        beat_function="establish",
    )
    assert r.preceding_scene_summary is None
    assert r.chapter == 1


def test_retrieval_hit_and_result() -> None:
    h = RetrievalHit(text="some text", source_path="p", chunk_id="c1", score=0.9)
    assert h.metadata == {}
    result = RetrievalResult(
        retriever_name="historical",
        hits=[h],
        bytes_used=100,
        query_fingerprint="qfp",
    )
    assert result.query_fingerprint == "qfp"
    assert len(result.hits) == 1


def test_context_pack_requires_fingerprint() -> None:
    """Schema enforces fingerprint presence — bundler populates in Phase 2."""
    sr = SceneRequest(
        chapter=1, scene_index=1, pov="P", date_iso="1519-01-01", location="L", beat_function="b"
    )
    cp = ContextPack(
        scene_request=sr, retrievals={}, total_bytes=0, fingerprint="deadbeef"
    )
    assert cp.fingerprint == "deadbeef"
    assert cp.assembly_strategy == "round_robin"


def test_transition_appends_history() -> None:
    rec = SceneStateRecord(scene_id="ch01_sc01", state=SceneState.PENDING)
    new_rec = transition(rec, SceneState.RAG_READY, "bundler produced pack")
    assert new_rec.state == SceneState.RAG_READY
    assert len(new_rec.history) == 1
    assert new_rec.history[0]["from"] == "pending"
    assert new_rec.history[0]["to"] == "rag_ready"
    assert new_rec.history[0]["note"] == "bundler produced pack"
    assert "ts_iso" in new_rec.history[0]
    # original unchanged (model_copy returns new instance)
    assert rec.state == SceneState.PENDING
    assert len(rec.history) == 0


def test_draft_response_defaults() -> None:
    d = DraftResponse(
        scene_text="...",
        mode="A",
        model_id="m",
        tokens_in=10,
        tokens_out=20,
        latency_ms=100,
        output_sha="h",
    )
    assert d.mode == "A"
    assert d.voice_pin_sha is None
    assert d.attempt_number == 1


def test_draft_request_defaults() -> None:
    sr = SceneRequest(
        chapter=1, scene_index=1, pov="P", date_iso="1519-01-01", location="L", beat_function="b"
    )
    cp = ContextPack(scene_request=sr, retrievals={}, total_bytes=0, fingerprint="h")
    req = DraftRequest(context_pack=cp)
    assert req.prior_scenes == []
    assert req.generation_config == {}
    assert req.prompt_template_id == "default"


def test_critic_response_shape() -> None:
    c = CriticResponse(
        pass_per_axis={
            "historical": True,
            "metaphysics": True,
            "entity": True,
            "arc": True,
            "donts": True,
        },
        scores_per_axis={
            "historical": 85.0,
            "metaphysics": 90.0,
            "entity": 88.0,
            "arc": 80.0,
            "donts": 95.0,
        },
        issues=[],
        overall_pass=True,
        model_id="claude-opus-4-7",
        rubric_version="v1",
        output_sha="h",
    )
    assert c.overall_pass
    assert len(c.pass_per_axis) == 5


def test_critic_issue_minimal() -> None:
    issue = CriticIssue(
        axis="historical",
        severity="high",
        location="para-3",
        claim="date anachronism",
        evidence="mentions printing press 200 years early",
    )
    assert issue.citation is None


def test_critic_request_minimal() -> None:
    sr = SceneRequest(
        chapter=1, scene_index=1, pov="P", date_iso="1519-01-01", location="L", beat_function="b"
    )
    cp = ContextPack(scene_request=sr, retrievals={}, total_bytes=0, fingerprint="h")
    req = CriticRequest(
        scene_text="scene", context_pack=cp, rubric_id="scene.v1", rubric_version="v1"
    )
    assert req.chapter_context is None


def test_regen_request_minimal() -> None:
    sr = SceneRequest(
        chapter=1, scene_index=1, pov="P", date_iso="1519-01-01", location="L", beat_function="b"
    )
    cp = ContextPack(scene_request=sr, retrievals={}, total_bytes=0, fingerprint="h")
    prior = DraftResponse(
        scene_text="...",
        mode="A",
        model_id="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
        output_sha="h",
    )
    req = RegenRequest(
        prior_draft=prior, context_pack=cp, issues=[], attempt_number=2, max_attempts=3
    )
    assert req.attempt_number == 2


def test_entity_card_minimal() -> None:
    card = EntityCard(entity_name="Andres", last_seen_chapter=3, source_chapter_sha="abc")
    assert card.state == {}
    assert card.evidence_spans == []


def test_retrospective_minimal() -> None:
    retro = Retrospective(
        chapter_num=1,
        what_worked="pacing",
        what_didnt="motive clarity",
        pattern="motive bleeds when POV drifts",
    )
    assert retro.candidate_theses == []


def test_thesis_evidence_minimal() -> None:
    t = ThesisEvidence(thesis_id="T-001", action="open", evidence="chapter 1 shows X")
    assert t.transferable_artifact is None


def test_scene_state_record_defaults() -> None:
    rec = SceneStateRecord(scene_id="ch01_sc01", state=SceneState.PENDING)
    assert rec.attempts == {}
    assert rec.mode_tag is None
    assert rec.history == []
    assert rec.blockers == []


def test_imports_from_interfaces_package() -> None:
    """FOUND-04: all types importable from book_pipeline.interfaces."""
    from book_pipeline.interfaces import (  # noqa: F401
        ContextPack,
        CriticIssue,
        CriticRequest,
        CriticResponse,
        DraftRequest,
        DraftResponse,
        EntityCard,
        Event,
        RegenRequest,
        RetrievalHit,
        RetrievalResult,
        Retrospective,
        SceneRequest,
        SceneState,
        SceneStateRecord,
        ThesisEvidence,
        transition,
    )


def test_event_rejects_unknown_fields_strict() -> None:
    """Event uses default Pydantic config — verify round-trip dump/load preserves shape."""
    e = Event(
        event_id="x",
        ts_iso="2026-04-21T00:00:00Z",
        role="drafter",
        model="m",
        prompt_hash="p",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
        output_hash="o",
    )
    dumped = e.model_dump()
    e2 = Event(**dumped)
    assert e2 == e


def test_event_can_be_constructed_with_all_fields() -> None:
    """Verify every OBS-01 field is settable."""
    e = Event(
        schema_version="1.0",
        event_id="id",
        ts_iso="2026-04-21T00:00:00Z",
        role="critic",
        model="claude-opus-4-7",
        prompt_hash="ph",
        input_tokens=500,
        cached_tokens=100,
        output_tokens=200,
        latency_ms=999,
        temperature=0.7,
        top_p=0.95,
        caller_context={"module": "critic", "scene_id": "ch01_sc01"},
        output_hash="oh",
        mode="A",
        rubric_version="scene.v1",
        checkpoint_sha="sha-of-voice-pin",
        extra={"custom": "value"},
    )
    assert e.mode == "A"
    assert e.checkpoint_sha == "sha-of-voice-pin"
    assert e.cached_tokens == 100
    assert e.temperature == pytest.approx(0.7)
