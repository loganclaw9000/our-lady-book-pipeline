"""Tests for book_pipeline.voice_fidelity.pin (Plan 03-04 Task 1).

AnchorSetProvider loads anchor_set_v1.yaml, verifies its SHA against
mode_thresholds.yaml voice_fidelity.anchor_set_sha, and caches the centroid
(with parquet fallback per W-2).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from book_pipeline.voice_fidelity.anchors import (
    EMBEDDING_DIM,
    Anchor,
    AnchorSet,
    compute_centroid,
)
from book_pipeline.voice_fidelity.pin import AnchorSetDrift, AnchorSetProvider


class _StubEmbedder:
    """Deterministic seeded embedder; tracks call_count on embed_texts."""

    revision_sha: str = "stub-rev-1"

    def __init__(self) -> None:
        self.call_count = 0

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        self.call_count += 1
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            seed = hash(t) & 0xFFFFFFFF
            rng = np.random.default_rng(seed=seed)
            out[i] = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
        return out


def _synth_anchor_set_3() -> AnchorSet:
    return AnchorSet(
        anchors=[
            Anchor(
                id="a1",
                text="text one alpha",
                sub_genre="essay",
                source_file="fixture.jsonl",
                source_line_range="1-1",
                provenance_sha="0" * 16,
            ),
            Anchor(
                id="a2",
                text="text two beta",
                sub_genre="essay",
                source_file="fixture.jsonl",
                source_line_range="2-2",
                provenance_sha="1" * 16,
            ),
            Anchor(
                id="a3",
                text="text three gamma",
                sub_genre="analytic",
                source_file="fixture.jsonl",
                source_line_range="3-3",
                provenance_sha="2" * 16,
            ),
        ]
    )


def _write_thresholds_yaml(path: Path, anchor_set_sha: str) -> None:
    path.write_text(
        f"""
mode_a:
  regen_budget_R: 3
  per_scene_cost_cap_usd: 0.0
  voice_fidelity_band:
    min: 0.6
    max: 0.88
mode_b:
  model_id: claude-opus-4-7
  per_scene_cost_cap_usd: 2.0
  regen_attempts: 1
  prompt_cache_ttl: 1h
oscillation:
  enabled: true
  max_axis_flips: 2
alerts:
  telegram_cool_down_seconds: 3600
  dedup_window_seconds: 3600
preflag_beats: []
voice_fidelity:
  anchor_set_sha: {anchor_set_sha}
  pass_threshold: 0.78
  flag_band_min: 0.75
  flag_band_max: 0.78
  fail_threshold: 0.75
  memorization_flag_threshold: 0.95
