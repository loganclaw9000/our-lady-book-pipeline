"""Plan 04-05 Task 1 — `book-pipeline chapter <N>` CLI tests.

6 tests covering:
  1. --help prints usage
  2. invalid chapter_num returns exit 2
  3. missing scene dir returns exit 2 with stderr
  4. _build_dag_orchestrator wires all dependencies
  5. run happy path (DAG_COMPLETE) returns exit 0
  6. run chapter-fail (exit 3) and dag-blocked (exit 4)

All tests mock external infrastructure (LLM clients, vLLM, BGE embedders,
rerankers) — NO real Anthropic API call, NO vLLM boot. Tests use tmp_path
for filesystem isolation.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from book_pipeline.interfaces.types import (
    ChapterState,
    ChapterStateRecord,
)

# --------------------------------------------------------------------------- #
# Test 1: --help                                                               #
# --------------------------------------------------------------------------- #


def test_chapter_help_prints_usage() -> None:
    """`book-pipeline chapter --help` exits 0 + usage contains 'chapter_num'."""
    result = subprocess.run(
        ["uv", "run", "book-pipeline", "chapter", "--help"],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )
    assert result.returncode == 0, (
        f"chapter --help failed: stdout={result.stdout} stderr={result.stderr}"
    )
    assert "chapter_num" in result.stdout.lower()


# --------------------------------------------------------------------------- #
# Test 2: invalid chapter_num → exit 2                                          #
# --------------------------------------------------------------------------- #


def test_chapter_invalid_chapter_num_returns_2() -> None:
    """`book-pipeline chapter -1` returns exit 2 without running the DAG."""
    result = subprocess.run(
        ["uv", "run", "book-pipeline", "chapter", "-1"],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )
    # argparse rejects negatives for a positional int; returncode should be
    # 2 either way (argparse 2 OR our explicit 2 from _run).
    assert result.returncode == 2, (
        f"expected exit 2, got {result.returncode}; "
        f"stdout={result.stdout} stderr={result.stderr}"
    )


# --------------------------------------------------------------------------- #
# Test 3: missing scene dir → exit 2                                           #
# --------------------------------------------------------------------------- #


def test_chapter_missing_scene_dir_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling chapter on a non-existent chapter dir → exit 2 via ChapterGateError."""
    import book_pipeline.cli.chapter as chapter_mod

    # Build a minimal fake orchestrator that raises ChapterGateError on run().
    from book_pipeline.chapter_assembler.dag import ChapterGateError

    class _FakeOrch:
        def run(
            self, chapter_num: int, *, expected_scene_count: int | None = None
        ) -> ChapterStateRecord:
            raise ChapterGateError(
                "scene_count_mismatch", expected=3, actual=0, missing=["ch99_sc01.md"]
            )

    monkeypatch.setattr(
        chapter_mod,
        "_build_dag_orchestrator",
        lambda chapter_num: _FakeOrch(),
    )
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(
        chapter_num=99, expected_scene_count=3, no_archive=False
    )
    rc = chapter_mod._run(args)
    assert rc == 2


# --------------------------------------------------------------------------- #
# Test 4: _build_dag_orchestrator wires all deps                                #
# --------------------------------------------------------------------------- #


