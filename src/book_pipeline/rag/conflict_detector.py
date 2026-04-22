"""Cross-retriever conflict detection. PITFALLS R-1 mitigation.

Extracts structured claims (location/date/possession) from each retrieval hit
and diffs across retrievers. Emits ConflictReports when >= 2 retrievers disagree
on the same (entity, dimension) pair.

W-1 revision: regex-only entity detection MISSES accented/non-Latin-capitalization
names common in the Mesoamerican corpus (Motecuhzoma, Malintzin, Tenochtitlán).
Hybrid approach: entity_candidates = union(regex_matches, entity_list_hits). The
entity_list is INJECTED by the CLI composition layer (Plan 06 wires in the
canonical Mesoamerican-name set from the book-domain entities module, which
lives outside this kernel package). Kernel stays clean — this module has zero
imports from that module.

Scope is deliberately SIMPLE for Phase 2 — this is a FORCING FUNCTION, not an NLI
engine. Thesis 005 in Phase 6 may replace this with a more sophisticated detector.

entity_list substrings are used only in `in`-membership checks, NEVER compiled
as regex — T-02-05-07: no regex-injection surface from a caller-supplied list.
"""

from __future__ import annotations

import re

from book_pipeline.interfaces.types import ConflictReport, RetrievalResult

# Regex patterns for English-style capitalization — complement the injected entity_list.
_LOCATION_PHRASE_RE = re.compile(
    r"(?:is at|arrives at|stays at|returns to|in)\s+([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+)*)",
)
_POSSESSION_PHRASE_RE = re.compile(
    r"(?:has|carries|possesses|holds)\s+(?:the\s+)?(\w+)\b",
)
_DATE_RE = re.compile(r"\b(\d{4}(?:-\d{2}-\d{2})?)\b")
# Capitalized name(s): "Andrés", "Juan Pablo" — unicode-aware via \w with re.UNICODE default.
_NAME_REGEX_RE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)?)\b")


def _extract_entity_candidates(
    text: str, entity_list: set[str] | None
) -> set[str]:
    """W-1: hybrid — regex matches union entity_list substring hits.

    entity_list supplies non-Latin/accented canonical forms (Motecuhzoma, Malintzin, ...)
    that English-capitalization regex would miss. Substrings are NEVER compiled
    as regex (T-02-05-07); they're plain `in`-membership checks.
    """
    regex_hits = {m.group(1).strip() for m in _NAME_REGEX_RE.finditer(text)}
    list_hits: set[str] = set()
    if entity_list:
        for name in entity_list:
            if name and name in text:
                list_hits.add(name)
    return regex_hits | list_hits


def _extract_claims_for_entity(text: str, entity: str) -> list[tuple[str, str]]:
    """For a given entity, scan text for (dimension, value) claims in a ~80-char window."""
    out: list[tuple[str, str]] = []
    for m in re.finditer(re.escape(entity), text):
        window = text[max(0, m.start() - 80) : m.end() + 80]
        for lm in _LOCATION_PHRASE_RE.finditer(window):
            out.append(("location", lm.group(1).strip()))
        for pm in _POSSESSION_PHRASE_RE.finditer(window):
            out.append(("possession", pm.group(1).strip()))
        for dm in _DATE_RE.finditer(window):
            out.append(("date", dm.group(1).strip()))
    return out


def detect_conflicts(
    retrievals: dict[str, RetrievalResult],
    entity_list: set[str] | None = None,
) -> list[ConflictReport]:
    """Diff (entity, dimension) claims across retrievers; emit a report per disagreement.

    Args:
        retrievals: dict keyed by retriever name -> RetrievalResult.
        entity_list: W-1 — optional set of canonical entity names the caller wants to
            detect (e.g., Mesoamerican names supplied by the book-domain layer
            via dependency injection from the CLI). When None, falls back to
            regex-only entity extraction (backwards-compat).

    Returns:
        Deterministic list of ConflictReport sorted by (entity, dimension).
        Empty input -> []; fully-disjoint entities across retrievers -> [].
    """
    # (entity, dimension) -> retriever_name -> set(values)
    claims_by_key: dict[tuple[str, str], dict[str, set[str]]] = {}
    evidence: dict[tuple[str, str], dict[str, list[str]]] = {}
    for retriever_name, rr in retrievals.items():
        for hit in rr.hits:
            entities = _extract_entity_candidates(hit.text, entity_list)
            for entity in entities:
                for dim, value in _extract_claims_for_entity(hit.text, entity):
                    key = (entity, dim)
                    claims_by_key.setdefault(key, {}).setdefault(
                        retriever_name, set()
                    ).add(value)
                    evidence_entry = evidence.setdefault(key, {}).setdefault(
                        retriever_name, []
                    )
                    if hit.chunk_id not in evidence_entry:
                        evidence_entry.append(hit.chunk_id)
    out: list[ConflictReport] = []
    for (entity, dim), by_ret in sorted(claims_by_key.items()):
        collapsed = {
            r: "|".join(sorted(vals)) for r, vals in by_ret.items() if vals
        }
        # At least 2 retrievers must produce distinct claim strings for this
        # (entity, dimension) pair to qualify as a conflict.
        if len(set(collapsed.values())) >= 2:
            out.append(
                ConflictReport(
                    entity=entity,
                    dimension=dim,
                    values_by_retriever=collapsed,
                    source_chunk_ids_by_retriever=evidence[(entity, dim)],
                    severity="mid",
                )
            )
    return out


__all__ = ["detect_conflicts"]