""".strip(),
        encoding="utf-8",
    )


# --- Test 7: SHA match returns (centroid, sha, voice_fidelity_config) --------

def test_anchor_set_provider_load_on_sha_match_returns_centroid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    anchors = _synth_anchor_set_3()
    yaml_path = tmp_path / "anchor_set.yaml"
    anchors.save_to_yaml(yaml_path)

    thresholds_path = tmp_path / "mode_thresholds.yaml"
    _write_thresholds_yaml(thresholds_path, anchors.sha)

    # Monkeypatch ModeThresholdsConfig.yaml_file to point at our tmp file.
    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
    monkeypatch.setitem(ModeThresholdsConfig.model_config, "yaml_file", str(thresholds_path))

    embedder = _StubEmbedder()
    provider = AnchorSetProvider(
        yaml_path=yaml_path, thresholds_path=thresholds_path, embedder=embedder
    )
    centroid, sha, vf_config = provider.load()

    assert centroid.shape == (EMBEDDING_DIM,)
    assert centroid.dtype == np.float32
    assert sha == anchors.sha
    assert vf_config.anchor_set_sha == anchors.sha
    # No parquet fixture → falls back to embedder.
    assert embedder.call_count == 1


# --- Test 7 (drift): SHA mismatch raises AnchorSetDrift ----------------------

def test_anchor_set_provider_load_on_sha_mismatch_raises_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    anchors = _synth_anchor_set_3()
    yaml_path = tmp_path / "anchor_set.yaml"
    anchors.save_to_yaml(yaml_path)

    thresholds_path = tmp_path / "mode_thresholds.yaml"
    # Pin a WRONG SHA.
    wrong_sha = "0" * 64
    _write_thresholds_yaml(thresholds_path, wrong_sha)

    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
    monkeypatch.setitem(ModeThresholdsConfig.model_config, "yaml_file", str(thresholds_path))

    embedder = _StubEmbedder()
    provider = AnchorSetProvider(
        yaml_path=yaml_path, thresholds_path=thresholds_path, embedder=embedder
    )
    with pytest.raises(AnchorSetDrift) as exc_info:
        provider.load()
    err = exc_info.value
    assert err.expected_sha == wrong_sha
    assert err.actual_sha == anchors.sha
    assert err.yaml_path == yaml_path


# --- Test 7a (W-2): parquet present + matching shape → no embedder call ------

def test_anchor_set_provider_uses_parquet_when_shape_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    anchors = _synth_anchor_set_3()
    yaml_path = tmp_path / "anchor_set.yaml"
    anchors.save_to_yaml(yaml_path)

    thresholds_path = tmp_path / "mode_thresholds.yaml"
    _write_thresholds_yaml(thresholds_path, anchors.sha)

    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
    monkeypatch.setitem(ModeThresholdsConfig.model_config, "yaml_file", str(thresholds_path))

    # Write a parquet with 3 rows × 1024-dim to the conventional location.
    parquet_dir = tmp_path / "indexes" / "voice_anchors"
    parquet_dir.mkdir(parents=True)
    parquet_path = parquet_dir / "embeddings.parquet"
    vectors = []
    for i in range(3):
        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        vec[i] = 1.0
        vectors.append(vec.tolist())
    table = pa.table(
        {
            "id": ["a1", "a2", "a3"],
            "sub_genre": ["essay", "essay", "analytic"],
            "embedding": vectors,
        }
    )
    pq.write_table(table, parquet_path)  # type: ignore[no-untyped-call]

    embedder = _StubEmbedder()
    provider = AnchorSetProvider(
        yaml_path=yaml_path,
        thresholds_path=thresholds_path,
        embedder=embedder,
        parquet_path=parquet_path,
    )
    centroid, sha, _vf = provider.load()

    # W-2: parquet consumed → embedder never called.
    assert embedder.call_count == 0
    # Centroid of 3 orthonormal unit vectors (L2-norm'd then meaned then norm'd) = unit.
    assert abs(float(np.linalg.norm(centroid)) - 1.0) < 1e-5


# --- Test 7b (W-2): parquet wrong shape → falls back to compute_centroid -----

def test_anchor_set_provider_falls_back_on_wrong_parquet_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    anchors = _synth_anchor_set_3()
    yaml_path = tmp_path / "anchor_set.yaml"
    anchors.save_to_yaml(yaml_path)

    thresholds_path = tmp_path / "mode_thresholds.yaml"
    _write_thresholds_yaml(thresholds_path, anchors.sha)

    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
    monkeypatch.setitem(ModeThresholdsConfig.model_config, "yaml_file", str(thresholds_path))

    # Write a parquet with WRONG row count (2 rows instead of 3).
    parquet_dir = tmp_path / "indexes" / "voice_anchors"
    parquet_dir.mkdir(parents=True)
    parquet_path = parquet_dir / "embeddings.parquet"
    vectors = [np.zeros(EMBEDDING_DIM, dtype=np.float32).tolist() for _ in range(2)]
    table = pa.table(
        {"id": ["a1", "a2"], "sub_genre": ["essay", "essay"], "embedding": vectors}
    )
    pq.write_table(table, parquet_path)  # type: ignore[no-untyped-call]

    embedder = _StubEmbedder()
    with caplog.at_level(logging.WARNING):
        provider = AnchorSetProvider(
            yaml_path=yaml_path,
            thresholds_path=thresholds_path,
            embedder=embedder,
            parquet_path=parquet_path,
        )
        provider.load()

    assert embedder.call_count == 1
    # Warning logged.
    assert any("parquet" in rec.message.lower() for rec in caplog.records)


# --- Test 7c (W-2): parquet absent → falls back to compute_centroid ----------

def test_anchor_set_provider_falls_back_when_parquet_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    anchors = _synth_anchor_set_3()
    yaml_path = tmp_path / "anchor_set.yaml"
    anchors.save_to_yaml(yaml_path)

    thresholds_path = tmp_path / "mode_thresholds.yaml"
    _write_thresholds_yaml(thresholds_path, anchors.sha)

    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
    monkeypatch.setitem(ModeThresholdsConfig.model_config, "yaml_file", str(thresholds_path))

    missing_parquet = tmp_path / "does_not_exist.parquet"
    embedder = _StubEmbedder()
    provider = AnchorSetProvider(
        yaml_path=yaml_path,
        thresholds_path=thresholds_path,
        embedder=embedder,
        parquet_path=missing_parquet,
    )
    provider.load()
    assert embedder.call_count == 1


# --- Test 8: second load returns cached centroid -----------------------------

def test_anchor_set_provider_second_load_uses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    anchors = _synth_anchor_set_3()
    yaml_path = tmp_path / "anchor_set.yaml"
    anchors.save_to_yaml(yaml_path)

    thresholds_path = tmp_path / "mode_thresholds.yaml"
    _write_thresholds_yaml(thresholds_path, anchors.sha)

    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
    monkeypatch.setitem(ModeThresholdsConfig.model_config, "yaml_file", str(thresholds_path))

    embedder = _StubEmbedder()
    provider = AnchorSetProvider(
        yaml_path=yaml_path, thresholds_path=thresholds_path, embedder=embedder
    )
    centroid1, sha1, _vf1 = provider.load()
    call_count_after_first = embedder.call_count
    assert call_count_after_first == 1

    centroid2, sha2, _vf2 = provider.load()
    # Cache was used — embedder NOT called again.
    assert embedder.call_count == call_count_after_first
    np.testing.assert_array_equal(centroid1, centroid2)
    assert sha1 == sha2