def test_build_orchestrator_wires_all_deps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct call to `_build_dag_orchestrator(99)` returns an orchestrator with
    assembler, chapter_critic, entity_extractor, retrospective_writer non-None.

    Mocks:
      - VoicePinConfig / RubricConfig / RagRetrieversConfig / ModeThresholdsConfig.
      - BgeM3Embedder / BgeReranker (avoid GPU loads).
      - build_llm_client (avoid subprocess).
      - build_retrievers_from_config (avoid LanceDB load).
      - _read_latest_ingestion_run_id (avoid indexes/ requirement).
    """
    import book_pipeline.cli.chapter as chapter_mod

    monkeypatch.chdir(tmp_path)

    # Fake config loaders with minimal attribute surfaces.
    fake_voice_pin = SimpleNamespace(
        voice_pin=SimpleNamespace(checkpoint_sha="fake_voice_pin_sha")
    )
    fake_rubric = SimpleNamespace(
        chapter_rubric=SimpleNamespace(rubric_version="chapter.v1"),
        rubric_version="v1",
    )
    fake_rag = SimpleNamespace(
        embeddings=SimpleNamespace(
            model="BAAI/bge-m3", model_revision="latest-stable", device="cpu"
        ),
        reranker=SimpleNamespace(model="BAAI/bge-reranker-v2-m3", device="cpu"),
    )
    fake_mode_thresholds = SimpleNamespace(
        critic_backend=SimpleNamespace(
            kind="claude_code_cli",
            model="claude-opus-4-7",
            timeout_s=180,
            max_budget_usd_per_scene=1.0,
        )
    )

    monkeypatch.setattr(
        chapter_mod, "VoicePinConfig", lambda: fake_voice_pin, raising=False
    )
    monkeypatch.setattr(
        chapter_mod, "RubricConfig", lambda: fake_rubric, raising=False
    )
    monkeypatch.setattr(
        chapter_mod, "RagRetrieversConfig", lambda: fake_rag, raising=False
    )
    monkeypatch.setattr(
        chapter_mod,
        "ModeThresholdsConfig",
        lambda: fake_mode_thresholds,
        raising=False,
    )

    # Patch heavy constructors.
    class _FakeEmbedder:
        def encode(self, text: str) -> list[float]:
            return [0.0] * 1024

    class _FakeReranker:
        pass

    class _FakeRetriever:
        def __init__(self, name: str) -> None:
            self.name = name

    monkeypatch.setattr(
        chapter_mod, "BgeM3Embedder", lambda **kw: _FakeEmbedder(), raising=False
    )
    monkeypatch.setattr(
        chapter_mod, "BgeReranker", lambda **kw: _FakeReranker(), raising=False
    )
    monkeypatch.setattr(
        chapter_mod,
        "build_retrievers_from_config",
        lambda **kw: {
            "historical": _FakeRetriever("historical"),
            "metaphysics": _FakeRetriever("metaphysics"),
            "entity_state": _FakeRetriever("entity_state"),
            "arc_position": _FakeRetriever("arc_position"),
            "negative_constraint": _FakeRetriever("negative_constraint"),
        },
        raising=False,
    )
    monkeypatch.setattr(
        chapter_mod, "build_llm_client", lambda cfg: object(), raising=False
    )
    monkeypatch.setattr(
        chapter_mod,
        "_read_latest_ingestion_run_id",
        lambda indexes_dir: "ing_test_001",
    )

    # Patch the Phase 4 concrete classes to avoid template file reads
    # (templates live under src/ and Jinja2 is scoped to the real location;
    # monkeypatch.chdir(tmp_path) makes relative paths fail).
    class _FakeAssembler:
        pass

    class _FakeChapterCritic:
        def __init__(self, **_kw: Any) -> None:
            pass

    class _FakeEntityExtractor:
        def __init__(self, **_kw: Any) -> None:
            pass

    class _FakeRetrospectiveWriter:
        def __init__(self, **_kw: Any) -> None:
            pass

    class _FakeBundler:
        def __init__(self, **_kw: Any) -> None:
            pass

    import book_pipeline.chapter_assembler as ca_mod
    import book_pipeline.critic.chapter as cc_mod
    import book_pipeline.entity_extractor as ee_mod
    import book_pipeline.rag.bundler as bundler_mod
    import book_pipeline.retrospective as rw_mod

    monkeypatch.setattr(ca_mod, "ConcatAssembler", _FakeAssembler)
    monkeypatch.setattr(cc_mod, "ChapterCritic", _FakeChapterCritic)
    monkeypatch.setattr(ee_mod, "OpusEntityExtractor", _FakeEntityExtractor)
    monkeypatch.setattr(
        rw_mod, "OpusRetrospectiveWriter", _FakeRetrospectiveWriter
    )
    monkeypatch.setattr(
        bundler_mod, "ContextPackBundlerImpl", _FakeBundler
    )

    orch = chapter_mod._build_dag_orchestrator(99)

    assert orch.assembler is not None
    assert orch.chapter_critic is not None
    assert orch.entity_extractor is not None
    assert orch.retrospective_writer is not None
    assert orch.bundler is not None
    assert orch.retrievers is not None
    assert len(orch.retrievers) == 5


# --------------------------------------------------------------------------- #
# Test 5: run happy path (DAG_COMPLETE) → exit 0                                #
# --------------------------------------------------------------------------- #


def test_run_happy_path_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Mock orchestrator.run to return a DAG_COMPLETE record; _run returns 0."""
    import book_pipeline.cli.chapter as chapter_mod

    monkeypatch.chdir(tmp_path)

    happy_record = ChapterStateRecord(
        chapter_num=99,
        state=ChapterState.DAG_COMPLETE,
        scene_ids=["ch99_sc01", "ch99_sc02", "ch99_sc03"],
        chapter_sha="abc123def456" + "0" * 28,
        dag_step=4,
        history=[],
        blockers=[],
    )

    class _FakeOrch:
        def run(
            self, chapter_num: int, *, expected_scene_count: int | None = None
        ) -> ChapterStateRecord:
            return happy_record

    monkeypatch.setattr(
        chapter_mod,
        "_build_dag_orchestrator",
        lambda chapter_num: _FakeOrch(),
    )

    args = argparse.Namespace(
        chapter_num=99, expected_scene_count=3, no_archive=False
    )
    rc = chapter_mod._run(args)
    assert rc == 0


