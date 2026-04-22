"""ContextPackBundler Protocol — assembles 5 retrievers' output into one ContextPack.

Pre-conditions:
  - All Retrievers passed to bundle() are ready (indexes built).
  - SceneRequest is validated.

Post-conditions:
  - Returned ContextPack contains a RetrievalResult per retriever (keyed by name).
  - total_bytes is the sum of retriever bytes_used values; enforces the ~30-40KB
    cap documented in RAG-01 (bundler may trim low-score hits to stay under cap).
  - fingerprint is a stable hash of the full pack (used by the Drafter as a
    cache key).

Swap points: round-robin bundler (default), relevance-weighted bundler
(future ablation under RAG thesis).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_pipeline.interfaces.retriever import Retriever
from book_pipeline.interfaces.types import ContextPack, SceneRequest


@runtime_checkable
class ContextPackBundler(Protocol):
    """Combines N typed retriever outputs into one ContextPack.
    Concrete impl in Phase 2 (RAG-01)."""

    def bundle(self, request: SceneRequest, retrievers: list[Retriever]) -> ContextPack:
        """Run every retriever, assemble into a ContextPack under the byte cap."""
        ...
