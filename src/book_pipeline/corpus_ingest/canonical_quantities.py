"""Canonical-quantity ingest for the CB-01 retriever (Plan 07-02 PHYSICS-04 / D-22).

Reads ``config/canonical_quantities_seed.yaml``, embeds each canonical row's
text via a BgeM3Embedder, writes to the 'continuity_bible' LanceDB table with
``rule_type='canonical_quantity'`` (D-22 — additive non-column extension; the
'continuity_bible' axis is a NEW VALUE for the existing rule_type column, not
a new schema column).

OQ-05 (c) RESOLVED 2026-04-25: hybrid hand-seed (5 canaries operator-confirmed
via the seed YAML) + extraction-agent for the long tail (deferred to v1.1).
The 5 hand-seeded values ARE the canonical truth as of phase planning; any
subsequent canon update flows through a separate `canon update` workflow that
re-ingests + alerts on prose drift — NOT through ad-hoc value-tuning here.

Idempotent re-ingest: chunk_id is deterministic from ``q.id`` so repeat runs
produce zero duplicate rows. Rows with the same chunk_ids are deleted before
insert.

T-07-03 mitigation: ``CanonicalQuantity.id`` is Pydantic-validated against
the regex ``^[a-z0-9_]+$`` (alphanumeric + underscore only). Adversarial
values like ``"x'; DROP TABLE scene_embeddings; --"`` are rejected at the
schema layer, so the downstream f-string ``f"canonical:{q.id}"`` is provably
safe to interpolate into a LanceDB delete WHERE clause. Defense in depth:
the field carries BOTH ``Field(pattern=...)`` AND a ``field_validator`` that
re-checks the same regex with an explicit error message.

T-07-10 mitigation: ``yaml.safe_load`` only — no ``yaml.load``. Plus the
``CanonicalQuantity`` model uses ``extra="forbid"`` so unknown YAML keys
fail loudly.

T-07-05 mitigation: writes to the dedicated 'continuity_bible' LanceDB table
which uses the existing CHUNK_SCHEMA (D-22 — no new column). No schema
migration needed; ``open_or_create_table`` enforces schema invariants.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import lancedb
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from book_pipeline.rag.embedding import BgeM3Embedder
from book_pipeline.rag.lance_schema import open_or_create_table

_LOG = logging.getLogger(__name__)

_CANONICAL_QUANTITY_ID_RE: str = r"^[a-z0-9_]+$"
_CANONICAL_QUANTITY_ID_PATTERN = re.compile(_CANONICAL_QUANTITY_ID_RE)


class CanonicalQuantity(BaseModel):
    """One hand-seeded canonical quantity (Plan 07-02 PHYSICS-04 / D-22).

    Each instance becomes ONE LanceDB row in the 'continuity_bible' table.
    The ``id`` field is regex-restricted to ``^[a-z0-9_]+$`` (T-07-03
    mitigation) so the deterministic chunk_id ``f"canonical:{q.id}"`` is
    provably safe for f-string interpolation into a SQL-style WHERE clause.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=_CANONICAL_QUANTITY_ID_RE, min_length=1)
    name: str = Field(min_length=1)
    canonical_value: str = Field(min_length=1)
    units: str = Field(min_length=1)
    chapter_scope: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _id_is_safe(cls, v: str) -> str:
        # Defense in depth — Field(pattern=...) already enforces this regex,
        # but an explicit validator (a) keeps the T-07-03 intent visible to
        # readers, and (b) hardens against future Field-level regression
        # (e.g., if someone widens the pattern).
        if not _CANONICAL_QUANTITY_ID_PATTERN.fullmatch(v):
            raise ValueError(
                f"CanonicalQuantity.id must match {_CANONICAL_QUANTITY_ID_RE!r}; "
                f"got {v!r} (T-07-03 mitigation)"
            )
        return v


