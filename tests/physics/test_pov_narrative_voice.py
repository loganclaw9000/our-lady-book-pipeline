"""Tests for pov_narrative_voice deterministic detector (PHYSICS-11)."""
from __future__ import annotations

import pytest

from book_pipeline.physics.pov_narrative_voice import (
    DEFAULT_FIRST_PERSON_MIN_RATE,
    DEFAULT_THIRD_PERSON_MAX_RATE,
    scan_pov_narrative_voice,
)
from book_pipeline.physics.schema import Perspective


# --------------------------------------------------------------------------- #
# 1st-person declared scenes                                                  #
# --------------------------------------------------------------------------- #


def test_first_person_well_voiced_passes() -> None:
    text = (
        "I crossed the courtyard. My breath caught when I saw the smoke. "
        "I knew then what I had to do. My hand went to the hilt. I waited."
    )
    hits = scan_pov_narrative_voice(text, Perspective.FIRST_PERSON)
    assert hits == []


def test_first_person_declared_but_third_person_prose_fails() -> None:
    text = (
        "Itzcoatl crossed the courtyard. He saw the smoke. The man knew "
        "what he had to do. His hand went to the hilt. He waited there."
    )
    hits = scan_pov_narrative_voice(text, Perspective.FIRST_PERSON)
    assert len(hits) == 1
    assert hits[0].hit_type == "first_person_declared_but_third_person_prose"
    assert hits[0].pronoun_rate < DEFAULT_FIRST_PERSON_MIN_RATE


def test_first_person_dialogue_inside_does_not_save_third_person_prose() -> None:
    """1st-person pronouns inside quoted dialogue must NOT count toward
    narrative-voice rate. A 3rd-person scene with 'I am here,' he said.
    is still 3rd-person."""
    text = (
        'Itzcoatl crossed the courtyard. "I am here," he said. He saw the '
        'smoke. The man knew what he had to do. "I will go," he muttered. '
        "His hand went to the hilt."
    )
    hits = scan_pov_narrative_voice(text, Perspective.FIRST_PERSON)
    assert len(hits) == 1
    assert hits[0].hit_type == "first_person_declared_but_third_person_prose"


# --------------------------------------------------------------------------- #
# 3rd-person declared scenes                                                  #
# --------------------------------------------------------------------------- #


def test_third_close_well_voiced_passes() -> None:
    text = (
        "Itzcoatl crossed the courtyard. He saw the smoke. He knew what "
        "he had to do. His hand went to the hilt. He waited."
    )
    hits = scan_pov_narrative_voice(text, Perspective.THIRD_CLOSE)
    assert hits == []


def test_third_close_with_first_person_dialogue_passes() -> None:
    text = (
        'Itzcoatl crossed the courtyard. "I am here," he said. He saw the '
        'smoke. "I will go," Itzcoatl muttered. His hand went to the hilt.'
    )
    hits = scan_pov_narrative_voice(text, Perspective.THIRD_CLOSE)
    assert hits == []  # 1st-person pronouns inside dialogue stripped


def test_third_close_first_person_narrative_fails() -> None:
    """If 3rd_close-declared scene has 1st-person NARRATIVE pronouns
    (outside dialogue), flag."""
    text = (
        "I crossed the courtyard. I saw the smoke. I knew what I had to "
        "do. My hand went to the hilt. I waited there for the signal."
    )
    hits = scan_pov_narrative_voice(text, Perspective.THIRD_CLOSE)
    assert len(hits) == 1
    assert hits[0].hit_type == "third_person_declared_but_first_person_prose"
    assert hits[0].pronoun_rate > DEFAULT_THIRD_PERSON_MAX_RATE


# --------------------------------------------------------------------------- #
# Edge cases                                                                  #
# --------------------------------------------------------------------------- #


def test_perspective_none_skips() -> None:
    text = "Some text without metadata constraint."
    assert scan_pov_narrative_voice(text, None) == []


def test_empty_scene_skips() -> None:
    assert scan_pov_narrative_voice("", Perspective.FIRST_PERSON) == []
    assert scan_pov_narrative_voice("   ", Perspective.FIRST_PERSON) == []


@pytest.mark.parametrize(
    "perspective",
    [
        Perspective.THIRD_CLOSE,
        Perspective.THIRD_LIMITED,
        Perspective.THIRD_OMNISCIENT,
        Perspective.THIRD_EXTERNAL,
    ],
)
def test_all_third_person_variants_enforce_no_first_person_narrative(
    perspective: Perspective,
) -> None:
    text = "I went there. I knew. I saw. I waited. My hand. My eyes. I was there."
    hits = scan_pov_narrative_voice(text, perspective)
    assert len(hits) == 1
    assert hits[0].hit_type == "third_person_declared_but_first_person_prose"


def test_threshold_overrides_respected() -> None:
    """Tunable thresholds let callers override defaults."""
    # Borderline scene with rate ~0.10 (1 pronoun, 10 sentences).
    text = " ".join(["Sentence." for _ in range(9)]) + " I went."
    # Default first_person_min_rate=0.20 -> would FAIL.
    default_hits = scan_pov_narrative_voice(text, Perspective.FIRST_PERSON)
    assert len(default_hits) == 1
    # Loosen to 0.05 -> should PASS.
    loose_hits = scan_pov_narrative_voice(
        text, Perspective.FIRST_PERSON, first_person_min_rate=0.05
    )
    assert loose_hits == []
