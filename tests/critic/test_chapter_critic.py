"""Tests for ChapterCritic (Plan 04-02 Task 2 — CRIT-02).

Covers tests A-K per plan <behavior>:
  A — Protocol conformance (isinstance(c, Critic), level == 'chapter').
  B — Happy path: all axes pass → overall_pass=True + 1 chapter_critic Event.
  C — Score below 60 threshold (3/5 × 20) → axis fails + overall_pass=False.
  D — High-severity issue on an axis with passing score → axis fails anyway.
  E — Fresh-pack invariant: audit records chapter_pack fingerprint, distinct
      from scene_pack fingerprints (CRIT-02 core mitigation).
  F — Audit record written on success under runs/critic_audit/chapter_NN_...
  G — W-7: audit record STILL written on tenacity exhaustion.
  H — Exactly 1 Event per review() call (success XOR error).
  I — rubric_version stamped on response + Event + audit record.
  J — _system_blocks object identity stable across review() calls (cache key).
  K — Tenacity exhaustion fast (<2s) with wait patch + audit written.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import tenacity
import yaml
from anthropic import APIConnectionError

from book_pipeline.config.rubric import RubricConfig
from book_pipeline.interfaces.critic import Critic
from book_pipeline.interfaces.types import (
    ContextPack,
    CriticIssue,
    CriticRequest,
    CriticResponse,
    RetrievalResult,
    SceneRequest,
)
from tests.critic.fixtures import (
    FakeAnthropicClient,
    FakeEventLogger,
    make_canonical_critic_response,
)

CHAPTER_FEWSHOT_PATH = Path("src/book_pipeline/critic/templates/chapter_fewshot.yaml")
CHAPTER_TEMPLATE_PATH = Path("src/book_pipeline/critic/templates/chapter_system.j2")


def _chapter_rubric_version_from_yaml() -> str:
    """Read chapter_rubric_version from config/rubric.yaml."""
    data = yaml.safe_load(Path("config/rubric.yaml").read_text(encoding="utf-8"))
    return data["chapter_rubric_version"]


def _patch_tenacity_wait_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the retry wait on ChapterCritic._call_opus_inner to ~0."""
    from book_pipeline.critic.chapter import ChapterCritic

    fast = tenacity.wait_fixed(0)
    monkeypatch.setattr(ChapterCritic._call_opus_inner.retry, "wait", fast)


def _chapter_response(
    *,
    overall_pass: bool = True,
    failing_axis: str | None = None,
    failing_score: float = 40.0,
    high_sev_axis: str | None = None,
    rubric_version: str = "chapter.v1",
) -> CriticResponse:
    """Build a CriticResponse at chapter scale. Scores are 0..100 (= 0..5 × 20)."""
    pass_per_axis = {
        "historical": True,
        "metaphysics": True,
        "entity": True,
        "arc": True,
        "donts": True,
    }
    scores_per_axis = {
        "historical": 80.0,
        "metaphysics": 80.0,
        "entity": 80.0,
        "arc": 80.0,
        "donts": 80.0,
    }
    issues: list[CriticIssue] = []
    if failing_axis is not None:
        pass_per_axis[failing_axis] = False
        scores_per_axis[failing_axis] = failing_score
    if high_sev_axis is not None:
        issues.append(
            CriticIssue(
                axis=high_sev_axis,
                severity="high",
                location="chapter para 2",
                claim="cross-scene entity drift",
                evidence="Malintzin relocates silently between sc02 and sc03",
                citation=None,
            )
        )
    final_overall = overall_pass if failing_axis is None and high_sev_axis is None else False
    return CriticResponse(
        pass_per_axis=pass_per_axis,
        scores_per_axis=scores_per_axis,
        issues=issues,
        overall_pass=final_overall,
        model_id="claude-opus-4-7",
        rubric_version=rubric_version,
        output_sha="will-be-overwritten",
    )


def _make_chapter_pack(fingerprint: str = "CHAPTER_FP_XYZ") -> ContextPack:
    """Build a FRESH ContextPack with a chapter-scoped SceneRequest."""
    return ContextPack(
        scene_request=SceneRequest(
            chapter=1,
            scene_index=0,  # chapter-level: sentinel scene_index=0 per plan spec
            pov="Primary POV",
            date_iso="1519-09-01",  # chapter midpoint ISO
            location="chapter arc",
            beat_function="chapter_overview",
        ),
        retrievals={
            "historical": RetrievalResult(
                retriever_name="historical",
                hits=[],
                bytes_used=0,
                query_fingerprint="q_hist_chapter",
            ),
        },
        total_bytes=1000,
        assembly_strategy="round_robin",
        fingerprint=fingerprint,
    )


