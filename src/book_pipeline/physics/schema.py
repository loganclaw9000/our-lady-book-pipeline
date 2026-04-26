"""SceneMetadata Pydantic schema (Phase 7 Plan 01).

Strict-validates YAML frontmatter from drafts/chNN/chNN_scNN.md stubs.
Pydantic ValidationError on shape violation — caught by gate and emitted as
physics_gate Event downstream (Plan 07-03).

D-03 mandatory fields (operator-locked 2026-04-25):
- contents: what physically/narratively happens (goal/conflict/outcome triplet).
- characters_present: explicit on-screen vs off-screen, with per-character
  motivation (D-02 load-bearing).
- voice: which FT pin / sampling profile.
- perspective: POV mode (Perspective enum, 5 values per 07-NARRATIVE_PHYSICS.md
  §1.2).
- treatment: tonal register (Treatment enum, 10 values per §4.3).

D-13 ownership fields:
- owns: list of beat tags this scene exclusively renders.
- do_not_renarrate: list of beat tags from prior scenes — must not re-cover.
- callback_allowed: list of beat tags this scene MAY reference but not narrate.

D-04 staging fields:
- staging.location_canonical, spatial_position, scene_clock, sensory_dominance,
  on_screen / off_screen_referenced / witness_only character partitions.

T-07-02 mitigation: chapter and scene_index Pydantic-validated as int with
ge=1 and le=999. Path traversal via these fields is unrepresentable. Every
downstream site that derives a scene_id MUST use the canonical f-string
`f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"` (see scene_kick.py:54-79
precedent) — never raw user-string interpolation.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Perspective(str, Enum):  # noqa: UP042 — match SceneState convention (interfaces/types.py:195)
    """POV mode declared per scene (07-NARRATIVE_PHYSICS.md §1.2 — 5 values).

    Inherits ``(str, Enum)`` rather than ``StrEnum`` to match the SceneState
    convention in ``book_pipeline.interfaces.types`` (Phase 1 frozen contract):
    StrEnum would change the visible MRO for downstream code, even though the
    runtime semantics are equivalent.
    """

    FIRST_PERSON = "1st_person"
    THIRD_CLOSE = "3rd_close"
    THIRD_LIMITED = "3rd_limited"
    THIRD_OMNISCIENT = "3rd_omniscient"
    THIRD_EXTERNAL = "3rd_external"


class Treatment(str, Enum):  # noqa: UP042 — match SceneState convention (interfaces/types.py:195)
    """Tonal register declared per scene (07-NARRATIVE_PHYSICS.md §4.3 — 10 values).

    See ``Perspective`` docstring for the (str, Enum) vs StrEnum rationale.
    """

    DRAMATIC = "dramatic"
    MOURNFUL = "mournful"
    COMEDIC = "comedic"
    LIGHT = "light"
    PROPULSIVE = "propulsive"
    CONTEMPLATIVE = "contemplative"
    OMINOUS = "ominous"
    LITURGICAL = "liturgical"
    REPORTORIAL = "reportorial"
    INTIMATE = "intimate"


# Documented shape: "ch{NN}_sc{II}_<beatname>" (e.g. "ch15_sc02_warning").
# Kept as a free-form str alias here; downstream validators (Plan 07-03 ownership
# gate) tighten the format with a regex check against the canonical scene_id.
BeatTag = str


class CharacterPresence(BaseModel):
    """One character row inside SceneMetadata.characters_present.

    motivation is the D-02 load-bearing field — when on_screen=True it MUST be
    populated with at least 3 words. The class-level field validator enforces
    "empty OR >= 3 words"; the parent SceneMetadata validator enforces
    "on_screen=True implies non-empty".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    on_screen: bool
    motivation: str = ""
    motivation_failure_state: str | None = None

    @field_validator("motivation")
    @classmethod
    def motivation_min_words_when_present(cls, v: str) -> str:
        if v and len(v.split()) < 3:
            raise ValueError("motivation must be empty OR >=3 words")
        return v


class Contents(BaseModel):
    """D-03 contents block — goal/conflict/outcome triplet (theatrical beat)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str = Field(min_length=1)
    conflict: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    sequel_to_prior: str | None = None


class Staging(BaseModel):
    """D-04 staging block — theater-of-mind spatial + temporal + sensory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location_canonical: str
    spatial_position: str
    scene_clock: str
    relative_clock: str | None = None
    sensory_dominance: list[
        Literal["sight", "sound", "smell", "taste", "touch", "kinesthetic"]
    ] = Field(min_length=1, max_length=2)
    on_screen: list[str] = Field(default_factory=list)
    off_screen_referenced: list[str] = Field(default_factory=list)
    witness_only: list[str] = Field(default_factory=list)


class ValueCharge(BaseModel):
    """McKee value-charge polarity per scene (positive ↔ negative on a named axis)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    axis: str
    starts_at: Literal["positive", "negative", "neutral"]
    ends_at: Literal[
        "positive",
        "negative",
        "neutral",
        "compound_positive",
        "compound_negative",
    ]


class SceneMetadata(BaseModel):
    """Phase 7 scene-stub schema — strict-validate from YAML frontmatter."""

    model_config = ConfigDict(extra="forbid")

    # T-07-02: bounded ints + canonical f-string at every derivation site
    # = path traversal via chapter/scene_index is unrepresentable.
    chapter: int = Field(ge=1, le=999)
    scene_index: int = Field(ge=1, le=999)

    contents: Contents
    characters_present: list[CharacterPresence] = Field(min_length=1)
    voice: str
    perspective: Perspective
    treatment: Treatment

    owns: list[BeatTag] = Field(min_length=1)
    do_not_renarrate: list[str] = Field(default_factory=list)
    callback_allowed: list[str] = Field(default_factory=list)

    staging: Staging
    value_charge: ValueCharge | None = None

    pov_lock_override: str | None = None

    @field_validator("characters_present")
    @classmethod
    def at_least_one_on_screen_with_motivation(
        cls, v: list[CharacterPresence]
    ) -> list[CharacterPresence]:
        on_screen = [c for c in v if c.on_screen]
        if not on_screen:
            raise ValueError("at least one character must be on_screen=True")
        for c in on_screen:
            if not c.motivation:
                raise ValueError(
                    f"on_screen character {c.name!r} requires motivation "
                    f"(D-02 load-bearing)"
                )
        return v


__all__ = [
    "BeatTag",
    "CharacterPresence",
    "Contents",
    "Perspective",
    "SceneMetadata",
    "Staging",
    "Treatment",
    "ValueCharge",
]
