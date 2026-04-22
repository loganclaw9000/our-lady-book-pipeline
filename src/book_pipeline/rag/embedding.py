"""BGE-M3 embedding wrapper — kernel primitive for the 5 RAG axes.

The 5 retrievers share ONE BgeM3Embedder instance (STACK.md) — the embedder
is heavy (~2GB weights loaded once per process) and embedding is pure, so
sharing is safe and cheap.

Loading is LAZY: constructing a BgeM3Embedder does NOT download / deserialize
the model. The model is materialized on the first embed_texts / revision_sha
call. This matters because:

  - Unit tests construct the embedder to inspect its attributes without ever
    needing the 2GB model on disk.
  - Plan 02 constructs the embedder during ingester wiring but doesn't need
    the model until it processes the first chunk batch.

`revision_sha` is the reproducibility anchor: Plan 02 writes it into each
`event_type=ingestion_run` Event so re-ingestion later can detect model drift.
If the user pinned a specific `revision` (hub revision SHA or tag), that value
is returned verbatim. If `revision=None`, the current HEAD SHA is resolved
from HfApi.model_info once (on first access) and cached.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import numpy as np
from huggingface_hub import HfApi
from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:  # pragma: no cover — types only.
    pass

EMBEDDING_DIM: Final[int] = 1024


class BgeM3Embedder:
    """Thin wrapper around sentence_transformers.SentenceTransformer for BGE-M3.

    One instance per process. Thread-safe for reads once loaded; not safe for
    concurrent first-load calls (Plan 02 loads at ingester startup on the main
    thread).
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        revision: str | None = None,
        device: str = "cuda:0",
    ) -> None:
        self.model_name = model_name
        self.revision = revision
        self.device = device
        # Lazy-loaded state.
        self._model: Any | None = None
        self._revision_sha: str | None = None

    # --- Lazy load ---------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        # Resolve revision SHA first — if the user passed an explicit revision
        # we trust it verbatim (it IS the pin). If not, we ask the hub for the
        # current HEAD SHA and record that as our pin for the lifetime of this
        # process. Plan 02 reads `revision_sha` after load to write into
        # `event_type=ingestion_run` events.
        if self.revision is not None:
            self._revision_sha = self.revision
        else:
            self._revision_sha = HfApi().model_info(self.model_name).sha

        self._model = SentenceTransformer(
            self.model_name,
            revision=self.revision,
            device=self.device,
        )

    # --- Public API --------------------------------------------------------

    @property
    def revision_sha(self) -> str:
        """Return the resolved revision SHA (triggers load if needed).

        Guaranteed non-empty post-load. If `revision` was passed explicitly at
        construction time, that string is returned verbatim. Otherwise the SHA
        resolved from HfApi.model_info on first access is returned (and cached).
        """
        self._ensure_loaded()
        assert self._revision_sha is not None  # set by _ensure_loaded
        return self._revision_sha

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Return a (len(texts), EMBEDDING_DIM) float32 array of unit-normalized embeddings.

        Degenerate: embed_texts([]) returns an empty (0, EMBEDDING_DIM) float32 array
        without loading the model.
        """
        if not texts:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

        self._ensure_loaded()
        assert self._model is not None

        raw = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        arr: np.ndarray = np.asarray(raw)
        # Ensure invariants: shape + dtype.
        if arr.dtype != np.float32:
            arr = arr.astype(np.float32)
        assert arr.shape == (len(texts), EMBEDDING_DIM), (
            f"BGE-M3 returned unexpected shape {arr.shape}; "
            f"expected ({len(texts)}, {EMBEDDING_DIM})"
        )
        return arr


__all__ = ["EMBEDDING_DIM", "BgeM3Embedder"]
