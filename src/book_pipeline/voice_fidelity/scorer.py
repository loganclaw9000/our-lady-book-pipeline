"""score_voice_fidelity — BGE-M3 cosine against the anchor centroid.

OBS-03: attached to every Mode-A DraftResponse's Event.caller_context
voice_fidelity_score. PITFALLS V-1/V-2 band (from config/mode_thresholds.yaml
voice_fidelity block): pass >=0.78, flag 0.75-0.78, fail <0.75, flag >=0.95
(V-2 memorization — retrieval, not synthesis).

Algorithm (pinned — do not drift):

    vec = embedder.embed_texts([scene_text])[0]  # (1024,) float32
    vec /= max(||vec||, 1e-12)
    centroid_norm = max(||anchor_centroid||, 1e-12)
    return float(dot(vec, anchor_centroid / centroid_norm))

Determinism: given a fixed embedder.revision_sha, score_voice_fidelity is
byte-identical across runs. Plan 03-04 drafter will compute the centroid
ONCE per CLI run and pass it per scene — no caching inside the scorer.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def score_voice_fidelity(
    scene_text: str,
    anchor_centroid: np.ndarray,
    embedder: Any,
) -> float:
    """Return cosine similarity of scene_text's embedding against anchor_centroid.

    Args:
        scene_text: Drafted scene text (non-empty; whitespace-only rejected).
        anchor_centroid: 1024-d float array (L2-normalized by caller, but
            this function re-normalizes defensively so callers can pass
            raw means too).
        embedder: Object with `.embed_texts(list[str]) -> np.ndarray` of
            shape `(N, 1024)` float32. Typically `BgeM3Embedder` from
            `book_pipeline.rag.embedding`.

    Returns:
        Cosine similarity in [-1, 1] (typical domain 0.2-0.9 for Paul's
        prose against his own curated anchors). >=0.95 flags memorization
        (V-2); <0.75 fails voice fidelity; 0.75-0.78 is the flag band.

    Raises:
        ValueError: scene_text is empty or whitespace-only.
    """
    if not scene_text or not scene_text.strip():
        raise ValueError("scene_text must be a non-empty string")
    vec = embedder.embed_texts([scene_text])[0].astype(np.float32)
    v_norm = max(float(np.linalg.norm(vec)), 1e-12)
    vec = vec / v_norm
    c_norm = max(float(np.linalg.norm(anchor_centroid)), 1e-12)
    centroid = anchor_centroid / c_norm
    return float(np.dot(vec, centroid))


__all__ = ["score_voice_fidelity"]
