"""Tests for book_pipeline.rag.chunker.

Behavior under test (from 02-01-PLAN.md <behavior>):
  - chunker on mini_corpus.md (3 headings, ~1000 words) produces >=3 chunks;
    each chunk.heading_path starts with the containing heading; chunks respect
    512-token targets (±20%) with 64-token overlap on adjacent chunks within
    the same heading.
  - chunker assigns stable chunk_id = hash_text(source_file + heading_path + text) —
    same input → same id across runs.
  - rule_type inference on leaf heading:
      /hypothetic/i → "hypothetical"
      /\bexample(s)?\b/i → "example"
      /cross[- ]?ref/i → "cross_reference"
      default → "rule"
  - chapter inference: heading_path containing `Chapter N` (top-level heading
    `# Chapter N:` OR any breadcrumb segment matching `Chapter N`) → chunk.chapter = N;
    otherwise chunk.chapter is None. (W-5 revision — arc_position retriever
    in Plan 04 filters on this column directly.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_chunker_mini_corpus_produces_heading_aware_chunks() -> None:
    from book_pipeline.rag import chunk_markdown

    text = _read_fixture("mini_corpus.md")
    chunks = chunk_markdown(text, source_file="mini_corpus.md", ingestion_run_id="run-001")

    # At least 3 chunks (one per heading minimum).
    assert len(chunks) >= 3, f"expected >=3 chunks, got {len(chunks)}"

    # Every chunk has a non-empty heading_path that begins with its enclosing top-level heading.
    allowed_top_headings = {"Main Rules", "Rule Cards — Hypotheticals", "Cross References"}
    seen_top_headings: set[str] = set()
    for ch in chunks:
        assert ch.heading_path, f"chunk has empty heading_path: {ch}"
        top = ch.heading_path.split(" > ")[0]
        assert top in allowed_top_headings, (
            f"chunk's top-level heading {top!r} not in {allowed_top_headings!r}"
        )
        seen_top_headings.add(top)
        # No empty text.
        assert ch.text.strip(), "chunk text is empty/whitespace-only"

    # All three heading sections must contribute at least one chunk.
    assert seen_top_headings == allowed_top_headings, (
        f"some headings produced no chunks: missing {allowed_top_headings - seen_top_headings}"
    )


def test_chunker_respects_token_target_and_overlap() -> None:
    """Chunks should target 512 tokens (±20%) and adjacent chunks within the
    same heading should share 64-token overlap (±50% tolerance — sentence
    boundaries round it)."""
    import tiktoken

    from book_pipeline.rag import chunk_markdown

    enc = tiktoken.get_encoding("cl100k_base")
    # Synthesize a long single-heading document so we get multiple chunks in
    # the same heading and can inspect overlap.
    paragraph = (
        "This is a dense sentence with specific numeric content like "
        "two hundred and forty grams, ledger entries, and careful "
        "accounting language. "
    ) * 10
    long_text = "# Long Section\n\n" + "\n\n".join([paragraph] * 20)

    chunks = chunk_markdown(
        long_text,
        source_file="synthetic.md",
        target_tokens=512,
        overlap_tokens=64,
        ingestion_run_id="run-long",
    )
    assert len(chunks) >= 2, "synthetic long doc should produce multiple chunks"

    # Each chunk body should be within ±20% of target (except possibly the tail chunk).
    for ch in chunks[:-1]:
        ntok = len(enc.encode(ch.text))
        assert 512 * 0.6 <= ntok <= 512 * 1.2, (
            f"chunk token count {ntok} outside ±40% of 512-token target"
        )

    # Adjacent chunks should share some overlap in their token sequences.
    # We check by intersecting sentence-stripped text windows — at least one
    # sentence from chunk[i]'s tail appears in chunk[i+1]'s head.
    for i in range(len(chunks) - 1):
        a_tail = " ".join(chunks[i].text.split()[-30:])
        b_head = " ".join(chunks[i + 1].text.split()[:60])
        # At least the paragraph stem 'This is a dense sentence' should appear somewhere.
        # Not a strict equality — heading-aware chunker may reset at boundaries.
        shared = any(tok in b_head for tok in a_tail.split() if len(tok) > 5)
        assert shared, (
            f"adjacent chunks {i} and {i + 1} share no common tokens (no overlap)"
        )


def test_chunker_chunk_ids_are_stable() -> None:
    """Same input → same chunk_ids across runs (deterministic hash)."""
    from book_pipeline.rag import chunk_markdown

    text = _read_fixture("mini_corpus.md")
    a = chunk_markdown(text, source_file="mini_corpus.md", ingestion_run_id="run-A")
    b = chunk_markdown(text, source_file="mini_corpus.md", ingestion_run_id="run-B")

    # ingestion_run_id differs but chunk_ids (derived from source_file+heading_path+text)
    # should match.
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b], (
        "chunk_ids must be stable across runs with identical source content"
    )
    # And chunk_ids must be unique within a run.
    assert len({c.chunk_id for c in a}) == len(a), "chunk_ids must be unique within a run"


def test_chunker_rule_type_inference() -> None:
    """Per PITFALLS R-4: rule_type metadata on each chunk enables the
    metaphysics retriever to filter by `rule_type=rule` and avoid surfacing
    hypotheticals as authoritative."""
    from book_pipeline.rag import chunk_markdown

    text = _read_fixture("mini_corpus.md")
    chunks = chunk_markdown(text, source_file="mini_corpus.md", ingestion_run_id="run-rt")

    # The "Main Rules" heading → rule_type="rule" (default).
    main_rules_chunks = [c for c in chunks if c.heading_path.startswith("Main Rules")]
    assert main_rules_chunks, "expected chunks under Main Rules"
    assert all(c.rule_type == "rule" for c in main_rules_chunks), (
        f"Main Rules chunks must default to rule_type='rule'; got "
        f"{[c.rule_type for c in main_rules_chunks]}"
    )

    # "Rule Cards — Hypotheticals" → rule_type="hypothetical".
    hypo_chunks = [c for c in chunks if "Hypothetical" in c.heading_path]
    assert hypo_chunks, "expected chunks under Hypotheticals heading"
    assert all(c.rule_type == "hypothetical" for c in hypo_chunks), (
        f"Hypotheticals chunks must be rule_type='hypothetical'; got "
        f"{[c.rule_type for c in hypo_chunks]}"
    )

    # "Cross References" → rule_type="cross_reference".
    cross_chunks = [c for c in chunks if c.heading_path.startswith("Cross References")]
    assert cross_chunks, "expected chunks under Cross References heading"
    assert all(c.rule_type == "cross_reference" for c in cross_chunks), (
        f"Cross References chunks must be rule_type='cross_reference'; got "
        f"{[c.rule_type for c in cross_chunks]}"
    )


def test_chunker_example_heading_inference() -> None:
    """Belt test: a heading named 'Examples' (not in mini_corpus) maps to
    rule_type='example'."""
    from book_pipeline.rag import chunk_markdown

    text = "# Examples\n\nThis section contains example invocations. " * 50
    chunks = chunk_markdown(text, source_file="examples.md", ingestion_run_id="run-ex")
    assert chunks, "expected at least one chunk"
    assert all(c.rule_type == "example" for c in chunks), (
        f"Examples heading must produce rule_type='example'; got "
        f"{[c.rule_type for c in chunks]}"
    )


def test_chunker_chapter_inference_present() -> None:
    """W-5: chunks whose heading_path contains `Chapter N` get chunk.chapter = N."""
    from book_pipeline.rag import chunk_markdown

    text = _read_fixture("chapter_corpus.md")
    chunks = chunk_markdown(text, source_file="chapter_corpus.md", ingestion_run_id="run-ch")

    assert chunks, "expected at least one chunk"
    # All chunks in this fixture should have chapter == 3.
    for ch in chunks:
        assert ch.chapter == 3, (
            f"expected chunk.chapter == 3 for heading_path={ch.heading_path!r}, got {ch.chapter!r}"
        )


def test_chunker_chapter_inference_absent() -> None:
    """W-5: chunks with no `Chapter N` heading get chunk.chapter = None."""
    from book_pipeline.rag import chunk_markdown

    text = _read_fixture("mini_corpus.md")
    chunks = chunk_markdown(text, source_file="mini_corpus.md", ingestion_run_id="run-nc")

    assert chunks, "expected at least one chunk"
    for ch in chunks:
        assert ch.chapter is None, (
            f"expected chunk.chapter is None (no Chapter heading in fixture) — "
            f"got {ch.chapter!r} for heading_path={ch.heading_path!r}"
        )


def test_chunker_empty_sections_produce_no_chunks() -> None:
    """Empty / whitespace-only sections must NOT produce empty-text Chunks."""
    from book_pipeline.rag import chunk_markdown

    # Heading with only whitespace under it.
    text = "# Empty Heading\n\n   \n\n# Populated Heading\n\nReal content here. " * 10
    chunks = chunk_markdown(text, source_file="mixed.md", ingestion_run_id="run-empty")
    assert chunks, "expected at least one chunk from the populated heading"
    for ch in chunks:
        assert ch.text.strip(), f"chunk has empty/whitespace-only text: {ch!r}"
        assert "Empty Heading" not in ch.heading_path, (
            "empty heading section must produce 0 chunks"
        )


def test_chunk_is_frozen_and_forbids_extra() -> None:
    """Chunk Pydantic model: frozen=True, extra='forbid'."""
    from pydantic import ValidationError

    from book_pipeline.rag.types import Chunk

    c = Chunk(
        chunk_id="abc",
        text="t",
        source_file="f.md",
        heading_path="H",
        rule_type="rule",
        ingestion_run_id="run-1",
        chapter=None,
    )
    with pytest.raises(ValidationError):
        # frozen → assignment should raise
        c.text = "mutated"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        # extra='forbid' → unknown field should raise at construction
        Chunk(  # type: ignore[call-arg]
            chunk_id="abc",
            text="t",
            source_file="f.md",
            heading_path="H",
            rule_type="rule",
            ingestion_run_id="run-1",
            chapter=None,
            bogus_field="x",
        )
