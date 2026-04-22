"""Tests for the REAL book_pipeline.voice_fidelity.scorer.score_voice_fidelity.

Plan 03-02 Task 1 tests 5-7. These tests REPLACE the Plan 03-01 stub test
(tests/voice_fidelity/test_scorer.py checks the stub raises) — once the
real impl lands, the stub test becomes obsolete and is removed.
"""
from __future__ import annotations

import numpy as np
import pytest

from book_pipeline.voice_fidelity.scorer import score_voice_fidelity

EMBEDDING_DIM = 1024


class FixedEmbedder:
    """Returns a mapping[str] -> 1024-d vector for deterministic tests."""

    revision_sha: str = "fixed-rev-1"

    def __init__(self, mapping: dict[str, np.ndarray]) -> None:
        self._mapping = mapping

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            out[i] = self._mapping[t].astype(np.float32)
        return out


def _unit_e(i: int) -> np.ndarray:
    v = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    v[i] = 1.0
    return v


# --- Test 5: scene vector == centroid returns 1.0 ------------------------

def test_score_voice_fidelity_identical_returns_one() -> None:
    centroid = _unit_e(0)
    embedder = FixedEmbedder({"hello": _unit_e(0)})
    result = score_voice_fidelity("hello", centroid, embedder)
    assert abs(result - 1.0) < 1e-6


# --- Test 6: scene vector orthogonal to centroid returns ~0 --------------

def test_score_voice_fidelity_orthogonal_returns_zero() -> None:
    centroid = _unit_e(0)
    embedder = FixedEmbedder({"orthogonal scene": _unit_e(1)})
    result = score_voice_fidelity("orthogonal scene", centroid, embedder)
    assert abs(result - 0.0) < 1e-6


# --- Test 7: empty scene_text raises ValueError --------------------------

def test_score_voice_fidelity_empty_raises() -> None:
    centroid = _unit_e(0)
    embedder = FixedEmbedder({})
    with pytest.raises(ValueError):
        score_voice_fidelity("", centroid, embedder)
    with pytest.raises(ValueError):
        score_voice_fidelity("   \n\t   ", centroid, embedder)


def test_score_voice_fidelity_anti_parallel_returns_negative_one() -> None:
    """Edge: scene embedding = -centroid → cosine -1.0. Normalizes properly."""
    centroid = _unit_e(0)
    anti = -_unit_e(0)
    embedder = FixedEmbedder({"anti": anti})
    result = score_voice_fidelity("anti", centroid, embedder)
    assert abs(result + 1.0) < 1e-6


def test_score_voice_fidelity_is_deterministic() -> None:
    centroid = _unit_e(0)
    v = np.array([0.5, 0.5] + [0.0] * (EMBEDDING_DIM - 2), dtype=np.float32)
    embedder = FixedEmbedder({"scene": v})
    r1 = score_voice_fidelity("scene", centroid, embedder)
    r2 = score_voice_fidelity("scene", centroid, embedder)
    assert r1 == r2
    # Expected: dot(v_norm, e0) = 0.5/sqrt(0.5) ≈ 0.7071.
    assert abs(r1 - 0.7071067811865476) < 1e-5
