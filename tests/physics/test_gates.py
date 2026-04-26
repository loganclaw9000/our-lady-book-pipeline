"""Tests for book_pipeline.physics.gates.* (Plan 07-03 Task 1).

Tests 1-10 + Test 7b from PLAN.md <behavior>.
"""
from __future__ import annotations

from typing import Any

import pytest

from book_pipeline.physics.canon_bible import CanonBibleView, CanonicalQuantityRow
from book_pipeline.physics.gates import GateError, run_pre_flight
from book_pipeline.physics.gates import (
    motivation as motivation_gate,
    ownership as ownership_gate,
    pov_lock as pov_lock_gate,
    quantity as quantity_gate,
    treatment as treatment_gate,
)
from book_pipeline.physics.locks import PovLock
from book_pipeline.physics.schema import Perspective, SceneMetadata


# --- Helpers ---------------------------------------------------------------


def _itzcoatl_lock_ch15() -> PovLock:
    return PovLock(
        character="Itzcoatl",
        perspective=Perspective.FIRST_PERSON,
        active_from_chapter=15,
        rationale="OQ-01(a) RESOLVED 2026-04-25 — D-16 + D-21 forward-only.",
    )


def _empty_canon_bible() -> CanonBibleView:
    return CanonBibleView(canonical_quantities=[], pov_locks={})


def _seeded_canon_bible() -> CanonBibleView:
    rows = [
        CanonicalQuantityRow(id="andres_age", text="Andres: 23 (ch01-ch14).", name="Andres"),
        CanonicalQuantityRow(id="la_nina_height", text="La Nina: 55ft.", name="La Nina"),
        CanonicalQuantityRow(id="santiago_del_paso_scale", text="Santiago del Paso: 210ft.", name="Santiago del Paso"),
        CanonicalQuantityRow(id="cholula_date", text="Cholula: October 18, 1519.", name="Cholula"),
        CanonicalQuantityRow(id="cempoala_arrival", text="Cempoala: June 2, 1519.", name="Cempoala"),
    ]
    return CanonBibleView(canonical_quantities=rows, pov_locks={})


# --- Test 1: pov_lock pass for ungated chapter (ch09) ---------------------


def test_pov_lock_check_passes_for_ungated_ch09(valid_scene_payload: dict[str, Any]) -> None:
    """ch09 is BEFORE the Itzcoatl lock activates (ch15) per OQ-01(a) RESOLVED.

    Even if the stub declares perspective=3rd_close while Itzcoatl is on-screen,
    the lock does NOT apply at ch09 -> gate passes.
    """
    payload = dict(valid_scene_payload)
    payload["chapter"] = 9
    # Override staging too because location_canonical etc. don't need ch
    payload["characters_present"] = [
        {
            "name": "Itzcoatl",
            "on_screen": True,
            "motivation": "spy on the Spanish camp",
        },
    ]
    payload["staging"] = dict(payload["staging"])
    payload["staging"]["on_screen"] = ["Itzcoatl"]
    stub = SceneMetadata.model_validate(payload)
    locks = {"itzcoatl": _itzcoatl_lock_ch15()}
    result = pov_lock_gate.check(stub, locks)
    assert result.passed is True
    assert result.severity == "pass"


# --- Test 2: pov_lock breach at ch15 (3rd_close while lock pins 1st) -------


def test_pov_lock_check_fails_high_at_ch15_for_lock_breach(valid_scene_payload: dict[str, Any]) -> None:
    """ch15+ Itzcoatl with declared 3rd_close -> high-severity breach."""
    payload = dict(valid_scene_payload)
    payload["chapter"] = 15
    payload["perspective"] = "3rd_close"
    payload["characters_present"] = [
        {
            "name": "Itzcoatl",
            "on_screen": True,
            "motivation": "warn Xochitl about the Spanish",
        },
    ]
    payload["staging"] = dict(payload["staging"])
    payload["staging"]["on_screen"] = ["Itzcoatl"]
    stub = SceneMetadata.model_validate(payload)
    locks = {"itzcoatl": _itzcoatl_lock_ch15()}
    result = pov_lock_gate.check(stub, locks)
    assert result.passed is False
    assert result.severity == "high"
    assert result.reason == "pov_lock_breach"
    assert "breaches" in result.detail
    assert len(result.detail["breaches"]) == 1


# --- Test 3: pov_lock_override path passes despite breach -----------------


