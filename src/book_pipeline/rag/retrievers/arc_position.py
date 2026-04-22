"""ArcPositionRetriever — queries the arc_position LanceDB table.

RAG-02: beat IDs from outline_parser are preserved as chunk_ids. This retriever's
reindex() uses outline_parser (NOT chunk_markdown), so beat-ID stability is
guaranteed — scene cross-references keyed on beat_function survive re-ingestion.

B-2 (revision): reindex(self) -> None matches the frozen Protocol signature
exactly. All state (outline_path, ingestion_run_id, embedder) is stored in
__init__ and read from self.* during reindex — no method-level args, no
classmethod workarounds.

W-5 (revision): chapter-scoped retrieval uses exact-equality on the `chapter`
int column added to CHUNK_SCHEMA by Plan 02-01. Replaces the fragile
prefix-match-on-heading-string approach from the original plan (which would
have false-matched "Chapter 1" against "Chapter 10..19" without careful space
discipline).

CorpusIngester (Plan 02-02) ingests outline.md as plain markdown chunks routed
to the arc_position axis by filename; ArcPositionRetriever.reindex() then
OVERWRITES that table with beat-ID-stable rows. Plan 06 CLI is expected to
call reindex() after ingest; no classmethod wrapper is required.

W-2 compliance: explicit keyword-only __init__ args.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from book_pipeline.interfaces.types import SceneRequest
from book_pipeline.observability.hashing import hash_text
from book_pipeline.rag.lance_schema import open_or_create_table
from book_pipeline.rag.outline_parser import parse_outline
from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

if TYPE_CHECKING:  # pragma: no cover
    from book_pipeline.rag.embedding import BgeM3Embedder
    from book_pipeline.rag.reranker import BgeReranker


class ArcPositionRetriever(LanceDBRetrieverBase):
    def __init__(
        self,
        *,
        db_path: Path,
        outline_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        ingestion_run_id: str | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(name="arc_position", db_path=db_path, embedder=embedder, reranker=reranker, **kw)
        self.outline_path = Path(outline_path)
        self.ingestion_run_id = ingestion_run_id

    def _build_query_text(self, request: SceneRequest) -> str:
        return (
            f"chapter {request.chapter} beat {request.beat_function} from "
            f"{request.pov}'s perspective at {request.location}"
        )

    def _where_clause(self, request: SceneRequest) -> str | None:
        # W-5: exact-equality filter on the chapter int column (Plan 02-01
        # CHUNK_SCHEMA). int() cast is belt-and-suspenders against format-
        # injection; Pydantic already types request.chapter as int, so this
        # is double-guarded. Eliminates the prefix-match-collision class of bug
        # from the plan's original heading-path-prefix approach (e.g. "Chapter 1 "
        # prefix-matching "Chapter 10..19" would have leaked rows).
        return f"chapter = {int(request.chapter)}"

    def reindex(self) -> None:
        """B-2: Protocol-conformant signature (self only). State from __init__.

        Re-parses self.outline_path into beat-granularity rows and OVERWRITES
        the arc_position LanceDB table with them. chunk_id == beat_id
        (RAG-02 stability); chapter int column populated directly from the
        parsed Beat.chapter (W-5).
        """
        text = self.outline_path.read_text()
        beats = parse_outline(text)
        tbl = open_or_create_table(self.db_path, "arc_position")
        # Full rebuild — truncate and rewrite. LanceDB's delete supports a
        # SQL-esque predicate; "true" deletes every row.
        tbl.delete("true")
        if not beats:
            return
        run_id = self.ingestion_run_id or f"arc_{hash_text(text)[:16]}"
        vectors = self.embedder.embed_texts([b.body for b in beats])
        rows = [
            {
                "chunk_id": b.beat_id,
                "text": b.body,
                "source_file": str(self.outline_path),
                "heading_path": b.heading_path,
                "rule_type": "beat",
                "ingestion_run_id": run_id,
                "chapter": b.chapter,  # W-5: direct int column population
                "embedding": v.tolist(),
            }
            for b, v in zip(beats, vectors, strict=True)
        ]
        tbl.add(rows)


__all__ = ["ArcPositionRetriever"]
