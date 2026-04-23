"""Oscillation detector — pure function over role='critic' Event trail (REGEN-04).

Plan 05-02 Task 1 / D-07. Stateless inspection of the Event list to decide if
the scene is oscillating between identical failure modes. Called at each
regen-attempt boundary inside cli/draft.py::run_draft_loop; firing → escalate
to Mode-B immediately (skip remaining Mode-A budget).

D-07 semantics (verified in 05-RESEARCH Pattern 2):
  - compare attempts N and N-2 (NOT N and N-1)
  - fire only on mid/high severity matches (low is noise)
  - need min_history >= 2 before considering firing; attempt 1 can't oscillate

Each role='critic' Event carries ``extra.severities = {axis: severity_str}``
stamped by the SceneCritic concrete (Plan 03-05 precedent).
"""
from __future__ import annotations

from book_pipeline.interfaces.types import Event


def _extract_axis_severity_set(event: Event) -> frozenset[tuple[str, str]]:
    """Pull (axis, severity) tuples from a role='critic' Event's extra.severities.

    Format: ``extra.severities = {'historical': 'mid', 'metaphysics': 'high', ...}``.
    Unknown shape → empty frozenset (defensive; malformed history must not
    crash the detector).
    """
    if not event.extra:
        return frozenset()
    severities_obj = event.extra.get("severities", {})
    if not isinstance(severities_obj, dict):
        return frozenset()
    return frozenset(
        (str(axis), str(sev)) for axis, sev in severities_obj.items()
    )


def detect_oscillation(
    critic_events: list[Event],
    *,
    min_history: int = 2,
) -> tuple[bool, frozenset[tuple[str, str]] | None]:
    """Return (fired, repeated_tuples) comparing attempts N vs N-2 per D-07.

    Args:
        critic_events: ordered oldest→newest role='critic' events for one
            scene.
        min_history: minimum events required before firing (default 2).

    Returns:
        (fired, repeated_tuples). repeated_tuples contains (axis, severity)
        pairs present in BOTH N and N-2 at mid/high severity only; None when
        not firing.
    """
    if len(critic_events) < min_history:
        return False, None
    latest = _extract_axis_severity_set(critic_events[-1])
    # N-2 = index -3 (oldest→newest). Need >= 3 events for that index to exist.
    two_back: frozenset[tuple[str, str]]
    if len(critic_events) >= 3:
        two_back = _extract_axis_severity_set(critic_events[-3])
    else:
        two_back = frozenset()
    common = latest & two_back
    significant = frozenset(
        (axis, sev) for axis, sev in common if sev in ("mid", "high")
    )
    if significant:
        return True, significant
    return False, None


__all__ = ["detect_oscillation"]
