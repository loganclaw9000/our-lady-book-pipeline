"""ownership pre-flight gate (Plan 07-03 PHYSICS-05).

D-13: do_not_renarrate must NOT overlap with the scene's own owns list (semantic
contradiction). callback_allowed must not overlap with do_not_renarrate (a beat
either is referenced or refused, never both).

Cross-scene ownership consistency (does ch15 sc02's do_not_renarrate reference a
real ch15 sc01 owns entry?) is mid-severity in v1: when prior_committed_metadata
is supplied, unresolved references warn-soft. Hardening to high is OQ for v1.1.
"""
from __future__ import annotations

from book_pipeline.physics.gates.base import GateResult
from book_pipeline.physics.schema import SceneMetadata

GATE_NAME = "ownership"


def check(
    stub: SceneMetadata,
    prior_committed_metadata: list[SceneMetadata] | None = None,
) -> GateResult:
    failures: list[str] = []

    # 1. do_not_renarrate must not overlap with owns (semantic contradiction).
    owns_set = set(stub.owns)
    overlap = owns_set & set(stub.do_not_renarrate)
    if overlap:
        failures.append(
            f"do_not_renarrate overlaps with owns: {sorted(overlap)} "
            f"(a scene cannot both own and refuse to renarrate the same beat)"
        )

    # 2. callback_allowed must not overlap with do_not_renarrate.
    callback_overlap = set(stub.callback_allowed) & set(stub.do_not_renarrate)
    if callback_overlap:
        failures.append(
            f"callback_allowed overlaps with do_not_renarrate: {sorted(callback_overlap)}"
        )

    # 3. (defense in depth) cross-scene check: do_not_renarrate references should
    # resolve to a prior scene's owns. Skip if prior_committed_metadata is None
    # (early-chapter scenes don't have prior).
    soft_unresolved: list[str] = []
    if prior_committed_metadata is not None:
        prior_owns: set[str] = set()
        for prior in prior_committed_metadata:
            prior_owns |= set(prior.owns)
        soft_unresolved = [r for r in stub.do_not_renarrate if r not in prior_owns]

    scene_id = f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"
    if not failures and not soft_unresolved:
        return GateResult(
            gate_name=GATE_NAME,
            passed=True,
            severity="pass",
            detail={"scene_id": scene_id},
        )

    if failures:
        return GateResult(
            gate_name=GATE_NAME,
            passed=False,
            severity="high",
            reason="ownership_inconsistency",
            detail={"failures": failures, "scene_id": scene_id},
        )

    # Only soft unresolved -> mid severity warning.
    return GateResult(
        gate_name=GATE_NAME,
        passed=False,
        severity="mid",
        reason="ownership_unresolved_reference",
        detail={
            "scene_id": scene_id,
            "unresolved": soft_unresolved,
            "note": "may be intentional shorthand; review",
        },
    )


__all__ = ["GATE_NAME", "check"]
