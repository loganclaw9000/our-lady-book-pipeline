"""Heading-aware markdown chunker — kernel primitive for the 5 RAG axes.

PITFALLS R-4 mitigation: chunks never cross heading boundaries, and each chunk
carries `rule_type` metadata so the metaphysics retriever can filter out
hypotheticals / cross-references by default. W-5 revision: chunks also carry
`chapter: int | None` inferred from the heading breadcrumb so the arc_position
retriever (Plan 04) can filter on exact chapter equality instead of a fragile
LIKE clause against heading_path.

Tokenization uses tiktoken `cl100k_base` — not a perfect match for BGE-M3's
own tokenizer but within ±15% per PITFALLS R-4 guidance ("heading boundaries
matter more than exact token count"). Chunk-boundary correctness is the
load-bearing invariant here, not token-exactness.
"""

from __future__ import annotations

import re

import tiktoken

from book_pipeline.observability.hashing import hash_text
from book_pipeline.rag.types import Chunk

# -----------------------------------------------------------------------------
# Regexes
# -----------------------------------------------------------------------------

# Matches a markdown ATX heading at the start of a line, capturing level + text.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# Sentence splitter — conservative: splits on `. ! ? ` followed by whitespace or EOL,
# preserving the terminator. Markdown-safe (does not split on `e.g.` etc in most cases
# because we require whitespace + an uppercase or newline after).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'\-\(\[])")

# rule_type inference patterns (case-insensitive, leaf-heading match).
_RULE_TYPE_HYPOTHETICAL = re.compile(r"hypothetic", re.IGNORECASE)
_RULE_TYPE_EXAMPLE = re.compile(r"\bexample(s)?\b", re.IGNORECASE)
_RULE_TYPE_CROSS_REF = re.compile(r"cross[- ]?ref", re.IGNORECASE)

# chapter inference: either `# Chapter N` as a top-level heading OR any
# breadcrumb segment starting with `Chapter N`.
_CHAPTER_RE = re.compile(r"\bChapter\s+(\d+)\b", re.IGNORECASE)


# -----------------------------------------------------------------------------
# Tokenization
# -----------------------------------------------------------------------------

_ENC = tiktoken.get_encoding("cl100k_base")


def _tokens(text: str) -> list[int]:
    return _ENC.encode(text)


def _detokenize(toks: list[int]) -> str:
    return _ENC.decode(toks)


# -----------------------------------------------------------------------------
# Internal types (not exported)
# -----------------------------------------------------------------------------


class _Section:
    """One markdown heading section: the heading_path breadcrumb + its body text."""

    __slots__ = ("body", "heading_level", "heading_path", "leaf_heading")

    def __init__(self, heading_path: str, body: str, heading_level: int, leaf_heading: str) -> None:
        self.heading_path = heading_path
        self.body = body
        self.heading_level = heading_level
        self.leaf_heading = leaf_heading


# -----------------------------------------------------------------------------
# Heading parsing
# -----------------------------------------------------------------------------


