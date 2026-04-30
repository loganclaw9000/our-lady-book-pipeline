"""pov_narrative_voice deterministic detector (PHYSICS-11).

Catches narrative-voice / declared-perspective mismatch BEFORE the Anthropic
call. The ``pov_lock`` pre-flight gate validates SceneMetadata.perspective
against the per-character lock; the ``pov_fidelity`` LLM-judged axis catches
*other-character interior leakage* but does NOT detect when a 1st-person
declared scene is actually written in 3rd-person prose (or vice versa).

Real incident (2026-04-26 ch15_sc02): Itzcoatl declared 1st_person from
ch15 lock, drafter shipped 3rd-person prose. pov_lock gate passed (metadata
matched lock). pov_fidelity LLM axis passed (no foreign interior). The
output was wrong but every gate said yes.

This deterministic counter looks at first-person pronoun rate vs sentence
count. Threshold tuned to be loose enough that a few 3rd-person-rendered
exterior beats inside an otherwise-1st-person scene don't trigger, but a
fully-3rd-person draft of a 1st-person scene gets flagged.

Pure function; no LLM. No false positives on edge cases (dialogue lines
quoted within 3rd-person scenes; quoted speech is excluded from the
pronoun count).
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from book_pipeline.physics.schema import Perspective

# Strip out all double-quoted speech before counting pronouns. Dialogue is
# always first-person (in-character) regardless of narrative perspective —
# counting "I said X" inside dialogue would mask a 3rd-person-narrated scene.
# Match curly + straight quotes; non-greedy.
_QUOTED_SPEECH_RE = re.compile(r'["“][^"”]*["”]', flags=re.DOTALL)
_FIRST_PERSON_PRONOUNS_RE = re.compile(
    r"\b(?:I|me|my|mine|myself)\b", flags=re.IGNORECASE
)
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+\s+")


class PovNarrativeVoiceHit(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    hit_type: Literal[
        "first_person_declared_but_third_person_prose",
        "third_person_declared_but_first_person_prose",
    ]
    detail: str
    pronoun_rate: float
    threshold: float


# Default thresholds — tunable via call-site.
# Below this rate ⇒ scene reads as 3rd-person prose despite 1st-person decl.
DEFAULT_FIRST_PERSON_MIN_RATE: float = 0.20
# Above this rate ⇒ scene reads as 1st-person prose despite 3rd-person decl.
# Set generously (3rd-person scenes legitimately have 1st-person dialogue,
# but dialogue is stripped before counting; remaining 1st-person pronouns
# = narrative voice ⇒ tight threshold).
DEFAULT_THIRD_PERSON_MAX_RATE: float = 0.05


def scan_pov_narrative_voice(
    scene_text: str,
    perspective: Perspective | None,
    *,
    first_person_min_rate: float = DEFAULT_FIRST_PERSON_MIN_RATE,
    third_person_max_rate: float = DEFAULT_THIRD_PERSON_MAX_RATE,
) -> list[PovNarrativeVoiceHit]:
    """Return narrative-voice mismatch hits, or empty list if pass.

    perspective=None ⇒ skip (no contract to enforce).
    Empty scene ⇒ skip.
    """
    if perspective is None or not scene_text.strip():
        return []

    narrative_only = _QUOTED_SPEECH_RE.sub(" ", scene_text)
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(narrative_only) if s.strip()]
    if not sentences:
        return []
    sentence_count = len(sentences)
    pronoun_count = len(_FIRST_PERSON_PRONOUNS_RE.findall(narrative_only))
    rate = pronoun_count / sentence_count

    is_first_person = perspective.value == "1st_person"
    if is_first_person:
        if rate < first_person_min_rate:
            return [
                PovNarrativeVoiceHit(
                    hit_type="first_person_declared_but_third_person_prose",
                    detail=(
                        f"perspective=1st_person but narrative-pronoun rate "
                        f"{rate:.3f} < min {first_person_min_rate:.2f} "
                        f"(I/me/my count={pronoun_count}, sentences={sentence_count})"
                    ),
                    pronoun_rate=rate,
                    threshold=first_person_min_rate,
                )
            ]
        return []

    # 3rd_close / 3rd_limited / 3rd_external all forbid 1st-person narrative.
    if rate > third_person_max_rate:
        return [
            PovNarrativeVoiceHit(
                hit_type="third_person_declared_but_first_person_prose",
                detail=(
                    f"perspective={perspective.value} but narrative-pronoun "
                    f"rate {rate:.3f} > max {third_person_max_rate:.2f} "
                    f"(I/me/my count={pronoun_count}, sentences={sentence_count}; "
                    f"dialogue stripped)"
                ),
                pronoun_rate=rate,
                threshold=third_person_max_rate,
            )
        ]
    return []


__all__ = [
    "DEFAULT_FIRST_PERSON_MIN_RATE",
    "DEFAULT_THIRD_PERSON_MAX_RATE",
    "PovNarrativeVoiceHit",
    "scan_pov_narrative_voice",
]
