"""Narrative Physics kernel package (Phase 7).

ADR-004 clean boundary — book-domain-free. Imports from
``book_pipeline.book_specifics`` are prohibited by import-linter contract 1;
imports into ``book_pipeline.interfaces`` are prohibited by contract 2 EXCEPT
for the additive scene_metadata field on DraftRequest, which uses a
TYPE_CHECKING forward-string + lazy ``model_rebuild()`` triggered from this
module (kernel-cycle stays empty at runtime).

Single-file modules per ADR-004 (this plan lands schema.py / locks.py /
gates/base.py; later plans land canon_bible.py, stub_leak.py,
repetition_loop.py, scene_buffer.py).
"""

from book_pipeline.interfaces.types import _rebuild_for_physics_forward_ref
from book_pipeline.physics.canon_bible import (
    CanonBibleView,
    CanonicalQuantityRow,
    build_canon_bible_view,
)
from book_pipeline.physics.gates import (
    GateError,
    GateResult,
    emit_gate_event,
    run_pre_flight,
)
from book_pipeline.physics.locks import PovLock, load_pov_locks
from book_pipeline.physics.schema import (
    BeatTag,
    CharacterPresence,
    Contents,
    Perspective,
    SceneMetadata,
    Staging,
    Treatment,
    ValueCharge,
)

# Resolve DraftRequest.scene_metadata forward-ref now that SceneMetadata is
# importable. Done at first physics import so any caller that has imported
# `book_pipeline.physics` (directly or transitively) gets a fully-resolved
# DraftRequest model.
_rebuild_for_physics_forward_ref()
del _rebuild_for_physics_forward_ref  # internal only

__all__ = [
    "BeatTag",
    "CanonBibleView",
    "CanonicalQuantityRow",
    "CharacterPresence",
    "Contents",
    "GateError",
    "GateResult",
    "Perspective",
    "PovLock",
    "SceneMetadata",
    "Staging",
    "Treatment",
    "ValueCharge",
    "build_canon_bible_view",
    "emit_gate_event",
    "load_pov_locks",
    "run_pre_flight",
]
