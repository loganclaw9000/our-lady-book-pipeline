"""SceneEmbeddingCache + cosine helpers (Plan 07-05 PHYSICS-10 / D-28).

SQLite-backed embedding cache keyed by ``(scene_id, bge_m3_revision_sha)``.

Pitfall 7 mitigation: cache key includes embedder ``revision_sha`` — model
upgrade naturally invalidates via missing composite-key cache hit (no manual
flush needed). Pitfall 12 mitigation: ``db_path`` is a constructor arg so
tests inject a tmp path; production wires
``.planning/intel/scene_embeddings.sqlite``.

Pitfall 3 mitigation: BGE-M3 returns unit-normalized vectors (verified at
``rag/embedding.py`` ``normalize_embeddings=True``). Cosine is therefore the
plain dot product; we do NOT recompute norms inside the hot path. Sanity
assertions ``|a| ≈ 1.0`` fire on read so a corrupt blob or a future
embedder-revision shift surfaces fast (T-07-07 cache-integrity surface).

Threat model — T-07-07 (Tampering, scene-buffer SQLite cache):
- All SQLite writes use parameterized ``?`` binding — never f-string-into-SQL.
- ``CREATE TABLE`` declares ``PRIMARY KEY (scene_id, bge_m3_revision_sha)``;
  ``INSERT OR REPLACE`` upserts cleanly on cache miss with no race window.
- ``db_path`` constructor-injected; tests use tmp_path (no concurrent writes
  against production cache file).
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from book_pipeline.rag.embedding import EMBEDDING_DIM, BgeM3Embedder


class SceneEmbeddingCache:
    """SQLite-backed embedding cache for committed scenes.

    Production path: ``.planning/intel/scene_embeddings.sqlite``.
    Test path: tmp_path injection (Pitfall 12).

    Schema:
        CREATE TABLE scene_embeddings (
            scene_id              TEXT NOT NULL,
            bge_m3_revision_sha   TEXT NOT NULL,
            embedding             BLOB NOT NULL,    -- float32 unit-norm bytes
            computed_at           TEXT NOT NULL,
            PRIMARY KEY (scene_id, bge_m3_revision_sha)
        )

    The embedder revision is part of the primary key — when the BGE-M3
    revision SHA changes, the cache key misses, the embedding is recomputed,
    and an entry under the new revision is inserted alongside any prior
    revision rows (no destructive overwrite).
    """

    def __init__(self, db_path: Path, embedder: BgeM3Embedder) -> None:
        self.db_path = Path(db_path)
        self.embedder = embedder
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        # Parameterized DDL — no user input flows into the table name. The
        # PRIMARY KEY (scene_id, bge_m3_revision_sha) is the load-bearing
        # invariant; revision-bump invalidation depends on it.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS scene_embeddings ("
            "  scene_id TEXT NOT NULL,"
            "  bge_m3_revision_sha TEXT NOT NULL,"
            "  embedding BLOB NOT NULL,"
            "  computed_at TEXT NOT NULL,"
            "  PRIMARY KEY (scene_id, bge_m3_revision_sha)"
            ")"
        )
        self._conn.commit()

    def compute_transient(self, scene_text: str) -> np.ndarray:
        """Compute embedding WITHOUT persisting. Use for uncommitted candidates.

        Critic-path callers want the candidate's embedding compared against
        prior committed scenes' cached embeddings, but MUST NOT pollute the
        cache with attempts that may be regenerated or hard-blocked. Storing
        attempts caused cosine-1.0 self-match bugs on retry (Phase 7 incident
        2026-04-27): a regen attempt would land in the cache, then the next
        attempt's critic call would receive the stored prior-attempt blob
        from ``get_or_compute`` and compare against itself.
        """
        arr = self.embedder.embed_texts([scene_text])[0].astype(np.float32)
        assert abs(float(np.linalg.norm(arr)) - 1.0) < 1e-3, (
            "BGE-M3 returned non-unit-normalized vector — "
            "Pitfall 3 invariant violated"
        )
        return arr

    def get_or_compute(self, scene_id: str, scene_text: str) -> np.ndarray:
        """Return embedding for ``scene_id``; compute + persist on cache miss.

        ⚠ COMMITTED-SCENE PATH ONLY. Do NOT call from the critic loop or any
        path that handles uncommitted attempts — use ``compute_transient``
        instead. Calling this from the critic stores the attempt's embedding
        permanently and breaks future comparisons (cosine-1.0 self-match on
        retry, observed 2026-04-27).

        Returns a ``(EMBEDDING_DIM,)`` float32 unit-normalized numpy array.
        Cache hit copies the row out so callers can mutate freely without
        affecting cached state.
        """
        revision = self.embedder.revision_sha
        row = self._conn.execute(
            "SELECT embedding FROM scene_embeddings "
            "WHERE scene_id = ? AND bge_m3_revision_sha = ?",
            (scene_id, revision),
        ).fetchone()
        if row is not None:
            arr = np.frombuffer(row[0], dtype=np.float32)
            assert arr.shape == (EMBEDDING_DIM,), (
                f"cached embedding wrong shape: {arr.shape}"
            )
            return arr.copy()

        # Cache miss — compute + persist.
        arr = self.compute_transient(scene_text)
        ts = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO scene_embeddings "
            "(scene_id, bge_m3_revision_sha, embedding, computed_at) "
            "VALUES (?, ?, ?, ?)",
            (scene_id, revision, arr.tobytes(), ts),
        )
        self._conn.commit()
        return arr

    def all_prior(self, prior_scene_ids: list[str]) -> dict[str, np.ndarray]:
        """Bulk-fetch cached embeddings for a list of prior scene_ids.

        Skips ids that are not in the cache (caller must populate via
        ``get_or_compute`` first if they need them). Returns a dict
        ``{scene_id: ndarray}`` with at most one entry per requested id.
        """
        revision = self.embedder.revision_sha
        out: dict[str, np.ndarray] = {}
        if not prior_scene_ids:
            return out
        # SQLite parameterized IN clause — bind one ``?`` per id then a final
        # ``?`` for the revision. No user string interpolation into SQL.
        placeholder = ",".join("?" * len(prior_scene_ids))
        params: tuple[str, ...] = (*prior_scene_ids, revision)
        rows = self._conn.execute(
            f"SELECT scene_id, embedding FROM scene_embeddings "
            f"WHERE scene_id IN ({placeholder}) AND bge_m3_revision_sha = ?",
            params,
        ).fetchall()
        for sid, blob in rows:
            arr = np.frombuffer(blob, dtype=np.float32)
            assert arr.shape == (EMBEDDING_DIM,), (
                f"cached embedding for {sid} has wrong shape: {arr.shape}"
            )
            out[sid] = arr.copy()
        return out


def cosine_similarity_to_prior(
    candidate_embedding: np.ndarray,
    prior_embeddings: dict[str, np.ndarray],
) -> dict[str, float]:
    """Return ``{scene_id: cosine_sim}`` for the candidate against each prior.

    BGE-M3 vectors are unit-normalized so cosine reduces to the plain dot
    product. Norm assertions are kept as Pitfall 3 mitigations: a non-unit
    input would silently scale the similarity, masking a real near-duplicate.
    """
    assert abs(float(np.linalg.norm(candidate_embedding)) - 1.0) < 1e-3, (
        "candidate embedding not unit-normalized — "
        "Pitfall 3 mitigation failed (cosine compute would be wrong)"
    )
    out: dict[str, float] = {}
    for sid, vec in prior_embeddings.items():
        assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-3, (
            f"{sid} embedding not unit-normalized"
        )
        out[sid] = float(np.dot(candidate_embedding, vec))
    return out


def max_cosine(
    candidate_embedding: np.ndarray,
    prior_embeddings: dict[str, np.ndarray],
) -> tuple[str | None, float]:
    """Return ``(scene_id_of_max_match, cosine_value)``.

    Empty ``prior_embeddings`` → ``(None, 0.0)``.
    """
    if not prior_embeddings:
        return None, 0.0
    sims = cosine_similarity_to_prior(candidate_embedding, prior_embeddings)
    sid, sim = max(sims.items(), key=lambda kv: kv[1])
    return sid, sim


__all__ = [
    "SceneEmbeddingCache",
    "cosine_similarity_to_prior",
    "max_cosine",
]