def _make_chapter_request(
    *,
    chapter_num: int = 1,
    rubric_version: str = "chapter.v1",
    assembly_commit_sha: str | None = "deadbeef",
    context_pack: ContextPack | None = None,
) -> CriticRequest:
    pack = context_pack if context_pack is not None else _make_chapter_pack()
    ctx: dict[str, object] = {"chapter_num": chapter_num}
    if assembly_commit_sha is not None:
        ctx["assembly_commit_sha"] = assembly_commit_sha
    return CriticRequest(
        scene_text="Assembled chapter text spanning three scenes.",
        context_pack=pack,
        rubric_id="chapter.v1",
        rubric_version=rubric_version,
        chapter_context=ctx,
    )


@pytest.fixture
def chapter_critic_cls():
    from book_pipeline.critic.chapter import ChapterCritic

    return ChapterCritic


@pytest.fixture
def make_chapter_critic(tmp_path, chapter_critic_cls):
    def _factory(
        *,
        anthropic_client,
        event_logger=None,
        rubric=None,
        audit_dir=None,
    ):
        return chapter_critic_cls(
            anthropic_client=anthropic_client,
            event_logger=event_logger if event_logger is not None else FakeEventLogger(),
            rubric=rubric if rubric is not None else RubricConfig(),
            fewshot_path=CHAPTER_FEWSHOT_PATH,
            template_path=CHAPTER_TEMPLATE_PATH,
            audit_dir=audit_dir if audit_dir is not None else tmp_path / "critic_audit",
        )

    return _factory


# ---------------------------------------------------------------------- #
# A — Protocol conformance                                                #
# ---------------------------------------------------------------------- #


def test_A_protocol_conformance(make_chapter_critic) -> None:
    """ChapterCritic satisfies the frozen Critic Protocol; level == 'chapter'."""
    critic = make_chapter_critic(anthropic_client=FakeAnthropicClient())
    assert critic.level == "chapter"
    assert isinstance(critic, Critic)


# ---------------------------------------------------------------------- #
# B — Happy path                                                          #
# ---------------------------------------------------------------------- #


def test_B_happy_path_passes(tmp_path, make_chapter_critic) -> None:
    """All 5 axes score 80 → overall_pass=True; 1 chapter_critic Event emitted
    with caller_context.chapter_num == 1 and rubric_version == chapter.v1."""
    expected = _chapter_rubric_version_from_yaml()
    fake_client = FakeAnthropicClient(parsed_response=_chapter_response())
    logger = FakeEventLogger()
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "critic_audit",
    )

    response = critic.review(_make_chapter_request())
    assert isinstance(response, CriticResponse)
    assert response.overall_pass is True
    assert response.rubric_version == expected

    events = [e for e in logger.events if e.role == "chapter_critic"]
    assert len(events) == 1
    ev = events[0]
    assert ev.caller_context["chapter_num"] == 1
    assert ev.rubric_version == expected


# ---------------------------------------------------------------------- #
# C — Sub-threshold fails axis                                            #
# ---------------------------------------------------------------------- #


def test_C_below_threshold_fails(tmp_path, make_chapter_critic) -> None:
    """An axis scoring below the 60 (3/5 × 20) threshold fails AND flips
    overall_pass=False via post-process invariant."""
    # Simulate a response where historical scores 50 but the LLM still claims True
    # (tests post-process threshold enforcement AND invariant fix together).
    bad = _chapter_response()
    bad.pass_per_axis["historical"] = True  # LLM claim
    bad.scores_per_axis["historical"] = 50.0  # below 60 threshold
    bad.overall_pass = True  # inconsistent

    fake_client = FakeAnthropicClient(parsed_response=bad)
    logger = FakeEventLogger()
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "critic_audit",
    )
    response = critic.review(_make_chapter_request())

    assert response.pass_per_axis["historical"] is False, (
        "score 50 < 60 threshold must flip pass=False"
    )
    assert response.overall_pass is False


# ---------------------------------------------------------------------- #
# D — High-severity overrides score                                       #
# ---------------------------------------------------------------------- #


