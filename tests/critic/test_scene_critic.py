"""Tests for SceneCritic (Plan 03-05 Task 2).

Covers Tests A-J per plan <behavior>:
  A — Protocol conformance (isinstance(c, Critic)).
  B (W-6) — happy path: 1 audit file + 1 role='critic' Event with
            rubric_version top-level field parameterized from config/rubric.yaml
            (NOT hardcoded 'v1').
  C — post-process fills missing axis with pass=True, score=75.0;
      Event.extra['filled_axes'] populated.
  D — overall_pass invariant enforced; Event.extra['invariant_fixed']=True.
  E (W-7) — tenacity exhaustion → SceneCriticError + audit STILL written with
            raw_anthropic_response={error, error_type, attempts_made} and
            parsed_critic_response=None; error Event emitted.
  F — cache_control={'type':'ephemeral','ttl':'1h'} present in system_blocks.
  G — Event has rubric_version on top-level Phase-1 field.
  H — Two review() calls send identical system_blocks (cache hits).
  I (W-6) — request.rubric_version mismatch vs rubric.yaml → warning + continue;
            Event.extra['request_rubric_version_mismatch']=True.
  J — CRIT-04 audit file content round-trips.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from anthropic import APIConnectionError

from book_pipeline.config.rubric import RubricConfig
from book_pipeline.interfaces.critic import Critic
from book_pipeline.interfaces.types import CriticResponse, Event
from tests.critic.fixtures import (
    FakeAnthropicClient,
    FakeEventLogger,
    make_canonical_critic_response,
    make_critic_request,
)


FEWSHOT_PATH = Path("src/book_pipeline/critic/templates/scene_fewshot.yaml")
TEMPLATE_PATH = Path("src/book_pipeline/critic/templates/system.j2")


def _rubric_version_from_yaml() -> str:
    """Read rubric_version dynamically from config/rubric.yaml (W-6)."""
    data = yaml.safe_load(Path("config/rubric.yaml").read_text(encoding="utf-8"))
    return data["rubric_version"]


def _patch_tenacity_wait_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch tenacity so retry waits are ~0 — keeps the suite fast."""
    import tenacity

    orig_init = tenacity.wait_exponential.__init__

    def fast_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        orig_init(self, *args, **kwargs)
        self.multiplier = 0.001
        self.min = 0.0
        self.max = 0.001

    monkeypatch.setattr(tenacity.wait_exponential, "__init__", fast_init)


@pytest.fixture
def scene_critic_cls():
    from book_pipeline.critic.scene import SceneCritic

    return SceneCritic


@pytest.fixture
def make_critic(tmp_path, scene_critic_cls):
    """Factory that builds a SceneCritic with sensible test defaults."""
    def _factory(
        *,
        anthropic_client,
        event_logger=None,
        rubric=None,
        audit_dir=None,
    ):
        return scene_critic_cls(
            anthropic_client=anthropic_client,
            event_logger=event_logger if event_logger is not None else FakeEventLogger(),
            rubric=rubric if rubric is not None else RubricConfig(),
            fewshot_path=FEWSHOT_PATH,
            template_path=TEMPLATE_PATH,
            audit_dir=audit_dir if audit_dir is not None else tmp_path / "critic_audit",
        )

    return _factory


def test_A_protocol_conformance(make_critic) -> None:
    """Test A: SceneCritic satisfies the frozen Critic Protocol."""
    critic = make_critic(anthropic_client=FakeAnthropicClient())
    assert critic.level == "scene"
    assert isinstance(critic, Critic)


def test_B_happy_path_writes_audit_and_emits_critic_event(tmp_path, make_critic) -> None:
    """Test B (W-6): happy-path review() writes 1 audit file + emits 1
    role='critic' Event whose top-level rubric_version field is
    parameterized from config/rubric.yaml (NOT hardcoded 'v1')."""
    expected_rubric_version = _rubric_version_from_yaml()

    fake_client = FakeAnthropicClient()
    logger = FakeEventLogger()
    audit_dir = tmp_path / "critic_audit"

    critic = make_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=audit_dir,
    )
    request = make_critic_request(rubric_version=expected_rubric_version)
    response = critic.review(request)

    assert isinstance(response, CriticResponse)
    assert response.rubric_version == expected_rubric_version

    # Exactly one audit file written
    audit_files = list(audit_dir.glob("*.json"))
    assert len(audit_files) == 1, f"Expected 1 audit file, got {len(audit_files)}"

    # Exactly one role='critic' Event emitted
    critic_events = [e for e in logger.events if e.role == "critic"]
    assert len(critic_events) == 1
    ev = critic_events[0]
    assert ev.rubric_version == expected_rubric_version, (
        f"Event.rubric_version top-level field must match config/rubric.yaml "
        f"(got {ev.rubric_version!r}, expected {expected_rubric_version!r})"
    )


