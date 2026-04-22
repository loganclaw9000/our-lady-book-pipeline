"""Tests for `book-pipeline smoke-event` CLI (plan 01-05 task 2).

Covers the exit-criterion smoke path AND the phase-goal drafter-role
voice-pin SHA wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from book_pipeline.cli.main import main
from book_pipeline.config.voice_pin import VoicePinConfig
from book_pipeline.interfaces.types import Event


def test_smoke_event_emits_and_roundtrips(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "events.jsonl"
    rc = main(["smoke-event", "--path", str(target)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "last event_id" in out
    assert target.exists()
    lines = [ln for ln in target.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["role"] == "smoke_test"
    assert obj["schema_version"] == "1.0"
    assert obj["extra"]["purpose"] == "phase1_exit_criterion"
    # Pydantic round-trip must succeed (no schema drift).
    Event.model_validate_json(lines[0])


def test_smoke_event_appends_not_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "events.jsonl"
    assert main(["smoke-event", "--path", str(target)]) == 0
    assert main(["smoke-event", "--path", str(target)]) == 0
    lines = [ln for ln in target.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2


def test_smoke_event_listed_in_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "smoke-event" in out


def test_smoke_event_drafter_role_wires_voice_pin_sha(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Phase goal: 'voice-pin SHA verification wired'.

    Exercises the schema path:
        config/voice_pin.yaml -> VoicePinConfig().voice_pin.checkpoint_sha
        -> Event.checkpoint_sha -> JSONL line -> Event.model_validate_json.

    Phase 3 DRAFT-01 adds the real hash-bytes-vs-weights verification;
    Phase 1 only proves the wiring and fidelity of the SHA through the
    observability pipeline.
    """
    target = tmp_path / "events.jsonl"
    rc = main(["smoke-event", "--role", "drafter", "--path", str(target)])
    assert rc == 0, capsys.readouterr().err

    # Last JSONL line must be the drafter Event with a populated checkpoint_sha.
    lines = [ln for ln in target.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["role"] == "drafter"
    assert obj["mode"] == "A"
    assert obj["checkpoint_sha"] is not None
    assert obj["checkpoint_sha"] != ""

    # The emitted checkpoint_sha must equal voice_pin.yaml's value
    # (Phase 1 placeholder is "TBD-phase3"; Phase 3 replaces with real SHA).
    expected_sha = VoicePinConfig().voice_pin.checkpoint_sha
    assert obj["checkpoint_sha"] == expected_sha

    # Round-trip via Pydantic for schema fidelity.
    parsed = Event.model_validate_json(lines[0])
    assert parsed.checkpoint_sha == expected_sha
    assert parsed.mode == "A"
    assert parsed.role == "drafter"

    # CLI output must surface the pin fields for operator visibility.
    out = capsys.readouterr().out
    assert "checkpoint_sha" in out
    assert expected_sha in out


def test_smoke_event_drafter_does_not_clobber_smoke_lines(tmp_path: Path) -> None:
    """Append semantics hold across different roles — smoke + drafter in
    sequence produce two lines, not one, with preserved ordering."""
    target = tmp_path / "events.jsonl"
    assert main(["smoke-event", "--path", str(target)]) == 0
    assert main(["smoke-event", "--role", "drafter", "--path", str(target)]) == 0
    lines = [ln for ln in target.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    roles = [json.loads(ln)["role"] for ln in lines]
    assert roles == ["smoke_test", "drafter"]
