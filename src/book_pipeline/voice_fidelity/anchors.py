"""AnchorSet + centroid math + deterministic SHA for OBS-03 voice anchors.

The anchor set is the curated collection of 20-30 passages (150-400 words
each) of Paul's prose, tagged by sub-genre (essay / analytic / narrative)
per PITFALLS V-1. The anchor centroid is the L2-normalized mean of their
BGE-M3 embeddings; Mode-A drafts are scored by cosine similarity against it.

This module lives in the kernel and MUST NOT carry book-domain-specific
logic. Import-linter contract 1 (pyproject.toml) guards the kernel boundary;
the CLI composition seam at src/book_pipeline/cli/curate_anchors.py is the
ONE sanctioned bridge into book_specifics.anchor_sources.

Algorithm pins (do not drift):

    anchor_set_sha = SHA256(JSON.dumps(
        sorted([(a.id, a.text, a.sub_genre) for a in anchors]),
        sort_keys=True, ensure_ascii=False
    ).encode("utf-8")).hexdigest()

    compute_centroid(anchors, embedder):
        raw = embedder.embed_texts([a.text for a in anchors])  # (N, 1024)
        row_norms = max(||raw_i||, 1e-12)
        normalized = raw / row_norms
        mean_vec = normalized.mean(axis=0)
        return (mean_vec / max(||mean_vec||, 1e-12)).astype(float32)
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from pydantic import BaseModel

SubGenre = Literal["essay", "analytic", "narrative"]

EMBEDDING_DIM = 1024


class Anchor(BaseModel):
    """A single curated voice anchor.

    Attributes:
        id: Stable identifier (e.g. "thinkpiece_v3_00042").
        text: The anchor passage (150-400 words by curation policy).
        sub_genre: One of essay / analytic / narrative (V-1 two-tier).
        source_file: Path the row was curated from (provenance).
        source_line_range: "START-END" (1-indexed inclusive) inside source_file.
        provenance_sha: xxhash64 of the source row's JSON bytes (drift detection).
    """

    id: str
    text: str
    sub_genre: SubGenre
    source_file: str
    source_line_range: str
    provenance_sha: str


class AnchorSet(BaseModel):
    """Wrapper around list[Anchor] with deterministic load/save + SHA."""

    anchors: list[Anchor]

    # --- SHA -----------------------------------------------------------------

    @property
    def sha(self) -> str:
        """Deterministic 64-hex SHA over (id, text, sub_genre) tuples.

        Sorted lexically on the tuple before hashing — so shuffling the
        `anchors` list does NOT change the SHA. UTF-8 / ensure_ascii=False
        preserves em-dashes and smart quotes byte-for-byte across machines.
        """
        triples = sorted(
            (a.id, a.text, a.sub_genre) for a in self.anchors
        )
        payload = json.dumps(triples, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # --- YAML round-trip -----------------------------------------------------

    @classmethod
    def load_from_yaml(cls, path: Path) -> AnchorSet:
        """Load AnchorSet from YAML. Top-level shape: `anchors: [...]`."""
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "anchors" not in data:
            raise ValueError(
                f"{path}: expected top-level mapping with 'anchors' key; "
                f"got {type(data).__name__}"
            )
        return cls.model_validate(data)

    def save_to_yaml(self, path: Path) -> None:
        """Write AnchorSet to path atomically (tempfile + os.replace).

        Determinism: sort_keys=False so anchor ORDER in the YAML matches the
        in-memory order; allow_unicode=True so em-dashes and smart quotes
        land as literal UTF-8 (not `\\u2014` escapes).
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(mode="json")
        body = yaml.safe_dump(
            payload,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)


# --- Free-standing helpers ---------------------------------------------------


def compute_anchor_set_sha(anchors: AnchorSet) -> str:
    """Delegates to AnchorSet.sha — exposed as a function for CLI callers."""
    return anchors.sha


def _l2_normalize_rows(raw: np.ndarray) -> np.ndarray:
    row_norms = np.linalg.norm(raw, axis=1, keepdims=True)
    row_norms = np.maximum(row_norms, 1e-12)
    normalized: np.ndarray = (raw / row_norms).astype(np.float32)
    return normalized


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = max(float(np.linalg.norm(vec)), 1e-12)
    normalized: np.ndarray = (vec / norm).astype(np.float32)
    return normalized


def compute_centroid(anchors: AnchorSet, embedder: Any) -> np.ndarray:
    """L2-normalized mean of anchor embeddings. Returns (EMBEDDING_DIM,) float32.

    Algorithm (pinned — do not drift):
      1. Embed all anchor texts as a single batch.
      2. L2-normalize each row.
      3. Mean across axis=0.
      4. L2-normalize the result.

    Determinism: given a fixed embedder.revision_sha and a fixed anchor set,
    compute_centroid is byte-identical across runs (numpy float32 ops are
    deterministic modulo BLAS thread-count, which sentence-transformers pins
    per revision).
    """
    if not anchors.anchors:
        raise ValueError("cannot compute centroid of empty AnchorSet")
    texts = [a.text for a in anchors.anchors]
    raw = embedder.embed_texts(texts)
    assert raw.shape == (len(texts), EMBEDDING_DIM), (
        f"embedder returned shape {raw.shape}; expected "
        f"({len(texts)}, {EMBEDDING_DIM})"
    )
    normalized = _l2_normalize_rows(raw)
    mean_vec = normalized.mean(axis=0)
    return _l2_normalize(mean_vec)


def compute_per_sub_genre_centroids(
    anchors: AnchorSet, embedder: Any
) -> dict[str, np.ndarray]:
    """Compute one centroid per sub_genre. Keys: actual sub_genres present.

    Phase 3 uses the overall centroid only; per-sub-genre centroids are
    computed here for Plan 03-04's per-sub-genre reporting (PITFALLS V-1
    two-tier mitigation).
    """
    groups: dict[str, list[Anchor]] = defaultdict(list)
    for a in anchors.anchors:
        groups[a.sub_genre].append(a)

    out: dict[str, np.ndarray] = {}
    for sg, members in groups.items():
        sub_set = AnchorSet(anchors=members)
        out[sg] = compute_centroid(sub_set, embedder)
    return out


def check_anchor_dominance(
    anchors: AnchorSet, embedder: Any, threshold: float = 0.15
) -> list[str]:
    """Return anchor IDs whose embedding contribution to the centroid exceeds threshold.

    Contribution = cosine(row_vec, centroid). With N anchors, the uniform
    baseline is 1/sqrt(N) for orthogonal vectors (~0.21 at N=22). The 0.15
    threshold is GENEROUS — flags only anchors that account for >> their
    share of the centroid direction. Tests + CLI both call this to detect
    the PITFALLS V-1 warning sign "one passage dominates the centroid".

    Returns sorted list for deterministic output.
    """
    if not anchors.anchors:
        return []
    centroid = compute_centroid(anchors, embedder)
    raw = embedder.embed_texts([a.text for a in anchors.anchors])
    normalized = _l2_normalize_rows(raw)
    flagged: list[str] = []
    for i, a in enumerate(anchors.anchors):
        contribution = float(np.dot(normalized[i], centroid))
        if abs(contribution) > threshold:
            flagged.append(a.id)
    return sorted(flagged)


__all__ = [
    "EMBEDDING_DIM",
    "Anchor",
    "AnchorSet",
    "SubGenre",
    "check_anchor_dominance",
    "compute_anchor_set_sha",
    "compute_centroid",
    "compute_per_sub_genre_centroids",
]
