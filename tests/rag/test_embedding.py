"""Tests for book_pipeline.rag.embedding.

Behavior under test (from 02-01-PLAN.md <behavior>):
  - EMBEDDING_DIM == 1024 (module-level constant; BGE-M3 dense output dim).
  - BgeM3Embedder is lazy: __init__ does NOT load the SentenceTransformer model.
  - revision_sha returns a non-empty string after load.
  - embed_texts returns (n, 1024) float32 numpy array, finite row norms.

The fake SentenceTransformer is monkeypatched into sentence_transformers to
avoid downloading the real ~2GB BGE-M3 model during unit tests.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pytest


class _FakeSentenceTransformer:
    """Stand-in for sentence_transformers.SentenceTransformer used in unit tests."""

    _instances: ClassVar[list[_FakeSentenceTransformer]] = []

    def __init__(
        self,
        model_name: str,
        revision: str | None = None,
        device: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.model_name = model_name
        self.revision = revision
        self.device = device
        _FakeSentenceTransformer._instances.append(self)

    def encode(
        self,
        texts: list[str],
        normalize_embeddings: bool = False,
        convert_to_numpy: bool = True,
        show_progress_bar: bool = False,
        **kwargs: Any,
    ) -> np.ndarray:
        n = len(texts)
        # Deterministic pseudo-embeddings: hash → row; float32.
        rng = np.random.default_rng(seed=abs(hash(tuple(texts))) % (2**32))
        arr = rng.standard_normal((n, 1024)).astype(np.float32)
        if normalize_embeddings:
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            arr = arr / norms
        return arr


@pytest.fixture(autouse=True)
def _clear_fake_instances() -> None:
    _FakeSentenceTransformer._instances.clear()


@pytest.fixture
def patch_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the SentenceTransformer symbol the embedder imports."""
    import sentence_transformers

    monkeypatch.setattr(
        sentence_transformers,
        "SentenceTransformer",
        _FakeSentenceTransformer,
    )
    # Also patch in case the embedder module binds it at import time.
    import book_pipeline.rag.embedding as emb_module

    if hasattr(emb_module, "SentenceTransformer"):
        monkeypatch.setattr(emb_module, "SentenceTransformer", _FakeSentenceTransformer)


def test_embedding_dim_is_1024() -> None:
    from book_pipeline.rag import EMBEDDING_DIM
    from book_pipeline.rag.embedding import EMBEDDING_DIM as EMBEDDING_DIM_INNER

    assert EMBEDDING_DIM == 1024
    assert EMBEDDING_DIM_INNER == 1024


def test_embedder_is_lazy(patch_sentence_transformers: None) -> None:
    """__init__ must NOT load the SentenceTransformer."""
    from book_pipeline.rag import BgeM3Embedder

    emb = BgeM3Embedder(model_name="BAAI/bge-m3", revision="stub-rev-abc", device="cpu")
    # Before any embed_texts or revision_sha call, no fake instances should exist.
    assert _FakeSentenceTransformer._instances == [], (
        "BgeM3Embedder.__init__ should NOT load the model (lazy loading required)"
    )
    # Attributes recorded.
    assert emb.model_name == "BAAI/bge-m3"
    assert emb.revision == "stub-rev-abc"
    assert emb.device == "cpu"


def test_embedder_revision_sha_returns_explicit_revision(
    patch_sentence_transformers: None,
) -> None:
    """If revision is passed explicitly, revision_sha returns it verbatim."""
    from book_pipeline.rag import BgeM3Embedder

    emb = BgeM3Embedder(
        model_name="BAAI/bge-m3", revision="stub-rev-abc-123", device="cpu"
    )
    sha = emb.revision_sha
    assert isinstance(sha, str)
    assert sha == "stub-rev-abc-123"
    assert len(sha) > 0


def test_embedder_revision_sha_resolves_from_hub_when_none(
    monkeypatch: pytest.MonkeyPatch, patch_sentence_transformers: None
) -> None:
    """If revision is None, revision_sha must be resolved via HfApi.model_info."""
    import huggingface_hub

    class _FakeModelInfo:
        sha = "fake-hub-sha-xyz"

    class _FakeHfApi:
        def model_info(self, repo_id: str) -> _FakeModelInfo:
            assert repo_id == "BAAI/bge-m3"
            return _FakeModelInfo()

    monkeypatch.setattr(huggingface_hub, "HfApi", _FakeHfApi)
    import book_pipeline.rag.embedding as emb_module

    monkeypatch.setattr(emb_module, "HfApi", _FakeHfApi, raising=False)

    from book_pipeline.rag import BgeM3Embedder

    emb = BgeM3Embedder(model_name="BAAI/bge-m3", revision=None, device="cpu")
    assert emb.revision_sha == "fake-hub-sha-xyz"


def test_embed_texts_shape_and_dtype(patch_sentence_transformers: None) -> None:
    """embed_texts(['hello', 'world']) → (2, 1024) float32 finite."""
    from book_pipeline.rag import BgeM3Embedder

    emb = BgeM3Embedder(
        model_name="BAAI/bge-m3", revision="stub-rev", device="cpu"
    )
    out = emb.embed_texts(["hello", "world"])
    assert isinstance(out, np.ndarray), f"expected np.ndarray, got {type(out)}"
    assert out.shape == (2, 1024), f"expected (2, 1024), got {out.shape}"
    assert out.dtype == np.float32, f"expected float32, got {out.dtype}"
    # Row norms are finite.
    norms = np.linalg.norm(out, axis=1)
    assert np.all(np.isfinite(norms)), f"non-finite row norm(s): {norms}"
    # And since we requested normalized embeddings, norms should be ~1.
    assert np.allclose(norms, 1.0, atol=1e-5), (
        f"expected unit-norm rows, got {norms}"
    )


def test_embed_texts_empty_list(patch_sentence_transformers: None) -> None:
    """Degenerate but defined: empty input → (0, 1024) or similar shape."""
    from book_pipeline.rag import BgeM3Embedder

    emb = BgeM3Embedder(model_name="BAAI/bge-m3", revision="stub-rev", device="cpu")
    out = emb.embed_texts([])
    assert isinstance(out, np.ndarray)
    assert out.shape[0] == 0
    # dtype should still be float32.
    assert out.dtype == np.float32
