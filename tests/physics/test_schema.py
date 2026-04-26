"""SceneMetadata Pydantic schema tests (Plan 07-01 Task 2).

Covers Tests 1-5c from the plan <behavior> block:
- Test 1: model_validate succeeds on minimal valid payload; extra="forbid"
  rejects unknown keys.
- Test 2: on_screen=True character with empty motivation raises ValidationError.
- Test 3: motivation with <3 words raises ValidationError.
- Test 4: Perspective has 5 members; Treatment has 10 members.
- Test 5: model_validate accepts the valid_scene_payload fixture (v2 shape).
- Test 5b: T-07-02 path-traversal mitigation — adversarial chapter values
  (0, 1000, "../etc/passwd", -1, "abc") each raise ValidationError.
- Test 5c: canonical scene_id derivation locks the f-string format at the
  schema layer (chapter=15, scene_index=2 → "ch15_sc02").
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from book_pipeline.physics.schema import (
    Perspective,
    SceneMetadata,
    Treatment,
)


def test_minimal_valid_payload_validates(valid_scene_payload: dict[str, Any]) -> None:
    """Test 1 + Test 5: full v2 payload from fixture round-trips cleanly."""
    sm = SceneMetadata.model_validate(valid_scene_payload)
    assert sm.chapter == 15
    assert sm.scene_index == 2
    assert sm.perspective is Perspective.THIRD_CLOSE
    assert sm.treatment is Treatment.OMINOUS


def test_extra_forbid_rejects_unknown_top_level_key(
    valid_scene_payload: dict[str, Any],
) -> None:
    """Test 1: unknown keys at the top level raise ValidationError."""
    payload = dict(valid_scene_payload)
    payload["flavor"] = "x"
    with pytest.raises(ValidationError, match=r"flavor|extra"):
        SceneMetadata.model_validate(payload)


def test_on_screen_character_requires_motivation(
    valid_scene_payload: dict[str, Any],
) -> None:
    """Test 2: on_screen=True with empty motivation raises ValidationError."""
    payload = dict(valid_scene_payload)
    payload["characters_present"] = [
        {"name": "Andres", "on_screen": True, "motivation": ""},
    ]
    with pytest.raises(ValidationError, match=r"requires motivation"):
        SceneMetadata.model_validate(payload)


def test_motivation_min_words_when_present(
    valid_scene_payload: dict[str, Any],
) -> None:
    """Test 3: motivation with <3 words raises ValidationError."""
    payload = dict(valid_scene_payload)
    payload["characters_present"] = [
        {"name": "Andres", "on_screen": True, "motivation": "x"},
    ]
    with pytest.raises(ValidationError, match=r"empty OR >=3 words"):
        SceneMetadata.model_validate(payload)


def test_perspective_enum_has_five_members() -> None:
    """Test 4a: Perspective enum is exactly 5 values per 07-NARRATIVE_PHYSICS.md §1.2."""
    assert len(Perspective) == 5
    assert {p.value for p in Perspective} == {
        "1st_person",
        "3rd_close",
        "3rd_limited",
        "3rd_omniscient",
        "3rd_external",
    }


def test_treatment_enum_has_ten_members() -> None:
    """Test 4b: Treatment enum is exactly 10 values per §4.3."""
    assert len(Treatment) == 10
    assert {t.value for t in Treatment} == {
        "dramatic",
        "mournful",
        "comedic",
        "light",
        "propulsive",
        "contemplative",
        "ominous",
        "liturgical",
        "reportorial",
        "intimate",
    }


@pytest.mark.parametrize(
    "bad_chapter",
    [0, 1000, -1, "../../etc/passwd", "abc"],
)
def test_chapter_path_traversal_mitigation(
    valid_scene_payload: dict[str, Any], bad_chapter: object
) -> None:
    """Test 5b (T-07-02): adversarial chapter values raise ValidationError.

    The combination of `int` cast + `ge=1` + `le=999` on the chapter field
    makes path traversal via the chapter integer unrepresentable.
    """
    payload = dict(valid_scene_payload)
    payload["chapter"] = bad_chapter
    with pytest.raises(ValidationError):
        SceneMetadata.model_validate(payload)


@pytest.mark.parametrize(
    "bad_scene_index",
    [0, 1000, -1, "../../etc/passwd"],
)
def test_scene_index_path_traversal_mitigation(
    valid_scene_payload: dict[str, Any], bad_scene_index: object
) -> None:
    """Test 5b (T-07-02): adversarial scene_index values raise ValidationError."""
    payload = dict(valid_scene_payload)
    payload["scene_index"] = bad_scene_index
    with pytest.raises(ValidationError):
        SceneMetadata.model_validate(payload)


def test_canonical_scene_id_derivation(
    valid_scene_payload: dict[str, Any],
) -> None:
    """Test 5c: canonical f-string lock at the schema layer.

    Every downstream site that derives a scene_id MUST use this exact
    f-string (precedent: scene_kick.py:54-79). This test pins the format
    string at the source.
    """
    sm = SceneMetadata.model_validate(valid_scene_payload)
    assert f"ch{sm.chapter:02d}_sc{sm.scene_index:02d}" == "ch15_sc02"


def test_at_least_one_on_screen_character_required(
    valid_scene_payload: dict[str, Any],
) -> None:
    """All-off-screen characters_present raises ValidationError."""
    payload = dict(valid_scene_payload)
    payload["characters_present"] = [
        {"name": "Andres", "on_screen": False, "motivation": ""},
    ]
    with pytest.raises(ValidationError, match=r"on_screen=True"):
        SceneMetadata.model_validate(payload)


def test_extra_forbid_on_child_models(
    valid_scene_payload: dict[str, Any],
) -> None:
    """Child model (Contents) also rejects unknown keys."""
    payload = dict(valid_scene_payload)
    payload["contents"] = dict(payload["contents"])
    payload["contents"]["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        SceneMetadata.model_validate(payload)
