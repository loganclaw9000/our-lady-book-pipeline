"""CanonBibleView (Plan 07-03 D-09) — read-only composer over CB-01 + entity_state + retrospectives.

Per Pitfall 11 (07-RESEARCH.md lines 673-682): NO module-scope cache decorator
(grep-acceptance). Per-bundle local dict memoization only. Builds once per scene-loop iteration, consumed by the
quantity pre-flight gate AND the drafter prompt header (D-23 canonical stamp).

Plan 07-02 ContinuityBibleRetriever (CB-01) populates LanceDB rows with chunk_id
shaped `f"canonical:{q.id}"` and text shaped `"{Name}: {value} ({chapter scope}). {Drift evidence}"`.
This composer parses each retrieved hit into a typed CanonicalQuantityRow.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from book_pipeline.interfaces.types import RetrievalResult
from book_pipeline.physics.locks import PovLock


class CanonicalQuantityRow(BaseModel):
    """Parsed canonical-quantity row (extracted from CB-01 retrieval text)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    text: str  # full row text
    name: str  # human-readable name extracted from text head ("Andres", "La Nina", ...)


class CanonBibleView:
    """Read-only composer (D-09).

    Constructed via ``build_canon_bible_view``. Holds per-bundle state; never
    module-scope cached (Pitfall 11).
    """

    def __init__(
        self,
        *,
        canonical_quantities: list[CanonicalQuantityRow],
        pov_locks: dict[str, PovLock],
    ) -> None:
        self._canonical_quantities = canonical_quantities
        self._pov_locks = pov_locks

    def get_canonical_quantity(self, entity_keyword: str) -> CanonicalQuantityRow | None:
        """Return the first canonical-quantity row whose name/id/text contains the keyword.

        Case-insensitive substring search. Returns None if no row matches.
        """
        kw = entity_keyword.lower()
        for row in self._canonical_quantities:
            if (
                kw in row.name.lower()
                or kw in row.id.lower()
                or kw in row.text.lower()
            ):
                return row
        return None

    def iter_canonical_quantities(self) -> Iterable[CanonicalQuantityRow]:
        """Iterate ALL canonical-quantity rows.

        Used by ``physics.gates.quantity`` so the gate walks the live CB-01
        rowset rather than a hardcoded keyword list (Warning #2 mitigation).
        Returns an iterator, not a list — callers that need a list call ``list(...)``.
        """
        return iter(self._canonical_quantities)

    def get_pov_lock(self, character: str) -> PovLock | None:
        """Return the per-character PovLock if registered (case-insensitive)."""
        return self._pov_locks.get(character.lower())

    def format_stamp(self) -> str:
        """Top-of-prompt CANONICAL stamp string (D-23). Empty list -> empty string.

        Format: ``"CANONICAL: <head1> | <head2> | ..."`` where each ``head`` is
        the leading sentence of the canonical-quantity row text (everything
        before the first period). Each row's text is structured
        ``"<Name>: <value> (<chapter scope>). <Drift evidence>"`` so this
        extracts the name+value+scope head and discards the drift narrative.
        """
        if not self._canonical_quantities:
            return ""
        parts: list[str] = []
        for row in self._canonical_quantities:
            head = row.text.split(".", 1)[0].strip()
            if head:
                parts.append(head)
        return "CANONICAL: " + " | ".join(parts)


_CHUNK_ID_RE = re.compile(r"^canonical:([a-z0-9_]+)$")


def build_canon_bible_view(
    *,
    cb01_retrieval: RetrievalResult | None,
    pov_locks: dict[str, PovLock],
) -> CanonBibleView:
    """Build a CanonBibleView from already-bundled CB-01 retrieval + pov_locks.

    Args:
        cb01_retrieval: result of bundler's CB-01 query (None if no CB-01 axis
            in the bundle — e.g., legacy 5-axis flow).
        pov_locks: result of ``load_pov_locks()`` (loaded once at composition root).
    """
    canonical_rows: list[CanonicalQuantityRow] = []
    if cb01_retrieval is not None:
        for hit in cb01_retrieval.hits:
            m = _CHUNK_ID_RE.match(hit.chunk_id)
            qid = m.group(1) if m else hit.chunk_id
            # Plan 07-02 ingest stamps row text as `"{Name}: {value} (...). ..."`.
            # Extract `Name` as everything before the first colon.
            name = hit.text.split(":", 1)[0].strip() if ":" in hit.text else qid
            canonical_rows.append(
                CanonicalQuantityRow(id=qid, text=hit.text, name=name)
            )
    return CanonBibleView(
        canonical_quantities=canonical_rows,
        pov_locks=pov_locks,
    )


__all__ = ["CanonBibleView", "CanonicalQuantityRow", "build_canon_bible_view"]
