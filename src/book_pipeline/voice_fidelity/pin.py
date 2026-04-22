"""AnchorSetProvider — anchor-set loader with SHA verification + parquet fallback.

Plan 03-04 Task 1. Composes Plan 03-02's AnchorSet + compute_centroid with
the voice_fidelity.anchor_set_sha pin in mode_thresholds.yaml (VoiceFidelityConfig).
Any SHA drift raises AnchorSetDrift at .load() time (V-3 extension for anchor
drift); within a single CLI invocation the centroid is cached so repeat
calls skip the BGE-M3 embed.

W-2 parquet fast-path:
  If indexes/voice_anchors/embeddings.parquet exists AND has (N, 1024) rows
  matching the AnchorSet's anchor count, the centroid is assembled directly
  from the parquet (L2-normalize rows, mean, L2-normalize) without calling
  the embedder. On mismatch (wrong row count or wrong dim) OR absence the
  provider falls back to compute_centroid(anchors, embedder) and logs a
  warning — the CLI should treat this as "parquet stale, regenerate".

This module lives in the kernel and MUST NOT carry book-domain-specific logic.
The parquet PATH default is a conventional location; Plan 03-06 CLI can
override it.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from book_pipeline.config.mode_thresholds import (
    ModeThresholdsConfig,
    VoiceFidelityConfig,
)
from book_pipeline.voice_fidelity.anchors import (
    EMBEDDING_DIM,
    AnchorSet,
    compute_centroid,
)

_LOG = logging.getLogger(__name__)

_DEFAULT_PARQUET_PATH: Path = Path("indexes/voice_anchors/embeddings.parquet")


class AnchorSetDrift(Exception):
    """Raised when anchor_set_v1.yaml SHA differs from mode_thresholds pin.

    Attributes:
        expected_sha: SHA pinned in mode_thresholds.yaml voice_fidelity.anchor_set_sha.
        actual_sha: SHA computed from anchor_set_v1.yaml on disk.
        yaml_path: The anchor_set yaml path that was hashed.
    """

    def __init__(
        self, expected_sha: str, actual_sha: str, yaml_path: Path
    ) -> None:
        self.expected_sha = expected_sha
        self.actual_sha = actual_sha
        self.yaml_path = yaml_path
        super().__init__(
            f"anchor-set SHA drift at {yaml_path}: "
            f"expected={expected_sha}, actual={actual_sha}"
        )


def _try_load_centroid_from_parquet(
    parquet_path: Path, expected_rows: int
) -> np.ndarray | None:
    """Return centroid from parquet or None if absent/wrong-shape.

    Log a warning on wrong-shape so operators know to regenerate.
    """
    if not parquet_path.exists():
        return None
    try:
        import pyarrow.parquet as pq
    except ImportError:
        _LOG.warning(
            "pyarrow not installed; parquet fast-path unavailable at %s", parquet_path
        )
        return None
    try:
        table = pq.read_table(parquet_path)  # type: ignore[no-untyped-call]
    except Exception as exc:  # pragma: no cover - pyarrow errors are env-dependent
        _LOG.warning(
            "parquet_mismatch_or_absent at %s (read error: %s); falling back to "
            "compute_centroid",
            parquet_path,
            exc,
        )
        return None
    if "embedding" not in table.column_names:
        _LOG.warning(
            "parquet_mismatch_or_absent at %s (no 'embedding' column); falling "
            "back to compute_centroid",
            parquet_path,
        )
        return None
    embeddings_col = table.column("embedding").to_pylist()
    if len(embeddings_col) != expected_rows:
        _LOG.warning(
            "parquet_mismatch_or_absent at %s (row_count=%d, expected=%d); "
            "falling back to compute_centroid",
            parquet_path,
            len(embeddings_col),
            expected_rows,
        )
        return None
    try:
        arr = np.array(embeddings_col, dtype=np.float32)
    except (ValueError, TypeError) as exc:
        _LOG.warning(
            "parquet_mismatch_or_absent at %s (cannot form ndarray: %s); "
            "falling back to compute_centroid",
            parquet_path,
            exc,
        )
        return None
    if arr.ndim != 2 or arr.shape != (expected_rows, EMBEDDING_DIM):
        _LOG.warning(
            "parquet_mismatch_or_absent at %s (shape=%s, expected=(%d, %d)); "
            "falling back to compute_centroid",
            parquet_path,
            arr.shape,
            expected_rows,
            EMBEDDING_DIM,
        )
        return None
    # L2-normalize each row, mean, L2-normalize — matches compute_centroid.
    row_norms = np.linalg.norm(arr, axis=1, keepdims=True)
    row_norms = np.maximum(row_norms, 1e-12)
    normalized = (arr / row_norms).astype(np.float32)
    mean_vec = normalized.mean(axis=0)
    mean_norm = max(float(np.linalg.norm(mean_vec)), 1e-12)
    centroid: np.ndarray = (mean_vec / mean_norm).astype(np.float32)
    return centroid


class AnchorSetProvider:
    """Verifies anchor SHA against mode_thresholds and hands out a cached centroid.

    Usage (Plan 03-04 ModeADrafter composition):

        provider = AnchorSetProvider(
            yaml_path=Path("config/voice_anchors/anchor_set_v1.yaml"),
            thresholds_path=Path("config/mode_thresholds.yaml"),
            embedder=bge_m3,
        )
        centroid, sha, vf_config = provider.load()
        # ModeADrafter passes centroid per-scene to score_voice_fidelity.
    """

    def __init__(
        self,
        yaml_path: Path,
        thresholds_path: Path,
        embedder: Any,
        *,
        parquet_path: Path | None = None,
    ) -> None:
        self.yaml_path = Path(yaml_path)
        self.thresholds_path = Path(thresholds_path)
        self.embedder = embedder
        self.parquet_path = (
            Path(parquet_path) if parquet_path is not None else _DEFAULT_PARQUET_PATH
        )
        self._cache: tuple[np.ndarray, str, VoiceFidelityConfig] | None = None

    def load(self) -> tuple[np.ndarray, str, VoiceFidelityConfig]:
        """Load anchors, verify SHA, return (centroid, sha, voice_fidelity_config).

        Repeat calls return the cached result.

        Raises:
            AnchorSetDrift: anchor SHA differs from mode_thresholds pin.
        """
        if self._cache is not None:
            return self._cache

        anchors = AnchorSet.load_from_yaml(self.yaml_path)
        actual_sha = anchors.sha

        # Load the mode_thresholds config — its yaml_file is wired to
        # config/mode_thresholds.yaml by pydantic-settings. Tests monkeypatch
        # SettingsConfigDict.yaml_file to tmp_path.
        cfg = ModeThresholdsConfig()  # type: ignore[call-arg]
        vf_config = cfg.voice_fidelity

        if actual_sha != vf_config.anchor_set_sha:
            raise AnchorSetDrift(
                expected_sha=vf_config.anchor_set_sha,
                actual_sha=actual_sha,
                yaml_path=self.yaml_path,
            )

        # W-2: try parquet first; fall back to compute_centroid on any mismatch.
        centroid = _try_load_centroid_from_parquet(
            self.parquet_path, expected_rows=len(anchors.anchors)
        )
        if centroid is None:
            centroid = compute_centroid(anchors, self.embedder)

        self._cache = (centroid, actual_sha, vf_config)
        return self._cache


__all__ = ["AnchorSetDrift", "AnchorSetProvider"]
