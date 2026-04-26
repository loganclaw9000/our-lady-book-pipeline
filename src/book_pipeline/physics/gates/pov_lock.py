"""pov_lock pre-flight gate (Plan 07-03 PHYSICS-05).

D-16 + Pitfall 8 (07-RESEARCH.md): activation is INCLUSIVE on active_from_chapter.
Override path emits its own Event for audit (T-07-08 mitigation per 07-RESEARCH.md
Threat Register) — the GateResult.detail records `pov_lock_override_used` +
rationale; ``emit_gate_event`` surfaces these in the Event extra dict; weekly
digest (Phase 6) flags overrides.
"""
from __future__ import annotations

from book_pipeline.physics.gates.base import GateResult
from book_pipeline.physics.locks import PovLock
from book_pipeline.physics.schema import SceneMetadata

GATE_NAME = "pov_lock"


def check(stub: SceneMetadata, locks: dict[str, PovLock]) -> GateResult:
    """Pre-flight: stub.perspective must match per-character pov_lock unless overridden."""
    on_screen_chars = [c.name for c in stub.characters_present if c.on_screen]
    breaches: list[str] = []
    override_used = False
    for char_name in on_screen_chars:
        lock = locks.get(char_name.lower())
        if lock is None or not lock.applies_to(stub.chapter):
            continue
        if lock.perspective != stub.perspective:
            if stub.pov_lock_override:
                override_used = True
                continue
            breaches.append(
                f"{char_name}: declared {stub.perspective.value} but lock pins "
                f"{lock.perspective.value} (active_from_chapter={lock.active_from_chapter}, "
                f"rationale={lock.rationale!r})"
            )
    scene_id = f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"
    if not breaches:
        return GateResult(
            gate_name=GATE_NAME,
            passed=True,
            severity="pass",
            detail={
                "scene_id": scene_id,
                "pov_lock_override_used": override_used,
                "rationale": stub.pov_lock_override or "",
            },
        )
    return GateResult(
        gate_name=GATE_NAME,
        passed=False,
        severity="high",
        reason="pov_lock_breach",
        detail={"breaches": breaches, "scene_id": scene_id},
    )


__all__ = ["GATE_NAME", "check"]
