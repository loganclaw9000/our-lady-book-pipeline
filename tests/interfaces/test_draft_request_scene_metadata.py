"""DraftRequest.scene_metadata additive-nullable field (Plan 07-01 Task 2).

Covers Tests 13-14 from the plan <behavior> block:
- Test 13: DraftRequest with scene_metadata=None validates and round-trips.
- Test 14: DraftRequest with explicit SceneMetadata validates + round-trips;
  backward-compat constructor (no scene_metadata kwarg) also validates.

Importing book_pipeline.physics triggers
``_rebuild_for_physics_forward_ref()`` (called from physics/__init__.py),
which resolves the SceneMetadata forward-ref on DraftRequest.
"""

from __future__ import annotations

from typing import Any

# Importing book_pipeline.physics triggers DraftRequest.model_rebuild() so the
# SceneMetadata forward-ref resolves. Required at module-load time before any
# DraftRequest with a non-None scene_metadata is constructed.
import book_pipeline.physics  # noqa: F401
from book_pipeline.interfaces.types import (
    ContextPack,
    DraftRequest,
    SceneRequest,
)
from book_pipeline.physics.schema import SceneMetadata


def _minimal_context_pack() -> ContextPack:
    return ContextPack(
        scene_request=SceneRequest(
            chapter=15,
            scene_index=2,
            pov="Andres",
            date_iso="1519-08-30",
            location="Cempoala",
            beat_function="warning",
        ),
        retrievals={},
        total_bytes=0,
        fingerprint="t1",
    )


def test_draft_request_backward_compat_no_scene_metadata() -> None:
    """Test 14b: existing instantiation pattern (no scene_metadata kwarg) validates."""
    req = DraftRequest(context_pack=_minimal_context_pack())
    assert req.scene_metadata is None


def test_draft_request_with_explicit_none() -> None:
    """Test 13: DraftRequest with scene_metadata=None validates."""
    req = DraftRequest(context_pack=_minimal_context_pack(), scene_metadata=None)
    assert req.scene_metadata is None
    # Round-trip JSON.
    dump = req.model_dump_json()
    rehydrated = DraftRequest.model_validate_json(dump)
    assert rehydrated.scene_metadata is None


def test_draft_request_with_scene_metadata(
    valid_scene_payload_for_drafter: dict[str, Any],
) -> None:
    """Test 14a: DraftRequest with valid SceneMetadata validates + round-trips."""
    sm = SceneMetadata.model_validate(valid_scene_payload_for_drafter)
    req = DraftRequest(
        context_pack=_minimal_context_pack(),
        scene_metadata=sm,
    )
    assert req.scene_metadata is not None
    assert req.scene_metadata.chapter == 15
    assert req.scene_metadata.scene_index == 2

    # Round-trip JSON — verifies the forward-ref resolves under
    # model_validate_json as well as direct construction.
    dump = req.model_dump_json()
    rehydrated = DraftRequest.model_validate_json(dump)
    assert rehydrated.scene_metadata is not None
    assert rehydrated.scene_metadata.chapter == 15
    assert rehydrated.scene_metadata.scene_index == 2
    # canonical scene_id derivation pin (T-07-02 echo)
    assert (
        f"ch{rehydrated.scene_metadata.chapter:02d}"
        f"_sc{rehydrated.scene_metadata.scene_index:02d}"
        == "ch15_sc02"
    )


def test_draft_request_scene_metadata_is_in_model_fields() -> None:
    """The scene_metadata field is present in DraftRequest.model_fields."""
    assert "scene_metadata" in DraftRequest.model_fields