def test_D_high_severity_fails_axis(tmp_path, make_chapter_critic) -> None:
    """An axis with score >=60 but a high-severity issue → axis fails."""
    bad = _chapter_response()
    # LLM outputs entity=80 pass=True but with a high-severity entity issue
    bad.pass_per_axis["entity"] = True
    bad.scores_per_axis["entity"] = 80.0
    bad.issues.append(
        CriticIssue(
            axis="entity",
            severity="high",
            location="chapter para 4",
            claim="Malintzin is simultaneously in Cempoala and Tlaxcala",
            evidence="sc02 places her in Cempoala; sc03 in Tlaxcala with no travel bridge",
            citation=None,
        )
    )
    bad.overall_pass = True

    fake_client = FakeAnthropicClient(parsed_response=bad)
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        audit_dir=tmp_path / "critic_audit",
    )
    response = critic.review(_make_chapter_request())

    assert response.pass_per_axis["entity"] is False, (
        "high-severity issue must flip axis pass=False regardless of score"
    )
    assert response.overall_pass is False


# ---------------------------------------------------------------------- #
# E — Fresh-pack invariant                                                #
# ---------------------------------------------------------------------- #


def test_E_fresh_pack_invariant(tmp_path, make_chapter_critic) -> None:
    """CRIT-02 core: audit record carries chapter_pack.fingerprint, which is
    DISTINCT from any scene_pack fingerprint. Plan 04-04 DAG orchestrator is
    responsible for passing a FRESH pack (bundler.bundle at chapter scope)."""
    scene_pack_fp = "SCENE_FP_ABC"
    chapter_pack_fp = "CHAPTER_FP_XYZ"
    assert scene_pack_fp != chapter_pack_fp

    chapter_pack = _make_chapter_pack(fingerprint=chapter_pack_fp)
    fake_client = FakeAnthropicClient(parsed_response=_chapter_response())
    audit_dir = tmp_path / "critic_audit"
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        audit_dir=audit_dir,
    )
    critic.review(_make_chapter_request(context_pack=chapter_pack))

    audit_files = list(audit_dir.glob("*.json"))
    assert len(audit_files) == 1
    record = json.loads(audit_files[0].read_text())
    assert record["context_pack_fingerprint"] == chapter_pack_fp
    assert scene_pack_fp != record["context_pack_fingerprint"]


# ---------------------------------------------------------------------- #
# F — Audit written on success                                            #
# ---------------------------------------------------------------------- #


def test_F_audit_record_on_success(tmp_path, make_chapter_critic) -> None:
    """Success path writes one audit file under runs/critic_audit with
    chapter_01_ prefix and all required fields populated."""
    audit_dir = tmp_path / "critic_audit"
    fake_client = FakeAnthropicClient(parsed_response=_chapter_response())
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        audit_dir=audit_dir,
    )
    critic.review(_make_chapter_request(chapter_num=1))

    audit_files = list(audit_dir.glob("chapter_01_*.json"))
    assert len(audit_files) == 1

    record = json.loads(audit_files[0].read_text())
    assert record["scene_id"] == "chapter_01"
    assert record["chapter_num"] == 1
    assert record["rubric_version"] == _chapter_rubric_version_from_yaml()
    assert record["model_id"] == "claude-opus-4-7"
    assert record["parsed_critic_response"] is not None
    assert record["raw_anthropic_response"] is not None


# ---------------------------------------------------------------------- #
# G — W-7 audit on failure                                                #
# ---------------------------------------------------------------------- #


def test_G_audit_record_on_failure_W7(
    tmp_path, make_chapter_critic, monkeypatch
) -> None:
    """Tenacity exhaustion still writes an audit record with failure-path shape."""
    _patch_tenacity_wait_fast(monkeypatch)
    from book_pipeline.critic.chapter import ChapterCriticError

    side_effect = [APIConnectionError(request=None) for _ in range(5)]  # type: ignore[arg-type]
    fake_client = FakeAnthropicClient(side_effect=side_effect)
    audit_dir = tmp_path / "critic_audit"
    logger = FakeEventLogger()
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=audit_dir,
    )

    with pytest.raises(ChapterCriticError) as exc_info:
        critic.review(_make_chapter_request())
    assert exc_info.value.reason == "anthropic_unavailable"

    audit_files = list(audit_dir.glob("*.json"))
    assert len(audit_files) == 1
    record = json.loads(audit_files[0].read_text())
    assert record["parsed_critic_response"] is None
    assert record["raw_anthropic_response"]["error_type"] == "APIConnectionError"
    assert record["raw_anthropic_response"]["attempts_made"] == 5

    err_events = [
        e for e in logger.events
        if e.role == "chapter_critic" and e.extra.get("status") == "error"
    ]
    assert len(err_events) == 1


