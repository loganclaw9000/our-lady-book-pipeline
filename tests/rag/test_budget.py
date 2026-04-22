"""Tests for book_pipeline.rag.budget.enforce_budget.

Covers:
  - HARD_CAP constant (40960) + PER_AXIS_SOFT_CAPS sums to 40960.
  - Pure semantics: input dict is never mutated.
  - Within-axis trimming: lowest-score hits are removed first.
  - Hard-cap overflow: additional trimming across all axes until under cap.
  - Trim log records every removed chunk_id with its axis and original score.
"""

from __future__ import annotations

import copy

from book_pipeline.interfaces.types import RetrievalHit, RetrievalResult


def _make_result(
    name: str, hits: list[tuple[str, str, float]]
) -> RetrievalResult:
    """Build a RetrievalResult from [(chunk_id, text, score), ...]."""
    rh = [
        RetrievalHit(
            text=text,
            source_path=f"fixture_{name}.md",
            chunk_id=cid,
            score=score,
            metadata={},
        )
        for (cid, text, score) in hits
    ]
    return RetrievalResult(
        retriever_name=name,
        hits=rh,
        bytes_used=sum(len(h.text.encode("utf-8")) for h in rh),
        query_fingerprint="q-fp",
    )


def test_hard_cap_and_soft_caps_sum_to_40960() -> None:
    from book_pipeline.rag.budget import HARD_CAP, PER_AXIS_SOFT_CAPS

    assert HARD_CAP == 40960
    assert sum(PER_AXIS_SOFT_CAPS.values()) == 40960
    assert set(PER_AXIS_SOFT_CAPS.keys()) == {
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
    }


def test_enforce_budget_no_trim_when_under_soft_caps() -> None:
    from book_pipeline.rag.budget import enforce_budget

    retrievals = {
        "historical": _make_result(
            "historical", [("h1", "x" * 1000, 0.9), ("h2", "y" * 500, 0.5)]
        ),
        "metaphysics": _make_result("metaphysics", [("m1", "z" * 1000, 0.8)]),
    }
    out, trim_log = enforce_budget(retrievals)
    assert trim_log == []
    # Preserved hits unchanged.
    assert len(out["historical"].hits) == 2
    assert len(out["metaphysics"].hits) == 1


def test_enforce_budget_within_axis_trims_lowest_score_first() -> None:
    from book_pipeline.rag.budget import enforce_budget

    # Historical axis cap is 12288; build 3 hits totaling 15000 bytes.
    hits = [
        ("h1", "a" * 6000, 0.9),  # highest score — survives
        ("h2", "b" * 6000, 0.5),  # middle
        ("h3", "c" * 3000, 0.1),  # lowest — trimmed first
    ]
    retrievals = {"historical": _make_result("historical", hits)}
    out, trim_log = enforce_budget(retrievals)

    remaining_ids = [h.chunk_id for h in out["historical"].hits]
    assert "h3" in [entry["chunk_id"] for entry in trim_log]
    # Highest-score hit must be preserved.
    assert "h1" in remaining_ids


def test_enforce_budget_shrinks_to_under_hard_cap() -> None:
    """Test 7: 60KB set → ≤40KB output; trim_log lists every removed chunk."""
    from book_pipeline.rag.budget import HARD_CAP, enforce_budget

    # 5 axes x 12000 bytes each = 60KB. Each axis has 3 hits of 4000 bytes.
    def _axis_hits(prefix: str) -> list[tuple[str, str, float]]:
        return [
            (f"{prefix}1", "x" * 4000, 0.9),
            (f"{prefix}2", "y" * 4000, 0.5),
            (f"{prefix}3", "z" * 4000, 0.1),
        ]

    retrievals = {
        "historical": _make_result("historical", _axis_hits("h")),
        "metaphysics": _make_result("metaphysics", _axis_hits("m")),
        "entity_state": _make_result("entity_state", _axis_hits("e")),
        "arc_position": _make_result("arc_position", _axis_hits("a")),
        "negative_constraint": _make_result("negative_constraint", _axis_hits("n")),
    }
    out, trim_log = enforce_budget(retrievals)
    total = sum(rr.bytes_used for rr in out.values())
    assert total <= HARD_CAP, f"total bytes {total} > {HARD_CAP}"
    assert len(trim_log) > 0
    # Every trim_log entry carries axis + chunk_id + original_score.
    for entry in trim_log:
        assert "axis" in entry
        assert "chunk_id" in entry
        assert "original_score" in entry


def test_enforce_budget_never_mutates_input() -> None:
    """Test 8: deep-copy sentinel compare asserts no mutation."""
    from book_pipeline.rag.budget import enforce_budget

    retrievals = {
        "historical": _make_result(
            "historical",
            [("h1", "a" * 8000, 0.9), ("h2", "b" * 8000, 0.5)],
        ),
    }
    sentinel = copy.deepcopy(retrievals)
    enforce_budget(retrievals)

    # Original dict has same keys.
    assert retrievals.keys() == sentinel.keys()
    for name in retrievals:
        assert retrievals[name].retriever_name == sentinel[name].retriever_name
        assert retrievals[name].bytes_used == sentinel[name].bytes_used
        assert len(retrievals[name].hits) == len(sentinel[name].hits)
        for a, b in zip(retrievals[name].hits, sentinel[name].hits, strict=True):
            assert a.chunk_id == b.chunk_id
            assert a.text == b.text


def test_enforce_budget_updates_bytes_used_on_returned_results() -> None:
    """bytes_used on returned results reflects post-trim content."""
    from book_pipeline.rag.budget import enforce_budget

    retrievals = {
        "historical": _make_result(
            "historical",
            [("h1", "a" * 6000, 0.9), ("h2", "b" * 8000, 0.5), ("h3", "c" * 4000, 0.1)],
        ),
    }
    out, _ = enforce_budget(retrievals)
    declared = out["historical"].bytes_used
    actual = sum(len(h.text.encode("utf-8")) for h in out["historical"].hits)
    assert declared == actual