def load_canonical_quantities_seed(
    yaml_path: str | Path,
) -> list[CanonicalQuantity]:
    """Load + validate the canonical-quantity seed YAML.

    Args:
        yaml_path: Path to ``config/canonical_quantities_seed.yaml`` (or any
            equivalent test fixture).

    Returns:
        List of validated ``CanonicalQuantity`` objects. Empty list if the
        file's ``quantities:`` key is missing or empty.

    Raises:
        pydantic.ValidationError: if any entry violates the schema (incl.
            T-07-03 id regex; T-07-10 unknown-key extra="forbid"; missing
            required fields).
    """
    path = Path(yaml_path)
    with path.open(encoding="utf-8") as f:
        # T-07-10: yaml.safe_load only. yaml.load is forbidden.
        raw = yaml.safe_load(f) or {}
    return [
        CanonicalQuantity.model_validate(q)
        for q in raw.get("quantities", [])
    ]


def ingest_canonical_quantities(
    *,
    db_path: Path,
    seed_yaml_path: Path,
    embedder: BgeM3Embedder,
    ingestion_run_id: str,
) -> int:
    """Ingest seed YAML rows into the 'continuity_bible' LanceDB table.

    Returns the number of rows written. Idempotent: chunk_id is deterministic
    ``f"canonical:{q.id}"`` and ``q.id`` is regex-validated (T-07-03), so
    re-running this function with the same seed YAML yields the same row
    count (existing rows with the same chunk_ids are deleted before insert).

    Args:
        db_path: LanceDB directory (created if absent).
        seed_yaml_path: ``config/canonical_quantities_seed.yaml`` or test
            fixture path.
        embedder: shared BgeM3Embedder instance (per STACK.md — one per
            process; do NOT load a second copy here).
        ingestion_run_id: stamped onto each row (matches Plan 02 corpus_ingest
            convention).
    """
    quantities = load_canonical_quantities_seed(seed_yaml_path)
    if not quantities:
        return 0

    db_path = Path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)

    # ``open_or_create_table`` uses the shared CHUNK_SCHEMA (D-22 — no new
    # column; rule_type='canonical_quantity' is a new VALUE only).
    table = open_or_create_table(db_path, "continuity_bible")

    texts = [q.text for q in quantities]
    embeddings = embedder.embed_texts(texts)

    rows: list[dict[str, Any]] = []
    for q, emb in zip(quantities, embeddings, strict=True):
        # Safe: q.id passed `^[a-z0-9_]+$` regex via CanonicalQuantity validator.
        chunk_id = f"canonical:{q.id}"
        emb_list = emb.tolist() if hasattr(emb, "tolist") else list(emb)
        rows.append(
            {
                "chunk_id": chunk_id,
                "text": q.text,
                "source_file": "config/canonical_quantities_seed.yaml",
                "heading_path": f"Canonical Quantity: {q.id}",
                "rule_type": "canonical_quantity",
                "ingestion_run_id": ingestion_run_id,
                # Canonical quantities are scope-aware via their ``text``
                # field; no per-row chapter column populated.
                "chapter": None,
                # Plan 05-03: corpus_ingest writes None for source_chapter_sha
                # — only entity_state's reindex stamps a real SHA.
                "source_chapter_sha": None,
                "embedding": emb_list,
            }
        )

    # Idempotent delete-before-insert. T-07-03: chunk_ids are derived from
    # regex-validated q.id values; the f-string interpolation is provably
    # safe (alphanumeric + underscore only — no quotes, no parens, no
    # whitespace, no SQL meta-characters can land in chunk_ids).
    chunk_ids = [r["chunk_id"] for r in rows]
    placeholder = ", ".join(f"'{cid}'" for cid in chunk_ids)
    try:
        table.delete(f"chunk_id IN ({placeholder})")
    except (RuntimeError, ValueError) as exc:
        # First-ingest into a fresh table can have nothing to delete; some
        # LanceDB error paths surface as RuntimeError, some as ValueError.
        # We intentionally do NOT swallow other exception classes (no bare
        # `except Exception: pass`). Real errors propagate.
        _LOG.debug(
            "continuity_bible delete pre-add no-op (%s): %r",
            type(exc).__name__,
            exc,
        )
    table.add(rows)
    return len(rows)


__all__ = [
    "CanonicalQuantity",
    "ingest_canonical_quantities",
    "load_canonical_quantities_seed",
]
