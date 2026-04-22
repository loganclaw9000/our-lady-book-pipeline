"""Voice-fidelity scorer (OBS-03). Plan 03-01 lands the stub; Plan 03-02 replaces.

Signature is frozen here so Plan 02 Drafter (Plan 03-04) can wire
``score_voice_fidelity(scene_text, anchor_centroid, embedder)`` before Plan
03-02 lands the real BGE-M3 cosine implementation. The stub MUST raise
NotImplementedError — silent returns of a default float would silently pass
Mode-A drafter voice-fidelity gates and poison OBS-03 telemetry.
"""
from __future__ import annotations

from typing import Any


def score_voice_fidelity(
    scene_text: str,
    anchor_centroid: Any | None = None,
    embedder: Any | None = None,
) -> float:
    """Voice-fidelity score stub — raises until Plan 03-02 lands the real impl.

    Args:
        scene_text: Drafted scene text to score.
        anchor_centroid: Mean embedding vector over curated voice anchors.
        embedder: BGE-M3 embedder instance (reused from book_pipeline.rag).

    Returns:
        Cosine similarity score in [0, 1] — when implemented.

    Raises:
        NotImplementedError: always. Plan 03-02 lands the real implementation.
    """
    raise NotImplementedError(
        "Plan 03-02 lands the BGE-M3 cosine implementation; "
        "Plan 03-01 ships only the signature stub."
    )
