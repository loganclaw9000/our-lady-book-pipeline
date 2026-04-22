"""EntityStateRetriever — queries the entity_state LanceDB table.

Zero-cards-tolerance (02-CONTEXT.md "entity_state retriever" section): when the
table is empty (Phase 4's auto-generated entity cards haven't landed yet,
PITFALLS I-1 transient-entity-cold-start state), retrieve() MUST return a
valid empty RetrievalResult, NEVER raise. This is the load-bearing guarantee
for Phase 4's scene-sequencer entry path.

Sources (Plan 02 ingestion routing):
  - Primary: pantheon.md + secondary-characters.md (routed to entity_state by
    the book-specific corpus-paths axis map established in Plan 02-02).
  - Secondary: entity-state/*.md (Phase 4 CORPUS-02 territory; empty at Phase 2
    landing — the zero-cards case handled here).

W-2 compliance: explicit keyword-only __init__ args. No positional-splat forwarding.
B-2 compliance: inherits reindex(self) -> None unchanged from base. The frozen
Protocol signature stays zero-arg after self; no classmethod workarounds. Phase
4's EntityExtractor (CORPUS-02) may override reindex later to re-scan the
entity-state/ directory; this plan doesn't need that.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from book_pipeline.interfaces.types import SceneRequest
from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

if TYPE_CHECKING:  # pragma: no cover
    from book_pipeline.rag.embedding import BgeM3Embedder
    from book_pipeline.rag.reranker import BgeReranker


class EntityStateRetriever(LanceDBRetrieverBase):
    def __init__(
        self,
        *,
        db_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        **kw: Any,
    ) -> None:
        super().__init__(name="entity_state", db_path=db_path, embedder=embedder, reranker=reranker, **kw)

    def _build_query_text(self, request: SceneRequest) -> str:
        # POV + location + date + beat context — entity cards are filtered by
        # POV-keyword semantic match, NOT by a hard SQL filter (tag-free).
        return (
            f"{request.pov} state at {request.location} on {request.date_iso}; "
            f"beat context: {request.beat_function}"
        )


__all__ = ["EntityStateRetriever"]
