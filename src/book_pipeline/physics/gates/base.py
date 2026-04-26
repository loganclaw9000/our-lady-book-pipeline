"""Physics gate base types + Event emission helper (Plan 07-01).

GateResult: pure value object every physics gate returns (07-RESEARCH.md
Pattern 2 lines 388-407). emit_gate_event: stamps role='physics_gate' on the
existing OBS-01 Event schema (analog: chapter_assembler.scene_kick._emit_scene_kick_event).

Plan 07-03 lands the per-gate files (pov_lock, motivation, ownership, treatment,
quantity) and the run_pre_flight composer that raises GateError on a
high-severity short-circuit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.types import Event
from book_pipeline.observability.hashing import event_id, hash_text


class GateError(Exception):
    """Raised by gate composer (Plan 07-03 run_pre_flight) on high-severity FAIL."""


class GateResult(BaseModel):
    """Value object emitted by every physics gate (Plan 07-01).

    Severity ladder mirrors CriticIssue.severity vocabulary so downstream
    scene-kick / Mode-B routing can reuse existing rubric thresholds. ``pass``
    is sentinel for the success path (passed=True); ``low``/``mid``/``high``
    are FAIL severities consumed by run_pre_flight (Plan 07-03).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_name: str
    passed: bool
    severity: Literal["pass", "low", "mid", "high"] = "pass"
    reason: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


def emit_gate_event(
    event_logger: EventLogger,
    *,
    gate_name: str,
    scene_id: str,
    chapter_num: int,
    result: GateResult,
) -> None:
    """Emit one role='physics_gate' Event per gate invocation (D-11).

    Mirrors chapter_assembler.scene_kick._emit_scene_kick_event: builds an
    Event with model='n/a' (no LLM call), zero token / latency fields, and the
    gate result payload in extra. caller_context carries module / function /
    scene_id / chapter_num for the digest aggregator.
    """
    ts_iso = datetime.now(UTC).isoformat()
    caller = f"physics.gates.{gate_name}:ch{chapter_num:02d}"
    prompt_h = hash_text(
        f"physics_gate:{gate_name}:{scene_id}:{result.passed}:{result.severity}"
    )
    eid = event_id(ts_iso, "physics_gate", caller, prompt_h)
    caller_context: dict[str, Any] = {
        "module": f"physics.gates.{gate_name}",
        "function": "check",
        "scene_id": scene_id,
        "chapter_num": chapter_num,
    }
    extra: dict[str, Any] = {
        "gate_name": gate_name,
        "passed": result.passed,
        "severity": result.severity,
        "reason": result.reason,
        "detail": dict(result.detail),
    }
    event = Event(
        event_id=eid,
        ts_iso=ts_iso,
        role="physics_gate",
        model="n/a",
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        latency_ms=0,
        caller_context=caller_context,
        output_hash=hash_text(f"{gate_name}:{scene_id}:{result.passed}"),
        extra=extra,
    )
    event_logger.emit(event)


__all__ = ["GateError", "GateResult", "emit_gate_event"]
