"""Physics pre-flight gate composer (Plan 07-03 PHYSICS-05).

run_pre_flight orchestrates the 5 gates sequentially. Per RESEARCH Pattern 2
lines 388-407: SHORT-CIRCUITS on first ``severity='high'`` FAIL (raises GateError).
Lower severities accumulate. Each gate emission produces one
``role='physics_gate'`` Event per OBS-01.
"""
from __future__ import annotations

from typing import Any

from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.physics.canon_bible import CanonBibleView
from book_pipeline.physics.gates import (
    motivation as motivation_gate,
)
from book_pipeline.physics.gates import (
    ownership as ownership_gate,
)
from book_pipeline.physics.gates import (
    pov_lock as pov_lock_gate,
)
from book_pipeline.physics.gates import (
    quantity as quantity_gate,
)
from book_pipeline.physics.gates import (
    treatment as treatment_gate,
)
from book_pipeline.physics.gates.base import (
    GateError,
    GateResult,
    emit_gate_event,
)
from book_pipeline.physics.locks import PovLock
from book_pipeline.physics.schema import SceneMetadata


def run_pre_flight(
    stub: SceneMetadata,
    *,
    pov_locks: dict[str, PovLock],
    canon_bible: CanonBibleView,
    event_logger: EventLogger | None = None,
    prior_committed_metadata: list[SceneMetadata] | None = None,
) -> list[GateResult]:
    """Run all 5 gates sequentially. Short-circuit on first severity='high' FAIL.

    Returns the list of GateResults accumulated up to and including the first
    high-severity FAIL (or all 5 if all pass / only mid-severity fails).

    Raises:
        GateError: on first high-severity FAIL. The accumulated results live in
            ``err.results``; the failed gate name in ``err.failed_gate``.
    """
    scene_id = f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"
    results: list[GateResult] = []

    gate_calls: list[tuple[str, Any]] = [
        ("pov_lock", lambda: pov_lock_gate.check(stub, pov_locks)),
        ("motivation", lambda: motivation_gate.check(stub)),
        ("ownership", lambda: ownership_gate.check(stub, prior_committed_metadata)),
        ("treatment", lambda: treatment_gate.check(stub)),
        ("quantity", lambda: quantity_gate.check(stub, canon_bible)),
    ]

    for gate_name, fn in gate_calls:
        result = fn()
        results.append(result)
        if event_logger is not None:
            emit_gate_event(
                event_logger,
                gate_name=gate_name,
                scene_id=scene_id,
                chapter_num=stub.chapter,
                result=result,
            )
        if result.severity == "high":
            err = GateError(
                f"physics pre-flight FAIL: gate={gate_name} reason={result.reason}"
            )
            err.results = results  # type: ignore[attr-defined]
            err.failed_gate = gate_name  # type: ignore[attr-defined]
            raise err

    return results


__all__ = [
    "GateError",
    "GateResult",
    "emit_gate_event",
    "run_pre_flight",
]
