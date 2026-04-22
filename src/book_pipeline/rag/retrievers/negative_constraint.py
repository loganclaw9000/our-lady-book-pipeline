"""NegativeConstraintRetriever — retrieves from the 'negative_constraint' LanceDB table.

PITFALLS R-5 mitigation: ALWAYS returns top-K regardless of tag match. Tag-based
filtering lives in the BUNDLER (Plan 02-05), never in this retriever — this
prevents the 'silent miss' failure where a scene's tag set doesn't match an
avoid-tag and the constraint never surfaces.

Sources (Plan 02 ingestion routing): known-liberties.md (Things to Avoid
section + calibration notes).

W-2 compliance: explicit keyword-only __init__ args. No positional-splat forwarding.
B-2 compliance: inherits `reindex(self) -> None` unchanged from base.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from book_pipeline.interfaces.types import SceneRequest
from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

if TYPE_CHECKING:  # pragma: no cover
    from book_pipeline.rag.embedding import BgeM3Embedder
    from book_pipeline.rag.reranker import BgeReranker


class NegativeConstraintRetriever(LanceDBRetrieverBase):
    def __init__(
        self,
        *,
        db_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        **kw: Any,
    ) -> None:
        super().__init__(name="negative_constraint", db_path=db_path, embedder=embedder, reranker=reranker, **kw)

    def _build_query_text(self, request: SceneRequest) -> str:
        return (
            f"landmines and things to avoid when {request.pov} is at "
            f"{request.location} on {request.date_iso}; beat: {request.beat_function}"
        )

    def _where_clause(self, request: SceneRequest) -> str | None:
        # DELIBERATE NO-OP — per PITFALLS R-5 we MUST return top-K unconditionally
        # and let the bundler filter on match. Do NOT add tag filtering here.
        return None


__all__ = ["NegativeConstraintRetriever"]
