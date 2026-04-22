"""MetaphysicsRetriever — retrieves from the 'metaphysics' LanceDB table.

PITFALLS R-4 mitigation: `rule_type='rule'` default filter. Hypothetical,
example, and cross_reference chunks are EXCLUDED unless the caller passes
`include_rule_types` to widen the allowed set.

Sources (Plan 02 ingestion routing): engineering.md, relics.md, and
brief.md metaphysics-classified headings. The chunker stamps each chunk with
a `rule_type` label; this retriever filters on that label at query time.

W-2 compliance: explicit keyword-only __init__ args (include_rule_types is
keyword-only). No positional-splat forwarding.
B-2 compliance: inherits `reindex(self) -> None` unchanged from base.

Security: `include_rule_types` is validated with a strict regex
`^[a-z_]+$` before being embedded into the SQL-esque where clause. Any
non-conforming value raises ValueError — prevents injection through the
where clause even though callers today are all trusted (defense in depth).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from book_pipeline.interfaces.types import SceneRequest
from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

if TYPE_CHECKING:  # pragma: no cover
    from book_pipeline.rag.embedding import BgeM3Embedder
    from book_pipeline.rag.reranker import BgeReranker


_RULE_TYPE_RE = re.compile(r"[a-z_]+")


class MetaphysicsRetriever(LanceDBRetrieverBase):
    def __init__(
        self,
        *,
        db_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        include_rule_types: tuple[str, ...] = ("rule",),
        **kw: Any,
    ) -> None:
        super().__init__(name="metaphysics", db_path=db_path, embedder=embedder, reranker=reranker, **kw)
        self._rule_types: tuple[str, ...] = tuple(include_rule_types)

    def _build_query_text(self, request: SceneRequest) -> str:
        return (
            f"{request.beat_function} engine metaphysics rules "
            f"at {request.location} on {request.date_iso}"
        )

    def _where_clause(self, request: SceneRequest) -> str | None:
        # PITFALLS R-4: restrict to 'rule' chunks by default; hypothetical/example
        # excluded. Injection guard: only accept alphanumeric-underscore values.
        for rt in self._rule_types:
            if not _RULE_TYPE_RE.fullmatch(rt):
                raise ValueError(f"Invalid rule_type: {rt!r}")
        quoted = ", ".join(f"'{rt}'" for rt in self._rule_types)
        return f"rule_type IN ({quoted})"


__all__ = ["MetaphysicsRetriever"]
