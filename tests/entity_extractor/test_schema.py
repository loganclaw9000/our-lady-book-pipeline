"""Tests for EntityExtractionResponse schema (Plan 04-03 Task 1 — CORPUS-02).

Two tests:
  - test_entity_extraction_response_validates: model_validate round-trip on
    valid + invalid payloads.
  - test_schema_json_schema_is_stable: the JSON Schema carries {entities,
    chapter_num, extraction_timestamp} — snapshot guard so the CLI
    --json-schema contract doesn't drift silently.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from book_pipeline.entity_extractor.schema import EntityExtractionResponse
from book_pipeline.interfaces.types import EntityCard


def test_entity_extraction_response_validates() -> None:
    """A valid payload round-trips cleanly; an invalid one raises."""
    valid = {
        "entities": [
            {
                "entity_name": "Cortes",
                "last_seen_chapter": 1,
                "state": {"current_state": "in Havana"},
                "evidence_spans": [],
                "source_chapter_sha": "deadbeef",
            }
        ],
        "chapter_num": 1,
        "extraction_timestamp": "2026-04-23T00:00:00Z",
    }
    model = EntityExtractionResponse.model_validate(valid)
    assert len(model.entities) == 1
    assert model.entities[0].entity_name == "Cortes"
    assert model.chapter_num == 1
    assert model.extraction_timestamp == "2026-04-23T00:00:00Z"

    # Missing source_chapter_sha on the inner EntityCard is a schema violation
    # (mandatory per CORPUS-02 V-3).
    invalid = {
        "entities": [
            {
                "entity_name": "Cortes",
                "last_seen_chapter": 1,
                "state": {},
                "evidence_spans": [],
                # source_chapter_sha missing
            }
        ],
        "chapter_num": 1,
        "extraction_timestamp": "2026-04-23T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        EntityExtractionResponse.model_validate(invalid)


def test_schema_json_schema_is_stable() -> None:
    """model_json_schema() must carry the 3 top-level keys the CLI validates."""
    schema = EntityExtractionResponse.model_json_schema()
    # Schema is a dict with 'properties' at the top level for Pydantic v2.
    assert "properties" in schema
    props = schema["properties"]
    assert set(props.keys()) == {"entities", "chapter_num", "extraction_timestamp"}
    # EntityCard entry carries the mandatory source_chapter_sha field.
    entity_card_schema = EntityCard.model_json_schema()
    assert "source_chapter_sha" in entity_card_schema["properties"]
    assert "source_chapter_sha" in entity_card_schema["required"]
