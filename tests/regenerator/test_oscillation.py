"""Tests for detect_oscillation() pure function (Plan 05-02 Task 1 / REGEN-04).

D-07 semantics: compare attempts N and N-2 axis+severity sets; fire only on
mid/high severity matches; attempt-1 oscillation is impossible (needs
min_history >= 2).

Tests build Event instances directly with role='critic' + extra={'severities':
{axis: severity_str}}. No real Anthropic / no real network.
"""
from __future__ import annotations

from book_pipeline.interfaces.types import Event
from book_pipeline.regenerator.oscillation import detect_oscillation


def _critic_event(*, severities: dict[str, str], event_id: str = "eid") -> Event:
    """Build a minimal Event with role='critic' and extra.severities set."""
    return Event(
        event_id=event_id,
        ts_iso="2026-04-23T00:00:00Z",
        role="critic",
        model="claude-opus-4-7",
        prompt_hash="phash",
        input_tokens=100,
        cached_tokens=0,
        output_tokens=50,
        latency_ms=10,
        caller_context={"scene_id": "ch01_sc01"},
        output_hash="ohash",
        extra={"severities": dict(severities)},
    )


def test_history_below_min_returns_false() -> None:
    """A single event cannot oscillate — min_history=2 is not met."""
    event = _critic_event(severities={"historical": "mid"})
    fired, common = detect_oscillation([event], min_history=2)
    assert fired is False
    assert common is None


def test_two_identical_axis_severity_fires() -> None:
    """Attempts N and N-2 share (axis='historical', severity='mid') -> oscillate."""
    # 3 events: [N-2, N-1, N]. N and N-2 share historical:mid (intermediate differs).
    e_n2 = _critic_event(severities={"historical": "mid"}, event_id="e_n2")
    e_n1 = _critic_event(severities={"metaphysics": "high"}, event_id="e_n1")
    e_n = _critic_event(severities={"historical": "mid"}, event_id="e_n")
    fired, common = detect_oscillation([e_n2, e_n1, e_n])
    assert fired is True
    assert common == frozenset({("historical", "mid")})


def test_low_severity_ignored() -> None:
    """LOW severity matches do not count per RESEARCH Pattern 2."""
    e_n2 = _critic_event(severities={"historical": "low"}, event_id="e_n2")
    e_n1 = _critic_event(severities={"metaphysics": "high"}, event_id="e_n1")
    e_n = _critic_event(severities={"historical": "low"}, event_id="e_n")
    fired, common = detect_oscillation([e_n2, e_n1, e_n])
    assert fired is False
    assert common is None


def test_different_axes_no_match() -> None:
    """N and N-2 differ entirely -> no oscillation."""
    e_n2 = _critic_event(severities={"metaphysics": "high"}, event_id="e_n2")
    e_n1 = _critic_event(severities={"arc": "mid"}, event_id="e_n1")
    e_n = _critic_event(severities={"historical": "mid"}, event_id="e_n")
    fired, common = detect_oscillation([e_n2, e_n1, e_n])
    assert fired is False
    assert common is None


def test_three_back_comparison_not_one_back() -> None:
    """D-07 compares N vs N-2 (NOT N vs N-1). If N and N-1 match but N-2 doesn't,
    no oscillation."""
    e_n2 = _critic_event(
        severities={"arc": "mid"}, event_id="e_n2"
    )  # different from N
    e_n1 = _critic_event(
        severities={"historical": "mid"}, event_id="e_n1"
    )  # matches N
    e_n = _critic_event(severities={"historical": "mid"}, event_id="e_n")
    fired, common = detect_oscillation([e_n2, e_n1, e_n])
    # N-1 and N match, but detector looks at N vs N-2 which differ → False.
    assert fired is False
    assert common is None


def test_multiple_common_tuples_returned() -> None:
    """N and N-2 share two mid/high (axis, severity) pairs — both returned."""
    shared = {"historical": "mid", "metaphysics": "high"}
    e_n2 = _critic_event(severities=shared, event_id="e_n2")
    e_n1 = _critic_event(severities={"arc": "low"}, event_id="e_n1")
    e_n = _critic_event(severities=shared, event_id="e_n")
    fired, common = detect_oscillation([e_n2, e_n1, e_n])
    assert fired is True
    assert common == frozenset({("historical", "mid"), ("metaphysics", "high")})


def test_empty_event_list() -> None:
    """Empty list returns (False, None) — no history to compare."""
    fired, common = detect_oscillation([], min_history=2)
    assert fired is False
    assert common is None


def test_two_events_does_not_compare_three_back() -> None:
    """With only 2 events, there's no N-2 to compare against -> False."""
    # Two events, both historical:mid. But detector needs 3+ events to
    # compare N (-1) vs N-2 (-3). min_history=2 is met but N-2 is empty.
    e0 = _critic_event(severities={"historical": "mid"}, event_id="e0")
    e1 = _critic_event(severities={"historical": "mid"}, event_id="e1")
    fired, common = detect_oscillation([e0, e1], min_history=2)
    # N is e1, N-2 doesn't exist (would be index -3 out of 2); empty set intersect
    # is empty → no oscillation.
    assert fired is False
    assert common is None
