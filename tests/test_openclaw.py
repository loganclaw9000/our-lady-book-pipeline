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
