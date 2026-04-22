"""book_pipeline.voice_fidelity — OBS-03 helpers (anchor curation, centroid, scoring, pin SHA).

Plan 03-01 lands this package skeleton + sha.py (compute_adapter_sha, verify_pin,
VoicePinMismatch) + scorer.py stub. Plan 03-02 lands anchors.py + the real
score_voice_fidelity implementation. Downstream plans import from this __init__
as the stable surface.

The imports below follow the Plan 02-03 retrievers/__init__.py precedent:
sha.py symbols are pre-declared via importlib + contextlib.suppress so the
package is importable even if a future wave-order regression breaks a submodule
— mirroring the B-1 robustness pattern. scorer.score_voice_fidelity is
particularly wave-sensitive (Plan 03-02 replaces the stub with the real BGE-M3
cosine impl) so its fallback is load-bearing.
"""
from __future__ import annotations

import contextlib as _contextlib
import importlib as _importlib
from typing import Any as _Any

# sha.py ships in Plan 03-01 Task 2; guarded to keep this package importable
# even if sha.py is absent mid-wave.
VoicePinMismatch: _Any = None
compute_adapter_sha: _Any = None
verify_pin: _Any = None
with _contextlib.suppress(ImportError):
    _sha = _importlib.import_module("book_pipeline.voice_fidelity.sha")
    VoicePinMismatch = getattr(_sha, "VoicePinMismatch", None)
    compute_adapter_sha = getattr(_sha, "compute_adapter_sha", None)
    verify_pin = getattr(_sha, "verify_pin", None)

# score_voice_fidelity is landed by Plan 03-02 (stub in Plan 03-01 Task 2);
# tolerate its absence here so Plan 03-01's tests (which do NOT require the
# real scorer) pass on first merge.
score_voice_fidelity: _Any = None
with _contextlib.suppress(ImportError, AttributeError):
    _scorer = _importlib.import_module("book_pipeline.voice_fidelity.scorer")
    score_voice_fidelity = getattr(_scorer, "score_voice_fidelity", None)

__all__ = [
    "VoicePinMismatch",
    "compute_adapter_sha",
    "score_voice_fidelity",
    "verify_pin",
]
