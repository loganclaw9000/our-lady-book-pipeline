"""Tests for book_pipeline.physics.canon_bible (Plan 07-03 Task 1).

Tests 11-13 from PLAN.md <behavior>:
- 11: build_canon_bible_view returns CanonBibleView with .get_canonical_quantity(name)
- 12: CanonBibleView.format_stamp() returns top-of-prompt-ready string
- 13: CanonBibleView.iter_canonical_quantities() returns the live list (used by quantity gate)
"""
from __future__ import annotations

from book_pipeline.interfaces.types import RetrievalHit, RetrievalResult
from book_pipeline.physics.canon_bible import (
    CanonBibleView,
    CanonicalQuantityRow,
    build_canon_bible_view,
)
from book_pipeline.physics.locks import PovLock
from book_pipeline.physics.schema import Perspective


def _make_cb01_retrieval() -> RetrievalResult:
    """5 manuscript-canary CB-01 hits matching Plan 07-02 ingest format."""
    hits = [
        RetrievalHit(
            text="Andres age: 23 (ch01-ch14). Drift evidence: ch02:26 -> ch04:23 (non-monotonic).",
            source_path="config/canonical_quantities_seed.yaml",
            chunk_id="canonical:andres_age",
            score=0.9,
            metadata={},
        ),
        RetrievalHit(
            text="La Nina height: 55 ft apex deck (ch01-ch14). Drift evidence: 50ft -> 60ft -> 55ft -> 42ft.",
            source_path="config/canonical_quantities_seed.yaml",
            chunk_id="canonical:la_nina_height",
            score=0.88,
            metadata={},
        ),
        RetrievalHit(
            text="Santiago del Paso scale: 210 ft apex deterrent (ch01-ch14). Drift: 210/300/11-stories.",
            source_path="config/canonical_quantities_seed.yaml",
            chunk_id="canonical:santiago_del_paso_scale",
            score=0.85,
            metadata={},
        ),
        RetrievalHit(
            text="Cholula date: October 18, 1519 (ch04-ch07). Drift: stub said Oct 30 vs canon Oct 18.",
            source_path="config/canonical_quantities_seed.yaml",
            chunk_id="canonical:cholula_date",
            score=0.82,
            metadata={},
        ),
        RetrievalHit(
            text="Cempoala arrival: June 2, 1519 (ch03 sole arrival).",
            source_path="config/canonical_quantities_seed.yaml",
            chunk_id="canonical:cempoala_arrival",
            score=0.80,
            metadata={},
        ),
    ]
    return RetrievalResult(
        retriever_name="continuity_bible",
        hits=hits,
        bytes_used=512,
        query_fingerprint="qfp-cb01",
    )


# --- Test 11: get_canonical_quantity returns row text or None ---

def test_get_canonical_quantity_returns_row_or_none() -> None:
    view = build_canon_bible_view(
        cb01_retrieval=_make_cb01_retrieval(),
        pov_locks={},
    )
    # Hit on the keyword
    row = view.get_canonical_quantity("andres")
    assert row is not None
    assert row.id == "andres_age"
    assert "23" in row.text

    # Miss returns None
    assert view.get_canonical_quantity("nonexistent_entity_xyz") is None


def test_build_canon_bible_view_handles_none_retrieval() -> None:
    """No CB-01 axis at all -> empty rowset, no crash."""
    view = build_canon_bible_view(cb01_retrieval=None, pov_locks={})
    assert list(view.iter_canonical_quantities()) == []
    assert view.format_stamp() == ""


# --- Test 12: format_stamp returns top-of-prompt-ready string ---

def test_format_stamp_emits_canonical_prefix() -> None:
    view = build_canon_bible_view(
        cb01_retrieval=_make_cb01_retrieval(),
        pov_locks={},
    )
    stamp = view.format_stamp()
    assert stamp.startswith("CANONICAL:")
    # All 5 canaries should appear in the stamp head
    assert "Andres" in stamp
    assert "La Nina" in stamp
    assert "Cholula" in stamp


def test_format_stamp_empty_for_no_rows() -> None:
    view = CanonBibleView(canonical_quantities=[], pov_locks={})
    assert view.format_stamp() == ""


# --- Test 13: iter_canonical_quantities exposes live rowset ---

def test_iter_canonical_quantities_returns_all_rows() -> None:
    view = build_canon_bible_view(
        cb01_retrieval=_make_cb01_retrieval(),
        pov_locks={},
    )
    rows = list(view.iter_canonical_quantities())
    assert len(rows) == 5
    ids = {r.id for r in rows}
    assert ids == {
        "andres_age",
        "la_nina_height",
        "santiago_del_paso_scale",
        "cholula_date",
        "cempoala_arrival",
    }


def test_iter_canonical_quantities_includes_synthetic_long_tail_row() -> None:
    """Inject a 6th synthetic row directly — iter_ exposes it without code change."""
    rows = [
        CanonicalQuantityRow(
            id="andres_age",
            text="Andres: 23 (ch01-ch14).",
            name="Andres",
        ),
        CanonicalQuantityRow(
            id="tlaxcala_population",
            text="Tlaxcala: ~150,000 inhabitants (ch07).",
            name="Tlaxcala",
        ),
    ]
    view = CanonBibleView(canonical_quantities=rows, pov_locks={})
    out = list(view.iter_canonical_quantities())
    assert len(out) == 2
    assert {r.id for r in out} == {"andres_age", "tlaxcala_population"}


def test_get_pov_lock_returns_lock_or_none() -> None:
    lock = PovLock(
        character="Itzcoatl",
        perspective=Perspective.FIRST_PERSON,
        active_from_chapter=15,
        rationale="OQ-01(a) RESOLVED 2026-04-25 — D-16 + D-21 forward-only.",
    )
    view = CanonBibleView(canonical_quantities=[], pov_locks={"itzcoatl": lock})
    assert view.get_pov_lock("Itzcoatl") is lock
    assert view.get_pov_lock("itzcoatl") is lock  # case-insensitive
    assert view.get_pov_lock("Andres") is None


def test_canon_bible_view_does_not_use_module_lru_cache() -> None:
    """Pitfall 11: module-scope lru_cache would break per-bundle state.

    Acceptance: source has zero `lru_cache` references. We assert the view
    is a per-instance composition (two distinct views = two distinct rowsets).
    """
    rows_a = [CanonicalQuantityRow(id="a", text="A: 1.", name="A")]
    rows_b = [CanonicalQuantityRow(id="b", text="B: 2.", name="B")]
    view_a = CanonBibleView(canonical_quantities=rows_a, pov_locks={})
    view_b = CanonBibleView(canonical_quantities=rows_b, pov_locks={})
    assert list(view_a.iter_canonical_quantities()) != list(view_b.iter_canonical_quantities())
