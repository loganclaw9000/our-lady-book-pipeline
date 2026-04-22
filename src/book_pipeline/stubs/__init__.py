"""book_pipeline.stubs — non-functional structural stubs for all 13 interfaces.

Every stub satisfies `isinstance(stub, CorrespondingProtocol)` (FOUND-04 SC-4)
but raises NotImplementedError on every method. Concrete implementations arrive
in later-phase plans (referenced in each stub's docstring).

Rationale (ADR-004 / CONTEXT.md D-04):
  - Phase 1 freezes the interface contract.
  - Phase 3/4/5 code can import and compose against these Protocols before
    concrete implementations exist.
  - Structural typing is verified at import time in each stub module via
    `_: Protocol = StubX()` assignment — if a Protocol's shape drifts, imports
    will fail fast.
"""

from book_pipeline.stubs.chapter_assembler import StubChapterAssembler
from book_pipeline.stubs.context_pack_bundler import StubContextPackBundler
from book_pipeline.stubs.critic import StubCritic
from book_pipeline.stubs.digest_generator import StubDigestGenerator
from book_pipeline.stubs.drafter import StubDrafter
from book_pipeline.stubs.entity_extractor import StubEntityExtractor
from book_pipeline.stubs.event_logger import StubEventLogger
from book_pipeline.stubs.orchestrator import StubOrchestrator
from book_pipeline.stubs.regenerator import StubRegenerator
from book_pipeline.stubs.retriever import StubRetriever
from book_pipeline.stubs.retrospective_writer import StubRetrospectiveWriter
from book_pipeline.stubs.scene_state_machine import StubSceneStateMachine
from book_pipeline.stubs.thesis_matcher import StubThesisMatcher

__all__ = [
    "StubChapterAssembler",
    "StubContextPackBundler",
    "StubCritic",
    "StubDigestGenerator",
    "StubDrafter",
    "StubEntityExtractor",
    "StubEventLogger",
    "StubOrchestrator",
    "StubRegenerator",
    "StubRetriever",
    "StubRetrospectiveWriter",
    "StubSceneStateMachine",
    "StubThesisMatcher",
]
