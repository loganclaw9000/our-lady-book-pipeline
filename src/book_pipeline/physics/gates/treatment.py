"""treatment pre-flight gate (Plan 07-03 PHYSICS-05).

Pydantic schema's Treatment enum already enforces membership at validation time.
This gate is defense in depth + emission point. Reports PASS for any stub that
loaded (any non-enum value would have raised ValidationError before this gate ran).
"""
from __future__ import annotations

from book_pipeline.physics.gates.base import GateResult
from book_pipeline.physics.schema import SceneMetadata, Treatment

GATE_NAME = "treatment"


def check(stub: SceneMetadata) -> GateResult:
    scene_id = f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"
    # Defense in depth: SceneMetadata.treatment is typed Treatment, so this
    # branch is normally unreachable. We check via membership on the enum
    # so the gate stays robust if a future caller bypasses Pydantic.
    if stub.treatment not in Treatment:
        return GateResult(
            gate_name=GATE_NAME,
            passed=False,
            severity="high",
            reason="treatment_enum_violation",
            detail={"scene_id": scene_id, "treatment": str(stub.treatment)},
        )
    return GateResult(
        gate_name=GATE_NAME,
        passed=True,
        severity="pass",
        detail={"scene_id": scene_id, "treatment": stub.treatment.value},
    )


__all__ = ["GATE_NAME", "check"]
