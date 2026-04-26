"""quantity pre-flight gate (Plan 07-03 PHYSICS-05).

Cross-checks the stub's contents/staging text + on-screen characters against the
CanonBibleView (CB-01 retrieved canonical quantities).

Iterates ``canon_bible.iter_canonical_quantities()`` so the gate covers BOTH the
operator-seeded 5 canaries (Plan 07-02) AND any long-tail extracted quantities
the OQ-05 (c) extraction agent (v1.1, deferred) adds later. NO hardcoded
entity keyword list — Warning #2 mitigation.

Severity model:
- 'pass': all canonical-quantity entities mentioned in the stub resolve via CB-01.
- 'mid': stub references an on-screen entity that has NO canonical row (soft
  signal — Cempoala double-arrival corner case per 07-NARRATIVE_PHYSICS.md §6.3
  says hard reject would over-fire at pre-flight; the critic catches the actual
  drift post-draft).
- 'high': stub explicitly contradicts a canonical value substring (reserved for
  v1.1; v1 leaves contradiction detection to the critic).
"""
from __future__ import annotations

from book_pipeline.physics.canon_bible import CanonBibleView
from book_pipeline.physics.gates.base import GateResult
from book_pipeline.physics.schema import SceneMetadata

GATE_NAME = "quantity"


def check(stub: SceneMetadata, canon_bible: CanonBibleView) -> GateResult:
    scene_id = f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"

    # Aggregate stub-level free-text fields likely to reference canonical quantities.
    stub_text_blob = " ".join(
        [
            stub.contents.goal,
            stub.contents.conflict,
            stub.contents.outcome,
            stub.staging.location_canonical,
            stub.staging.spatial_position,
            stub.staging.scene_clock,
            stub.staging.relative_clock or "",
        ]
    ).lower()

    failures: list[str] = []
    soft_warnings: list[str] = []
    matched_rows: list[str] = []

    # Walk EVERY canonical-quantity row known to the CanonBibleView. The gate fires
    # for hand-seeded canaries AND for any long-tail row the v1.1 extraction agent
    # injects later — no code change required (Warning #2 mitigation).
    for row in canon_bible.iter_canonical_quantities():
        name_lc = row.name.lower()
        id_lc = row.id.lower()
        if name_lc in stub_text_blob or id_lc in stub_text_blob:
            matched_rows.append(row.id)

    # Soft-warning logic: on-screen characters with no canonical-row match.
    # We restrict the soft-warn to the on-screen list (smaller, well-defined set)
    # rather than running NER on the prose blob — prose-level checks are the
    # critic's job (Plan 07-04 named_quantity_drift axis).
    on_screen_names = [c.name for c in stub.characters_present if c.on_screen]
    for ch_name in on_screen_names:
        ch_lc = ch_name.lower()
        # Already matched as a canonical row?
        if any(ch_lc in r.lower() or r.lower() in ch_lc for r in matched_rows):
            continue
        if canon_bible.get_canonical_quantity(ch_name) is None:
            soft_warnings.append(
                f"{ch_lc}: on-screen character has no CB-01 canonical row "
                f"(may be acceptable — extraction agent v1.1 is opt-in)"
            )

    severity: str
    passed: bool
    reason: str
    if failures:
        severity = "high"
        passed = False
        reason = "named_quantity_contradiction"
    elif soft_warnings:
        severity = "mid"
        passed = False
        reason = "named_quantity_unresolved"
    else:
        severity = "pass"
        passed = True
        reason = ""

    return GateResult(
        gate_name=GATE_NAME,
        passed=passed,
        severity=severity,  # type: ignore[arg-type]
        reason=reason,
        detail={
            "scene_id": scene_id,
            "matched_rows": matched_rows,
            "failures": failures,
            "soft_warnings": soft_warnings,
        },
    )


__all__ = ["GATE_NAME", "check"]
