"""Mode-B preflag reader (Plan 05-01 Task 2, D-04).

Pure function + config loader seam. The scene loop (Plan 05-02) calls
``is_preflagged(scene_id, load_preflag_set())`` before the first Mode-A
drafter attempt; True → skip Mode-A entirely and route to Mode-B.

Demotion to Mode-A happens via YAML removal at config/mode_preflags.yaml
with a pre-commit audit log entry — never silent.
"""
from __future__ import annotations

from book_pipeline.config.mode_preflags import PreflagConfig


def is_preflagged(scene_id: str, preflag_set: frozenset[str]) -> bool:
    """Return True iff ``scene_id`` is in ``preflag_set``.

    Args:
        scene_id: canonical "ch{NN:02d}_sc{II:02d}" string (or beat_id when
            the scene loop uses beat-grain preflags).
        preflag_set: immutable set of preflagged identifiers; typically the
            return of ``load_preflag_set()``.

    Returns:
        True if preflagged → route directly to Mode-B. False → Mode-A first.
    """
    return scene_id in preflag_set


def load_preflag_set() -> frozenset[str]:
    """Load config/mode_preflags.yaml and return an immutable frozenset.

    Called once per scene loop invocation (cheap — YAML is tiny).
    """
    return frozenset(PreflagConfig().preflagged_beats)


__all__ = ["is_preflagged", "load_preflag_set"]
