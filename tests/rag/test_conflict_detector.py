"""Tests for book_pipeline.rag.conflict_detector.detect_conflicts.

Covers the hybrid entity-list + regex detection (W-1 revision). The kernel
module does NOT import book_specifics — tests import the W-1 canonical Nahuatl
names from book_specifics.nahuatl_entities and pass them in explicitly.
"""

from __future__ import annotations

from book_pipeline.interfaces.types import RetrievalHit, RetrievalResult


def _make_result(name: str, hits: list[tuple[str, str]]) -> RetrievalResult:
    """Build a RetrievalResult from [(chunk_id, text), ...]."""
    return RetrievalResult(
        retriever_name=name,
        hits=[
            RetrievalHit(
                text=text,
                source_path=f"fixture_{name}.md",
                chunk_id=cid,
                score=1.0,
                metadata={},
            )
            for (cid, text) in hits
        ],
        bytes_used=sum(len(t.encode("utf-8")) for (_, t) in hits),
        query_fingerprint="q-fp",
    )


def _nahuatl_entity_list() -> set[str]:
    """Tests are allowed to import book_specifics (only the kernel is forbidden).

    Build a flattened set of canonical + variant names for the W-1 tests.
    """
    from book_pipeline.book_specifics.nahuatl_entities import NAHUATL_CANONICAL_NAMES

    names: set[str] = set()
    names.update(NAHUATL_CANONICAL_NAMES.keys())
    for variants in NAHUATL_CANONICAL_NAMES.values():
        names.update(variants)
    return names


def test_detect_conflicts_empty_input_returns_empty_list() -> None:
    """Empty input → empty list (deterministic, no spurious conflicts)."""
    from book_pipeline.rag.conflict_detector import detect_conflicts

    out = detect_conflicts({})
    assert out == []


def test_detect_conflicts_location_disagreement_produces_report() -> None:
    """Test 3: two retrievers contradict on a location — exactly one ConflictReport."""
    from book_pipeline.rag.conflict_detector import detect_conflicts

    retrievals = {
        "historical": _make_result(
            "historical", [("h1", "Andrés is at Cempoala on 1519-06-02.")]
        ),
        "entity_state": _make_result(
            "entity_state", [("e1", "Andrés is at Cerro Gordo on 1519-06-02.")]
        ),
    }
    conflicts = detect_conflicts(retrievals)
    location_conflicts = [c for c in conflicts if c.dimension == "location"]
    # Should fire for Andrés / location.
    andres_locs = [c for c in location_conflicts if c.entity == "Andrés"]
    assert len(andres_locs) == 1, f"expected 1 Andrés-location conflict; got {conflicts}"
    c = andres_locs[0]
    assert set(c.values_by_retriever.keys()) == {"historical", "entity_state"}
    vals = set(c.values_by_retriever.values())
    # Some parse variation is tolerable — we require each retriever's city token present somewhere.
    joined = " ".join(vals)
    assert "Cempoala" in joined
    assert "Cerro Gordo" in joined
    assert c.source_chunk_ids_by_retriever["historical"] == ["h1"]
    assert c.source_chunk_ids_by_retriever["entity_state"] == ["e1"]


def test_detect_conflicts_no_overlap_yields_no_conflicts() -> None:
    """Test 4: 5 retrievers with no overlapping entities → 0 conflicts."""
    from book_pipeline.rag.conflict_detector import detect_conflicts

    retrievals = {
        "historical": _make_result("historical", [("h1", "The Spaniards marched inland.")]),
        "metaphysics": _make_result(
            "metaphysics", [("m1", "A rule of the engine is invariant under rotation.")]
        ),
        "entity_state": _make_result("entity_state", [("e1", "No named entity here.")]),
        "arc_position": _make_result("arc_position", [("a1", "The beat opens on dawn.")]),
        "negative_constraint": _make_result(
            "negative_constraint", [("n1", "Avoid anachronistic gunpowder references.")]
        ),
    }
    conflicts = detect_conflicts(retrievals)
    assert conflicts == []


def test_detect_conflicts_w1_nahuatl_entity_list_catches_motecuhzoma() -> None:
    """Test 5 (W-1): entity_list catches Motecuhzoma across 2 retrievers w/ different locations."""
    from book_pipeline.rag.conflict_detector import detect_conflicts

    retrievals = {
        "historical": _make_result(
            "historical",
            [("h1", "Motecuhzoma in Tenochtitlan received the delegation.")],
        ),
        "arc_position": _make_result(
            "arc_position",
            [("a1", "Motecuhzoma is at Cholula during the reckoning.")],
        ),
    }
    entity_list = _nahuatl_entity_list()

    with_list = detect_conflicts(retrievals, entity_list=entity_list)
    motecuh = [c for c in with_list if c.entity == "Motecuhzoma"]
    assert len(motecuh) >= 1, (
        f"entity_list path failed to detect Motecuhzoma conflict; got {with_list}"
    )
    c = motecuh[0]
    assert c.dimension == "location"
    joined = " ".join(c.values_by_retriever.values())
    assert "Tenochtitlan" in joined
    assert "Cholula" in joined


def test_detect_conflicts_w1_malintzin_date_disagreement() -> None:
    """Test 6 (W-1): entity_list catches Malintzin across retrievers with different dates."""
    from book_pipeline.rag.conflict_detector import detect_conflicts

    retrievals = {
        "historical": _make_result(
            "historical",
            [("h1", "Malintzin appeared in 1519 at the Tabascan gift.")],
        ),
        "entity_state": _make_result(
            "entity_state",
            [("e1", "Malintzin appeared in 1521 — according to misaligned notes.")],
        ),
    }
    entity_list = _nahuatl_entity_list()
    # entity_list contains Malintzin (as canonical), Malinche, Doña Marina.
    assert "Malintzin" in entity_list

    conflicts = detect_conflicts(retrievals, entity_list=entity_list)
    malintzin_date_conflicts = [
        c for c in conflicts if c.entity == "Malintzin" and c.dimension == "date"
    ]
    assert len(malintzin_date_conflicts) >= 1, (
        f"W-1 entity_list date-conflict detection failed; got {conflicts}"
    )
    c = malintzin_date_conflicts[0]
    joined = " ".join(c.values_by_retriever.values())
    assert "1519" in joined
    assert "1521" in joined


def test_detect_conflicts_deterministic_sorted_output() -> None:
    """Same input → same output (ordered by entity, dimension)."""
    from book_pipeline.rag.conflict_detector import detect_conflicts

    retrievals = {
        "historical": _make_result(
            "historical", [("h1", "Andrés is at Cempoala; Juan has the sword.")]
        ),
        "entity_state": _make_result(
            "entity_state",
            [("e1", "Andrés is at Cerro Gordo; Juan has the musket.")],
        ),
    }
    out1 = detect_conflicts(retrievals)
    out2 = detect_conflicts(retrievals)
    assert [(c.entity, c.dimension) for c in out1] == [
        (c.entity, c.dimension) for c in out2
    ]
    # Sorted by (entity, dimension).
    keys = [(c.entity, c.dimension) for c in out1]
    assert keys == sorted(keys)
