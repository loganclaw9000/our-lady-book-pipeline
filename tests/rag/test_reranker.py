"""Tests for book_pipeline.rag.reranker.BgeReranker.

Behavior under test (from 02-03-PLAN.md Task 1 <behavior>):
  - rerank([]) returns [] and does NOT trigger model load.
  - rerank(query, candidates, top_k=K) returns min(K, len(candidates)) tuples
    sorted by rerank_score descending.
  - rerank with top_k > len(candidates) returns all candidates sorted.
  - rerank never mutates the `candidates` argument.

The fake CrossEncoder is monkeypatched into sentence_transformers to avoid
downloading the real ~2GB BAAI/bge-reranker-v2-m3 model during unit tests.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest


class _FakeCrossEncoder:
    """Stand-in for sentence_transformers.CrossEncoder used in unit tests.

    `predict(pairs)` returns a deterministic score per pair: the score equals
    the NEGATIVE of the pair's index (so pair index 0 -> 0.0, pair index 1 ->
    -1.0, ...) — this makes the "first candidate gets the highest score" path
    testable, since BgeReranker sorts by score descending.
    """

    _instances: ClassVar[list[_FakeCrossEncoder]] = []

    def __init__(
        self,
        model_name: str,
        device: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.model_name = model_name
        self.device = device
        _FakeCrossEncoder._instances.append(self)

    def predict(self, pairs: list[tuple[str, str]], **kwargs: Any) -> list[float]:
        # Index 0 -> 0.0, index 1 -> -1.0, ... so index 0 is always "best".
        return [float(-i) for i in range(len(pairs))]


@pytest.fixture(autouse=True)
def _clear_fake_instances() -> None:
    _FakeCrossEncoder._instances.clear()


@pytest.fixture
def patch_cross_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch sentence_transformers.CrossEncoder to the fake."""
    import sentence_transformers

    monkeypatch.setattr(
        sentence_transformers,
        "CrossEncoder",
        _FakeCrossEncoder,
    )
    # The reranker module does `from sentence_transformers import CrossEncoder`
    # inside _ensure_loaded (lazy import), so the monkeypatch on the package
    # symbol above is what _ensure_loaded picks up.


def test_rerank_empty_candidates_returns_empty_without_loading(
    patch_cross_encoder: None,
) -> None:
    """rerank([]) returns [] and MUST NOT trigger CrossEncoder load."""
    from book_pipeline.rag.reranker import BgeReranker

    r = BgeReranker(model_name="BAAI/bge-reranker-v2-m3", device="cpu")
    out = r.rerank("query", [], top_k=8)
    assert out == []
    assert _FakeCrossEncoder._instances == [], (
        "Empty-candidates path must not load the model"
    )


def test_rerank_five_candidates_top_k_three_returns_three_sorted(
    patch_cross_encoder: None,
) -> None:
    from book_pipeline.rag.reranker import BgeReranker

    r = BgeReranker(model_name="BAAI/bge-reranker-v2-m3", device="cpu")
    candidates = [
        ("text-0", {"id": "p0"}),
        ("text-1", {"id": "p1"}),
        ("text-2", {"id": "p2"}),
        ("text-3", {"id": "p3"}),
        ("text-4", {"id": "p4"}),
    ]
    out = r.rerank("query", candidates, top_k=3)
    assert len(out) == 3
    # The fake assigns highest score to index 0; sorted descending -> [0, 1, 2].
    assert [t[0] for t in out] == ["text-0", "text-1", "text-2"]
    # Verify scores are in descending order.
    scores = [t[2] for t in out]
    assert scores == sorted(scores, reverse=True)
    # Payload preserved.
    assert out[0][1] == {"id": "p0"}


def test_rerank_top_k_greater_than_candidates_returns_all_sorted(
    patch_cross_encoder: None,
) -> None:
    from book_pipeline.rag.reranker import BgeReranker

    r = BgeReranker(model_name="BAAI/bge-reranker-v2-m3", device="cpu")
    candidates = [
        ("a", 1),
        ("b", 2),
        ("c", 3),
        ("d", 4),
        ("e", 5),
    ]
    out = r.rerank("query", candidates, top_k=10)
    assert len(out) == 5
    scores = [t[2] for t in out]
    assert scores == sorted(scores, reverse=True)


def test_rerank_does_not_mutate_candidates(patch_cross_encoder: None) -> None:
    from book_pipeline.rag.reranker import BgeReranker

    r = BgeReranker(model_name="BAAI/bge-reranker-v2-m3", device="cpu")
    candidates = [
        ("x", "payload-x"),
        ("y", "payload-y"),
        ("z", "payload-z"),
    ]
    original = list(candidates)
    _ = r.rerank("query", candidates, top_k=8)
    assert candidates == original, "rerank() must not mutate its candidates argument"
