"""HistoricalRetriever — retrieves from the 'historical' LanceDB table.

Sources (Plan 02 ingestion routing): brief.md historical-classified headings,
glossary.md, maps.md. Query shape: date_iso + location + beat_function + POV.
No where_clause — historical is a factual retriever; rule_type defaults to
'rule' at chunk time for these corpus files.

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


class HistoricalRetriever(LanceDBRetrieverBase):
    def __init__(
        self,
        *,
        db_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        **kw: Any,
    ) -> None:
        super().__init__(name="historical", db_path=db_path, embedder=embedder, reranker=reranker, **kw)

    def _build_query_text(self, request: SceneRequest) -> str:
        return (
            f"{request.date_iso} {request.location} {request.beat_function} "
            f"historical context for {request.pov}"
        )


__all__ = ["HistoricalRetriever"]
