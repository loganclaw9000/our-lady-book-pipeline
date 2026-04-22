"""book_pipeline.interfaces — Protocol contracts + Pydantic type models.

FOUND-04 requirement: 13 Protocols importable from this module. Concrete
implementations live in book_pipeline.stubs (Phase 1) and later phases'
production modules.

Event schema (OBS-01) is frozen at end of Phase 1. Later phases may add
OPTIONAL fields to Event; never rename or remove.

Protocols (task 2 adds these to the namespace):
    Retriever, ContextPackBundler, Drafter, Critic, Regenerator,
    ChapterAssembler, EntityExtractor, RetrospectiveWriter, ThesisMatcher,
    DigestGenerator, Orchestrator, EventLogger
"""
from book_pipeline.interfaces.scene_state_machine import (
    SceneState,
    SceneStateRecord,
    transition,
)
from book_pipeline.interfaces.types import (
    ContextPack,
    CriticIssue,
    CriticRequest,
    CriticResponse,
    DraftRequest,
    DraftResponse,
    EntityCard,
    Event,
    RegenRequest,
    RetrievalHit,
    RetrievalResult,
    Retrospective,
    SceneRequest,
    ThesisEvidence,
)

__all__ = [
    "ContextPack",
    "CriticIssue",
    "CriticRequest",
    "CriticResponse",
    "DraftRequest",
    "DraftResponse",
    "EntityCard",
    "Event",
    "RegenRequest",
    "RetrievalHit",
    "RetrievalResult",
    "Retrospective",
    "SceneRequest",
    "SceneState",
    "SceneStateRecord",
    "ThesisEvidence",
    "transition",
]
