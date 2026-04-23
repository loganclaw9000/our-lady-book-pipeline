"""Tests for book-pipeline curate-voice-samples CLI (Plan 05-01 Task 3).

The CLI:
  1. Iterates candidate .txt files from source directories (default from
     book_specifics.voice_samples.DEFAULT_SOURCE_DIRS).
  2. Filters by word_count in [400, 600] (slack 300-700 accepted per
     RESEARCH.md).
  3. Balances across narrative / essay / analytic per GENRE_BALANCE.
  4. Writes config/voice_samples.yaml atomically (tmp+rename).
  5. Exits 0 on success, 1 on insufficient candidates.

All tests use tmp_path — no reads of /home/admin/paul-thinkpiece-pipeline.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


# --- helpers --------------------------------------------------------- #


def _write_txt(dir_: Path, name: str, text: str) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / name
    path.write_text(text, encoding="utf-8")
    return path


def _prose(n_words: int) -> str:
    return " ".join(["word"] * n_words)


def _make_source_dir(tmp_path: Path) -> Path:
    """Make a source dir with 5 passages of ~500 words each, balanced across
    narrative/essay/analytic per GENRE_BALANCE (2/2/1).

    File naming encodes sub-genre: narrative_*.txt / essay_*.txt / analytic_*.txt.
    """
    src = tmp_path / "sources"
    _write_txt(src, "narrative_01.txt", _prose(500))
    _write_txt(src, "narrative_02.txt", _prose(500))
    _write_txt(src, "essay_01.txt", _prose(500))
    _write_txt(src, "essay_02.txt", _prose(500))
    _write_txt(src, "analytic_01.txt", _prose(500))
    return src


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run book-pipeline with given args; capture stdout/stderr."""
    return subprocess.run(
        [sys.executable, "-m", "book_pipeline.cli.main", *args],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )


# --- Tests ----------------------------------------------------------- #


def test_cli_discoverable() -> None:
    """book-pipeline --help lists curate-voice-samples."""
    result = _run_cli(["--help"])
    assert result.returncode == 0, result.stderr
    assert "curate-voice-samples" in result.stdout


def test_cli_writes_yaml(tmp_path: Path) -> None:
    """CLI writes valid YAML loadable by VoiceSamplesConfig with >=3 passages."""
    src = _make_source_dir(tmp_path)
    out = tmp_path / "voice_samples.yaml"
    result = _run_cli(
        [
            "curate-voice-samples",
            "--out",
            str(out),
            "--source-dir",
            str(src),
        ]
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert out.is_file()
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "passages" in data
    assert len(data["passages"]) >= 3
    # Every passage must be 300-700 words (drafter-validator-compatible).
    for p in data["passages"]:
        wc = len(p.split())
        assert 300 <= wc <= 700, f"passage wc={wc} outside slack band 300-700"


def test_cli_rejects_short_sources(tmp_path: Path) -> None:
    """Sources with <300 words get filtered out; if too few remain, exit 1."""
    src = tmp_path / "short_sources"
    # All short — should fail
    _write_txt(src, "narrative_01.txt", _prose(50))
    _write_txt(src, "essay_01.txt", _prose(50))
    _write_txt(src, "analytic_01.txt", _prose(50))
    out = tmp_path / "voice_samples.yaml"
    result = _run_cli(
        [
            "curate-voice-samples",
            "--out",
            str(out),
            "--source-dir",
            str(src),
        ]
    )
    assert result.returncode == 1, (
        f"Expected exit 1 on short sources; got {result.returncode}. stderr: {result.stderr}"
    )


def test_cli_atomic_write(tmp_path: Path) -> None:
    """CLI uses tmp+rename atomic write (no partial writes).

    Verified by checking the final file exists as a single atomic artifact,
    and no .tmp file leaks into the output directory.
    """
    src = _make_source_dir(tmp_path)
    out = tmp_path / "voice_samples.yaml"
    result = _run_cli(
        [
            "curate-voice-samples",
            "--out",
            str(out),
            "--source-dir",
            str(src),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert out.is_file()
    # No .tmp file leaked
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob("voice_samples.yaml.tmp"))
