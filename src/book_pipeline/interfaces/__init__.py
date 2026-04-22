"""book_pipeline.interfaces — Protocol contracts + Pydantic type models.

FOUND-04 requirement: 13 Protocols importable from this module. Concrete
implementations live in book_pipeline.stubs (Phase 1) and later phases'
production modules.

Event schema (OBS-01) is frozen at end of Phase 1. Later phases may add
OPTIONAL fields to Event; never rename or remove.

Protocols (12 PEP-544 runtime-checkable Protocols):
    Retriever, ContextPackBundler, Drafter, Critic, Regenerator,
    ChapterAssembler, EntityExtractor, RetrospectiveWriter, ThesisMatcher,
    DigestGenerator, Orchestrator, EventLogger

The 13th interface — SceneStateMachine — is intentionally not a Protocol;
it's a Pydantic model (SceneStateRecord) + Enum (SceneState) + pure-Python
helper (transition).
"""

from book_pipeline.interfaces.chapter_assembler import ChapterAssembler
from book_pipeline.interfaces.context_pack_bundler import ContextPackBundler
from book_pipeline.interfaces.critic import Critic
from book_pipeline.interfaces.digest_generator import DigestGenerator
from book_pipeline.interfaces.drafter import Drafter
from book_pipeline.interfaces.entity_extractor import EntityExtractor
from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.orchestrator import Orchestrator
from book_pipeline.interfaces.regenerator import Regenerator
from book_pipeline.interfaces.retriever import Retriever
from book_pipeline.interfaces.retrospective_writer import RetrospectiveWriter
from book_pipeline.interfaces.scene_state_machine import (
    SceneState,
    SceneStateRecord,
    transition,
)
from book_pipeline.interfaces.thesis_matcher import ThesisMatcher
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
    "ChapterAssembler",
    "ContextPack",
    "ContextPackBundler",
    "Critic",
    "CriticIssue",
    "CriticRequest",
    "CriticResponse",
    "DigestGenerator",
    "DraftRequest",
    "DraftResponse",
    "Drafter",
    "EntityCard",
    "EntityExtractor",
    "Event",
    "EventLogger",
    "Orchestrator",
    "RegenRequest",
    "Regenerator",
    "RetrievalHit",
    "RetrievalResult",
    "Retriever",
    "Retrospective",
    "RetrospectiveWriter",
    "SceneRequest",
    "SceneState",
    "SceneStateRecord",
    "ThesisEvidence",
    "ThesisMatcher",
    "transition",
]
