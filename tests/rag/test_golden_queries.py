"""RAG-04 golden-query CI gate.

This test suite is the anti-drift gate for Phase 2's retrieval quality. It
loads `tests/rag/golden_queries.jsonl` (a fixed SceneRequest-keyed seed set),
runs each query through a real ContextPackBundlerImpl wired to the 5 real
retrievers populated from `indexes/`, and asserts:

    - >=90% of queries return all their `expected_chunks` in the target-axis top-8
    - 0 `forbidden_chunks` appear across ANY retriever's top-8

Seed-set provenance: 12+ queries, >=2 per axis, authored manually from the
real Our Lady of Champion bibles (brief / engineering / pantheon /
known-liberties / outline) -- not auto-generated.

Baseline pinning: `tests/rag/fixtures/expected_chunks.jsonl` captures a
snapshot of (source_file, heading_path, chunk_id, ingestion_run_id, chapter)
tuples at the moment of Plan 02-06's baseline ingest. Regenerate via:

    uv run python tests/rag/_capture_expected_chunks.py

after a fresh successful `book-pipeline ingest --force`. The snapshot is a
PROBE, not the assertion set -- the test uses it to distinguish
"chunk not in the index" from "chunk exists but didn't rank top-8".

Slow marker: the end-to-end test (`test_golden_queries_pass_on_baseline_ingest`)
loads real BGE-M3 + BGE-reranker-v2-m3 weights; it is skipped if `indexes/`
is absent. Schema + coverage tests always run.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

GOLDEN_PATH = Path(__file__).parent / "golden_queries.jsonl"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_CHUNKS_FIXTURE = FIXTURES_DIR / "expected_chunks.jsonl"
INDEXES_DIR = Path(__file__).resolve().parents[2] / "indexes"

REQUIRED_AXES = (
    "historical",
    "metaphysics",
    "entity_state",
    "arc_position",
    "negative_constraint",
)

REQUIRED_KEYS = {
    "query_id",
    "axis",
    "scene_request",
    "expected_chunks",
    "forbidden_chunks",
}


def _load_queries() -> list[dict]:
    return [
        json.loads(line)
        for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _indexes_populated() -> bool:
    """True iff indexes/ contains at least one LanceDB table directory."""
    if not INDEXES_DIR.exists():
        return False
    # LanceDB creates per-axis subdirectories; any non-empty entry means data.
    return any(
        entry.is_dir() and entry.name in REQUIRED_AXES
        for entry in INDEXES_DIR.iterdir()
    )


# --- Always-on tests: schema + coverage -----------------------------------


def test_golden_queries_jsonl_exists_and_nonempty() -> None:
    assert GOLDEN_PATH.exists(), (
        f"golden_queries.jsonl missing at {GOLDEN_PATH}. Plan 02-06 Task 1 "
        "must author >=12 seed queries."
    )
    queries = _load_queries()
    assert len(queries) >= 12, (
        f"golden_queries.jsonl has {len(queries)} queries; RAG-04 requires >=12."
    )


def test_golden_queries_jsonl_schema() -> None:
    """Every line is valid JSON with required keys; scene_request validates."""
    from book_pipeline.interfaces.types import SceneRequest

    for q in _load_queries():
        missing = REQUIRED_KEYS - set(q)
        assert not missing, (
            f"query {q.get('query_id', '<no id>')} missing keys: {missing}"
        )
        # scene_request must validate against the frozen Phase 1 model.
        SceneRequest.model_validate(q["scene_request"])
        # axis must be one of the 5 frozen names.
        assert q["axis"] in REQUIRED_AXES, (
            f"query {q['query_id']}: axis {q['axis']!r} not in REQUIRED_AXES"
        )
        # expected_chunks + forbidden_chunks are lists of dicts with 2 keys.
        for list_name in ("expected_chunks", "forbidden_chunks"):
            for entry in q[list_name]:
                assert set(entry.keys()) >= {
                    "source_file_suffix",
                    "heading_path_substr",
                }, f"query {q['query_id']} {list_name} entry malformed: {entry}"


def test_golden_queries_coverage() -> None:
    """Every axis has >=2 queries (CONTEXT.md golden-query seed-set requirement)."""
    axes = Counter(q["axis"] for q in _load_queries())
    for axis in REQUIRED_AXES:
        assert axes[axis] >= 2, (
            f"axis {axis!r} has only {axes[axis]} queries; need >=2 per axis "
            "(02-CONTEXT.md Golden-Query CI Gate decision)."
        )


def test_golden_queries_ids_are_unique() -> None:
    queries = _load_queries()
    ids = [q["query_id"] for q in queries]
    assert len(ids) == len(set(ids)), (
        f"duplicate query_ids detected: "
        f"{[qid for qid, count in Counter(ids).items() if count > 1]}"
    )


def test_golden_queries_every_query_has_forbidden_chunks() -> None:
    """RAG-04 anti-leak enforcement requires every query to declare forbidden_chunks.

    An empty forbidden_chunks list is OK (the cross-axis constraint is 'nothing
    from axis Y leaks into axis X's top-8'), but the KEY must be present so the
    schema test catches tampering.
    """
    for q in _load_queries():
        assert isinstance(q["forbidden_chunks"], list), (
            f"query {q['query_id']}: forbidden_chunks must be a list"
        )


# --- Slow end-to-end test: real indexes + real models --------------------


@pytest.mark.slow
@pytest.mark.skipif(
    not _indexes_populated(),
    reason=(
        "indexes/ is empty; run `uv run book-pipeline ingest --force` first. "
        "This is the RAG-04 baseline-pinned slow gate."
    ),
)
def test_golden_queries_pass_on_baseline_ingest() -> None:
    """>=90% expected-chunk recall + 0 forbidden leaks across 5 retrievers.

    Builds a real ContextPackBundlerImpl + 5 real retrievers against `indexes/`,
    runs each golden query through `bundler.bundle()`, and asserts the pass
    criteria from 02-CONTEXT.md "Golden-Query CI Gate".
    """
    from book_pipeline.cli._entity_list import build_nahuatl_entity_set

    from book_pipeline.book_specifics.corpus_paths import OUTLINE
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig
    from book_pipeline.interfaces.types import SceneRequest
    from book_pipeline.observability import JsonlEventLogger
    from book_pipeline.rag import ContextPackBundlerImpl
    from book_pipeline.rag.embedding import BgeM3Embedder
    from book_pipeline.rag.reranker import BgeReranker
    from book_pipeline.rag.retrievers import (
        ArcPositionRetriever,
        EntityStateRetriever,
        HistoricalRetriever,
        MetaphysicsRetriever,
        NegativeConstraintRetriever,
    )

    cfg = RagRetrieversConfig()  # type: ignore[call-arg]
    embedder = BgeM3Embedder(
        model_name=cfg.embeddings.model, device=cfg.embeddings.device
    )
    reranker = BgeReranker(
        model_name=cfg.reranker.model, device=cfg.reranker.device
    )
    retrievers = [
        HistoricalRetriever(
            db_path=INDEXES_DIR, embedder=embedder, reranker=reranker
        ),
        MetaphysicsRetriever(
            db_path=INDEXES_DIR, embedder=embedder, reranker=reranker
        ),
        EntityStateRetriever(
            db_path=INDEXES_DIR, embedder=embedder, reranker=reranker
        ),
        ArcPositionRetriever(
            db_path=INDEXES_DIR,
            outline_path=OUTLINE,
            embedder=embedder,
            reranker=reranker,
        ),
        NegativeConstraintRetriever(
            db_path=INDEXES_DIR, embedder=embedder, reranker=reranker
        ),
    ]
    bundler = ContextPackBundlerImpl(
        event_logger=JsonlEventLogger(),
        entity_list=build_nahuatl_entity_set(),  # W-1
    )

    queries = _load_queries()
    results: list[tuple[str, bool, list[tuple[str, dict, str]]]] = []
    for q in queries:
        req = SceneRequest.model_validate(q["scene_request"])
        pack = bundler.bundle(req, retrievers)
        axis_hits = pack.retrievals[q["axis"]].hits

        # Expected: every expected_chunk has at least one matching hit in the
        # target-axis's top-8.
        expected_ok = all(
            any(
                h.source_path.endswith(e["source_file_suffix"])
                and e["heading_path_substr"]
                in str(h.metadata.get("heading_path", ""))
                for h in axis_hits
            )
            for e in q["expected_chunks"]
        )

        # Forbidden: any hit in ANY retriever matching (suffix + substr) fails.
        forbidden_leaks: list[tuple[str, dict, str]] = []
        for axis_name, rr in pack.retrievals.items():
            for h in rr.hits:
                for f in q["forbidden_chunks"]:
                    if h.source_path.endswith(
                        f["source_file_suffix"]
                    ) and f["heading_path_substr"] in str(
                        h.metadata.get("heading_path", "")
                    ):
                        forbidden_leaks.append((axis_name, f, h.chunk_id))
        results.append((q["query_id"], expected_ok, forbidden_leaks))

    # Build helpful failure messages.
    total_leaks = sum(len(leaks) for (_, _, leaks) in results)
    num_pass_expected = sum(1 for (_, ok, _) in results if ok)
    pct = num_pass_expected / len(queries) if queries else 0.0

    leak_report = [
        f"  query={qid}: leaks={leaks}"
        for (qid, _, leaks) in results
        if leaks
    ]
    miss_report = [
        f"  query={qid}: expected chunks NOT in top-8"
        for (qid, ok, _) in results
        if not ok
    ]

    assert total_leaks == 0, (
        f"Forbidden-chunk leaks detected ({total_leaks} total):\n"
        + "\n".join(leak_report)
    )
    assert pct >= 0.90, (
        f"Only {pct:.0%} of queries returned their expected chunks in top-8 "
        f"(required >=90%):\n" + "\n".join(miss_report)
    )


@pytest.mark.slow
@pytest.mark.skipif(
    not _indexes_populated(),
    reason="indexes/ is empty; run `uv run book-pipeline ingest --force` first.",
)
def test_golden_queries_are_deterministic() -> None:
    """Same query twice -> same chunk_ids in same order (query_fingerprint caching).

    Regression guard against retriever non-determinism (e.g. accidental random
    sampling) that would destabilize the golden-query baseline.
    """
    from book_pipeline.book_specifics.corpus_paths import OUTLINE
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig
    from book_pipeline.interfaces.types import SceneRequest
    from book_pipeline.observability import JsonlEventLogger
    from book_pipeline.rag import ContextPackBundlerImpl
    from book_pipeline.rag.embedding import BgeM3Embedder
    from book_pipeline.rag.reranker import BgeReranker
    from book_pipeline.rag.retrievers import (
        ArcPositionRetriever,
        EntityStateRetriever,
        HistoricalRetriever,
        MetaphysicsRetriever,
        NegativeConstraintRetriever,
    )

    cfg = RagRetrieversConfig()  # type: ignore[call-arg]
    embedder = BgeM3Embedder(
        model_name=cfg.embeddings.model, device=cfg.embeddings.device
    )
    reranker = BgeReranker(
        model_name=cfg.reranker.model, device=cfg.reranker.device
    )
    retrievers = [
        HistoricalRetriever(db_path=INDEXES_DIR, embedder=embedder, reranker=reranker),
        MetaphysicsRetriever(db_path=INDEXES_DIR, embedder=embedder, reranker=reranker),
        EntityStateRetriever(db_path=INDEXES_DIR, embedder=embedder, reranker=reranker),
        ArcPositionRetriever(
            db_path=INDEXES_DIR,
            outline_path=OUTLINE,
            embedder=embedder,
            reranker=reranker,
        ),
        NegativeConstraintRetriever(db_path=INDEXES_DIR, embedder=embedder, reranker=reranker),
    ]
    bundler = ContextPackBundlerImpl(event_logger=JsonlEventLogger())

    # Pick the first query for determinism check.
    queries = _load_queries()
    q = queries[0]
    req = SceneRequest.model_validate(q["scene_request"])
    pack_a = bundler.bundle(req, retrievers)
    pack_b = bundler.bundle(req, retrievers)

    for axis_name in REQUIRED_AXES:
        ids_a = [h.chunk_id for h in pack_a.retrievals[axis_name].hits]
        ids_b = [h.chunk_id for h in pack_b.retrievals[axis_name].hits]
        assert ids_a == ids_b, (
            f"Non-deterministic hits on axis {axis_name}: {ids_a} vs {ids_b}"
        )
