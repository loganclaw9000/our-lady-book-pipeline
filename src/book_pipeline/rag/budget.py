"""Budget enforcement for ContextPackBundler. RAG-03 hard cap + per-axis soft caps.

enforce_budget() is PURE — never mutates input; returns (trimmed_copy, trim_log).

Budgeting algorithm:
  1. For each axis, if bytes_used > axis_soft_cap, trim lowest-score hits until
     bytes_used <= axis_soft_cap.
  2. Compute sum of bytes; if > hard_cap, trim additional hits across all axes
     (again lowest-score first within each axis, iterating round-robin) until
     sum <= hard_cap.
  3. Return (new_retrievals, trim_log_list).

trim_log entry shape: {"axis": str, "chunk_id": str, "original_score": float,
"reason": "per_axis_soft_cap" | "hard_cap_overflow"}.

Notes on score semantics: higher score = higher confidence (post-rerank cross-
encoder output from BgeReranker). Trimming removes the LOWEST-score hit first
within each over-cap axis.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from book_pipeline.interfaces.types import RetrievalHit, RetrievalResult

HARD_CAP: int = 40960

PER_AXIS_SOFT_CAPS: dict[str, int] = {
    "historical": 12288,
    "metaphysics": 8192,
    "entity_state": 8192,
    "arc_position": 6144,
    "negative_constraint": 6144,
}


def _hit_bytes(h: RetrievalHit) -> int:
    return len(h.text.encode("utf-8"))


def _result_bytes(hits: list[RetrievalHit]) -> int:
    return sum(_hit_bytes(h) for h in hits)


def enforce_budget(
    retrievals: dict[str, RetrievalResult],
    per_axis_caps: dict[str, int] | None = None,
    hard_cap: int = HARD_CAP,
) -> tuple[dict[str, RetrievalResult], list[dict[str, Any]]]:
    """Enforce per-axis soft caps + a global hard cap on the 5-axis retrieval set.

    Args:
        retrievals: dict keyed by retriever name -> RetrievalResult.
        per_axis_caps: optional override of PER_AXIS_SOFT_CAPS; defaults to module constants.
        hard_cap: global byte ceiling; defaults to HARD_CAP (40960).

    Returns:
        (trimmed_retrievals, trim_log). The input dict and its RetrievalResult
        values are NEVER mutated — a deep copy is made and trimmed in place on
        the copy.
    """
    caps = per_axis_caps if per_axis_caps is not None else PER_AXIS_SOFT_CAPS
    # Deep copy so we never mutate caller's data structures.
    work: dict[str, RetrievalResult] = deepcopy(retrievals)
    trim_log: list[dict[str, Any]] = []

    # --- Step 1: per-axis soft cap trimming -------------------------------
    for axis, result in work.items():
        axis_cap = caps.get(axis)
        if axis_cap is None:
            # Unknown axis — skip soft-cap trimming but still participates in hard-cap pass.
            continue
        # Sort hits by ascending score — lowest first (easy to pop from front).
        hits_sorted = sorted(result.hits, key=lambda h: h.score)
        current_bytes = _result_bytes(hits_sorted)
        while current_bytes > axis_cap and hits_sorted:
            victim = hits_sorted.pop(0)
            trim_log.append(
                {
                    "axis": axis,
                    "chunk_id": victim.chunk_id,
                    "original_score": victim.score,
                    "reason": "per_axis_soft_cap",
                }
            )
            current_bytes -= _hit_bytes(victim)
        # Restore original hit order (by score descending) for the surviving subset.
        result.hits[:] = sorted(hits_sorted, key=lambda h: h.score, reverse=True)
        result.bytes_used = current_bytes

    # --- Step 2: hard cap trimming across all axes ------------------------
    def _total() -> int:
        return sum(rr.bytes_used for rr in work.values())

    total = _total()
    # Iterate axes in a stable order; trim lowest score across all axes until under cap.
    while total > hard_cap:
        # Find the axis/hit with the globally lowest score.
        lowest: tuple[str, int, RetrievalHit] | None = None  # (axis, index, hit)
        for axis, result in work.items():
            for idx, hit in enumerate(result.hits):
                if lowest is None or hit.score < lowest[2].score:
                    lowest = (axis, idx, hit)
        if lowest is None:
            # Nothing left to trim — unusual; break to avoid infinite loop.
            break
        axis, idx, victim = lowest
        rr = work[axis]
        rr.hits.pop(idx)
        rr.bytes_used -= _hit_bytes(victim)
        trim_log.append(
            {
                "axis": axis,
                "chunk_id": victim.chunk_id,
                "original_score": victim.score,
                "reason": "hard_cap_overflow",
            }
        )
        total = _total()

    return work, trim_log


__all__ = ["HARD_CAP", "PER_AXIS_SOFT_CAPS", "enforce_budget"]
