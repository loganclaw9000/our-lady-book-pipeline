"""book_pipeline.drafter — Mode-A (Plan 03-04) and Mode-B (Plan 05-01) concretes live here.

Plan 03-04 exports: ModeADrafter + ModeADrafterBlocked + VOICE_DESCRIPTION +
RUBRIC_AWARENESS. Plan 05-01 exports: ModeBDrafter + ModeBDrafterBlocked +
is_preflagged + load_preflag_set. B-1 fallback-import pattern keeps the
package importable even if mode_a.py or mode_b.py is absent mid-wave.
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

ModeBDrafter: _Any = None
ModeBDrafterBlocked: _Any = None
with _contextlib.suppress(ImportError):
    _mode_b = _importlib.import_module("book_pipeline.drafter.mode_b")
    ModeBDrafter = getattr(_mode_b, "ModeBDrafter", None)
    ModeBDrafterBlocked = getattr(_mode_b, "ModeBDrafterBlocked", None)

is_preflagged: _Any = None
load_preflag_set: _Any = None
with _contextlib.suppress(ImportError):
    _preflag = _importlib.import_module("book_pipeline.drafter.preflag")
    is_preflagged = getattr(_preflag, "is_preflagged", None)
    load_preflag_set = getattr(_preflag, "load_preflag_set", None)

__all__ = [
    "RUBRIC_AWARENESS",
    "VOICE_DESCRIPTION",
    "ModeADrafter",
    "ModeADrafterBlocked",
    "ModeBDrafter",
    "ModeBDrafterBlocked",
    "is_preflagged",
    "load_preflag_set",
]
