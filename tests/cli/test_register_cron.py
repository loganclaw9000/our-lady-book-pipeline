"""Tests for `book-pipeline register-cron` CLI (Plan 05-04 Task 2, D-14 + D-15).

Covers:
  - Happy path: --nightly flag invokes openclaw cron add with the D-15 flag
    list; exit 0.
  - Idempotency: `openclaw cron list` already shows the job → skip the add;
    exit 0; no second subprocess.run(..., cron add) call.
  - Missing OPENCLAW_GATEWAY_TOKEN → exit 2 with actionable stderr message.

NO real openclaw gateway is ever touched — subprocess.run is monkeypatched.
"""
from __future__ import annotations

import argparse
from typing import Any

import pytest

from book_pipeline.cli import register_cron as register_cron_mod


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_register_nightly_cron_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OPENCLAW_GATEWAY_TOKEN set + job not registered → subprocess invoked
    with the D-15 flag list; exit 0."""
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "dummy-token")
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> _FakeCompleted:
        captured.append(list(cmd))
        # First call: `openclaw cron list` returns empty (job not registered).
        if len(cmd) >= 3 and cmd[1] == "cron" and cmd[2] == "list":
            return _FakeCompleted(returncode=0, stdout="", stderr="")
        # Second call: `openclaw cron add` succeeds.
        return _FakeCompleted(returncode=0, stdout="registered", stderr="")

    monkeypatch.setattr(register_cron_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(register_cron_mod.shutil, "which", lambda _: "/bin/openclaw")

    args = argparse.Namespace(nightly=True, cron_freshness=False)
    rc = register_cron_mod._run(args)
    assert rc == 0, f"expected exit 0; got {rc}"

    # Assert the D-15 flag shape was used in the cron-add subprocess call.
    add_calls = [c for c in captured if len(c) >= 3 and c[1] == "cron" and c[2] == "add"]
    assert len(add_calls) == 1, f"expected 1 cron-add call; got {len(add_calls)}"
    add = add_calls[0]
    assert "--name" in add
    name_idx = add.index("--name")
    assert add[name_idx + 1] == "book-pipeline:nightly-run"
    assert "--cron" in add
    cron_idx = add.index("--cron")
    assert add[cron_idx + 1] == "0 2 * * *"
    assert "--tz" in add
    tz_idx = add.index("--tz")
    assert add[tz_idx + 1] == "America/Los_Angeles"
    assert "--session" in add
    assert "isolated" in add
    assert "--agent" in add
    agent_idx = add.index("--agent")
    assert add[agent_idx + 1] == "nightly-runner"
    assert "--message" in add


def test_register_nightly_cron_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`openclaw cron list` already shows the job → CLI skips cron-add."""
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "dummy-token")
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> _FakeCompleted:
        captured.append(list(cmd))
        if len(cmd) >= 3 and cmd[1] == "cron" and cmd[2] == "list":
            return _FakeCompleted(
                returncode=0,
                stdout="book-pipeline:nightly-run 0 2 * * * ...",
                stderr="",
            )
        return _FakeCompleted(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(register_cron_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(register_cron_mod.shutil, "which", lambda _: "/bin/openclaw")

    args = argparse.Namespace(nightly=True, cron_freshness=False)
    rc = register_cron_mod._run(args)
    assert rc == 0, f"expected exit 0 on idempotent skip; got {rc}"

    add_calls = [c for c in captured if len(c) >= 3 and c[1] == "cron" and c[2] == "add"]
    assert len(add_calls) == 0, f"expected NO cron-add on idempotent run; got {add_calls!r}"


def test_register_nightly_cron_missing_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """OPENCLAW_GATEWAY_TOKEN unset → exit 2 + actionable stderr message."""
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    monkeypatch.setattr(register_cron_mod.shutil, "which", lambda _: "/bin/openclaw")

    args = argparse.Namespace(nightly=True, cron_freshness=False)
    rc = register_cron_mod._run(args)
    assert rc == 2, f"expected exit 2 when token missing; got {rc}"

    captured = capsys.readouterr()
    combined = (captured.err + captured.out).lower()
    assert "openclaw_gateway_token" in combined, (
        f"stderr must mention OPENCLAW_GATEWAY_TOKEN; got {captured.err!r}"
    )
    assert "openclaw auth setup" in combined or "auth setup" in combined, (
        f"stderr must include actionable auth setup hint; got {captured.err!r}"
    )


def test_register_cron_freshness_uses_08_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--cron-freshness registers the D-14 08:00 PT stale detector."""
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "dummy-token")
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> _FakeCompleted:
        captured.append(list(cmd))
        if len(cmd) >= 3 and cmd[1] == "cron" and cmd[2] == "list":
            return _FakeCompleted(returncode=0, stdout="", stderr="")
        return _FakeCompleted(returncode=0, stdout="registered", stderr="")

    monkeypatch.setattr(register_cron_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(register_cron_mod.shutil, "which", lambda _: "/bin/openclaw")

    args = argparse.Namespace(nightly=False, cron_freshness=True)
    rc = register_cron_mod._run(args)
    assert rc == 0

    add_calls = [c for c in captured if len(c) >= 3 and c[1] == "cron" and c[2] == "add"]
    assert len(add_calls) == 1
    add = add_calls[0]
    cron_idx = add.index("--cron")
    assert add[cron_idx + 1] == "0 8 * * *", (
        f"expected D-14 08:00 schedule; got {add[cron_idx + 1]!r}"
    )
    name_idx = add.index("--name")
    assert add[name_idx + 1] == "book-pipeline:check-cron-freshness"
