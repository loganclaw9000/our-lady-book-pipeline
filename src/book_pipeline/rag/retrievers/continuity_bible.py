"""ContinuityBibleRetriever — 6th RAG axis (Plan 07-02 PHYSICS-04 / D-22).

Retrieves canonical-quantity rows from a dedicated LanceDB table. The
'continuity_bible' axis is a NEW VALUE for the existing rule_type column
('canonical_quantity') — NOT a new schema column (D-22 + Plan 05-03 D-11
additive-nullable contract).

Retrieval semantics (07-RESEARCH.md Pattern 3):
  - Primary: entity-name fuzzy semantic match. Query string names the
    entity-and-context ("Andrés age and origin", "La Niña ship dimensions");
    top-K embedding match.
  - Secondary: deterministic dict-style direct lookup INSIDE the returned row.
    Each row's text field is structured (parseable). Bundler/drafter extracts
    the value verbatim for the D-23 prompt-header stamp. The embedder surfaces
    the right row; the consumer reads the value out.

PITFALLS R-4 analog: rule_type='canonical_quantity' filter is defense in
depth — the dedicated 'continuity_bible' table holds only CB-01 rows in v1,
but the WHERE clause guarantees that any cross-axis schema accident (e.g., a
mistakenly-shared table during ingest) cannot leak non-canonical rows.

W-2 compliance: explicit keyword-only __init__ args; no positional-splat
forwarding.

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


class ContinuityBibleRetriever(LanceDBRetrieverBase):
    """6th retriever — named-quantity continuity (D-15 / D-22 / PHYSICS-04)."""

    def __init__(
        self,
        *,
        db_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        **kw: Any,
    ) -> None:
        super().__init__(
            name="continuity_bible",
            db_path=db_path,
            embedder=embedder,
            reranker=reranker,
            **kw,
        )

    def _build_query_text(self, request: SceneRequest) -> str:
        # Surface POV character + location + date + beat so canonical-quantity
        # rows for those tokens rerank high (07-RESEARCH.md Pattern 3).
        return (
            f"canonical named quantities for {request.pov} at {request.location} "
            f"on {request.date_iso}; beat: {request.beat_function}; "
            f"chapter: ch{int(request.chapter):02d}"
        )

    def _where_clause(self, request: SceneRequest) -> str | None:
        # Filter to canonical_quantity rows only — defense in depth even though
        # the dedicated table holds only CB-01 rows (D-22 contract).
        return "rule_type = 'canonical_quantity'"


__all__ = ["ContinuityBibleRetriever"]