def test_C_missing_axis_is_filled_with_default(tmp_path, make_critic) -> None:
    """Test C: response missing 'metaphysics' → post-process fills with
    pass=True, score=75.0; Event.extra['filled_axes']==['metaphysics']."""
    partial = make_canonical_critic_response(include_all_axes=False)
    fake_client = FakeAnthropicClient(parsed_response=partial)
    logger = FakeEventLogger()
    critic = make_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "critic_audit",
    )
    response = critic.review(make_critic_request())

    assert response.pass_per_axis["metaphysics"] is True
    assert response.scores_per_axis["metaphysics"] == 75.0

    ev = [e for e in logger.events if e.role == "critic"][0]
    assert ev.extra.get("filled_axes") == ["metaphysics"]


def test_D_invariant_fix_when_overall_pass_inconsistent(tmp_path, make_critic) -> None:
    """Test D: response with overall_pass=True but historical=False → invariant
    corrected to overall_pass=False; Event.extra['invariant_fixed']=True."""
    # Build a response where overall_pass is True but one axis fails
    bad = CriticResponse(
        pass_per_axis={
            "historical": False,
            "metaphysics": True,
            "entity": True,
            "arc": True,
            "donts": True,
        },
        scores_per_axis={
            "historical": 50.0,
            "metaphysics": 88.0,
            "entity": 90.0,
            "arc": 89.0,
            "donts": 94.0,
        },
        issues=[],
        overall_pass=True,  # INCONSISTENT
        model_id="claude-opus-4-7",
        rubric_version="v1",
        output_sha="will-be-overwritten",
    )
    fake_client = FakeAnthropicClient(parsed_response=bad)
    logger = FakeEventLogger()
    critic = make_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "critic_audit",
    )
    response = critic.review(make_critic_request())

    assert response.overall_pass is False, "overall_pass must be corrected to False"
    ev = [e for e in logger.events if e.role == "critic"][0]
    assert ev.extra.get("invariant_fixed") is True


def test_E_tenacity_exhaustion_writes_failure_audit(
    tmp_path, make_critic, monkeypatch
) -> None:
    """Test E (W-7 UPDATED): tenacity exhausts → SceneCriticError raised AND
    audit file written with failure-path payload."""
    _patch_tenacity_wait_fast(monkeypatch)
    from book_pipeline.critic.scene import SceneCriticError

    side_effect = [APIConnectionError(request=None) for _ in range(5)]  # type: ignore[arg-type]
    fake_client = FakeAnthropicClient(side_effect=side_effect)
    logger = FakeEventLogger()
    audit_dir = tmp_path / "critic_audit"
    critic = make_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=audit_dir,
    )

    with pytest.raises(SceneCriticError) as exc_info:
        critic.review(make_critic_request())
    assert exc_info.value.reason == "anthropic_unavailable"

    # Audit file IS written on failure
    audit_files = list(audit_dir.glob("*.json"))
    assert len(audit_files) == 1

    import json
    record = json.loads(audit_files[0].read_text())

    # W-7 failure-path shape
    assert record["parsed_critic_response"] is None
    assert record["raw_anthropic_response"]["error_type"] == "APIConnectionError"
    assert record["raw_anthropic_response"]["attempts_made"] == 5
    assert "error" in record["raw_anthropic_response"]

    # Other fields still populated
    for field_name in (
        "event_id",
        "scene_id",
        "attempt_number",
        "timestamp_iso",
        "rubric_version",
        "model_id",
        "system_prompt_sha",
        "user_prompt_sha",
    ):
        assert field_name in record and record[field_name] is not None, (
            f"failure audit must populate {field_name}"
        )

    # Error event emitted
    error_events = [
        e for e in logger.events
        if e.role == "critic" and e.extra.get("status") == "error"
    ]
    assert len(error_events) == 1


