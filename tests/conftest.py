"""pytest configuration and shared fixtures.

WR-03: Close and evict all cached FileHandler objects after each test so that
pytest's tmp_path cleanup can remove temporary directories without hitting
open file descriptors.  The handler cache (_HANDLERS_BY_PATH) is designed for
a long-running production process with exactly one log path; in tests each
tmp_path call produces a unique directory, so without teardown the process
accumulates O(N) open FDs across the suite.

This fixture also prevents test_handler_idempotent from passing spuriously
because a leftover cached handler from a prior test happens to share the same
path key (unlikely with tmp_path, but not impossible with manually constructed
paths).
"""

from __future__ import annotations

import pytest

import book_pipeline.observability.event_logger as _el


@pytest.fixture(autouse=True)
def _clear_handler_cache() -> object:
    yield
    with _el._HANDLER_LOCK:
        for handler in _el._HANDLERS_BY_PATH.values():
            handler.close()
        _el._HANDLERS_BY_PATH.clear()
