"""Retriever Protocol — one typed retriever per RAG axis (5 total in production).

Pre-conditions:
  - Index has been built (see reindex()) and is loadable from disk.
  - Caller has constructed a valid SceneRequest.

Post-conditions:
  - Returned RetrievalResult.retriever_name equals self.name.
  - query_fingerprint is a stable hash of the SceneRequest (used as cache key).
  - bytes_used counts the total retrieved text payload.
  - EventLogger is NOT directly called here; retriever events are emitted by the
    ContextPackBundler that orchestrates all 5 retrievers.

Swap points: LanceDB-backed retriever (Phase 2 primary), in-memory stub (Phase 1),
future hybrid BGE-M3 + sparse variants.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.types import RetrievalResult, SceneRequest


@runtime_checkable
class Retriever(Protocol):
    """One of the 5 typed retrievers (historical, metaphysics, entity_state,
    arc_position, negative_constraint). Concrete impls in Phase 2 (RAG-01)."""

    name: str

    def retrieve(self, request: SceneRequest) -> RetrievalResult:
        """Return structured retrieval results for one scene request."""
        ...

    def reindex(self) -> None:
        """Rebuild the index from disk sources (corpus refresh)."""
        ...

    def index_fingerprint(self) -> str:
        """Return a stable identifier for the current index state (for cache keys)."""
        ...
