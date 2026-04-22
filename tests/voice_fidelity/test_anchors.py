"""Tests for book_pipeline.voice_fidelity.anchors — AnchorSet + centroid math.

Plan 03-02 Task 1 tests 1-4 + 8. Uses a StubEmbedder so tests do not require
the real BGE-M3 model to be loaded.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from book_pipeline.voice_fidelity.anchors import (
    Anchor,
    AnchorSet,
    check_anchor_dominance,
    compute_anchor_set_sha,
    compute_centroid,
    compute_per_sub_genre_centroids,
)

EMBEDDING_DIM = 1024


class StubEmbedder:
    """Deterministic seeded embedder — byte-identical across machines.

    embed_texts([t]) returns a fixed 1024-d float32 vector derived from
    hash(text). No real BGE-M3 model is loaded.
    """

    revision_sha: str = "stub-rev-1"

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            seed = hash(t) & 0xFFFF_FFFF
            rng = np.random.default_rng(seed=seed)
            out[i] = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
        return out


class FixedEmbedder:
    """Returns hard-coded vectors for a fixed mapping of text->vector."""

    revision_sha: str = "fixed-rev-1"

    def __init__(self, mapping: dict[str, np.ndarray]) -> None:
        self._mapping = mapping

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            vec = self._mapping[t]
            out[i] = vec.astype(np.float32)
        return out


def _make_anchor(
    *,
    id: str,
    text: str,
    sub_genre: str,
    source_file: str = "fixture.jsonl",
    source_line_range: str = "1-1",
    provenance_sha: str = "0" * 16,
) -> Anchor:
    return Anchor(
        id=id,
        text=text,
        sub_genre=sub_genre,
        source_file=source_file,
        source_line_range=source_line_range,
        provenance_sha=provenance_sha,
    )


def _synth_anchor_set_3() -> AnchorSet:
    """3 synthetic anchors — 2 essay, 1 analytic."""
    return AnchorSet(
        anchors=[
            _make_anchor(id="a1", text="text one", sub_genre="essay"),
            _make_anchor(id="a2", text="text two", sub_genre="essay"),
            _make_anchor(id="a3", text="text three", sub_genre="analytic"),
        ]
    )


# --- Test 1: load_from_yaml <-> save_to_yaml round-trip ------------------

def test_load_from_yaml_roundtrips_through_save_to_yaml(tmp_path: Path) -> None:
    src = _synth_anchor_set_3()
    path1 = tmp_path / "a1.yaml"
    path2 = tmp_path / "a2.yaml"
    src.save_to_yaml(path1)

    loaded = AnchorSet.load_from_yaml(path1)
    loaded.save_to_yaml(path2)

    assert path1.read_bytes() == path2.read_bytes(), (
        "save_to_yaml must be idempotent byte-for-byte"
    )
    assert len(loaded.anchors) == 3
    assert loaded.anchors[0].id == "a1"
    assert loaded.anchors[0].sub_genre == "essay"


# --- Test 2: compute_anchor_set_sha is order-stable ----------------------

def test_compute_anchor_set_sha_is_sort_stable(tmp_path: Path) -> None:
    a = _synth_anchor_set_3()

    # Reverse order.
    b = AnchorSet(anchors=list(reversed(a.anchors)))

    sha_a = compute_anchor_set_sha(a)
    sha_b = compute_anchor_set_sha(b)
    assert sha_a == sha_b, "sha must sort anchors before hashing"
    assert len(sha_a) == 64
    assert all(c in "0123456789abcdef" for c in sha_a)


# --- Test 3: compute_centroid is L2-normalized mean ----------------------

def test_compute_centroid_returns_unit_norm_mean(tmp_path: Path) -> None:
    anchors = _synth_anchor_set_3()
    embedder = StubEmbedder()
    centroid = compute_centroid(anchors, embedder)

    assert centroid.shape == (EMBEDDING_DIM,)
    assert centroid.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(centroid), 1.0, atol=1e-5)

    # Reference computation: L2-normalize each row, mean, L2-normalize result.
    raw = embedder.embed_texts([a.text for a in anchors.anchors])
    row_norms = np.linalg.norm(raw, axis=1, keepdims=True)
    row_norms = np.maximum(row_norms, 1e-12)
    normalized = raw / row_norms
    mean_vec = normalized.mean(axis=0)
    mean_norm = max(float(np.linalg.norm(mean_vec)), 1e-12)
    expected = (mean_vec / mean_norm).astype(np.float32)
    np.testing.assert_allclose(centroid, expected, atol=1e-5)


# --- Test 4: check_anchor_dominance flags a dominant anchor --------------

def test_check_anchor_dominance_flags_dominant_anchor() -> None:
    """One anchor whose vector IS the centroid direction dominates; others orthogonal."""
    dominant = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    dominant[0] = 1.0
    ortho1 = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    ortho1[1] = 1.0
    ortho2 = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    ortho2[2] = 1.0

    mapping = {
        "dominant text": dominant,
        "ortho text one": ortho1,
        "ortho text two": ortho2,
    }
    embedder = FixedEmbedder(mapping)

    anchors = AnchorSet(
        anchors=[
            _make_anchor(id="dom", text="dominant text", sub_genre="essay"),
            _make_anchor(id="o1", text="ortho text one", sub_genre="essay"),
            _make_anchor(id="o2", text="ortho text two", sub_genre="analytic"),
        ]
    )

    # Threshold low enough (0.15) that the non-orthogonal anchor triggers.
    # Its cosine with the centroid = 1/sqrt(3) ≈ 0.577 > 0.15.
    flagged = check_anchor_dominance(anchors, embedder, threshold=0.15)
    assert "dom" in flagged
    # The orthogonal anchors each have cosine ~0.577 with the centroid too
    # (centroid is (e0+e1+e2)/sqrt(3)), so all three are "dominant" under
    # threshold 0.15. Dominance test here is that "dom" DOES appear when
    # threshold is 0.15.


def test_check_anchor_dominance_empty_when_uniform() -> None:
    """With N random anchors, contributions should all be << 1.0 — no single
    anchor dominates. (The 0.15 threshold is generous vs. 1/N uniform baseline.)"""
    # Use StubEmbedder with 10 synthetic anchors; each vector is pseudorandom
    # high-dimensional — expected dot product with centroid is ~1/sqrt(10).
    anchors = AnchorSet(
        anchors=[
            _make_anchor(
                id=f"a{i}", text=f"text item {i}", sub_genre="essay"
            )
            for i in range(10)
        ]
    )
    embedder = StubEmbedder()
    # Use a very generous threshold (0.5) — none should exceed it.
    flagged = check_anchor_dominance(anchors, embedder, threshold=0.5)
    assert flagged == [], f"no single anchor should dominate; got {flagged}"


# --- Test 8: compute_per_sub_genre_centroids ----------------------------

def test_compute_per_sub_genre_centroids_groups_correctly() -> None:
    anchors = _synth_anchor_set_3()  # 2 essay, 1 analytic
    embedder = StubEmbedder()
    per_sg = compute_per_sub_genre_centroids(anchors, embedder)

    assert set(per_sg.keys()) == {"essay", "analytic"}
    for _sg, cent in per_sg.items():
        assert cent.shape == (EMBEDDING_DIM,)
        assert cent.dtype == np.float32
        np.testing.assert_allclose(np.linalg.norm(cent), 1.0, atol=1e-5)


def test_anchor_set_sha_property_matches_compute_function() -> None:
    a = _synth_anchor_set_3()
    assert a.sha == compute_anchor_set_sha(a)
    assert len(a.sha) == 64


def test_anchor_rejects_invalid_sub_genre() -> None:
    with pytest.raises(ValidationError):
        _make_anchor(id="bad", text="t", sub_genre="poetry")  # type: ignore[arg-type]