def test_F_cache_control_applied_to_system_prompt(tmp_path, make_critic) -> None:
    """Test F: cache_control={'type':'ephemeral','ttl':'1h'} in system_blocks."""
    fake_client = FakeAnthropicClient()
    critic = make_critic(
        anthropic_client=fake_client,
        audit_dir=tmp_path / "critic_audit",
    )
    critic.review(make_critic_request())

    assert len(fake_client.messages.call_args_list) == 1
    call_kwargs = fake_client.messages.call_args_list[0]
    system_blocks = call_kwargs["system"]
    assert isinstance(system_blocks, list)
    assert len(system_blocks) >= 1
    first_block = system_blocks[0]
    assert first_block["type"] == "text"
    assert first_block["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_G_event_rubric_version_top_level_field(tmp_path, make_critic) -> None:
    """Test G: Event carries rubric_version on TOP-LEVEL field (Phase-1 schema);
    Event round-trips via model_validate."""
    fake_client = FakeAnthropicClient()
    logger = FakeEventLogger()
    critic = make_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "critic_audit",
    )
    critic.review(make_critic_request())

    ev = [e for e in logger.events if e.role == "critic"][0]
    assert ev.rubric_version is not None
    dumped = ev.model_dump()
    assert "rubric_version" in dumped
    # round-trip
    Event.model_validate(dumped)


def test_H_two_review_calls_send_identical_system_blocks(tmp_path, make_critic) -> None:
    """Test H: prompt caching effectiveness — two review() calls produce
    object-equal system_blocks (pre-rendered once at __init__)."""
    fake_client = FakeAnthropicClient()
    critic = make_critic(
        anthropic_client=fake_client,
        audit_dir=tmp_path / "critic_audit",
    )
    critic.review(make_critic_request())
    critic.review(make_critic_request(scene_index=2))

    calls = fake_client.messages.call_args_list
    assert len(calls) == 2
    sb1 = calls[0]["system"]
    sb2 = calls[1]["system"]
    assert sb1 == sb2, "system_blocks must be identical across review() calls"
    # Same system prompt text (cache-key stable)
    assert sb1[0]["text"] == sb2[0]["text"]


def test_I_request_rubric_version_mismatch_logged_and_continues(
    tmp_path, make_critic
) -> None:
    """Test I (W-6): rubric_version on CriticRequest different from
    RubricConfig().rubric_version → warning + continue;
    Event.extra['request_rubric_version_mismatch']=True."""
    expected_rubric_version = _rubric_version_from_yaml()
    assert expected_rubric_version != "__mismatch_v_99"

    fake_client = FakeAnthropicClient()
    logger = FakeEventLogger()
    critic = make_critic(
        anthropic_client=fake_client,
        event_logger=logger,
        audit_dir=tmp_path / "critic_audit",
    )

    # Request with a mismatched rubric_version
    request = make_critic_request(rubric_version="__mismatch_v_99")
    response = critic.review(request)

    # Response still stamped with the critic's rubric_version (from RubricConfig)
    assert response.rubric_version == expected_rubric_version

    ev = [e for e in logger.events if e.role == "critic"][0]
    assert ev.extra.get("request_rubric_version_mismatch") is True


def test_J_audit_file_content_round_trips_critic_response(
    tmp_path, make_critic
) -> None:
    """Test J: audit file has all 11 expected keys; parsed_critic_response
    round-trips via CriticResponse.model_validate."""
    fake_client = FakeAnthropicClient()
    audit_dir = tmp_path / "critic_audit"
    critic = make_critic(
        anthropic_client=fake_client,
        audit_dir=audit_dir,
    )
    critic.review(make_critic_request())

    audit_files = list(audit_dir.glob("*.json"))
    assert len(audit_files) == 1
    import json
    record = json.loads(audit_files[0].read_text())

    # All required keys
    required_keys = {
        "event_id",
        "scene_id",
        "attempt_number",
        "timestamp_iso",
        "rubric_version",
        "model_id",
        "opus_model_id_response",
        "caching_cache_control_applied",
        "cached_input_tokens",
        "system_prompt_sha",
        "user_prompt_sha",
        "context_pack_fingerprint",
        "raw_anthropic_response",
        "parsed_critic_response",
    }
    missing = required_keys - record.keys()
    assert not missing, f"audit record missing keys: {missing}"

    # parsed_critic_response round-trips
    parsed = record["parsed_critic_response"]
    CriticResponse.model_validate(parsed)
