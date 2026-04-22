"""Tests for book_pipeline.critic.audit (Plan 03-05 Task 1).

write_audit_record persists per-call CRIT-04 audit records to
runs/critic_audit/{scene_id}_{attempt:02d}_{timestamp}.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


def _sample_record() -> dict:
    return {
        "event_id": "dead" * 4,
        "scene_id": "ch01_sc01",
        "attempt_number": 1,
        "timestamp_iso": "2026-04-22T14:30:05.123456Z",
        "rubric_version": "v1",
        "model_id": "claude-opus-4-7",
        "opus_model_id_response": "claude-opus-4-7",
        "caching_cache_control_applied": True,
        "cached_input_tokens": 3000,
        "system_prompt_sha": "cafe" * 4,
        "user_prompt_sha": "beef" * 4,
        "context_pack_fingerprint": "abcd1234",
        "raw_anthropic_response": {"id": "msg_01", "type": "message"},
        "parsed_critic_response": {"pass_per_axis": {}, "overall_pass": True},
    }


def test_write_audit_record_writes_valid_json_with_expected_filename(tmp_path: Path) -> None:
    """Test 1a: write_audit_record writes indented JSON and filename matches
    {scene_id}_{attempt:02d}_{timestamp}.json shape."""
    from book_pipeline.critic.audit import write_audit_record

    record = _sample_record()
    path = write_audit_record(tmp_path, "ch01_sc01", 1, record)

    assert path.exists()
    assert path.parent == tmp_path
    # Filename shape: ch01_sc01_01_<timestamp>.json
    name = path.name
    assert name.startswith("ch01_sc01_01_")
    assert name.endswith(".json")
    # Timestamp part (between "_01_" and ".json") should match %Y%m%dT%H%M%S%f — 21 chars
    ts_part = name[len("ch01_sc01_01_") : -len(".json")]
    assert len(ts_part) == 21, f"Expected 21-char timestamp, got {ts_part!r}"

    # Content is valid JSON, indented (has newlines)
    text = path.read_text(encoding="utf-8")
    assert "\n" in text, "Expected indented JSON (indent=2)"
    loaded = json.loads(text)
    assert loaded == record


def test_write_audit_record_rerun_does_not_overwrite(tmp_path: Path) -> None:
    """Test 1b: Re-running with same scene_id+attempt creates a NEW file with a
    distinct timestamp — never overwrites."""
    from book_pipeline.critic.audit import write_audit_record

    record = _sample_record()
    path1 = write_audit_record(tmp_path, "ch01_sc01", 1, record)
    # Sleep enough for microsecond timestamp to tick
    time.sleep(0.002)
    path2 = write_audit_record(tmp_path, "ch01_sc01", 1, record)

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()


def test_write_audit_record_creates_missing_dir(tmp_path: Path) -> None:
    """Test 2: write_audit_record on a non-existent audit_dir creates the dir."""
    from book_pipeline.critic.audit import write_audit_record

    nested = tmp_path / "does" / "not" / "exist" / "critic_audit"
    assert not nested.exists()

    path = write_audit_record(nested, "ch02_sc03", 2, _sample_record())
    assert nested.exists()
    assert path.parent == nested
    assert path.name.startswith("ch02_sc03_02_")
