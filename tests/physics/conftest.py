"""Shared fixtures for tests/physics/*."""

from __future__ import annotations

from typing import Any

import pytest

from book_pipeline.interfaces.types import Event


class FakeEventLogger:
    """Captures Event objects in-memory for gate-emit assertions."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


@pytest.fixture
def fake_event_logger() -> FakeEventLogger:
    return FakeEventLogger()


@pytest.fixture
def valid_scene_payload() -> dict[str, Any]:
    """Minimal valid v2 SceneMetadata payload (ch15 sc02 shape)."""
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
