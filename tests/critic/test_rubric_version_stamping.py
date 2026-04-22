"""Tests for SystemPromptBuilder + scene_fewshot.yaml curation (Plan 03-05 Task 1).

Covers:
  Test 3: Jinja2 render of system.j2 produces a string containing rubric_version,
          all 5 axis names, and both few-shot scenes verbatim.
  Test 4: Rendered system prompt has stable SHA under reruns (determinism for
          prompt caching).
  Test 5: The curated fewshot yaml passes YAML parsing + the bad example has
          historical.pass == false, the good example has all 5 pass == true.
  Test 5a (B-2): bad_example.scene_text contains real historical entities + real
                 prose length (150-250 words).
  Test 5b (B-2): good_example.scene_text contains real historical entities +
                 real prose length (150-250 words).
  Test 5c (B-2): test_fewshot_yaml_validates_as_critic_response_schema — both
                 examples' expected_critic_response Pydantic-validate through
                 CriticResponse.model_validate.
  Test 6: __init__.py fallback pattern — `from book_pipeline.critic import
          write_audit_record` succeeds regardless of Task 2 state.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


FEWSHOT_PATH = Path("src/book_pipeline/critic/templates/scene_fewshot.yaml")
TEMPLATE_PATH = Path("src/book_pipeline/critic/templates/system.j2")

REAL_ENTITIES = {
    "Cempoala",
    "Malintzin",
    "Cortés",
    "Tlaxcalteca",
    "Veracruz",
    "Moctezuma",
    "Motecuhzoma",
    "Tenochtitlan",
    "Cholula",
    "1519",
    "1520",
}


def _load_fewshot() -> dict:
    return yaml.safe_load(FEWSHOT_PATH.read_text(encoding="utf-8"))


def test_system_template_renders_rubric_version_and_five_axes() -> None:
    """Test 3: Render system.j2 with RubricConfig() + the real fewshot yaml.
    Assert output contains 'v1' rubric_version, all 5 axis names, and both
    few-shot scenes verbatim."""
    from book_pipeline.config.rubric import RubricConfig
    from book_pipeline.critic.scene import SystemPromptBuilder

    rubric = RubricConfig()
    builder = SystemPromptBuilder(
        rubric=rubric,
        fewshot_path=FEWSHOT_PATH,
        template_path=TEMPLATE_PATH,
    )
    rendered, sha = builder.render()

    # rubric_version stamped
    assert rubric.rubric_version in rendered

    # All 5 axes present
    for axis in ("historical", "metaphysics", "entity", "arc", "donts"):
        assert axis in rendered, f"axis {axis!r} missing from system prompt"

    # Few-shot scenes embedded verbatim (at least first 40 chars of each scene_text)
    fewshot = _load_fewshot()
    bad_prefix = fewshot["bad"]["scene_text"].strip().splitlines()[0][:40]
    good_prefix = fewshot["good"]["scene_text"].strip().splitlines()[0][:40]
    assert bad_prefix in rendered, f"bad example prefix {bad_prefix!r} not in rendered prompt"
    assert good_prefix in rendered, f"good example prefix {good_prefix!r} not in rendered prompt"

    # SHA is non-empty hex-ish
    assert isinstance(sha, str)
    assert len(sha) >= 8


def test_system_template_renders_stable_sha() -> None:
    """Test 4: Rendered system prompt has stable SHA under reruns (identical
    inputs produce identical output — determinism for prompt caching)."""
    from book_pipeline.config.rubric import RubricConfig
    from book_pipeline.critic.scene import SystemPromptBuilder

    rubric = RubricConfig()
    b1 = SystemPromptBuilder(
        rubric=rubric, fewshot_path=FEWSHOT_PATH, template_path=TEMPLATE_PATH
    )
    b2 = SystemPromptBuilder(
        rubric=rubric, fewshot_path=FEWSHOT_PATH, template_path=TEMPLATE_PATH
    )
    text1, sha1 = b1.render()
    text2, sha2 = b2.render()
    assert text1 == text2
    assert sha1 == sha2


def test_fewshot_yaml_parses_and_has_correct_pass_shape() -> None:
    """Test 5: Curated fewshot yaml loads, bad example fails historical, good
    example passes all 5."""
    fewshot = _load_fewshot()

    bad = fewshot["bad"]["expected_critic_response"]
    good = fewshot["good"]["expected_critic_response"]

    # bad: historical fails, overall_pass false
    assert bad["pass_per_axis"]["historical"] is False
    assert bad["overall_pass"] is False

    # good: all 5 pass, overall_pass true
    for axis in ("historical", "metaphysics", "entity", "arc", "donts"):
        assert good["pass_per_axis"][axis] is True, f"good example should pass {axis}"
    assert good["overall_pass"] is True


def test_fewshot_bad_example_has_real_entities_and_length(  # noqa: D401 — test name describes intent
) -> None:
    """Test 5a (B-2): bad_example.scene_text contains >=2 real historical
    entities and is 150-250 words — not placeholder prose."""
    fewshot = _load_fewshot()
    scene_text = fewshot["bad"]["scene_text"]

    hits = sum(1 for ent in REAL_ENTITIES if ent in scene_text)
    assert hits >= 2, (
        f"bad_example.scene_text contains only {hits} of real entities "
        f"{REAL_ENTITIES}; B-2 requires >=2 to assert curated prose"
    )

    word_count = len(scene_text.split())
    assert 150 <= word_count <= 250, (
        f"bad_example.scene_text has {word_count} words; B-2 requires 150-250"
    )


def test_fewshot_good_example_has_real_entities_and_length() -> None:
    """Test 5b (B-2): good_example.scene_text contains >=2 real historical
    entities and is 150-250 words — parity with bad_example."""
    fewshot = _load_fewshot()
    scene_text = fewshot["good"]["scene_text"]

    hits = sum(1 for ent in REAL_ENTITIES if ent in scene_text)
    assert hits >= 2, (
        f"good_example.scene_text contains only {hits} of real entities "
        f"{REAL_ENTITIES}; B-2 requires >=2"
    )

    word_count = len(scene_text.split())
    assert 150 <= word_count <= 250, (
        f"good_example.scene_text has {word_count} words; B-2 requires 150-250"
    )


def test_fewshot_yaml_validates_as_critic_response_schema() -> None:
    """Test 5c (B-2): both examples' expected_critic_response round-trip
    through CriticResponse.model_validate (with output_sha placeholder)."""
    from book_pipeline.interfaces.types import CriticResponse

    fewshot = _load_fewshot()
    for name in ("bad", "good"):
        raw = dict(fewshot[name]["expected_critic_response"])
        # scene_fewshot.yaml stores output_sha as "<runtime-computed>" placeholder
        raw["output_sha"] = "placeholder_sha_" + name
        CriticResponse.model_validate(raw)


def test_audit_import_available_via_package() -> None:
    """Test 6: `from book_pipeline.critic import write_audit_record` succeeds
    regardless of whether scene.py Task 2 has landed yet."""
    from book_pipeline.critic import write_audit_record, AuditRecord

    assert callable(write_audit_record)
    assert AuditRecord is not None
