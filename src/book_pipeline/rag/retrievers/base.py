"""LanceDBRetrieverBase — shared retriever machinery for the 5 typed RAG axes.

Concrete retrievers (historical, metaphysics, negative_constraint here in Plan
02-03; entity_state, arc_position in Plan 02-04) subclass this base and
customize two hooks:

  - `_build_query_text(request)` — the query string passed to the embedder.
  - `_where_clause(request)` — optional SQL-esque filter for LanceDB.search.

The base class handles the common machinery:

  1. Compute `query_fingerprint = hash_text(request.model_dump_json())`.
  2. Open the axis's LanceDB table via `open_or_create_table`.
  3. Short-circuit if the table is empty (return a valid empty RetrievalResult).
  4. Embed the query text with the shared BgeM3Embedder.
  5. Run `table.search(query_vec).limit(candidate_k)` with optional where clause.
  6. Rerank the candidates with BgeReranker to pick top `final_k`.
  7. Build RetrievalHit instances carrying text + source_path + chunk_id +
     rerank_score + metadata (rule_type, heading_path, ingestion_run_id,
     chapter, vector_distance).
  8. Return RetrievalResult with retriever_name=self.name.

B-2 frozen-Protocol compliance: `reindex(self) -> None` has NO extra positional
or keyword arguments. Any state the subclass needs for axis-specific reindex
(e.g., ArcPositionRetriever's `outline_path`) is stored on `self` at `__init__`
time and read during `reindex()`.

Retrievers NEVER log observability events directly (Protocol docstring contract
— the bundler in Plan 05 is the event-emission site for all 5 retrievers).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from book_pipeline.interfaces.types import RetrievalHit, RetrievalResult, SceneRequest
from book_pipeline.observability.hashing import hash_text
from book_pipeline.rag.lance_schema import open_or_create_table

if TYPE_CHECKING:  # pragma: no cover — avoid runtime dep / import cycles in type hints.
    from book_pipeline.rag.embedding import BgeM3Embedder
    from book_pipeline.rag.reranker import BgeReranker

_LOG = logging.getLogger(__name__)


class LanceDBRetrieverBase:
    """Shared retriever machinery — concrete axis retrievers subclass this.

    Subclasses MUST override `_build_query_text`. They MAY override
    `_where_clause` if the axis needs a SQL-like filter (metaphysics: rule_type).
    """

    def __init__(
        self,
        *,
        name: str,
        db_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        candidate_k: int = 50,
        final_k: int = 8,
        ingestion_run_id: str | None = None,
    ) -> None:
        self.name = name
        self.db_path = Path(db_path)
        self.embedder = embedder
        self.reranker = reranker
        self.candidate_k = candidate_k
        self.final_k = final_k
        # Plan 03-07 W-1: uniform ingestion_run_id kw accepted by the factory
        # (build_retrievers_from_config). Subclasses that need it for reindex
        # (ArcPositionRetriever) may override by also setting it on self; the
        # base stores it defensively so the factory signature stays uniform.
        self.ingestion_run_id = ingestion_run_id

    # --- Subclass hooks ----------------------------------------------------

    def _build_query_text(self, request: SceneRequest) -> str:
        """Build the query text that will be embedded. Subclasses MUST override."""
        raise NotImplementedError(
            "LanceDBRetrieverBase subclass must implement _build_query_text()"
        )

    def _where_clause(self, request: SceneRequest) -> str | None:
        """Optional SQL-esque filter applied to LanceDB.search. Default: no filter.

        Subclasses override to add axis-specific filters (e.g., MetaphysicsRetriever
        returns `rule_type IN ('rule')`).
        """
        return None

    # --- Protocol impl -----------------------------------------------------

    def retrieve(self, request: SceneRequest) -> RetrievalResult:
        """Return top-final_k hits for `request` as a RetrievalResult."""
        query_fingerprint = hash_text(request.model_dump_json())
        table = open_or_create_table(self.db_path, self.name)

        # Empty-table tolerance (entity_state zero-cards guarantee from
        # 02-CONTEXT.md, applied here as a general safety net).
        if table.count_rows() == 0:
            return RetrievalResult(
                retriever_name=self.name,
                hits=[],
                bytes_used=0,
                query_fingerprint=query_fingerprint,
            )

        query_text = self._build_query_text(request)
        query_vec = self.embedder.embed_texts([query_text])[0]  # drop batch dim

        search = table.search(query_vec).limit(self.candidate_k)
        where = self._where_clause(request)
        if where is not None:
            search = search.where(where)

        candidates_rows: list[dict[str, Any]] = search.to_list()
        # Feed the reranker (text, original_row) pairs so we can re-hydrate
        # metadata from the winning rows without a second LanceDB round-trip.
        pair_inputs: list[tuple[str, Any]] = [
            (row["text"], row) for row in candidates_rows
        ]
        reranked = self.reranker.rerank(
            query_text, pair_inputs, top_k=self.final_k
        )

        hits = [
            RetrievalHit(
                text=text,
                source_path=row["source_file"],
                chunk_id=row["chunk_id"],
                score=rerank_score,
                metadata={
                    "rule_type": row["rule_type"],
                    "heading_path": row["heading_path"],
                    "ingestion_run_id": row["ingestion_run_id"],
                    "chapter": row.get("chapter"),
                    "vector_distance": row.get("_distance"),
                    # Plan 05-03 (D-11 / SC6): entity_state rows carry the
                    # source_chapter_sha stamped at extraction time. Other
                    # axes carry None (corpus-immutable). Bundler's
                    # scan_for_stale_cards reads this for the stale-card
                    # conflict signal.
                    "source_chapter_sha": row.get("source_chapter_sha"),
                },
            )
            for (text, row, rerank_score) in reranked
        ]
        bytes_used = sum(len(h.text.encode("utf-8")) for h in hits)
        return RetrievalResult(
            retriever_name=self.name,
            hits=hits,
            bytes_used=bytes_used,
            query_fingerprint=query_fingerprint,
        )

    def reindex(self) -> None:
        """B-2: EXACT frozen Protocol signature — no extra args.

        The base class reindex is a no-op. `CorpusIngester` (Plan 02) owns
        full-corpus reindex during ingestion. Subclasses that need an
        axis-specific reindex step (e.g., ArcPositionRetriever re-parsing
        outline.md from `self.outline_path`) override this method while
        keeping the zero-arg signature.
        """
        _LOG.info(
            "LanceDBRetrieverBase.reindex is a no-op for %s; "
            "CorpusIngester owns full-corpus reindex. Override in subclass if "
            "axis-specific reindex is required (e.g. ArcPositionRetriever).",
            self.name,
        )

    def index_fingerprint(self) -> str:
        """Stable fingerprint of the axis table's current ingestion state.

        Implementation: open the axis table, collect the set of distinct
        `ingestion_run_id` values (all rows in one ingestion share an id),
        sort, join with '|', and return `hash_text(joined)`. Empty tables
        return the literal string "empty".
        """
        table = open_or_create_table(self.db_path, self.name)
        if table.count_rows() == 0:
            return "empty"
        # to_arrow() avoids the pandas round-trip; iterate the column directly.
        col = table.to_arrow()["ingestion_run_id"].to_pylist()
        unique = sorted(set(col))
        joined = "|".join(unique)
        return hash_text(joined)


__all__ = ["LanceDBRetrieverBase"]
