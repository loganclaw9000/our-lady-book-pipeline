"""book_pipeline.drafter — Mode-A (Plan 03-02) and mode_a concrete (Plan 03-04) live here.

Plan 03-04 exports: ModeADrafter + ModeADrafterBlocked + VOICE_DESCRIPTION +
RUBRIC_AWARENESS. B-1 fallback-import pattern keeps the package importable
even if mode_a.py is absent mid-wave.
"""
from __future__ import annotations

import contextlib as _contextlib
import importlib as _importlib
from typing import Any as _Any

ModeADrafter: _Any = None
ModeADrafterBlocked: _Any = None
VOICE_DESCRIPTION: _Any = None
RUBRIC_AWARENESS: _Any = None
with _contextlib.suppress(ImportError):
    _mode_a = _importlib.import_module("book_pipeline.drafter.mode_a")
    ModeADrafter = getattr(_mode_a, "ModeADrafter", None)
    ModeADrafterBlocked = getattr(_mode_a, "ModeADrafterBlocked", None)
    VOICE_DESCRIPTION = getattr(_mode_a, "VOICE_DESCRIPTION", None)
    RUBRIC_AWARENESS = getattr(_mode_a, "RUBRIC_AWARENESS", None)

__all__ = [
    "RUBRIC_AWARENESS",
    "VOICE_DESCRIPTION",
    "ModeADrafter",
    "ModeADrafterBlocked",
]
