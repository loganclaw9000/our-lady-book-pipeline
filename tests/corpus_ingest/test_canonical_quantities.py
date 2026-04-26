"""Tests for book_pipeline.corpus_ingest.canonical_quantities (Plan 07-02 PHYSICS-04).

Behavior under test:
  - Test 1: load_canonical_quantities_seed("config/canonical_quantities_seed.yaml")
    returns >=5 CanonicalQuantity objects with the 5 canary IDs.
  - Test 2 (slow): ingest_canonical_quantities writes >=5 rows to the
    'continuity_bible' LanceDB table; each row has rule_type='canonical_quantity'.
  - Test 3 (slow): idempotent re-ingest — running twice yields same row count
    (deterministic chunk_id `f"canonical:{q.id}"`).
  - Test 4: parseable text field — each row's text contains the canonical value.
  - Test 7 (T-07-03 ADVERSARIAL): adversarial id strings rejected at the schema
    layer with ValidationError.
  - Test 8 (T-07-03 round-trip): clean ids interpolate safely into the LanceDB
    chunk_id f-string; payload after the literal "canonical:" prefix matches
    the regex `^[a-z0-9_]+$`.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "config" / "canonical_quantities_seed.yaml"

CANARY_IDS = {
    "andres_age",
    "la_nina_height",
    "santiago_del_paso_scale",
    "cholula_date",
    "cempoala_arrival",
}


class _FakeEmbedder:
    """Deterministic embedder used by fast-path ingest tests; revision_sha is
    not required (canonical_quantities ingest does not call it)."""

    revision_sha = "fake-cb-emb-sha"

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)
        rng = np.random.default_rng(seed=abs(hash(tuple(texts))) % (2**32))
        arr = rng.standard_normal((len(texts), 1024)).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / norms


# --- Test 1: load_canonical_quantities_seed ---------------------------------


def test_load_seed_yaml_returns_at_least_five_canaries() -> None:
    """The hand-seeded YAML contains the 5 D-15 manuscript canaries."""
    from book_pipeline.corpus_ingest.canonical_quantities import (
        load_canonical_quantities_seed,
    )

    quantities = load_canonical_quantities_seed(SEED_PATH)
    assert len(quantities) >= 5
    ids = {q.id for q in quantities}
    assert ids >= CANARY_IDS, f"expected canary ids {CANARY_IDS}; got {ids}"


def test_load_seed_yaml_text_contains_canonical_values() -> None:
    """Each canary's text field embeds the canonical value as parseable string
    (D-23 prereq — drafter substring-matches the value out of the row)."""
    from book_pipeline.corpus_ingest.canonical_quantities import (
        load_canonical_quantities_seed,
    )

    quantities = {
        q.id: q for q in load_canonical_quantities_seed(SEED_PATH)
    }
    # Andrés age = 23
    assert "23" in quantities["andres_age"].text
    # La Niña height = 55ft
    assert "55" in quantities["la_nina_height"].text
    # Santiago del Paso scale = 210
    assert "210" in quantities["santiago_del_paso_scale"].text
    # Cholula date — accept either ISO or human format
    cholula_text = quantities["cholula_date"].text
    assert (
        "October 18" in cholula_text
        or "Oct 18" in cholula_text
        or "1519-10-18" in cholula_text
    )
    # Cempoala arrival
    cempoala_text = quantities["cempoala_arrival"].text
    assert (
        "June 2" in cempoala_text
        or "Jun 2" in cempoala_text
        or "1519-06-02" in cempoala_text
    )


# --- Test 2 + Test 3: ingest writes rows; idempotent re-ingest --------------


def test_ingest_writes_five_rows_to_continuity_bible_table(tmp_path: Path) -> None:
    """Ingest writes 5 rows with rule_type='canonical_quantity' to a fresh
    LanceDB at tmp_path."""
    import lancedb

    from book_pipeline.corpus_ingest.canonical_quantities import (
        ingest_canonical_quantities,
    )

    n_written = ingest_canonical_quantities(
        db_path=tmp_path,
        seed_yaml_path=SEED_PATH,
        embedder=_FakeEmbedder(),
        ingestion_run_id="ing-test-cb-1",
    )
    assert n_written >= 5

    db = lancedb.connect(str(tmp_path))
    table = db.open_table("continuity_bible")
    assert table.count_rows() >= 5

    rows = table.to_arrow().to_pylist()
    for row in rows:
        assert row["rule_type"] == "canonical_quantity"
        assert row["text"]  # non-empty
        assert row["embedding"] is not None
        assert row["chunk_id"].startswith("canonical:")


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    """Re-running ingest does NOT duplicate rows — chunk_id is deterministic."""
    import lancedb

    from book_pipeline.corpus_ingest.canonical_quantities import (
        ingest_canonical_quantities,
    )

    # First ingest.
    ingest_canonical_quantities(
        db_path=tmp_path,
        seed_yaml_path=SEED_PATH,
        embedder=_FakeEmbedder(),
        ingestion_run_id="ing-test-cb-A",
    )
    db = lancedb.connect(str(tmp_path))
    n_after_first = db.open_table("continuity_bible").count_rows()
    assert n_after_first == 5

    # Second ingest — same source SHA / same chunk_ids; row count must not grow.
    ingest_canonical_quantities(
        db_path=tmp_path,
        seed_yaml_path=SEED_PATH,
        embedder=_FakeEmbedder(),
        ingestion_run_id="ing-test-cb-B",
    )
    n_after_second = db.open_table("continuity_bible").count_rows()
    assert n_after_second == 5, (
        f"idempotency broken: {n_after_first} -> {n_after_second}"
    )


def test_ingest_chunk_ids_are_canonical_prefixed(tmp_path: Path) -> None:
    """Each chunk_id is `canonical:{q.id}` with q.id matching ^[a-z0-9_]+$."""
    import lancedb

    from book_pipeline.corpus_ingest.canonical_quantities import (
        ingest_canonical_quantities,
    )

    ingest_canonical_quantities(
        db_path=tmp_path,
        seed_yaml_path=SEED_PATH,
        embedder=_FakeEmbedder(),
        ingestion_run_id="ing-test-cb-1",
    )
    db = lancedb.connect(str(tmp_path))
    rows = db.open_table("continuity_bible").to_arrow().to_pylist()
    expected_chunk_ids = {f"canonical:{cid}" for cid in CANARY_IDS}
    actual_chunk_ids = {r["chunk_id"] for r in rows}
    assert actual_chunk_ids >= expected_chunk_ids, (
        f"missing canonical chunk_ids: {expected_chunk_ids - actual_chunk_ids}"
    )


# --- Test 7: T-07-03 ADVERSARIAL id rejection -------------------------------


_BAD_ID_PARAMS = [
    "x'; DROP TABLE scene_embeddings; --",  # SQL injection
    "X",  # uppercase
    "x.y",  # dot
    "x;y",  # semicolon
    "x y",  # space
    "x-y",  # dash
    "andres age",  # space
    "",  # empty
    "AndresAge",  # uppercase
    "id\nwith\nnewlines",  # newline
    "id with' quote",  # quote
]


@pytest.mark.parametrize("bad_id", _BAD_ID_PARAMS)
def test_canonical_quantity_id_rejects_adversarial_strings(bad_id: str) -> None:
    """T-07-03 mitigation: id is Pydantic-validated against ^[a-z0-9_]+$.

    Adversarial values (including SQL-injection candidates) raise
    ValidationError at the schema layer — the f-string `f"canonical:{q.id}"`
    that flows into LanceDB's WHERE clause is provably safe.
    """
    from book_pipeline.corpus_ingest.canonical_quantities import (
        CanonicalQuantity,
    )

    payload = {
        "id": bad_id,
        "name": "x",
        "canonical_value": "x",
        "units": "x",
        "chapter_scope": "x",
        "text": "x",
        "source": "x",
    }
    with pytest.raises(ValidationError):
        CanonicalQuantity.model_validate(payload)


# --- Test 8: T-07-03 round-trip — clean ids interpolate safely ---------------


@pytest.mark.parametrize(
    "good_id",
    [
        "andres_age",
        "la_nina_height",
        "santiago_del_paso_scale",
        "cholula_date",
        "cempoala_arrival",
        "abc123",
        "x_y_z",
        "0",
        "a",
    ],
)
def test_canonical_quantity_id_clean_ids_interpolate_safely(good_id: str) -> None:
    """Clean ids validate AND f"canonical:{q.id}" payload is regex-safe."""
    from book_pipeline.corpus_ingest.canonical_quantities import (
        CanonicalQuantity,
    )

    q = CanonicalQuantity.model_validate(
        {
            "id": good_id,
            "name": "x",
            "canonical_value": "x",
            "units": "x",
            "chapter_scope": "x",
            "text": "x",
            "source": "x",
        }
    )
    chunk_id = f"canonical:{q.id}"
    payload_after_prefix = chunk_id[len("canonical:"):]
    assert re.fullmatch(r"^[a-z0-9_]+$", payload_after_prefix), (
        f"interpolated payload {payload_after_prefix!r} would break SQL safety"
    )


def test_canonical_quantity_extra_forbid_rejects_unknown_fields() -> None:
    """T-07-10 defense in depth: extra='forbid' on the Pydantic model rejects
    YAML rows with unknown keys."""
    from book_pipeline.corpus_ingest.canonical_quantities import (
        CanonicalQuantity,
    )

    with pytest.raises(ValidationError):
        CanonicalQuantity.model_validate(
            {
                "id": "andres_age",
                "name": "x",
                "canonical_value": "x",
                "units": "x",
                "chapter_scope": "x",
                "text": "x",
                "source": "x",
                "unknown_field": "should be rejected",
            }
        )
