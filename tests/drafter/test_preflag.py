"""Tests for book_pipeline.drafter.preflag (Plan 05-01 Task 2, D-04).

Pure function over frozenset — no I/O, no side effects.
"""
from __future__ import annotations


def test_is_preflagged_true() -> None:
    from book_pipeline.drafter.preflag import is_preflagged

    preflag_set = frozenset({"ch01_sc01"})
    assert is_preflagged("ch01_sc01", preflag_set) is True


def test_is_preflagged_false() -> None:
    from book_pipeline.drafter.preflag import is_preflagged

    preflag_set = frozenset({"ch01_sc01"})
    assert is_preflagged("ch02_sc01", preflag_set) is False


def test_is_preflagged_empty_set() -> None:
    from book_pipeline.drafter.preflag import is_preflagged

    assert is_preflagged("anything", frozenset()) is False


def test_load_preflag_set_returns_frozenset() -> None:
    """load_preflag_set() reads config/mode_preflags.yaml into a frozenset."""
    from book_pipeline.drafter.preflag import load_preflag_set

    result = load_preflag_set()
    assert isinstance(result, frozenset)
    # config/mode_preflags.yaml ships with >=3 seed beats per Task 1.
    assert len(result) >= 3