# ---------------------------------------------------------------------- #
# H — One event per invocation                                            #
# ---------------------------------------------------------------------- #


def test_H_one_event_per_invocation(tmp_path, make_chapter_critic) -> None:
    """Success path: exactly 1 chapter_critic event per review() call."""
    logger = FakeEventLogger()
    fake_client = FakeAnthropicClient(parsed_response=_chapter_response())
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "critic_audit",
    )
    critic.review(_make_chapter_request())
    chapter_events = [e for e in logger.events if e.role == "chapter_critic"]
    assert len(chapter_events) == 1


# ---------------------------------------------------------------------- #
# I — rubric_version stamped consistently                                 #
# ---------------------------------------------------------------------- #


def test_I_rubric_version_stamped_everywhere(tmp_path, make_chapter_critic) -> None:
    """CriticResponse.rubric_version, Event.rubric_version, and
    audit_record.rubric_version all carry the critic's chapter_rubric version."""
    expected = _chapter_rubric_version_from_yaml()

    logger = FakeEventLogger()
    fake_client = FakeAnthropicClient(parsed_response=_chapter_response())
    audit_dir = tmp_path / "critic_audit"
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=audit_dir,
    )
    response = critic.review(_make_chapter_request())

    assert response.rubric_version == expected
    ev = next(e for e in logger.events if e.role == "chapter_critic")
    assert ev.rubric_version == expected
    record = json.loads(next(audit_dir.glob("*.json")).read_text())
    assert record["rubric_version"] == expected


# ---------------------------------------------------------------------- #
# J — cached system_blocks identity                                       #
# ---------------------------------------------------------------------- #


def test_J_cached_system_blocks_identity(tmp_path, make_chapter_critic) -> None:
    """Two review() calls reuse the SAME _system_blocks list object — proves
    cache-key stability (Anthropic caches on identical prefix text/object)."""
    fake_client = FakeAnthropicClient(parsed_response=_chapter_response())
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        audit_dir=tmp_path / "critic_audit",
    )
    sb_before = critic._system_blocks
    critic.review(_make_chapter_request())
    sb_after_1 = critic._system_blocks
    critic.review(_make_chapter_request(chapter_num=2))
    sb_after_2 = critic._system_blocks
    assert sb_before is sb_after_1 is sb_after_2, (
        "_system_blocks must be the SAME object across review() calls"
    )


# ---------------------------------------------------------------------- #
# K — tenacity exhaustion fast                                            #
# ---------------------------------------------------------------------- #


def test_K_tenacity_exhaustion_fast(
    tmp_path, make_chapter_critic, monkeypatch
) -> None:
    """With wait patched to 0, tenacity exhaustion completes quickly AND
    writes the failure audit."""
    import time as _time

    _patch_tenacity_wait_fast(monkeypatch)
    from book_pipeline.critic.chapter import ChapterCriticError

    side_effect = [APIConnectionError(request=None) for _ in range(5)]  # type: ignore[arg-type]
    fake_client = FakeAnthropicClient(side_effect=side_effect)
    audit_dir = tmp_path / "critic_audit"
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        audit_dir=audit_dir,
    )

    t0 = _time.monotonic()
    with pytest.raises(ChapterCriticError):
        critic.review(_make_chapter_request())
    elapsed = _time.monotonic() - t0
    assert elapsed < 2.0, f"tenacity exhaustion took {elapsed:.2f}s (expected <2s)"

    assert len(list(audit_dir.glob("*.json"))) == 1


# ---------------------------------------------------------------------- #
# Supplementary — missing-axes fill                                       #
# ---------------------------------------------------------------------- #


def test_missing_axis_is_filled(tmp_path, make_chapter_critic) -> None:
    """Response omitting an axis → post-process fills with pass=True, score=60.0
    (chapter default matches 3/5 threshold so filled axis default-passes)."""
    partial = make_canonical_critic_response(
        include_all_axes=False, rubric_version="chapter.v1"
    )
    fake_client = FakeAnthropicClient(parsed_response=partial)
    logger = FakeEventLogger()
    critic = make_chapter_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "critic_audit",
    )
    response = critic.review(_make_chapter_request())
    assert response.pass_per_axis["metaphysics"] is True
    assert response.scores_per_axis["metaphysics"] == 60.0

    ev = next(e for e in logger.events if e.role == "chapter_critic")
    assert ev.extra.get("filled_axes") == ["metaphysics"]
