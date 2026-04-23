"""Plan 04-05 Task 1 — `book-pipeline chapter-status [<N>]` CLI tests.

4 tests:
  1. No args + pipeline_state.json present → pretty-print JSON view
  2. No args + no pipeline_state.json → hint message
  3. chapter_num present + state file on disk → print state/dag_step/history
  4. chapter_num present + no state file → "No chapter buffer state for chNN."
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from book_pipeline.interfaces.types import (
    ChapterState,
    ChapterStateRecord,
)


def test_no_args_prints_pipeline_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """No args → pretty-prints `.planning/pipeline_state.json`."""
    import book_pipeline.cli.chapter_status as cs

    monkeypatch.chdir(tmp_path)
    planning = tmp_path / ".planning"
    planning.mkdir()
    state = {
        "last_committed_chapter": 1,
        "last_committed_dag_step": 4,
        "dag_complete": True,
        "last_hard_block": None,
    }
    (planning / "pipeline_state.json").write_text(json.dumps(state, indent=2))

    args = argparse.Namespace(chapter_num=None)
    rc = cs._run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "last_committed_chapter" in out
    assert "dag_complete" in out


def test_no_args_no_state_prints_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """No args + no pipeline_state.json → hint message."""
    import book_pipeline.cli.chapter_status as cs

    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(chapter_num=None)
    rc = cs._run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "no pipeline state" in out.lower()


def test_with_chapter_num_prints_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """chapter_num with matching state.json → prints state/dag_step/history summary."""
    import book_pipeline.cli.chapter_status as cs

    monkeypatch.chdir(tmp_path)
    buf = tmp_path / "drafts" / "chapter_buffer"
    buf.mkdir(parents=True)
    record = ChapterStateRecord(
        chapter_num=1,
        state=ChapterState.DAG_COMPLETE,
        scene_ids=["ch01_sc01", "ch01_sc02", "ch01_sc03"],
        chapter_sha="b" * 40,
        dag_step=4,
        history=[
            {
                "from": "pending_scenes",
                "to": "assembling",
                "ts_iso": "2026-04-23T00:00:00Z",
                "note": "start concat",
            },
            {
                "from": "assembling",
                "to": "assembled",
                "ts_iso": "2026-04-23T00:00:01Z",
                "note": "concat ok",
            },
            {
                "from": "post_commit_dag",
                "to": "dag_complete",
                "ts_iso": "2026-04-23T00:00:02Z",
                "note": "retro written",
            },
        ],
        blockers=[],
    )
    (buf / "ch01.state.json").write_text(record.model_dump_json(indent=2))

    args = argparse.Namespace(chapter_num=1)
    rc = cs._run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "state:" in out.lower()
    assert "dag_step:" in out.lower()
    assert "history" in out.lower()
    # DAG_COMPLETE value should appear
    assert "dag_complete" in out


def test_with_chapter_num_missing_prints_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """chapter_num with NO matching state.json → hint with ch{NN}."""
    import book_pipeline.cli.chapter_status as cs

    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(chapter_num=42)
    rc = cs._run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "ch42" in out.lower()
    assert "no chapter buffer state" in out.lower()
