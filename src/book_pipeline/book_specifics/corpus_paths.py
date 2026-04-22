"""File-path + corpus-name constants for the Our Lady of Champion lore bibles.

Updated by Phase 2 Plan 02 to reconcile with the actual on-disk filenames at
~/Source/our-lady-of-champion/ (which all carry the `our-lady-of-champion-`
prefix — confirmed by `ls ~/Source/our-lady-of-champion/` during execution).

Phase 2 Plan 02-02 additions:
  - All per-file constants now point at `our-lady-of-champion-<stem>.md`.
  - New constants: RELICS, GLOSSARY, MAPS, HANDOFF (10 total).
  - CORPUS_FILES: dict[axis, list[Path]] — inverse of the file→axis router,
    provided here for CLI/ingester convenience. brief.md deliberately appears
    in BOTH historical and metaphysics axes (file-level routing); per-heading
    split for multi-axis files is delegated to heading_classifier.py at
    ingestion time (W-3).
  - HANDOFF is a meta-document and is NOT in any axis list (router returns []).

These constants are used by Phase 2 ingestion + Phase 4 entity extraction.
They are book-specific by construction — no other writing pipeline needs them.
"""

from __future__ import annotations

from pathlib import Path

CORPUS_ROOT = Path("~/Source/our-lady-of-champion").expanduser()


def _p(stem: str) -> Path:
    """Return the path for `our-lady-of-champion-<stem>.md` under CORPUS_ROOT."""
    return CORPUS_ROOT / f"our-lady-of-champion-{stem}.md"


BRIEF = _p("brief")
ENGINEERING = _p("engineering")
PANTHEON = _p("pantheon")
SECONDARY_CHARACTERS = _p("secondary-characters")
OUTLINE = _p("outline")
KNOWN_LIBERTIES = _p("known-liberties")
RELICS = _p("relics")
GLOSSARY = _p("glossary")
MAPS = _p("maps")
HANDOFF = _p("handoff")  # meta-document; NOT routed to any axis.


# Axis -> ordered list of source files. The kernel router in
# corpus_ingest/router.py is the single source of truth for file-level routing;
# this mapping is its inverse, exposed for CLI/ingester convenience. If a file
# appears in 2 axes (currently only brief.md: historical + metaphysics), the
# ingester applies book_pipeline.book_specifics.heading_classifier to decide
# per-chunk routing so the same chunk_id never lands in 2 tables.
CORPUS_FILES: dict[str, list[Path]] = {
    "historical":          [BRIEF, GLOSSARY, MAPS],
    "metaphysics":         [ENGINEERING, RELICS, BRIEF],  # brief has metaphysics-flavored headings
    "entity_state":        [PANTHEON, SECONDARY_CHARACTERS],
    "arc_position":        [OUTLINE],
    "negative_constraint": [KNOWN_LIBERTIES],
}
