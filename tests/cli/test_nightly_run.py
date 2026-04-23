"""Unit tests for `book-pipeline nightly-run` CLI (Plan 05-04 Task 3).

Exit codes (D-16 + OQ 5):
  0  ≥1 scene reached COMMITTED this run.
  2  vllm-bootstrap-failed.
  3  hard-block-fired (Telegram alert sent; STOP — don't cascade).
  4  max-scenes-reached with zero progress.

All externals are mocked:
  - boot_vllm_if_needed → int (monkeypatched).
  - scene_loop_runner (per-scene call) → int (monkeypatched).
  - TelegramAlerter → FakeAlerter that records calls.
  - chapter DAG trigger → no-op.
"""
from __future__ import annotations

import argparse
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


def _base_args(
    *,
    max_scenes: int = 5,
    chapter: int | None = None,
    skip_vllm: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        max_scenes=max_scenes,
        chapter=chapter,
        skip_vllm=skip_vllm,
        dry_run=False,
    )


def test_nightly_run_exit_0_on_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fake scene loop that COMMITS 2 scenes → exit 0; role='nightly_run'
    Event emitted with extra.committed_count=2."""
    alerter = _FakeAlerter()
    logger = _FakeEventLogger()

    monkeypatch.setattr(nightly_mod, "boot_vllm_if_needed", lambda: 0)
    monkeypatch.setattr(nightly_mod, "_build_nightly_alerter", lambda: alerter)
    monkeypatch.setattr(nightly_mod, "_build_event_logger", lambda: logger)
    monkeypatch.setattr(
        nightly_mod,
        "_discover_pending_scenes",
        lambda _max: ["ch99_sc01", "ch99_sc02"],
    )
    # 2 successful scenes (rc=0 twice).
    monkeypatch.setattr(
        nightly_mod,
        "_run_one_scene",
        lambda scene_id, alerter, logger: 0,
    )
    # Chapter DAG not triggered in this minimal test.
    monkeypatch.setattr(nightly_mod, "_maybe_trigger_chapter_dag", lambda *a, **k: None)

    rc = nightly_mod._run_nightly(_base_args(max_scenes=5))
    assert rc == 0, f"expected exit 0; got {rc}"

    nightly_events = [e for e in logger.events if getattr(e, "role", None) == "nightly_run"]
    assert len(nightly_events) == 1, f"expected 1 nightly_run Event; got {logger.events!r}"
    extra = nightly_events[0].extra
    assert extra["committed_count"] == 2
    assert extra["hard_blocked"] is False
    assert alerter.calls == [], f"no alerts expected; got {alerter.calls!r}"


def test_nightly_run_exit_2_on_vllm_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """boot_vllm_if_needed nonzero → exit 2; no scene loop; alert 'vllm_health_failed' sent."""
    alerter = _FakeAlerter()
    logger = _FakeEventLogger()
    scene_call_count: list[int] = [0]

    monkeypatch.setattr(nightly_mod, "boot_vllm_if_needed", lambda: 2)
    monkeypatch.setattr(nightly_mod, "_build_nightly_alerter", lambda: alerter)
    monkeypatch.setattr(nightly_mod, "_build_event_logger", lambda: logger)

    def _scene_loop(scene_id: str, alerter: Any, logger: Any) -> int:
        scene_call_count[0] += 1
        return 0

    monkeypatch.setattr(nightly_mod, "_run_one_scene", _scene_loop)

    rc = nightly_mod._run_nightly(_base_args())
    assert rc == 2, f"expected exit 2 on vllm fail; got {rc}"
    assert scene_call_count[0] == 0, "scene loop must NOT run when vllm fails"

    assert len(alerter.calls) == 1
    cond, _detail = alerter.calls[0]
    assert cond == "vllm_health_failed"


def test_nightly_run_exit_3_on_hard_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First scene returns rc=3 (hard-block) → STOP + exit 3 (don't cascade)."""
    alerter = _FakeAlerter()
    logger = _FakeEventLogger()
    call_count: list[int] = [0]

    monkeypatch.setattr(nightly_mod, "boot_vllm_if_needed", lambda: 0)
    monkeypatch.setattr(nightly_mod, "_build_nightly_alerter", lambda: alerter)
    monkeypatch.setattr(nightly_mod, "_build_event_logger", lambda: logger)
    monkeypatch.setattr(
        nightly_mod,
        "_discover_pending_scenes",
        lambda _max: ["ch99_sc01", "ch99_sc02", "ch99_sc03"],
    )

    def _scene_loop(scene_id: str, alerter: Any, logger: Any) -> int:
        call_count[0] += 1
        return 3  # hard-block on first scene

    monkeypatch.setattr(nightly_mod, "_run_one_scene", _scene_loop)
    monkeypatch.setattr(nightly_mod, "_maybe_trigger_chapter_dag", lambda *a, **k: None)

    rc = nightly_mod._run_nightly(_base_args(max_scenes=5))
    assert rc == 3, f"expected exit 3 on hard-block; got {rc}"
    assert call_count[0] == 1, f"must STOP after first hard-block; got {call_count[0]} calls"

    nightly_events = [e for e in logger.events if getattr(e, "role", None) == "nightly_run"]
    assert len(nightly_events) == 1
    assert nightly_events[0].extra["hard_blocked"] is True


def test_nightly_run_exit_4_max_scenes_no_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All N scenes return rc=4 (no-progress, non-hard-block) → exit 4."""
    alerter = _FakeAlerter()
    logger = _FakeEventLogger()

    monkeypatch.setattr(nightly_mod, "boot_vllm_if_needed", lambda: 0)
    monkeypatch.setattr(nightly_mod, "_build_nightly_alerter", lambda: alerter)
    monkeypatch.setattr(nightly_mod, "_build_event_logger", lambda: logger)
    monkeypatch.setattr(
        nightly_mod,
        "_discover_pending_scenes",
        lambda _max: ["ch99_sc01", "ch99_sc02"],
    )
    # All scenes exit 4 (no-progress) — not a hard-block; just nothing committed.
    monkeypatch.setattr(
        nightly_mod, "_run_one_scene", lambda scene_id, alerter, logger: 4
    )
    monkeypatch.setattr(nightly_mod, "_maybe_trigger_chapter_dag", lambda *a, **k: None)

    rc = nightly_mod._run_nightly(_base_args(max_scenes=2))
    assert rc == 4, f"expected exit 4 when max-scenes hit with zero progress; got {rc}"

    nightly_events = [e for e in logger.events if getattr(e, "role", None) == "nightly_run"]
    assert len(nightly_events) == 1
    assert nightly_events[0].extra["committed_count"] == 0
    assert nightly_events[0].extra["hard_blocked"] is False


def test_nightly_run_dry_run_asserts_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run verifies composition without invoking vllm / scene loop."""
    scene_calls: list[int] = [0]

    def _should_not_fire() -> int:
        scene_calls[0] += 1
        return 0

    monkeypatch.setattr(nightly_mod, "boot_vllm_if_needed", _should_not_fire)
    monkeypatch.setattr(nightly_mod, "_build_nightly_alerter", lambda: _FakeAlerter())
    monkeypatch.setattr(nightly_mod, "_build_event_logger", lambda: _FakeEventLogger())

    args = argparse.Namespace(
        max_scenes=5, chapter=None, skip_vllm=False, dry_run=True
    )
    rc = nightly_mod._run_nightly(args)
    assert rc == 0, f"expected exit 0 on dry-run; got {rc}"
    assert scene_calls[0] == 0, "dry-run must NOT call vllm bootstrap"
