"""CLI tests for `book-pipeline validate-config`."""

from __future__ import annotations

import subprocess

import pytest

from book_pipeline.cli.main import main

REPO_ROOT = "/home/admin/Source/our-lady-book-pipeline"


def test_validate_config_exits_0_on_valid_configs(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["validate-config"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "voice_pin.base_model" in out
    assert "rubric.axes" in out


def test_validate_config_does_not_leak_secret(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leaky-value-xyz")
    rc = main(["validate-config"])
    assert rc == 0
    out = capsys.readouterr().out
    # Secret value MUST NOT appear in output; presence status MUST.
    assert "sk-ant-leaky-value-xyz" not in out
    assert "PRESENT" in out


def test_validate_config_entry_via_uv_run() -> None:
    result = subprocess.run(
        ["uv", "run", "book-pipeline", "validate-config"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "[OK]" in result.stdout


def test_validate_config_subcommand_in_help() -> None:
    result = subprocess.run(
        ["uv", "run", "book-pipeline", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert "validate-config" in result.stdout


def test_validate_config_fails_with_missing_field(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete a required field from voice_pin.yaml → exit nonzero + field name in stderr."""
    import shutil

    # Copy real config/ into tmp_path so we hit the cwd-relative path resolution
    src_config = f"{REPO_ROOT}/config"
    dst_config = tmp_path / "config"
    shutil.copytree(src_config, dst_config)

    # Remove base_model from voice_pin.yaml
    vp_path = dst_config / "voice_pin.yaml"
    content = vp_path.read_text()
    filtered = "\n".join(line for line in content.splitlines() if "base_model:" not in line)
    vp_path.write_text(filtered)

    monkeypatch.chdir(tmp_path)
    rc = main(["validate-config"])
    assert rc == 1  # ValidationError path
    err = capsys.readouterr().err
    assert "base_model" in err
