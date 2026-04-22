"""Stub Retriever — raises NotImplementedError. Concrete impl lands in Phase 2 (RAG-01)."""

from __future__ import annotations

from book_pipeline.interfaces.retriever import Retriever
from book_pipeline.interfaces.types import RetrievalResult, SceneRequest


class StubRetriever:
    """Structurally satisfies Retriever Protocol. All methods raise NotImplementedError."""

    name: str = "stub"

    def retrieve(self, request: SceneRequest) -> RetrievalResult:
        raise NotImplementedError(
            "StubRetriever.retrieve: concrete impl lands in Phase 2 (RAG-01)."
        )

    def reindex(self) -> None:
        raise NotImplementedError("StubRetriever.reindex: concrete impl lands in Phase 2 (RAG-01).")

    def index_fingerprint(self) -> str:
        raise NotImplementedError(
            "StubRetriever.index_fingerprint: concrete impl lands in Phase 2 (RAG-01)."
        )


# Verify structural typing at import time (fails early if Protocol changes).
_: Retriever = StubRetriever()
