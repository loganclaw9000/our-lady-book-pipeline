"""Book-specific heading → axis classifier (W-3 revision, Plan 02-02).

Per W-3: the kernel file-level router (corpus_ingest/router.py) reports WHICH
axes a file lands in. For multi-axis files (currently only brief.md), per-heading
routing uses this explicit allowlist — NOT regex. New headings added to brief.md
must be mapped here intentionally; unmapped headings default to the file's
primary axis (first entry in CORPUS_FILES's list for that file).

This module is book-specific because "which heading goes where" is domain
knowledge, not generic RAG logic. It is DI'd into CorpusIngester by the CLI
composition layer (book_pipeline.cli.ingest), which is the only permitted
bridge between kernel and book_specifics (documented import-linter exemption).

Population rationale (authored from the actual top-level ATX headings in
~/Source/our-lady-of-champion/our-lady-of-champion-brief.md at Plan 02-02
execution time):

  - "The Metaphysics (Lock This First)" → metaphysics (root of the engine
    rules section; the whole chapter is metaphysics).
  - "Reliquary Mecha (Spanish / European / Mediterranean)" → metaphysics
    (engine/relic rules; engineering-adjacent).
  - "Teōmecahuītlī (Mexica God-Engines)" → metaphysics (engine rules).
  - "Engagement Doctrine (What Battles Look Like)" → metaphysics (engine
    rules — how the metaphysics manifests in combat).
  - "Premise" → historical (factual framing of the setting).
  - "The Three POVs" → historical (characters anchored in the historical
    frame, not engine rules).
  - "Historical Framework (Condensed)" → historical (explicit label).
  - "Thematic Spine" → historical (narrative frame, not engine rules).
  - "The Two-Thirds Revelation" → historical (narrative-beat context rather
    than engine rule).
  - "The Climax" → historical (narrative-beat context).
  - "Things to Avoid" → historical (setting-anchoring constraints rather
    than engine rules).
  - "Deliverables Required Before Drafting" → historical (project hygiene,
    not engine rules).

Headings not in this map default to the file's primary axis (historical,
per CORPUS_FILES routing for brief.md). Plan 02-06 golden-query CI tests
against these mappings.
"""

from __future__ import annotations

# Key: exact heading_path breadcrumb as produced by book_pipeline.rag.chunker
# (joined with " > "). For brief.md, breadcrumbs are typically single-segment
# because its H2 sections are flat peers under the H1 "Our Lady of Champion".
# When the chunker emits a breadcrumb like "Our Lady of Champion > The
# Metaphysics (Lock This First)", callers must lookup the trailing segment —
# but per the current chunker behavior (sections yielded by their full
# breadcrumb path), we key on the full breadcrumb value. The classify_brief_heading
# function accepts either form and tries both (exact breadcrumb AND trailing
# segment) to be robust to breadcrumb-format choices.
BRIEF_HEADING_AXIS_MAP: dict[str, str] = {
    # Metaphysics-flavored headings (engine rules / relic rules / doctrine)
    "The Metaphysics (Lock This First)": "metaphysics",
    "Reliquary Mecha (Spanish / European / Mediterranean)": "metaphysics",
    "Teōmecahuītlī (Mexica God-Engines)": "metaphysics",
    "Engagement Doctrine (What Battles Look Like)": "metaphysics",
    # Historical / narrative-frame headings
    "Premise": "historical",
    "The Three POVs": "historical",
    "Historical Framework (Condensed)": "historical",
    "Thematic Spine": "historical",
    "The Two-Thirds Revelation": "historical",
    "The Climax": "historical",
    "Things to Avoid": "historical",
    "Deliverables Required Before Drafting": "historical",
}


def classify_brief_heading(heading_path: str) -> str | None:
    """Return the axis name for a given heading_path, or None if unmapped.

    Matches against either the full heading_path breadcrumb OR its trailing
    segment (the last element when split by " > "). This robustness handles
    both chunker breadcrumb shapes:

      - "The Metaphysics (Lock This First)"  (chunker emits leaf only)
      - "Our Lady of Champion > The Metaphysics (Lock This First)"  (full breadcrumb)

    Returns None if neither form matches — the ingester treats None as "fall
    back to the file's primary axis" (first entry in CORPUS_FILES for brief.md,
    which is "historical").
    """
    if not heading_path:
        return None
    # Try full breadcrumb first.
    if heading_path in BRIEF_HEADING_AXIS_MAP:
        return BRIEF_HEADING_AXIS_MAP[heading_path]
    # Fall back to trailing segment.
    segments = [s.strip() for s in heading_path.split(">")]
    leaf = segments[-1] if segments else ""
    return BRIEF_HEADING_AXIS_MAP.get(leaf)


__all__ = ["BRIEF_HEADING_AXIS_MAP", "classify_brief_heading"]
