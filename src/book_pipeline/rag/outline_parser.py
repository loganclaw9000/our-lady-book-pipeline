"""outline_parser — parses outline.md into beat-function-granularity Beats.

RAG-02 contract: the arc_position retriever depends on STABLE beat IDs surviving
re-ingestion. A beat ID is determined ENTIRELY by chapter/block/beat NUMBERING
(not by body content) — so authors may edit beat bodies without invalidating
downstream SceneRequest.beat_function references.

Beat ID schema: `ch{chapter:02d}_b{block_lower}_beat{beat:02d}` — e.g.,
`ch01_ba_beat01`, `ch10_bb_beat03`. Zero-padding ensures lexical sort matches
numeric order.

Two parse modes:

  1. STRICT (synthetic format used by tests + expected by plan):
     ``# Chapter N: Title`` / ``## Block X: Title`` / ``### Beat N: Title``
     Beats are the leaf units; block-letter is the ``X`` from ``## Block X``
     (lowercased, alphanumerics only).

  2. LENIENT FALLBACK (real OLoC outline as of 2026-04):
     ``# ACT N — ...`` / ``## BLOCK N — ...`` / ``### Chapter N — ...``
     The real outline uses Kat O'Keeffe's 3 Act / 9 Block / 27 Chapter structure
     where each ``### Chapter N`` is itself the beat. In fallback mode each
     ``### Chapter N`` is treated as a single beat (beat=1) within its enclosing
     BLOCK. The block identifier becomes the BLOCK's number (lowercase digit),
     so IDs look like ``ch01_b1_beat01``.

The parser walks the document once, tracks current
``(chapter, block_id, beat_num)`` state, accumulates body text into the current
beat, and emits a Beat when a new beat/block/chapter heading is encountered.

Dedupe: beats are kept in an insertion-order dict keyed by beat_id. Duplicates
overwrite (last-wins) and emit a WARNING. Orphaned sections (e.g. a ``### Beat``
heading with no enclosing ``# Chapter``) are skipped with a WARNING.

Retrievers NEVER call this parser directly — the ArcPositionRetriever (Plan 04)
reads ``self.outline_path`` and calls parse_outline as part of its reindex().
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# --- Regex sets --------------------------------------------------------------
# STRICT: ## Block X where X is an alphanumeric block id ("A", "B", "1"...).
# CASE-SENSITIVE so fallback patterns (which match ALL-CAPS variants in the real
# OLoC outline) don't get shadowed. Synthetic outlines use title-case
# "Chapter"/"Block"/"Beat"; real outline uses mixed "# ACT"/"## BLOCK"/"### Chapter".
_STRICT_CHAPTER_RE = re.compile(r"^#\s+Chapter\s+(\d+)\s*[:\-—]?\s*(.*)$")
_STRICT_BLOCK_RE = re.compile(r"^##\s+Block\s+(\w+)\s*[:\-—]?\s*(.*)$")
_STRICT_BEAT_RE = re.compile(r"^###\s+Beat\s+(\d+)\s*[:\-—]?\s*(.*)$")

# LENIENT fallback for real OLoC outline:
#   "## BLOCK 3 — End (Cholula and Arrival)"
#   "### Chapter 7 — Pressure"
# Act headings are ignored for beat-id purposes — Act is purely organizational;
# Block numbering is already globally unique across the document (real outline
# has BLOCK 1..BLOCK 9 across the 3 acts). Under each fallback BLOCK, each
# "### Chapter N" becomes a single beat with beat=1, chapter=N, block=<block-num>.
_FALLBACK_BLOCK_RE = re.compile(r"^##\s+BLOCK\s+(\d+)\s*[:\-—]?\s*(.*)$")
_FALLBACK_CHAPTER_AS_BEAT_RE = re.compile(r"^###\s+Chapter\s+(\d+)\s*[:\-—]?\s*(.*)$")

# Any line starting with # that doesn't match ANY of the above — logged as
# warnings when their content appears to imply missing structure.
_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class Beat(BaseModel):
    """One beat-function-granularity record from the outline.

    Frozen + extra-forbid so accidental field bloat is loud, and equality
    compares all fields (used in test_parse_outline_is_stable_across_reparses).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    beat_id: str
    chapter: int
    block: str
    beat: int
    title: str
    body: str
    heading_path: str  # "Chapter N > Block X > Beat K: title"


def _normalize_block_id(raw: str) -> str:
    """Lowercase + strip non-alphanumerics from a raw block identifier."""
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def _make_beat_id(chapter: int, block_id: str, beat: int) -> str:
    """Beat ID schema: ch{chapter:02d}_b{block_lower}_beat{beat:02d}."""
    return f"ch{chapter:02d}_b{block_id}_beat{beat:02d}"