def _split_into_sections(text: str) -> list[_Section]:
    """Split markdown text on ATX headings. Each returned Section owns the
    body text under its heading up to the next same-or-higher-level heading.

    heading_path is a ` > `-joined breadcrumb of the ancestor chain, e.g.:
        "Chapter 3: The Cholula Stir > Scene 2: The Priest's Refusal"
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        # No headings at all → one pseudo-section with empty heading_path.
        return [_Section(heading_path="", body=text, heading_level=0, leaf_heading="")]

    sections: list[_Section] = []
    # Stack of (level, heading_text) representing current ancestor path.
    stack: list[tuple[int, str]] = []

    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading_text = m.group(2).strip()

        # Pop stack down to just-above this level.
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading_text))

        breadcrumb = " > ".join(h for _, h in stack)

        # Body text = everything from end-of-heading-line to start of next heading.
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()

        sections.append(
            _Section(
                heading_path=breadcrumb,
                body=body,
                heading_level=level,
                leaf_heading=heading_text,
            )
        )

    return sections


# -----------------------------------------------------------------------------
# rule_type + chapter inference
# -----------------------------------------------------------------------------


def _infer_rule_type(heading_path: str, leaf_heading: str) -> str:
    """Per PITFALLS R-4: tag each chunk so the retriever can filter on rule_type.

    Inspects BOTH the leaf heading and the full heading_path breadcrumb — a
    section nested under an "Examples" top-level heading should still be tagged
    `example` even if its own leaf heading is a numbered sub-heading.
    """
    haystack = f"{heading_path} {leaf_heading}"
    if _RULE_TYPE_HYPOTHETICAL.search(haystack):
        return "hypothetical"
    if _RULE_TYPE_EXAMPLE.search(haystack):
        return "example"
    if _RULE_TYPE_CROSS_REF.search(haystack):
        return "cross_reference"
    return "rule"


def _infer_chapter(heading_path: str) -> int | None:
    """W-5: extract chapter number from heading_path breadcrumb, else None.

    Matches any `Chapter N` segment in the breadcrumb. If multiple match, the
    first (outermost) wins — the chapter boundary is set at the enclosing
    `# Chapter N:` heading, not at nested scene markers.
    """
    m = _CHAPTER_RE.search(heading_path)
    if m is None:
        return None
    return int(m.group(1))


# -----------------------------------------------------------------------------
# Sliding-window chunker within a section
# -----------------------------------------------------------------------------


def _split_sentences(body: str) -> list[str]:
    """Sentence split that preserves paragraph structure. Empty paragraphs drop."""
    # First split on blank lines, then on sentence boundaries within each paragraph.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    sentences: list[str] = []
    for p in paragraphs:
        parts = _SENTENCE_SPLIT_RE.split(p)
        for s in parts:
            s = s.strip()
            if s:
                sentences.append(s)
    return sentences


def _pack_chunks(
    sentences: list[str], target_tokens: int, overlap_tokens: int
) -> list[str]:
    """Pack sentences into chunks of ~target_tokens with overlap_tokens carry-over.

    Algorithm:
      - Accumulate sentences until the running token count reaches target_tokens.
      - Emit the chunk.
      - For the next chunk, carry over the last overlap_tokens tokens' worth of
        sentences (rounded to sentence boundary) and continue packing.

    A single sentence larger than target_tokens is emitted as its own (over-sized)
    chunk; we do not split mid-sentence.
    """
    if not sentences:
        return []

    chunks: list[str] = []
    i = 0
    n = len(sentences)
    while i < n:
        running_tokens = 0
        start_idx = i
        while i < n and running_tokens < target_tokens:
            s_tokens = len(_tokens(sentences[i]))
            # If adding this sentence would overshoot by a wide margin AND we
            # already have content, stop and emit.
            if running_tokens > 0 and running_tokens + s_tokens > target_tokens * 1.2:
                break
            running_tokens += s_tokens
            i += 1

        chunk_text = " ".join(sentences[start_idx:i]).strip()
        if chunk_text:
            chunks.append(chunk_text)

        if i >= n:
            break

        # Carry overlap_tokens worth of sentences from the tail of the just-emitted chunk.
        overlap_start = i
        tail_tokens = 0
        while overlap_start > start_idx and tail_tokens < overlap_tokens:
            overlap_start -= 1
            tail_tokens += len(_tokens(sentences[overlap_start]))
        # Advance i back so the next iteration includes the overlap sentences.
        i = overlap_start

        # Safety: ensure forward progress. If overlap swallowed the whole window
        # (degenerate: overlap_tokens >= target_tokens), jump forward one sentence.
        if i <= start_idx:
            i = start_idx + max(1, (i - start_idx) + 1)

    return chunks


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def chunk_markdown(
    text: str,
    source_file: str,
    *,
    target_tokens: int = 512,
    overlap_tokens: int = 64,
    ingestion_run_id: str = "",
) -> list[Chunk]:
    """Chunk markdown `text` into Chunk rows respecting heading boundaries.

    Args:
      text: Full markdown source.
      source_file: Identifier written into each chunk (used by the retriever
        to locate the source doc). Typically a filename, e.g.
        "our-lady-of-champion-brief.md".
      target_tokens: Target chunk size in cl100k_base tokens. Default 512.
      overlap_tokens: Sliding-window overlap in tokens. Default 64.
      ingestion_run_id: The ingestion run this chunk was created during.
        Used by Plan 02 to correlate chunks with `event_type=ingestion_run`
        event records.

    Returns:
      List of Chunk instances. Empty / whitespace-only sections produce zero
      chunks. Each chunk_id is a stable xxhash64 of
      (source_file + heading_path + chunk_text).
    """
    if not text or not text.strip():
        return []

    sections = _split_into_sections(text)
    out: list[Chunk] = []

    for section in sections:
        if not section.body.strip():
            continue
        sentences = _split_sentences(section.body)
        if not sentences:
            continue

        chunk_texts = _pack_chunks(sentences, target_tokens, overlap_tokens)
        rule_type = _infer_rule_type(section.heading_path, section.leaf_heading)
        chapter = _infer_chapter(section.heading_path)

        for chunk_text in chunk_texts:
            if not chunk_text.strip():
                continue
            cid = hash_text(f"{source_file}|{section.heading_path}|{chunk_text}")
            out.append(
                Chunk(
                    chunk_id=cid,
                    text=chunk_text,
                    source_file=source_file,
                    heading_path=section.heading_path,
                    rule_type=rule_type,
                    ingestion_run_id=ingestion_run_id,
                    chapter=chapter,
                )
            )

    return out


__all__ = ["Chunk", "chunk_markdown"]
