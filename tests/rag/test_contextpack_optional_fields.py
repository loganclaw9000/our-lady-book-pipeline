"""Tests for Plan 02-05 OPTIONAL additions to ContextPack + new ConflictReport model.

Per Phase 1 freeze (01-02-SUMMARY + 02-CONTEXT.md): later phases may add OPTIONAL
fields to Pydantic contracts, never rename or remove. This plan adds:
  - ContextPack.conflicts: list[ConflictReport] | None = None
  - ContextPack.ingestion_run_id: str | None = None
  - New top-level ConflictReport model.
"""

from __future__ import annotations


def test_conflict_report_instantiable_with_required_fields_only() -> None:
    """ConflictReport's minimum required surface works (no severity default drift)."""
    from book_pipeline.interfaces.types import ConflictReport

    cr = ConflictReport(
        entity="Andrés",
        dimension="location",
        values_by_retriever={"historical": "Cempoala", "entity_state": "Cerro Gordo"},
        source_chunk_ids_by_retriever={"historical": ["h1"], "entity_state": ["e1"]},
    )
    assert cr.entity == "Andrés"
    assert cr.dimension == "location"
    assert cr.values_by_retriever == {
        "historical": "Cempoala",
        "entity_state": "Cerro Gordo",
    }
    assert cr.severity == "mid"  # default


def test_context_pack_conflicts_default_is_none() -> None:
    """ContextPack.conflicts defaults to None (OPTIONAL addition)."""
    from book_pipeline.interfaces.types import ContextPack, SceneRequest

    req = SceneRequest(
        chapter=1,
        scene_index=1,
        pov="Andrés",
        date_iso="1519-03-25",
        location="Potonchán",
        beat_function="inciting",
    )
    cp = ContextPack(
        scene_request=req,
        retrievals={},
        total_bytes=0,
        fingerprint="deadbeef",
    )
    assert cp.conflicts is None
    assert cp.ingestion_run_id is None


def test_context_pack_accepts_old_schema_json_roundtrip() -> None:
    """Old-schema JSON (no conflicts, no ingestion_run_id) round-trips cleanly.

    Regression guard: adding fields must NOT break existing JSON payloads on disk.
    """
    from book_pipeline.interfaces.types import ContextPack

    old_schema_payload = {
        "scene_request": {
            "chapter": 1,
            "scene_index": 1,
            "pov": "Andrés",
            "date_iso": "1519-03-25",
            "location": "Potonchán",
            "beat_function": "inciting",
        },
        "retrievals": {},
        "total_bytes": 0,
        "assembly_strategy": "round_robin",
        "fingerprint": "cafebabe",
    }
    cp = ContextPack.model_validate(old_schema_payload)
    dumped = cp.model_dump(mode="json")
    assert dumped["fingerprint"] == "cafebabe"
    assert dumped["conflicts"] is None
    assert dumped["ingestion_run_id"] is None
    # Round-trip: parse the dump back.
    cp2 = ContextPack.model_validate(dumped)
    assert cp2.fingerprint == "cafebabe"


def test_context_pack_accepts_conflicts_and_ingestion_run_id() -> None:
    """New fields populate cleanly when provided."""
    from book_pipeline.interfaces.types import (
        ConflictReport,
        ContextPack,
        SceneRequest,
    )

    req = SceneRequest(
        chapter=1,
        scene_index=1,
        pov="Andrés",
        date_iso="1519-03-25",
        location="Potonchán",
        beat_function="inciting",
    )
    conflict = ConflictReport(
        entity="Andrés",
        dimension="location",
        values_by_retriever={"historical": "Cempoala", "entity_state": "Cerro Gordo"},
        source_chunk_ids_by_retriever={"historical": ["h1"], "entity_state": ["e1"]},
    )
    cp = ContextPack(
        scene_request=req,
        retrievals={},
        total_bytes=0,
        fingerprint="abc",
        conflicts=[conflict],
        ingestion_run_id="ing-test-1",
    )
    assert cp.conflicts is not None
    assert len(cp.conflicts) == 1
    assert cp.conflicts[0].entity == "Andrés"
    assert cp.ingestion_run_id == "ing-test-1"


def test_conflict_report_exported_from_interfaces() -> None:
    """ConflictReport reachable via the top-level interfaces package (not just .types)."""
    from book_pipeline.interfaces import ConflictReport as CR1
    from book_pipeline.interfaces.types import ConflictReport as CR2

    assert CR1 is CR2