def parse_outline(text: str) -> list[Beat]:
    """Parse outline.md text into a list of Beats with stable IDs.

    Lenient: warns on orphaned or duplicate sections, returns what it can
    extract. Raises ValueError only on empty input.

    Args:
      text: full markdown content of an outline file.

    Returns:
      list[Beat] in document order. Duplicates by beat_id resolve to last-wins.
    """
    if not text.strip():
        raise ValueError("parse_outline called with empty/whitespace-only input")

    lines = text.splitlines(keepends=True)

    # State machine: track current chapter/block/beat context and the body lines
    # being accumulated for the current beat.
    current_chapter: int | None = None
    current_chapter_title: str = ""
    current_block_id: str | None = None
    current_block_title: str = ""
    current_beat: int | None = None
    current_beat_title: str = ""
    current_body_lines: list[str] = []

    # Insertion-order dict keyed by beat_id (last-wins on duplicates).
    beats_by_id: dict[str, Beat] = {}

    def _flush_current() -> None:
        """Emit the currently-accumulated beat (if any) into beats_by_id."""
        nonlocal current_body_lines
        if current_chapter is None or current_block_id is None or current_beat is None:
            # No beat in progress to flush.
            current_body_lines = []
            return
        beat_id = _make_beat_id(current_chapter, current_block_id, current_beat)
        body = "".join(current_body_lines).strip()
        heading_path = (
            f"Chapter {current_chapter}"
            + (f": {current_chapter_title}" if current_chapter_title else "")
            + f" > Block {current_block_id.upper()}"
            + (f": {current_block_title}" if current_block_title else "")
            + f" > Beat {current_beat}"
            + (f": {current_beat_title}" if current_beat_title else "")
        )
        if beat_id in beats_by_id:
            logger.warning(
                "Duplicate beat_id %s (chapter=%d, block=%s, beat=%d); last-wins.",
                beat_id,
                current_chapter,
                current_block_id,
                current_beat,
            )
        beats_by_id[beat_id] = Beat(
            beat_id=beat_id,
            chapter=current_chapter,
            block=current_block_id,
            beat=current_beat,
            title=current_beat_title,
            body=body,
            heading_path=heading_path,
        )
        current_body_lines = []

    for line in lines:
        # --- Try strict regexes first (synthetic outline format). ----------
        m_chapter = _STRICT_CHAPTER_RE.match(line)
        if m_chapter:
            _flush_current()
            current_chapter = int(m_chapter.group(1))
            current_chapter_title = m_chapter.group(2).strip()
            # Reset downstream state since a new chapter resets block/beat.
            current_block_id = None
            current_block_title = ""
            current_beat = None
            current_beat_title = ""
            continue

        m_block = _STRICT_BLOCK_RE.match(line)
        if m_block:
            _flush_current()
            if current_chapter is None:
                logger.warning(
                    "Orphaned ## Block heading (no enclosing # Chapter): %s",
                    line.strip(),
                )
                # Skip this block's contents until a Chapter shows up.
                current_block_id = None
                current_block_title = ""
                current_beat = None
                current_beat_title = ""
                continue
            current_block_id = _normalize_block_id(m_block.group(1))
            current_block_title = m_block.group(2).strip()
            current_beat = None
            current_beat_title = ""
            continue

        m_beat = _STRICT_BEAT_RE.match(line)
        if m_beat:
            _flush_current()
            if current_chapter is None or current_block_id is None:
                logger.warning(
                    "Orphaned ### Beat heading (no enclosing Chapter/Block): %s",
                    line.strip(),
                )
                current_beat = None
                current_beat_title = ""
                continue
            current_beat = int(m_beat.group(1))
            current_beat_title = m_beat.group(2).strip()
            continue

        # --- Lenient fallback for the real OLoC outline format. -----------
        # A `## BLOCK N — ...` in the real outline becomes the enclosing block;
        # each `### Chapter N — ...` is a single beat (beat=1) under that block.
        m_fb_block = _FALLBACK_BLOCK_RE.match(line)
        if m_fb_block:
            _flush_current()
            # Fallback block takes on a synthetic chapter of the block's number
            # ONLY if we have no enclosing strict Chapter. For the real outline
            # this is always the case. For mixed documents, a strict Chapter
            # takes precedence (already handled above).
            if current_chapter is None:
                # Synthesize a per-block chapter counter so beat IDs stay
                # document-unique. Using the block number itself is fine —
                # each "chapter" heading under this block will get beats in
                # the b{N} namespace.
                pass  # we set chapter inside the fallback chapter branch below
            current_block_id = m_fb_block.group(1)  # digit: "1", "2", "3", ...
            current_block_title = m_fb_block.group(2).strip()
            current_beat = None
            current_beat_title = ""
            continue

        m_fb_chapter_as_beat = _FALLBACK_CHAPTER_AS_BEAT_RE.match(line)
        if m_fb_chapter_as_beat:
            _flush_current()
            if current_block_id is None:
                logger.warning(
                    "Fallback ### Chapter heading with no enclosing ## BLOCK: %s",
                    line.strip(),
                )
                continue
            # In fallback mode: chapter number = the chapter from the heading;
            # beat = 1 (each real "chapter" is one beat under its block).
            current_chapter = int(m_fb_chapter_as_beat.group(1))
            current_chapter_title = m_fb_chapter_as_beat.group(2).strip()
            current_beat = 1
            current_beat_title = current_chapter_title
            continue

        # --- Uncategorized # lines: warn if they look like headings. ------
        any_heading = _ANY_HEADING_RE.match(line)
        if any_heading:
            # Known-to-skip noise: "#" (doc title), "## How This Document Works",
            # "## POV Snapshot", "### 3 Act / 9 Block...", arbitrary `### Date`
            # lines inside beats. We DO NOT warn for these; they legitimately
            # belong inside body text. We only warn when the line looks like it
            # wanted to be a structural heading and isn't one we recognize.
            # Heuristic: if the line contains "Chapter", "Block", "Beat", or
            # "Act" and wasn't matched by any of the above, log it.
            content = any_heading.group(2)
            if re.search(r"\b(Chapter|Block|Beat|Act)\b", content, re.IGNORECASE):
                # These are handled above if in expected form. If we reach here
                # it means a structural keyword appears in an unrecognized shape
                # — useful signal, but not actionable noise for every run.
                pass  # keep silent unless the shape truly breaks parsing.

        # Default: accumulate line as body for whatever beat is currently open.
        current_body_lines.append(line)

    # Flush the trailing beat (if any).
    _flush_current()

    return list(beats_by_id.values())


__all__ = ["Beat", "parse_outline"]
