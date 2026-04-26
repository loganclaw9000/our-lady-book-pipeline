"""repetition_loop deterministic detector (Plan 07-04 PHYSICS-09).

n-gram (trigram) repetition + identical-line repetition with
treatment-conditional thresholds per Pitfall 10. LITURGICAL treatment gets
raised tolerance — repetition is the form (chant, prayer, ritual). Default
treatment uses tighter thresholds.

Pure function. ``xxhash.xxh64_intdigest`` for deterministic gram-hashing
(matches the ``drafter.memorization_gate`` n-gram pattern; xxh64 is stable
across processes — no PYTHONHASHSEED risk).

Defaults (Pitfall 10):
  default:           trigram_rate_max=0.15  identical_line_max=2  (>=3 fails)
  liturgical:        trigram_rate_max=0.40  identical_line_max=5  (>=6 fails)
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import xxhash
from pydantic import BaseModel, ConfigDict

from book_pipeline.physics.schema import Treatment


class RepetitionHit(BaseModel):
    """One repetition-loop detection.

    ``hit_type`` ∈ {"trigram_rate", "identical_line"}.
    ``score`` is the rate (0.0-1.0) for trigram_rate, the count (cast to float)
    for identical_line. ``threshold`` is the corresponding limit that was
    crossed. ``detail`` gives a short human-readable summary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    hit_type: str
    score: float
    threshold: float
    detail: str


_DEFAULT_THRESHOLDS: dict[str, float] = {
    "trigram_repetition_rate_max": 0.15,
    "identical_line_count_max": 2.0,  # >=3 distinct identical lines = FAIL
}
_LITURGICAL_THRESHOLDS: dict[str, float] = {
    "trigram_repetition_rate_max": 0.40,
    "identical_line_count_max": 5.0,  # >=6 distinct identical lines = FAIL
}


def _resolve_thresholds(
    treatment: Treatment | None,
    user_thresholds: dict[str, Any] | None,
) -> dict[str, float]:
    """Pick the threshold set: user_thresholds (if given) takes priority.

    user_thresholds shape supports both:
      - flat dict: ``{trigram_repetition_rate_max: ..., identical_line_count_max: ...}``
      - nested:   ``{default: {...}, liturgical_treatment: {...}}``
    """
    if user_thresholds is not None:
        if (
            treatment == Treatment.LITURGICAL
            and "liturgical_treatment" in user_thresholds
        ):
            section = user_thresholds["liturgical_treatment"]
            return {k: float(v) for k, v in section.items()}
        if "default" in user_thresholds:
            section = user_thresholds["default"]
            return {k: float(v) for k, v in section.items()}
        # Flat dict fallback.
        return {k: float(v) for k, v in user_thresholds.items()}
    if treatment == Treatment.LITURGICAL:
        return dict(_LITURGICAL_THRESHOLDS)
    return dict(_DEFAULT_THRESHOLDS)


def scan_repetition_loop(
    scene_text: str,
    *,
    treatment: Treatment | None = None,
    thresholds: dict[str, Any] | None = None,
) -> list[RepetitionHit]:
    """Return the list of repetition-loop hits in ``scene_text``. Empty = pass.

    Args:
        scene_text: drafted scene prose.
        treatment: scene's tonal register (LITURGICAL gets raised thresholds).
        thresholds: optional override dict; expected shape from
            ``config/mode_thresholds.yaml`` ``physics_repetition`` section:
            ``{default: {...}, liturgical_treatment: {...}}``.

    Pure function; no side effects; no LLM call. Run BEFORE the Anthropic
    critic call to short-circuit at FAIL severity.
    """
    if not scene_text or not scene_text.strip():
        return []

    cfg = _resolve_thresholds(treatment, thresholds)
    trigram_rate_max = float(cfg.get("trigram_repetition_rate_max", 0.15))
    identical_line_count_max = int(cfg.get("identical_line_count_max", 2))

    hits: list[RepetitionHit] = []

    # Identical-line check.
    lines = [line.strip() for line in scene_text.splitlines() if line.strip()]
    line_counter = Counter(lines)
    for line, count in line_counter.most_common():
        if count > identical_line_count_max:
            hits.append(
                RepetitionHit(
                    hit_type="identical_line",
                    score=float(count),
                    threshold=float(identical_line_count_max),
                    detail=line[:200],
                )
            )

    # Trigram-rate check.
    tokens = scene_text.split()
    if len(tokens) >= 3:
        gram_hashes: list[int] = []
        for i in range(len(tokens) - 2):
            gram = " ".join(tokens[i : i + 3])
            gram_hashes.append(xxhash.xxh64_intdigest(gram.encode("utf-8")))
        gram_counter = Counter(gram_hashes)
        repeated = sum(c - 1 for c in gram_counter.values() if c > 1)
        rate = repeated / len(gram_hashes)
        if rate > trigram_rate_max:
            top_hash, top_count = gram_counter.most_common(1)[0]
            for i in range(len(tokens) - 2):
                gram = " ".join(tokens[i : i + 3])
                if xxhash.xxh64_intdigest(gram.encode("utf-8")) == top_hash:
                    hits.append(
                        RepetitionHit(
                            hit_type="trigram_rate",
                            score=rate,
                            threshold=trigram_rate_max,
                            detail=f"{gram!r} appears {top_count}x; rate={rate:.3f}",
                        )
                    )
                    break

    return hits


__all__ = ["RepetitionHit", "scan_repetition_loop"]
