"""Tests for book_pipeline.voice_fidelity.scorer — stub signature pinning.

Plan 03-01 lands only the stub; Plan 03-02 replaces it with the real BGE-M3
cosine implementation. The stub MUST raise NotImplementedError so downstream
consumers that try to use it prematurely get an unmistakable error.
"""
from __future__ import annotations

import pytest

from book_pipeline.voice_fidelity.scorer import score_voice_fidelity


def test_score_voice_fidelity_stub_raises_not_implemented() -> None:
    """Test 8: Stub raises NotImplementedError with a clear message naming
    Plan 03-02 as the owning plan."""
    with pytest.raises(NotImplementedError) as excinfo:
        score_voice_fidelity("any scene text", None, None)

    # Message must cite Plan 03-02 so the caller knows where the real impl lands.
    assert "03-02" in str(excinfo.value)
