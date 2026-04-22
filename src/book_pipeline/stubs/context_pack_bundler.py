"""Stub ContextPackBundler — NotImplementedError. Concrete impl lands in Phase 2 (RAG-01)."""

from __future__ import annotations

from book_pipeline.interfaces.context_pack_bundler import ContextPackBundler
from book_pipeline.interfaces.retriever import Retriever
from book_pipeline.interfaces.types import ContextPack, SceneRequest


class StubContextPackBundler:
    """Structurally satisfies ContextPackBundler Protocol. NotImplementedError on every call."""

    def bundle(self, request: SceneRequest, retrievers: list[Retriever]) -> ContextPack:
        raise NotImplementedError(
            "StubContextPackBundler.bundle: concrete impl lands in Phase 2 (RAG-01)."
        )


_: ContextPackBundler = StubContextPackBundler()
