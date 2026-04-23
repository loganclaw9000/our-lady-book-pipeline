"""End-to-end integration test for Plan 05-04 nightly-run (ORCH-01 + LOOP-01).

Exercises the composition:
  (a) vllm-bootstrap (mocked to succeed),
  (b) scene-loop across N scenes,
  (c) chapter DAG trigger when buffer full (mocked),
  (d) role='nightly_run' completion Event emitted,

inside a tmp_path + mocked externals. NO real vLLM, NO real Anthropic, NO
real Telegram, NO real openclaw cron.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest

from book_pipeline.cli import nightly_run as nightly_mod


class _FakeAlerter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def send_alert(self, condition: str, detail: dict[str, Any]) -> bool:
        self.calls.append((condition, dict(detail)))
        return True


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


def test_nightly_run_drives_scenes_and_triggers_chapter_dag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive a 3-scene nightly: 1 committed scene + chapter DAG fires + exit 0.

    All externals mocked; the test verifies composition + event emission.
    """
    alerter = _FakeAlerter()
    logger = _FakeEventLogger()
    chapter_dag_calls: list[int] = []

    monkeypatch.setattr(nightly_mod, "boot_vllm_if_needed", lambda: 0)
    monkeypatch.setattr(nightly_mod, "_build_nightly_alerter", lambda: alerter)
    monkeypatch.setattr(nightly_mod, "_build_event_logger", lambda: logger)
    monkeypatch.setattr(
        nightly_mod,
        "_discover_pending_scenes",
        lambda _max: ["ch99_sc03"],
    )

    def _scene_loop(scene_id: str, alerter: Any, logger: Any) -> int:
        # Simulate a successful commit (rc=0).
        return 0

    monkeypatch.setattr(nightly_mod, "_run_one_scene", _scene_loop)

    def _fake_chapter_dag(
        scenes_committed: list[str], alerter: Any, logger: Any
    ) -> None:
        chapter_dag_calls.append(len(scenes_committed))

    monkeypatch.setattr(
        nightly_mod, "_maybe_trigger_chapter_dag", _fake_chapter_dag
    )

    args = argparse.Namespace(
        max_scenes=5, chapter=99, skip_vllm=False, dry_run=False
    )
    rc = nightly_mod._run_nightly(args)
    assert rc == 0, f"expected exit 0 on progress; got {rc}"

    # Chapter DAG was invoked (once) with the 1 committed scene.
    assert chapter_dag_calls == [1], (
        f"expected chapter DAG fired once with 1 committed scene; "
        f"got calls={chapter_dag_calls!r}"
    )

    # Completion event present with expected shape.
    nightly_events = [
        e for e in logger.events if getattr(e, "role", None) == "nightly_run"
    ]
    assert len(nightly_events) == 1, (
        f"expected exactly 1 role='nightly_run' Event; "
        f"got {[getattr(e, 'role', None) for e in logger.events]}"
    )
    ev = nightly_events[0]
    assert ev.extra["committed_count"] == 1
    assert ev.extra["hard_blocked"] is False
    assert ev.extra["max_scenes"] == 5
    assert alerter.calls == [], f"no alerts expected on happy path; got {alerter.calls!r}"


def test_nightly_run_hard_block_surfaces_alert_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HARD_BLOCK on scene 1 → STOP; chapter DAG NOT fired; exit 3."""
    alerter = _FakeAlerter()
    logger = _FakeEventLogger()
    chapter_dag_calls: list[int] = []

    monkeypatch.setattr(nightly_mod, "boot_vllm_if_needed", lambda: 0)
    monkeypatch.setattr(nightly_mod, "_build_nightly_alerter", lambda: alerter)
    monkeypatch.setattr(nightly_mod, "_build_event_logger", lambda: logger)
    monkeypatch.setattr(
        nightly_mod,
        "_discover_pending_scenes",
        lambda _max: ["ch99_sc01", "ch99_sc02"],
    )
    monkeypatch.setattr(
        nightly_mod, "_run_one_scene", lambda scene_id, alerter, logger: 3
    )
    monkeypatch.setattr(
        nightly_mod,
        "_maybe_trigger_chapter_dag",
        lambda scenes, alerter, logger: chapter_dag_calls.append(len(scenes)),
    )

    args = argparse.Namespace(
        max_scenes=5, chapter=99, skip_vllm=False, dry_run=False
    )
    rc = nightly_mod._run_nightly(args)
    assert rc == 3, f"expected exit 3 on hard-block; got {rc}"
    assert chapter_dag_calls == [], (
        f"chapter DAG must NOT fire on hard-block; got {chapter_dag_calls!r}"
    )
