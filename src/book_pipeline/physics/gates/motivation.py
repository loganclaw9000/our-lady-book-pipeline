"""motivation pre-flight gate (Plan 07-03 PHYSICS-05).

Pydantic schema already enforces motivation min-words + on-screen-with-motivation.
This gate is the runtime safety belt for non-Pydantic call paths AND the audit
emission point (one role='physics_gate' Event per check).

D-02 hard-stop semantic lives in the CRITIC (Plan 07-04). At pre-flight, this gate
fires HIGH if motivation is missing entirely (Pydantic-impossible but defensive)
or contains stub-leak vocabulary at the start of the motivation field.
"""
from __future__ import annotations

import re

from book_pipeline.physics.gates.base import GateResult
from book_pipeline.physics.schema import SceneMetadata

GATE_NAME = "motivation"

# Stub-leak guard at motivation level — defensive against operator pasting stub
# scaffolding into the motivation field. NOTE: 'Goal', 'Conflict', 'Outcome'
# intentionally OMITTED — these are legitimate motivation prefixes ("His goal: to
# warn Xochitl.") that would over-fire on real operator-authored motivation strings.
# The full stub-leak axis (Plan 07-04 stub_leak.py) covers prose-level scans; this
# gate is the narrow motivation-field guard.
#
# T-07-02 (regex DoS): anchored line-start pattern (^\s*(...)) — bounded
# alternation, no nested quantifiers, no `.*` followed by `\s*$`. The motivation
# field is also bounded by Pydantic min-words validator (single line in practice).
_STUB_LEAK_IN_MOTIVATION = re.compile(
    r"^\s*(?:Establish|Resolve|Set up|Setup|Beat|Function|Disaster|Reaction|Dilemma|Decision)\s*:",
    re.IGNORECASE,
)


def check(stub: SceneMetadata) -> GateResult:
    on_screen = [c for c in stub.characters_present if c.on_screen]
    failures: list[str] = []
    for c in on_screen:
        if not c.motivation or not c.motivation.strip():
            failures.append(f"{c.name}: empty motivation (D-02 load-bearing)")
            continue
        if _STUB_LEAK_IN_MOTIVATION.match(c.motivation):
            failures.append(
                f"{c.name}: motivation contains stub vocabulary: {c.motivation[:80]!r}"
            )
    scene_id = f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"
    if not failures:
        return GateResult(
            gate_name=GATE_NAME,
            passed=True,
            severity="pass",
            detail={"scene_id": scene_id},
        )
    return GateResult(
        gate_name=GATE_NAME,
        passed=False,
        severity="high",
        reason="missing_or_stub_leaked_motivation",
        detail={"failures": failures, "scene_id": scene_id},
    )


__all__ = ["GATE_NAME", "check"]
