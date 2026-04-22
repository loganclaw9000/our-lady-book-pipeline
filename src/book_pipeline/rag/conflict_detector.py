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

import logging
import re

from book_pipeline.interfaces.types import ConflictReport, RetrievalResult

logger = logging.getLogger(__name__)

# WR-01: saturation threshold. If more than this many conflicts fire for a
# single retrievals dict we log a warning — a forcing-function this noisy is
# degraded signal and the Phase 3 critic should know.
_CONFLICT_SATURATION_THRESHOLD: int = 50

# Regex patterns for English-style capitalization — complement the injected entity_list.
# WR-01: dropped the bare `|in` from the verb set — it was catastrophically
# promiscuous (any capitalized word after "in" got tagged as a location:
# "in Him", "in Christ", "in March"). Require an explicit spatial verb.
_LOCATION_PHRASE_RE = re.compile(
    r"(?:is at|arrives at|stays at|returns to)\s+([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+)*)",
)
_POSSESSION_PHRASE_RE = re.compile(
    r"(?:has|carries|possesses|holds)\s+(?:the\s+)?(\w+)\b",
)
_DATE_RE = re.compile(r"\b(\d{4}(?:-\d{2}-\d{2})?)\b")
# Capitalized name(s): "Andrés", "Juan Pablo" — unicode-aware via \w with re.UNICODE default.
_NAME_REGEX_RE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)?)\b")

# WR-01: stoplist of values that MUST NOT count as a possession claim. The
# pre-fix regex captured "has been" / "has a" / "holds his" with group(1)
# being an auxiliary, article, pronoun, etc. — all false positives.
_POSSESSION_STOPLIST: frozenset[str] = frozenset(
    {
        "been",
        "a",
        "an",
        "the",
        "his",
        "her",
        "its",
        "my",
        "our",
        "your",
        "their",
        "some",
        "no",
        "any",
        "all",
        "become",
    }
)

# WR-01: stoplist of capitalized tokens that MUST NOT count as location targets.
# Month names + weekday names + titles collide with the location regex
# (e.g. "is at March" would never fire in practice but "returns to Lord
# Cortés" would spuriously flag "Lord" as a location). The regex already
# requires capital-first, so we match the lowercased form against this set.
_LOCATION_STOPLIST: frozenset[str] = frozenset(
    {
        # Months.
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        # Weekdays.
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        # Titles.
        "lord",
        "lady",
        "father",
        "mother",
        "king",
        "queen",
        "sir",
        "dame",
        "saint",
    }
)


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
    """For a given entity, scan text for (dimension, value) claims in a ~80-char window.

    WR-01: apply stoplists to suppress the worst false-positive classes from
    the tightened-but-still-approximate regexes:
      - possession values like "been" / "a" / "his" (auxiliary-verb / article
        / pronoun collisions from "has been", "has a", "holds his")
      - location values like "Lord" / "March" / "Monday" (titles, months,
        weekdays caught by capital-first matching)
    """
    out: list[tuple[str, str]] = []
    for m in re.finditer(re.escape(entity), text):
        window = text[max(0, m.start() - 80) : m.end() + 80]
        for lm in _LOCATION_PHRASE_RE.finditer(window):
            loc_value = lm.group(1).strip()
            # WR-01: stoplist — reject months/weekdays/titles even though
            # they're capital-first. Compare first token case-insensitively
            # so multi-word phrases like "Lord Cortés" are caught at token 0.
            first_token = loc_value.split()[0].lower() if loc_value else ""
            if first_token in _LOCATION_STOPLIST:
                continue
            out.append(("location", loc_value))
        for pm in _POSSESSION_PHRASE_RE.finditer(window):
            poss_value = pm.group(1).strip()
            # WR-01: stoplist — reject auxiliary-verb / article / pronoun
            # captures that are not really possessions.
            if poss_value.lower() in _POSSESSION_STOPLIST:
                continue
            out.append(("possession", poss_value))
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

    # WR-01: saturation warning. If the forcing function produces more than
    # _CONFLICT_SATURATION_THRESHOLD conflicts for a single scene, the signal
    # is degraded — Phase 3 critic will drown. Log-only (no exception); the
    # bundler's role="context_pack_bundler" Event still lands normally.
    if len(out) > _CONFLICT_SATURATION_THRESHOLD:
        logger.warning(
            "conflict_detector saturation: %d conflicts > threshold %d — "
            "forcing-function signal degraded; consider tightening entity_list "
            "or disabling noisy retrievers for this scene",
            len(out),
            _CONFLICT_SATURATION_THRESHOLD,
        )

    return out


__all__ = ["detect_conflicts"]