def test_pov_lock_check_passes_when_override_set(valid_scene_payload: dict[str, Any]) -> None:
    payload = dict(valid_scene_payload)
    payload["chapter"] = 15
    payload["perspective"] = "3rd_close"
    payload["pov_lock_override"] = "ch15 sc02 dream sequence — 3rd close intentional"
    payload["characters_present"] = [
        {
            "name": "Itzcoatl",
            "on_screen": True,
            "motivation": "dream of the future",
        },
    ]
    payload["staging"] = dict(payload["staging"])
    payload["staging"]["on_screen"] = ["Itzcoatl"]
    stub = SceneMetadata.model_validate(payload)
    locks = {"itzcoatl": _itzcoatl_lock_ch15()}
    result = pov_lock_gate.check(stub, locks)
    assert result.passed is True
    assert result.severity == "pass"
    # Override audit (T-07-08)
    assert result.detail.get("pov_lock_override_used") is True
    assert "rationale" in result.detail
    assert "dream" in result.detail["rationale"]


# --- Test 4: motivation gate passes / fails -------------------------------


def test_motivation_check_passes_for_valid_stub(valid_scene_payload: dict[str, Any]) -> None:
    stub = SceneMetadata.model_validate(valid_scene_payload)
    result = motivation_gate.check(stub)
    assert result.passed is True
    assert result.severity == "pass"


def test_motivation_check_fails_when_stub_leak_in_motivation(
    valid_scene_payload: dict[str, Any],
) -> None:
    """A motivation that begins with stub vocabulary 'Establish:' fires high."""
    payload = dict(valid_scene_payload)
    payload["characters_present"] = [
        {
            "name": "Andres",
            "on_screen": True,
            "motivation": "Establish: warn Xochitl about the count's intent",
        },
        {
            "name": "Xochitl",
            "on_screen": True,
            "motivation": "decide whether to flee or stay",
        },
    ]
    stub = SceneMetadata.model_validate(payload)
    result = motivation_gate.check(stub)
    assert result.passed is False
    assert result.severity == "high"
    assert "Andres" in str(result.detail["failures"])


# --- Test 5: ownership do_not_renarrate overlap -> high -------------------


def test_ownership_check_fails_high_on_owns_donotrenarrate_overlap(
    valid_scene_payload: dict[str, Any],
) -> None:
    payload = dict(valid_scene_payload)
    payload["owns"] = ["ch15_sc02_warning"]
    payload["do_not_renarrate"] = ["ch15_sc02_warning", "ch15_sc01_arrival"]
    stub = SceneMetadata.model_validate(payload)
    result = ownership_gate.check(stub)
    assert result.passed is False
    assert result.severity == "high"
    assert result.reason == "ownership_inconsistency"


def test_ownership_check_passes_for_disjoint_lists(valid_scene_payload: dict[str, Any]) -> None:
    stub = SceneMetadata.model_validate(valid_scene_payload)
    result = ownership_gate.check(stub)
    assert result.passed is True
    assert result.severity == "pass"


# --- Test 6: treatment gate (defense in depth) ----------------------------


def test_treatment_check_passes_when_enum_valid(valid_scene_payload: dict[str, Any]) -> None:
    stub = SceneMetadata.model_validate(valid_scene_payload)
    result = treatment_gate.check(stub)
    assert result.passed is True
    assert result.severity == "pass"


# --- Test 7: quantity gate canary pass; unrecognized entity = soft mid ----


def test_quantity_check_passes_when_entity_resolves(valid_scene_payload: dict[str, Any]) -> None:
    payload = dict(valid_scene_payload)
    payload["contents"] = dict(payload["contents"])
    payload["contents"]["goal"] = "Andres reports the count's plan to Xochitl"
    payload["characters_present"] = [
        {"name": "Andres", "on_screen": True, "motivation": "warn Xochitl about the count"},
        {"name": "Xochitl", "on_screen": True, "motivation": "decide whether to flee or stay"},
    ]
    payload["staging"] = dict(payload["staging"])
    payload["staging"]["on_screen"] = ["Andres", "Xochitl"]
    stub = SceneMetadata.model_validate(payload)
    cb = _seeded_canon_bible()
    result = quantity_gate.check(stub, cb)
    assert result.passed is True
    assert result.severity == "pass"
    assert "andres_age" in result.detail["matched_rows"]


def test_quantity_check_soft_warns_for_unmapped_entity(
    valid_scene_payload: dict[str, Any],
) -> None:
    """Stub references on-screen char with no canonical row -> mid severity."""
    payload = dict(valid_scene_payload)
    payload["characters_present"] = [
        {"name": "Zorro", "on_screen": True, "motivation": "save Xochitl from the count"},
    ]
    payload["staging"] = dict(payload["staging"])
    payload["staging"]["on_screen"] = ["Zorro"]
    stub = SceneMetadata.model_validate(payload)
    cb = _seeded_canon_bible()
    result = quantity_gate.check(stub, cb)
    assert result.passed is False
    assert result.severity == "mid"
    assert any("zorro" in w.lower() for w in result.detail["soft_warnings"])


# --- Test 7b: long-tail synthetic row picked up WITHOUT code change -------


