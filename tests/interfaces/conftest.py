"""Shared fixtures for tests/interfaces/*."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def valid_scene_payload_for_drafter() -> dict[str, Any]:
    """Same shape as tests/physics/conftest.py::valid_scene_payload.

    Duplicated here (rather than cross-imported) to avoid cross-package
    fixture coupling between tests/physics/ and tests/interfaces/.
    """
    return {
        "chapter": 15,
        "scene_index": 2,
        "contents": {
            "goal": "warn Xochitl about the count's intent",
            "conflict": "the count's guards arrive before the warning lands",
            "outcome": "partial-disaster: Xochitl receives the warning but cannot act",
        },
        "characters_present": [
            {
                "name": "Andres",
                "on_screen": True,
                "motivation": "warn Xochitl about the count",
            },
            {
                "name": "Xochitl",
                "on_screen": True,
                "motivation": "decide whether to flee or stay",
            },
        ],
        "voice": "paul-v7c",
        "perspective": "3rd_close",
        "treatment": "ominous",
        "owns": ["ch15_sc02_warning"],
        "do_not_renarrate": ["ch15_sc01_arrival"],
        "callback_allowed": [],
        "staging": {
            "location_canonical": "Cempoala fortress courtyard",
            "spatial_position": "north steps, second tier",
            "scene_clock": "late afternoon, day after ch15 sc01",
            "relative_clock": "one day after sc01",
            "sensory_dominance": ["sight", "sound"],
            "on_screen": ["Andres", "Xochitl"],
            "off_screen_referenced": ["the count"],
            "witness_only": [],
        },
    }
