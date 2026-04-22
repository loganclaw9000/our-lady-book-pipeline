"""Tests for JsonlEventLogger (plan 01-05, OBS-01).

Covers 13 behaviors specified in 01-05-PLAN.md task 1 <behavior>:

    1.  isinstance(JsonlEventLogger(path=tmp), EventLogger) is True
    2.  emit(event) appends EXACTLY ONE line (line-count delta = 1)
    3.  Appended line is valid JSON with all required Event fields
    4.  Event.model_validate_json(last_line) round-trips to same event_id/model/role
    5.  Two emits produce exactly 2 lines
    6.  Existing content preserved when logger re-instantiated (append mode)
    7.  fsync is called at least once per emit
    8.  Two loggers pointing at the same path do NOT duplicate lines (handler idempotency)
    9.  hash_text determinism + length 16
    10. event_id produces 16 hex chars
    11. Optional fields (mode, checkpoint_sha, rubric_version) round-trip as None
    12. schema_version is "1.0" on every emitted line
    13. checkpoint_sha round-trips verbatim when populated (load-bearing for drafter-role smoke)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from book_pipeline.interfaces import Event, EventLogger
from book_pipeline.observability import JsonlEventLogger, event_id, hash_text


def _make_event(
    role: str = "smoke_test",
    checkpoint_sha: str | None = None,
    mode: str | None = None,
) -> Event:
    return Event(
        event_id=event_id("2026-04-21T00:00:00Z", role, "test", "p"),
        ts_iso="2026-04-21T00:00:00Z",
        role=role,
        model="test-model",
        prompt_hash=hash_text("prompt"),
        input_tokens=10,
        output_tokens=20,
        latency_ms=100,
        output_hash=hash_text("out"),
        mode=mode,
        checkpoint_sha=checkpoint_sha,
    )


# 1
def test_isinstance_protocol(tmp_path: Path) -> None:
    assert isinstance(JsonlEventLogger(path=tmp_path / "e.jsonl"), EventLogger)


# 2 + 3
def test_emit_appends_one_line_with_required_fields(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    JsonlEventLogger(path=p).emit(_make_event())
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["role"] == "smoke_test"
    assert obj["schema_version"] == "1.0"


# 3 (explicit full-field coverage)
def test_all_required_fields_in_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    JsonlEventLogger(path=p).emit(_make_event())
    obj = json.loads(p.read_text().strip())
    for f in (
        "schema_version",
        "event_id",
        "ts_iso",
        "role",
        "model",
        "prompt_hash",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "output_hash",
    ):
        assert f in obj, f"missing field: {f}"


# 4
def test_roundtrip_via_pydantic(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    original = _make_event()
    JsonlEventLogger(path=p).emit(original)
    last = p.read_text().strip().split("\n")[-1]
    parsed = Event.model_validate_json(last)
    assert parsed.event_id == original.event_id
    assert parsed.role == original.role
    assert parsed.model == original.model


# 5
def test_two_emits_two_lines(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    logger = JsonlEventLogger(path=p)
    logger.emit(_make_event("a"))
    logger.emit(_make_event("b"))
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2


# 6
def test_append_preserves_existing(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text('{"schema_version":"1.0","pre":"existing"}\n')
    JsonlEventLogger(path=p).emit(_make_event())
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["pre"] == "existing"


# 7
def test_fsync_called(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    logger = JsonlEventLogger(path=p)
    with patch("book_pipeline.observability.event_logger.os.fsync") as m:
        logger.emit(_make_event())
    assert m.call_count >= 1


# 8 — handler idempotency (CRITICAL per success_criteria)
def test_handler_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    l1 = JsonlEventLogger(path=p)
    l2 = JsonlEventLogger(path=p)
    l1.emit(_make_event("a"))
    l2.emit(_make_event("b"))
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    # EXACTLY 2 lines, not 3 and not 4 — proves FileHandler is shared per-path
    assert len(lines) == 2


# 9
def test_hash_text_determinism() -> None:
    assert hash_text("abc") == hash_text("abc")
    assert hash_text("abc") != hash_text("abd")
    assert len(hash_text("abc")) == 16


# 10
def test_event_id_shape() -> None:
    eid = event_id("2026-04-21T00:00:00Z", "drafter", "test", "p1")
    assert len(eid) == 16


# 11
def test_optional_fields_roundtrip_as_none(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    JsonlEventLogger(path=p).emit(_make_event())
    parsed = Event.model_validate_json(p.read_text().strip())
    assert parsed.mode is None
    assert parsed.checkpoint_sha is None
    assert parsed.rubric_version is None
    assert parsed.cached_tokens == 0


# 12
def test_schema_version_frozen_1_0(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    JsonlEventLogger(path=p).emit(_make_event())
    assert json.loads(p.read_text().strip())["schema_version"] == "1.0"


# 13 — load-bearing for task-2 drafter-role smoke
def test_checkpoint_sha_roundtrips_when_populated(tmp_path: Path) -> None:
    """Task-2 drafter-role smoke depends on checkpoint_sha surviving the
    serialize -> write -> read -> parse round-trip. Proves the schema path."""
    p = tmp_path / "events.jsonl"
    JsonlEventLogger(path=p).emit(
        _make_event(role="drafter", mode="A", checkpoint_sha="TBD-phase3")
    )
    parsed = Event.model_validate_json(p.read_text().strip())
    assert parsed.role == "drafter"
    assert parsed.mode == "A"
    assert parsed.checkpoint_sha == "TBD-phase3"