# --------------------------------------------------------------------------- #
# Test 6: chapter-fail → 3; dag-blocked → 4                                     #
# --------------------------------------------------------------------------- #


def test_run_chapter_fail_returns_3_and_dag_blocked_returns_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Map CHAPTER_FAIL → 3 and DAG_BLOCKED → 4 in _run's state-to-exit-code mapping."""
    import book_pipeline.cli.chapter as chapter_mod

    monkeypatch.chdir(tmp_path)

    # Case 1: CHAPTER_FAIL → 3
    fail_record = ChapterStateRecord(
        chapter_num=99,
        state=ChapterState.CHAPTER_FAIL,
        scene_ids=["ch99_sc01"],
        chapter_sha=None,
        dag_step=0,
        history=[],
        blockers=["chapter_critic_axis_fail"],
    )

    class _OrchFail:
        def run(
            self, chapter_num: int, *, expected_scene_count: int | None = None
        ) -> ChapterStateRecord:
            return fail_record

    monkeypatch.setattr(
        chapter_mod,
        "_build_dag_orchestrator",
        lambda chapter_num: _OrchFail(),
    )
    args = argparse.Namespace(
        chapter_num=99, expected_scene_count=3, no_archive=False
    )
    rc = chapter_mod._run(args)
    assert rc == 3

    # Case 2: DAG_BLOCKED → 4
    blocked_record = ChapterStateRecord(
        chapter_num=99,
        state=ChapterState.DAG_BLOCKED,
        scene_ids=["ch99_sc01"],
        chapter_sha="a" * 40,
        dag_step=1,
        history=[],
        blockers=["entity_extraction:failed"],
    )

    class _OrchBlocked:
        def run(
            self, chapter_num: int, *, expected_scene_count: int | None = None
        ) -> ChapterStateRecord:
            return blocked_record

    monkeypatch.setattr(
        chapter_mod,
        "_build_dag_orchestrator",
        lambda chapter_num: _OrchBlocked(),
    )
    rc = chapter_mod._run(args)
    assert rc == 4


# --------------------------------------------------------------------------- #
# Test 7: EXPECTED_SCENE_COUNTS book-specifics table                            #
# --------------------------------------------------------------------------- #


def test_expected_scene_counts_table_shape() -> None:
    """`EXPECTED_SCENE_COUNTS` covers chapters 1-27 + 99 with int values."""
    from book_pipeline.book_specifics.outline_scene_counts import (
        EXPECTED_SCENE_COUNTS,
        expected_scene_count,
    )

    # Chapters 1-27 + 99 all present.
    for n in range(1, 28):
        assert n in EXPECTED_SCENE_COUNTS, f"chapter {n} missing"
        assert isinstance(EXPECTED_SCENE_COUNTS[n], int)
        assert EXPECTED_SCENE_COUNTS[n] >= 1
    assert 99 in EXPECTED_SCENE_COUNTS
    assert EXPECTED_SCENE_COUNTS[99] == 3

    # Helper returns 3 as fallback on unknown chapter.
    assert expected_scene_count(999) == 3
    assert expected_scene_count(99) == 3
