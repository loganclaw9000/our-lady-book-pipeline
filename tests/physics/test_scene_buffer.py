"""Tests for SceneEmbeddingCache + cosine helpers (Plan 07-05 PHYSICS-10 / D-28).

Tests 1-5 per plan <behavior>. Slow-marked because they instantiate a real
BgeM3Embedder (loads the ~2GB model on first call); skipped automatically
if indexes/ is empty (the smoke harness expects an ingest run).

Pitfall 12 mitigation: tmp_path injection for db_path.
Pitfall 3 mitigation: cosine assertions on unit-normalized vectors.
Pitfall 7 mitigation: cache key composite (scene_id, bge_m3_revision_sha).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from book_pipeline.physics import (
    SceneEmbeddingCache,
    cosine_similarity_to_prior,
    max_cosine,
)


def _indexes_populated() -> bool:
    p = Path("indexes")
    return p.exists() and any(p.iterdir())


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not _indexes_populated(),
        reason="indexes/ empty; run uv run book-pipeline ingest first",
    ),
]


@pytest.fixture(scope="module")
def real_embedder() -> Any:
    """Real BgeM3Embedder (cpu device — vLLM may be running on cuda:0)."""
    from book_pipeline.rag.embedding import BgeM3Embedder

    return BgeM3Embedder(device="cpu")


@pytest.fixture
def cache(tmp_path: Path, real_embedder: Any) -> SceneEmbeddingCache:
    return SceneEmbeddingCache(
        db_path=tmp_path / "scene_embeddings.sqlite",
        embedder=real_embedder,
    )


# --------------------------------------------------------------------- #
# Test 1 — get_or_compute returns unit-norm float32 (EMBEDDING_DIM,)    #
# --------------------------------------------------------------------- #


def test_1_get_or_compute_returns_unit_norm_vector(cache: SceneEmbeddingCache) -> None:
    """SceneEmbeddingCache.get_or_compute returns a (EMBEDDING_DIM,) float32
    numpy array with norm ≈ 1.0 (Pitfall 3)."""
    from book_pipeline.rag.embedding import EMBEDDING_DIM

    arr = cache.get_or_compute("ch15_sc02", "Andrés walked the beach at dawn.")
    assert arr.shape == (EMBEDDING_DIM,)
    assert arr.dtype == np.float32
    norm = float(np.linalg.norm(arr))
    assert abs(norm - 1.0) < 1e-3, f"expected unit-norm, got {norm}"


# --------------------------------------------------------------------- #
# Test 2 — second get_or_compute hits cache (no second embed call)      #
# --------------------------------------------------------------------- #


def test_2_second_call_hits_cache(tmp_path: Path, real_embedder: Any) -> None:
    """Calling get_or_compute twice with the same scene_id returns the cached
    vector — verified by counting embed_texts invocations on a wrapper."""
    call_count = [0]
    real_embed = real_embedder.embed_texts

    def counting_embed(texts: list[str]) -> Any:
        call_count[0] += 1
        return real_embed(texts)

    real_embedder.embed_texts = counting_embed  # type: ignore[method-assign]
    try:
        cache_obj = SceneEmbeddingCache(
            db_path=tmp_path / "se.sqlite",
            embedder=real_embedder,
        )
        first = cache_obj.get_or_compute("ch15_sc02", "scene text alpha")
        assert call_count[0] == 1
        second = cache_obj.get_or_compute("ch15_sc02", "scene text alpha")
        assert call_count[0] == 1, "cache miss on second call"
        np.testing.assert_array_equal(first, second)
    finally:
        real_embedder.embed_texts = real_embed  # type: ignore[method-assign]


# --------------------------------------------------------------------- #
# Test 3 — cosine_similarity_to_prior returns dict with values in [-1,1] #
# --------------------------------------------------------------------- #


def test_3_cosine_similarity_to_prior_in_range(cache: SceneEmbeddingCache) -> None:
    """cosine_similarity_to_prior returns {sid: float} in [-1, 1]."""
    candidate = cache.get_or_compute("ch15_sc02", "Andrés walked the beach.")
    prior = {
        "sc01": cache.get_or_compute(
            "ch15_sc01", "The drum first. Always the drum first."
        ),
    }
    sims = cosine_similarity_to_prior(candidate, prior)
    assert "sc01" in sims
    val = sims["sc01"]
    assert -1.0 <= val <= 1.0, f"cosine outside [-1,1]: {val}"


# --------------------------------------------------------------------- #
# Test 4 — Pitfall 3: assertion fires on non-unit input                  #
# --------------------------------------------------------------------- #


def test_4_pitfall3_assert_fires_on_non_unit_input() -> None:
    """cosine_similarity_to_prior asserts unit-norm on the candidate."""
    bad = np.ones((1024,), dtype=np.float32) * 0.5  # not unit-normalized
    good = np.zeros((1024,), dtype=np.float32)
    good[0] = 1.0  # unit-norm
    with pytest.raises(AssertionError, match="not unit-normalized"):
        cosine_similarity_to_prior(bad, {"prior": good})


# --------------------------------------------------------------------- #
# Test 5 — D-28 threshold: near-copy ≥ 0.80; distinct < 0.65            #
# --------------------------------------------------------------------- #


def test_5_d28_threshold_near_copy_vs_distinct(cache: SceneEmbeddingCache) -> None:
    """D-28: a near-copy of a prior scene yields cosine ≥ 0.80; a distinct
    scene yields cosine < 0.65. Margins chosen to be robust to BGE-M3
    embedding variance."""
    candidate = cache.get_or_compute(
        "ch15_sc02_candidate",
        "Andrés walked the beach at dawn. The smell of salt was strong.",
    )
    near_copy = cache.get_or_compute(
        "ch15_sc01_near",
        "Andrés walked the beach at dawn. The smell of salt and pitch was strong.",
    )
    distinct = cache.get_or_compute(
        "ch01_sc01_distinct",
        "Xochitl prayed at the temple under copal smoke. The hum filled her bones.",
    )

    sims = cosine_similarity_to_prior(
        candidate, {"near": near_copy, "distinct": distinct}
    )
    assert sims["near"] >= 0.80, (
        f"near-copy cosine {sims['near']:.3f} < 0.80 — D-28 threshold "
        f"would not fire on a real near-duplicate"
    )
    assert sims["distinct"] < 0.65, (
        f"distinct-scene cosine {sims['distinct']:.3f} >= 0.65 — too high "
        f"(would risk false-positive scene-buffer FAIL)"
    )


# --------------------------------------------------------------------- #
# Pitfall 7: PRIMARY KEY (scene_id, bge_m3_revision_sha) — sanity row    #
# --------------------------------------------------------------------- #


def test_pitfall7_cache_key_includes_revision_sha(
    tmp_path: Path, real_embedder: Any
) -> None:
    """PRIMARY KEY includes bge_m3_revision_sha so a model upgrade naturally
    invalidates via composite-key cache miss (Pitfall 7)."""
    cache_obj = SceneEmbeddingCache(
        db_path=tmp_path / "rev.sqlite",
        embedder=real_embedder,
    )
    cache_obj.get_or_compute("ch15_sc02", "scene")
    # Inspect the schema directly.
    conn = sqlite3.connect(str(tmp_path / "rev.sqlite"))
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='scene_embeddings'"
    ).fetchall()
    conn.close()
    assert rows, "scene_embeddings table missing"
    schema_sql = rows[0][0]
    assert "PRIMARY KEY (scene_id, bge_m3_revision_sha)" in schema_sql, (
        f"composite primary key missing in schema: {schema_sql}"
    )


# --------------------------------------------------------------------- #
# max_cosine — empty prior → (None, 0.0)                                #
# --------------------------------------------------------------------- #


def test_max_cosine_empty_prior_returns_none_zero() -> None:
    candidate = np.zeros((1024,), dtype=np.float32)
    candidate[0] = 1.0
    sid, sim = max_cosine(candidate, {})
    assert sid is None
    assert sim == 0.0
