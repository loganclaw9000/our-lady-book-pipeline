"""Tests for SceneCritic 13-axis extension (Plan 07-04 PHYSICS-07 + PHYSICS-13).

Test coverage (per Plan 07-04 Task 2 <behavior>):
  Test 1 — REQUIRED_AXES set has 13 elements
  Test 2 — AXES_ORDERED is a 13-tuple in the documented order
  Test 3 — Anthropic mock returns parsed CriticResponse with all 13 axes True;
           _post_process clean; overall_pass=True
  Test 4 (PHYSICS-13 hard-stop) — motivation_fidelity=False forces overall_pass=False
  Test 5 — historical=False, motivation=True, others True → overall_pass=False
           (existing AND-of-axes invariant)
  Test 6 — Mock returns 5 axes only; _post_process fills the missing 8 with
           pass=False; overall_pass=False
  Test 7 — Rendered system.j2 contains all 6 LLM-judged physics axes;
           does NOT contain stub_leak/repetition_loop in non-comment lines
  Test 8 — rubric_version on every emitted Event = "v2"
  Test 9 (Warning #3) — scene_fewshot.yaml total NEW few-shot count <= 8
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from book_pipeline.config.rubric import REQUIRED_AXES, RubricConfig
from book_pipeline.interfaces.types import CriticResponse, Event
from tests.critic.fixtures import (
    FakeAnthropicClient,
    FakeEventLogger,
    make_critic_request,
)

FEWSHOT_PATH = Path("src/book_pipeline/critic/templates/scene_fewshot.yaml")
TEMPLATE_PATH = Path("src/book_pipeline/critic/templates/system.j2")


# Phase 7 Plan 04: documented 13-axis order (Pitfall 9 — schema field order
# = prompt rubric order).
EXPECTED_AXES_13 = (
    "historical",
    "metaphysics",
    "entity",
    "arc",
    "donts",
    "pov_fidelity",
    "motivation_fidelity",
    "treatment_fidelity",
    "content_ownership",
    "named_quantity_drift",
    "scene_buffer_similarity",
    "stub_leak",
    "repetition_loop",
)


def _rubric_version_from_yaml() -> str:
    data = yaml.safe_load(Path("config/rubric.yaml").read_text(encoding="utf-8"))
    return data["rubric_version"]


def make_canonical_critic_response_v2(
    *,
    overall_pass: bool = True,
    overrides: dict[str, bool] | None = None,
    include_axes: tuple[str, ...] | None = None,
    rubric_version: str = "v2",
    model_id: str = "claude-opus-4-7",
) -> CriticResponse:
    """Build a 13-axis CriticResponse for Phase 7 tests.

    overrides: per-axis pass override map (e.g. {"motivation_fidelity": False}).
    include_axes: if provided, only emit these axes (used for Test 6 partial
        response). Otherwise all 13 are emitted.
    """
    axes = include_axes if include_axes is not None else EXPECTED_AXES_13
    pass_per_axis: dict[str, bool] = {a: True for a in axes}
    if not overall_pass and "historical" in axes:
        pass_per_axis["historical"] = False
    if overrides:
        for k, v in overrides.items():
            if k in axes:
                pass_per_axis[k] = v

    scores_per_axis: dict[str, float] = {
        a: (90.0 if pass_per_axis.get(a, False) else 40.0) for a in axes
    }

    return CriticResponse(
        pass_per_axis=pass_per_axis,
        scores_per_axis=scores_per_axis,
        issues=[],
        overall_pass=all(pass_per_axis.values()) if pass_per_axis else False,
        model_id=model_id,
        rubric_version=rubric_version,
        output_sha="will-be-overwritten",
    )


@pytest.fixture
def make_critic_v2(tmp_path: Path):
    """Factory that builds a SceneCritic configured for 13-axis rubric v2."""
    from book_pipeline.critic.scene import SceneCritic

    def _factory(
        *,
        anthropic_client: Any,
        event_logger: Any | None = None,
        rubric: Any = None,
        audit_dir: Any = None,
    ) -> SceneCritic:
        return SceneCritic(
            anthropic_client=anthropic_client,
            event_logger=event_logger if event_logger is not None else FakeEventLogger(),
            rubric=rubric if rubric is not None else RubricConfig(),
            fewshot_path=FEWSHOT_PATH,
            template_path=TEMPLATE_PATH,
            audit_dir=audit_dir if audit_dir is not None else tmp_path / "critic_audit",
        )

    return _factory


# ---------------------------------------------------------------- #
# Test 1 — REQUIRED_AXES set has 13 elements                       #
# ---------------------------------------------------------------- #


def test_1_required_axes_has_13_elements() -> None:
    """REQUIRED_AXES contains exactly the 13 documented axes (5 existing +
    6 LLM-judged physics + 2 pre-LLM short-circuits)."""
    assert len(REQUIRED_AXES) == 13
    assert set(EXPECTED_AXES_13) == set(REQUIRED_AXES)


# ---------------------------------------------------------------- #
# Test 2 — AXES_ORDERED is a 13-tuple in documented order          #
# ---------------------------------------------------------------- #


def test_2_axes_ordered_is_13_tuple_in_order() -> None:
    """AXES_ORDERED tuple in critic/scene.py — Pitfall 9 (schema field order
    = prompt rubric order)."""
    from book_pipeline.critic.scene import AXES_ORDERED

    assert isinstance(AXES_ORDERED, tuple)
    assert len(AXES_ORDERED) == 13
    assert AXES_ORDERED == EXPECTED_AXES_13


# ---------------------------------------------------------------- #
# Test 3 — happy path: all 13 axes pass, overall_pass=True         #
# ---------------------------------------------------------------- #


def test_3_happy_path_all_13_axes_pass(make_critic_v2) -> None:
    """All 13 axes pass; _post_process clean; overall_pass=True."""
    parsed = make_canonical_critic_response_v2(overall_pass=True)
    fake_client = FakeAnthropicClient(parsed_response=parsed)
    logger = FakeEventLogger()
    critic = make_critic_v2(anthropic_client=fake_client, event_logger=logger)

    response = critic.review(make_critic_request(rubric_version="v2"))
    assert response.overall_pass is True
    for axis in EXPECTED_AXES_13:
        assert response.pass_per_axis[axis] is True, f"axis {axis} should pass"


# ---------------------------------------------------------------- #
# Test 4 (PHYSICS-13) — motivation_fidelity FAIL hard-stop          #
# ---------------------------------------------------------------- #


def test_4_motivation_fidelity_fail_forces_overall_false(make_critic_v2) -> None:
    """PHYSICS-13 hard-stop (D-02 load-bearing): motivation_fidelity=False
    forces overall_pass=False UNCONDITIONALLY, even if all other axes pass."""
    # Build a response where motivation_fidelity is False but all others pass,
    # and the LLM erroneously sets overall_pass=True (the hard-stop must
    # override the LLM's claim).
    parsed = make_canonical_critic_response_v2(
        overall_pass=True,
        overrides={"motivation_fidelity": False},
    )
    # Force overall_pass=True at the input boundary so we're testing the
    # hard-stop override path, not just the AND-invariant fix.
    parsed.overall_pass = True

    fake_client = FakeAnthropicClient(parsed_response=parsed)
    logger = FakeEventLogger()
    critic = make_critic_v2(anthropic_client=fake_client, event_logger=logger)

    response = critic.review(make_critic_request(rubric_version="v2"))
    assert response.pass_per_axis["motivation_fidelity"] is False
    assert response.overall_pass is False, (
        "motivation_fidelity=False MUST force overall_pass=False "
        "(D-02 hard-stop, PHYSICS-13)"
    )


# ---------------------------------------------------------------- #
# Test 5 — historical=False, motivation=True → overall_pass=False  #
# ---------------------------------------------------------------- #


def test_5_historical_fail_motivation_pass_overall_false(make_critic_v2) -> None:
    """Existing all-axes-AND invariant: historical=False even with motivation=True
    forces overall_pass=False."""
    parsed = make_canonical_critic_response_v2(
        overall_pass=True,
        overrides={"historical": False},
    )
    parsed.overall_pass = True  # exercise the invariant fix path explicitly
    fake_client = FakeAnthropicClient(parsed_response=parsed)
    critic = make_critic_v2(anthropic_client=fake_client)

    response = critic.review(make_critic_request(rubric_version="v2"))
    assert response.pass_per_axis["historical"] is False
    assert response.pass_per_axis["motivation_fidelity"] is True
    assert response.overall_pass is False


# ---------------------------------------------------------------- #
# Test 6 — Partial response: 5 of 13 axes only                     #
# ---------------------------------------------------------------- #


def test_6_partial_response_fills_missing_axes_with_false(make_critic_v2) -> None:
    """Mock returns only the original 5 axes; _post_process fills the 8 new
    axes with pass=False; overall_pass=False."""
    parsed = make_canonical_critic_response_v2(
        overall_pass=True,
        include_axes=("historical", "metaphysics", "entity", "arc", "donts"),
    )
    fake_client = FakeAnthropicClient(parsed_response=parsed)
    critic = make_critic_v2(anthropic_client=fake_client)

    response = critic.review(make_critic_request(rubric_version="v2"))
    # Existing 5 axes preserved as-is.
    for axis in ("historical", "metaphysics", "entity", "arc", "donts"):
        assert response.pass_per_axis[axis] is True
    # 8 new axes filled with pass=False.
    for axis in EXPECTED_AXES_13[5:]:
        assert response.pass_per_axis[axis] is False, (
            f"axis {axis} should be filled pass=False on omission"
        )
    assert response.overall_pass is False


# ---------------------------------------------------------------- #
# Test 7 — Rendered system.j2 contains 6 LLM axes; not 2 pre-LLM   #
# ---------------------------------------------------------------- #


def test_7_system_template_contains_6_llm_axes_not_pre_llm() -> None:
    """Rendered system prompt contains ALL 6 LLM-judged physics axes; does
    NOT contain stub_leak or repetition_loop in non-comment lines (NIT #2:
    Jinja2-comment-tolerant grep — those two are pre-LLM short-circuits)."""
    from book_pipeline.critic.scene import SystemPromptBuilder

    rubric = RubricConfig()
    builder = SystemPromptBuilder(
        rubric=rubric,
        fewshot_path=FEWSHOT_PATH,
        template_path=TEMPLATE_PATH,
    )
    rendered, _sha = builder.render()

    # 6 LLM-judged physics axes MUST be present.
    for axis in (
        "pov_fidelity",
        "motivation_fidelity",
        "treatment_fidelity",
        "content_ownership",
        "named_quantity_drift",
        "scene_buffer_similarity",
    ):
        assert axis in rendered, f"LLM-judged axis {axis} missing from system prompt"

    # 5 original axes still present.
    for axis in ("historical", "metaphysics", "entity", "arc", "donts"):
        assert axis in rendered, f"original axis {axis} missing from system prompt"


def test_7b_template_source_excludes_stub_leak_repetition_in_non_comment_lines() -> None:
    """NIT #2: Jinja2-comment-tolerant grep — stub_leak and repetition_loop
    must NOT appear in non-comment lines of the SOURCE system.j2 template
    (these are deterministic pre-LLM short-circuits, not LLM-judged axes)."""
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    # Strip Jinja2 comments {# ... #} (single-line) and {#- ... -#}.
    import re

    def _strip_jinja_comments(text: str) -> str:
        # Non-greedy single-line + multi-line comment strip.
        return re.sub(r"\{#-?.*?-?#\}", "", text, flags=re.DOTALL)

    stripped = _strip_jinja_comments(template_text)
    for forbidden in ("stub_leak", "repetition_loop"):
        assert forbidden not in stripped, (
            f"forbidden token {forbidden!r} appears in non-comment portion of "
            f"system.j2 — must be pre-LLM short-circuit only"
        )


# ---------------------------------------------------------------- #
# Test 8 — rubric_version on emitted Event = "v2"                  #
# ---------------------------------------------------------------- #


def test_8_event_rubric_version_v2(make_critic_v2) -> None:
    """rubric_version on every emitted Event is 'v2' (bumped from v1)."""
    expected_version = _rubric_version_from_yaml()
    assert expected_version == "v2", (
        f"config/rubric.yaml rubric_version must be 'v2' for Plan 07-04 "
        f"(got {expected_version!r})"
    )

    parsed = make_canonical_critic_response_v2(overall_pass=True)
    fake_client = FakeAnthropicClient(parsed_response=parsed)
    logger = FakeEventLogger()
    critic = make_critic_v2(anthropic_client=fake_client, event_logger=logger)
    critic.review(make_critic_request(rubric_version="v2"))

    critic_events = [e for e in logger.events if isinstance(e, Event) and e.role == "critic"]
    assert len(critic_events) == 1
    assert critic_events[0].rubric_version == "v2"


# ---------------------------------------------------------------- #
# Test 9 (Warning #3) — few-shot budget <= 8                       #
# ---------------------------------------------------------------- #


def test_9_scene_fewshot_yaml_phase7_budget_within_8() -> None:
    """Plan 07-04 added <=8 NEW few-shot entries across the 4 subjective
    Phase-7 axes (pov_fidelity, content_ownership, treatment_fidelity,
    motivation_fidelity). Pitfall 2 budget guard."""
    data = yaml.safe_load(FEWSHOT_PATH.read_text(encoding="utf-8"))

    phase7_axes = (
        "pov_fidelity",
        "content_ownership",
        "treatment_fidelity",
        "motivation_fidelity",
    )
    total_new = 0
    per_axis_data = data.get("axes", {})
    for axis in phase7_axes:
        bucket = per_axis_data.get(axis, {})
        if isinstance(bucket, dict):
            for sub in ("bad", "good", "examples"):
                total_new += len(bucket.get(sub, []) or [])
        elif isinstance(bucket, list):
            total_new += len(bucket)
    assert total_new <= 8, (
        f"few-shot count {total_new} exceeds Pitfall 2 budget of 8 NEW entries"
    )


# ---------------------------------------------------------------- #
# Sanity: rubric.yaml v2 carries all 13 axis blocks                #
# ---------------------------------------------------------------- #


def test_rubric_yaml_v2_has_all_13_axis_blocks() -> None:
    """config/rubric.yaml has rubric_version='v2' and all 13 axis blocks."""
    data = yaml.safe_load(Path("config/rubric.yaml").read_text(encoding="utf-8"))
    assert data["rubric_version"] == "v2"
    axes = data["axes"]
    assert set(axes.keys()) == set(EXPECTED_AXES_13)
