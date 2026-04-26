"""GateResult + emit_gate_event tests (Plan 07-01 Task 2).

Covers Tests 11-12 from the plan <behavior> block:
- Test 11: GateResult validates pass + fail severity Literal.
- Test 12: emit_gate_event writes one Event with role='physics_gate', model='n/a'.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from book_pipeline.physics.gates.base import (
    GateError,
    GateResult,
    emit_gate_event,
)


def test_gate_result_pass_severity() -> None:
    """Test 11a: severity='pass' + passed=True validates."""
    result = GateResult(gate_name="x", passed=True, severity="pass")
    assert result.passed is True
    assert result.severity == "pass"
    assert result.reason == ""
    assert result.detail == {}


def test_gate_result_high_severity_fail() -> None:
    """Test 11b: severity='high' + passed=False validates (Literal check)."""
    result = GateResult(
        gate_name="motivation",
        passed=False,
        severity="high",
        reason="motivation_fidelity FAIL — Andres motivation drifted",
        detail={"declared": "warn Xochitl", "delivered": "argue with guards"},
    )
    assert result.passed is False
    assert result.severity == "high"
    assert "drifted" in result.reason
    assert result.detail["declared"] == "warn Xochitl"


def test_gate_result_invalid_severity_rejected() -> None:
    """Severity outside the Literal set raises ValidationError."""
    with pytest.raises(ValidationError):
        GateResult(gate_name="x", passed=False, severity="catastrophic")  # type: ignore[arg-type]


def test_gate_result_extra_forbid() -> None:
    """Unknown fields rejected (extra='forbid')."""
    with pytest.raises(ValidationError):
        GateResult(
            gate_name="x", passed=True, severity="pass", unknown_field="y"  # type: ignore[call-arg]
        )


def test_gate_result_frozen() -> None:
    """GateResult is frozen — assignment after construction raises."""
    result = GateResult(gate_name="x", passed=True)
    with pytest.raises(ValidationError):
        result.gate_name = "y"  # type: ignore[misc]


def test_emit_gate_event_writes_one_event(fake_event_logger: Any) -> None:
    """Test 12: emit_gate_event appends ONE Event with the expected shape."""
    result = GateResult(
        gate_name="x",
        passed=False,
        severity="mid",
        reason="test fail",
        detail={"hint": "value"},
    )
    emit_gate_event(
        fake_event_logger,
        gate_name="x",
        scene_id="ch15_sc02",
        chapter_num=15,
        result=result,
    )
    assert len(fake_event_logger.events) == 1
    event = fake_event_logger.events[0]
    assert event.role == "physics_gate"
    assert event.model == "n/a"
    assert event.input_tokens == 0
    assert event.output_tokens == 0
    assert event.cached_tokens == 0
    assert event.latency_ms == 0
    assert event.caller_context["module"] == "physics.gates.x"
    assert event.caller_context["scene_id"] == "ch15_sc02"
    assert event.caller_context["chapter_num"] == 15
    assert event.extra["gate_name"] == "x"
    assert event.extra["passed"] is False
    assert event.extra["severity"] == "mid"
    assert event.extra["reason"] == "test fail"
    assert event.extra["detail"] == {"hint": "value"}


def test_emit_gate_event_pass_path(fake_event_logger: Any) -> None:
    """emit_gate_event with passed=True still emits one Event (D-11: pass + fail)."""
    result = GateResult(gate_name="ownership", passed=True, severity="pass")
    emit_gate_event(
        fake_event_logger,
        gate_name="ownership",
        scene_id="ch15_sc02",
        chapter_num=15,
        result=result,
    )
    assert len(fake_event_logger.events) == 1
    event = fake_event_logger.events[0]
    assert event.role == "physics_gate"
    assert event.extra["passed"] is True


def test_gate_error_is_exception_subclass() -> None:
    """GateError is a usable Exception subclass for run_pre_flight short-circuit."""
    assert issubclass(GateError, Exception)
    err = GateError("high-severity FAIL")
    with pytest.raises(GateError, match="FAIL"):
        raise err
