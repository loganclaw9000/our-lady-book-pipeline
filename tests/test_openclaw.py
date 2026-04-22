"""Tests for the openclaw bootstrap + register-cron helpers + CLI entry."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from book_pipeline.cli.main import main
from book_pipeline.openclaw.bootstrap import bootstrap, register_placeholder_cron


def test_bootstrap_against_committed_openclaw_json() -> None:
    report = bootstrap()
    assert report.openclaw_json_exists
    assert report.openclaw_json_valid
    assert report.gateway_port == 18790
    assert report.vllm_base_url == "http://127.0.0.1:8002/v1"
    assert "drafter" in report.agents
    # Gateway may or may not be listening depending on user env — must not raise.


def test_openclaw_json_not_in_dot_openclaw_dir() -> None:
    # Per STACK.md: openclaw.json at repo root, NOT .openclaw/
    assert not Path(".openclaw/openclaw.json").exists()
    assert Path("openclaw.json").exists()


def test_bootstrap_fails_cleanly_on_missing_drafter_md(tmp_path: Path) -> None:
    # Create a tmp repo with openclaw.json but no workspaces/drafter/
    (tmp_path / "openclaw.json").write_text(
        json.dumps(
            {
                "meta": {
                    "lastTouchedVersion": "2026.4.5",
                    "lastTouchedAt": "2026-04-21T00:00:00.000Z",
                },
                "env": {"vars": {}},
                "models": {"mode": "merge", "providers": {}},
                "agents": {
                    "defaults": {},
                    "list": [{"id": "drafter", "workspace": "x"}],
                },
                "gateway": {
                    "port": 18790,
                    "mode": "local",
                    "bind": "loopback",
                    "auth": {"mode": "token", "token": "x"},
                },
                "tools": {},
                "plugins": {"entries": {}},
            }
        )
    )
    report = bootstrap(repo_root=tmp_path)
    assert any("workspaces/drafter" in e for e in report.errors)
    assert not report.ok


def test_bootstrap_cli_entry(capsys: object) -> None:
    rc = main(["openclaw", "bootstrap"])
    # rc may be 0 (fully green) or 1 (some error) depending on env;
    # we only assert that the report printed the right fields.
    assert rc in (0, 1)
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "openclaw.json:" in captured.out
    assert "gateway.port:          18790" in captured.out


def test_register_cron_without_openclaw_cli_gives_manual_command(
    monkeypatch: object,
) -> None:
    # Force shutil.which to return None for 'openclaw'
    real_which = shutil.which

    def fake_which(name: str, *a: object, **k: object) -> str | None:
        if name == "openclaw":
            return None
        return real_which(name)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "book_pipeline.openclaw.bootstrap.shutil.which", fake_which
    )
    ok, _out, err = register_placeholder_cron()
    assert not ok
    assert "openclaw cron add" in err
    assert "book-pipeline:phase1-placeholder" in err


# --- Plan 02-06: register_nightly_ingest (openclaw cron nightly) -------------


def test_register_nightly_ingest_without_openclaw_cli_gives_manual_command(
    monkeypatch: object,
) -> None:
    """openclaw not on PATH -> (False, '', diagnostic with the manual command)."""
    from book_pipeline.openclaw.bootstrap import register_nightly_ingest

    real_which = shutil.which

    def fake_which(name: str, *a: object, **k: object) -> str | None:
        if name == "openclaw":
            return None
        return real_which(name)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "book_pipeline.openclaw.bootstrap.shutil.which", fake_which
    )
    ok, _out, err = register_nightly_ingest()
    assert not ok
    assert "openclaw cron add" in err
    assert "book-pipeline:nightly-ingest" in err
    assert "0 2 * * *" in err


def test_register_nightly_ingest_invokes_subprocess_with_correct_args(
    monkeypatch: object,
) -> None:
    """openclaw on PATH -> subprocess.run called with the exact cron-add argv."""
    from book_pipeline.openclaw import bootstrap as bootstrap_mod

    # Force openclaw to look present.
    monkeypatch.setattr(  # type: ignore[attr-defined]
        bootstrap_mod.shutil, "which", lambda name: "/usr/bin/openclaw" if name == "openclaw" else None
    )

    captured: dict[str, object] = {}

    class _FakeCompleted:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeCompleted()

    monkeypatch.setattr(  # type: ignore[attr-defined]
        bootstrap_mod.subprocess, "run", fake_run
    )

    ok, out, _err = bootstrap_mod.register_nightly_ingest()
    assert ok
    assert out == "ok"
    cmd = captured["cmd"]
    # Must include the key argv elements.
    assert isinstance(cmd, list)
    assert "openclaw" == cmd[0]
    assert "cron" in cmd
    assert "add" in cmd
    # --name book-pipeline:nightly-ingest
    assert "--name" in cmd
    assert "book-pipeline:nightly-ingest" in cmd
    # --cron "0 2 * * *"
    assert "--cron" in cmd
    assert "0 2 * * *" in cmd
    # --tz America/New_York
    assert "--tz" in cmd
    assert "America/New_York" in cmd
    # --session isolated
    assert "--session" in cmd
    assert "isolated" in cmd
    # --session-agent drafter
    assert "--session-agent" in cmd
    assert "drafter" in cmd
    # --system-event must mention "book-pipeline ingest"
    assert "--system-event" in cmd
    event_idx = cmd.index("--system-event")
    system_event = cmd[event_idx + 1]
    assert isinstance(system_event, str)
    assert "book-pipeline ingest" in system_event


def test_register_cron_cli_registers_both_placeholder_and_nightly(
    monkeypatch: object, capsys: object
) -> None:
    """`book-pipeline openclaw register-cron` invokes BOTH functions by default."""
    from book_pipeline.cli import openclaw_cmd as oc_mod

    calls: list[str] = []

    def fake_placeholder() -> tuple[bool, str, str]:
        calls.append("placeholder")
        return (True, "placeholder-ok", "")

    def fake_nightly() -> tuple[bool, str, str]:
        calls.append("nightly")
        return (True, "nightly-ok", "")

    monkeypatch.setattr(oc_mod, "register_placeholder_cron", fake_placeholder)  # type: ignore[attr-defined]
    monkeypatch.setattr(oc_mod, "register_nightly_ingest", fake_nightly)  # type: ignore[attr-defined]

    rc = main(["openclaw", "register-cron"])
    assert rc == 0
    assert calls == ["placeholder", "nightly"], (
        f"Expected both cron registrations; got: {calls}"
    )


def test_register_cron_cli_ingest_only_flag(
    monkeypatch: object, capsys: object
) -> None:
    """--ingest-only skips the placeholder and only registers the nightly job."""
    from book_pipeline.cli import openclaw_cmd as oc_mod

    calls: list[str] = []

    def fake_placeholder() -> tuple[bool, str, str]:
        calls.append("placeholder")
        return (True, "p-ok", "")

    def fake_nightly() -> tuple[bool, str, str]:
        calls.append("nightly")
        return (True, "n-ok", "")

    monkeypatch.setattr(oc_mod, "register_placeholder_cron", fake_placeholder)  # type: ignore[attr-defined]
    monkeypatch.setattr(oc_mod, "register_nightly_ingest", fake_nightly)  # type: ignore[attr-defined]

    rc = main(["openclaw", "register-cron", "--ingest-only"])
    assert rc == 0
    assert calls == ["nightly"], (
        f"--ingest-only should skip placeholder; got calls: {calls}"
    )


def test_register_cron_help_lists_ingest_only_flag(capsys: object) -> None:
    """--help output must surface the --ingest-only flag."""
    try:
        main(["openclaw", "register-cron", "--help"])
    except SystemExit:
        pass
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "--ingest-only" in captured.out