def test_quantity_check_iterates_synthetic_sixth_row(
    valid_scene_payload: dict[str, Any],
) -> None:
    """Inject a 6th 'tlaxcala_population' row into the view; the quantity gate
    must surface it via matched_rows when the stub goal references "Tlaxcala"
    — without any code change to gates/quantity.py.

    This is the Warning #2 mitigation acceptance: the gate iterates
    canon_bible.iter_canonical_quantities(), not a hardcoded keyword list.
    """
    payload = dict(valid_scene_payload)
    payload["contents"] = dict(payload["contents"])
    payload["contents"]["goal"] = "Andres surveys the Tlaxcala alliance numbers"
    stub = SceneMetadata.model_validate(payload)

    rows = [
        CanonicalQuantityRow(id="andres_age", text="Andres: 23.", name="Andres"),
        CanonicalQuantityRow(id="la_nina_height", text="La Nina: 55ft.", name="La Nina"),
        CanonicalQuantityRow(id="santiago_del_paso_scale", text="Santiago del Paso: 210ft.", name="Santiago del Paso"),
        CanonicalQuantityRow(id="cholula_date", text="Cholula: October 18, 1519.", name="Cholula"),
        CanonicalQuantityRow(id="cempoala_arrival", text="Cempoala: June 2, 1519.", name="Cempoala"),
        # Synthetic 6th row — added without modifying gates/quantity.py:
        CanonicalQuantityRow(
            id="tlaxcala_population",
            text="Tlaxcala: ~150,000 inhabitants (ch07).",
            name="Tlaxcala",
        ),
    ]
    cb = CanonBibleView(canonical_quantities=rows, pov_locks={})
    result = quantity_gate.check(stub, cb)
    assert "tlaxcala_population" in result.detail["matched_rows"]


# --- Test 8: run_pre_flight returns 5 GateResults on full pass ------------


def test_run_pre_flight_returns_5_gate_results_on_pass(
    valid_scene_payload: dict[str, Any],
    fake_event_logger: Any,
) -> None:
    stub = SceneMetadata.model_validate(valid_scene_payload)
    cb = _seeded_canon_bible()
    results = run_pre_flight(
        stub,
        pov_locks={},
        canon_bible=cb,
        event_logger=fake_event_logger,
    )
    assert len(results) == 5
    gate_names = [r.gate_name for r in results]
    assert gate_names == ["pov_lock", "motivation", "ownership", "treatment", "quantity"]


# --- Test 9: run_pre_flight short-circuits on first high-severity FAIL ----


def test_run_pre_flight_short_circuits_on_high_severity_fail(
    valid_scene_payload: dict[str, Any],
    fake_event_logger: Any,
) -> None:
    """Inject a stub-leak motivation -> motivation gate fires HIGH at index 1.

    Expected: pov_lock (pass) + motivation (high) only — ownership/treatment/
    quantity NOT called. GateError raised. fake_event_logger.events has length 2.
    """
    payload = dict(valid_scene_payload)
    payload["characters_present"] = [
        {
            "name": "Andres",
            "on_screen": True,
            "motivation": "Establish: warn Xochitl about the count's intent",
        },
        {
            "name": "Xochitl",
            "on_screen": True,
            "motivation": "decide whether to flee or stay",
        },
    ]
    stub = SceneMetadata.model_validate(payload)
    cb = _seeded_canon_bible()

    with pytest.raises(GateError) as exc_info:
        run_pre_flight(
            stub,
            pov_locks={},
            canon_bible=cb,
            event_logger=fake_event_logger,
        )

    # Short-circuit: only 2 events emitted (pov_lock pass + motivation high)
    assert len(fake_event_logger.events) == 2
    assert fake_event_logger.events[0].extra["gate_name"] == "pov_lock"
    assert fake_event_logger.events[1].extra["gate_name"] == "motivation"
    assert fake_event_logger.events[1].extra["severity"] == "high"

    # GateError carries failed_gate + accumulated results
    err = exc_info.value
    assert getattr(err, "failed_gate", None) == "motivation"
    assert len(getattr(err, "results", [])) == 2


# --- Test 10: run_pre_flight emits one event per gate on pass-through -----


def test_run_pre_flight_emits_one_event_per_gate_on_full_pass(
    valid_scene_payload: dict[str, Any],
    fake_event_logger: Any,
) -> None:
    stub = SceneMetadata.model_validate(valid_scene_payload)
    cb = _seeded_canon_bible()
    run_pre_flight(
        stub,
        pov_locks={},
        canon_bible=cb,
        event_logger=fake_event_logger,
    )
    assert len(fake_event_logger.events) == 5
    # Every event has role='physics_gate'
    assert all(e.role == "physics_gate" for e in fake_event_logger.events)
    # Order matches the deterministic gate_calls order
    names_in_order = [e.extra["gate_name"] for e in fake_event_logger.events]
    assert names_in_order == ["pov_lock", "motivation", "ownership", "treatment", "quantity"]
