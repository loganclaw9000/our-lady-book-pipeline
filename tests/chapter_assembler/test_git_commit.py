"""Tests for git_commit helpers (Plan 04-04 Task 1).

Covers 4 tests per plan <action> §5:
  - Happy path: tmp_path git repo + file -> commit_paths returns 40-char sha.
  - Dirty subprocess: mock subprocess.run to return non-zero -> GitCommitError.
  - allow_empty=True -> commit_paths succeeds even with no staged changes.
  - check_worktree_dirty returns list of porcelain lines for modified files.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest import mock

import pytest

# --------------------------------------------------------------------- #
# Fixtures                                                              #
# --------------------------------------------------------------------- #


def _init_tmp_repo(tmp_path: Path) -> Path:
    """Run `git init` + configure author at tmp_path; return the repo root.

    Uses subprocess.run with list argv (no shell). Sets user.email / user.name
    so `git commit` does not complain about missing author identity.
    """
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=main", str(tmp_path)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True,
    )
    # Silence hooks (none in tmp_path anyway).
    return tmp_path


# --------------------------------------------------------------------- #
# Tests                                                                 #
# --------------------------------------------------------------------- #


def test_commit_paths_happy_path(tmp_path: Path) -> None:
    """Happy path: init repo, create file, commit_paths returns valid sha."""
    from book_pipeline.chapter_assembler.git_commit import commit_paths

    repo = _init_tmp_repo(tmp_path)
    (repo / "canon").mkdir()
    (repo / "canon" / "chapter_01.md").write_text("body\n", encoding="utf-8")

    sha = commit_paths(
        ["canon/chapter_01.md"],
        message="canon(ch01): commit chapter 1",
        repo_root=repo,
    )

    # 40-char lowercase hex sha
    assert re.fullmatch(r"[0-9a-f]{40}", sha), f"not a sha: {sha!r}"

    # Exactly 1 commit on the branch
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in log.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    assert "canon(ch01): commit chapter 1" in lines[0]


def test_commit_paths_fails_on_dirty_subprocess(tmp_path: Path) -> None:
    """subprocess.run returning non-zero -> GitCommitError with stderr."""
    from book_pipeline.chapter_assembler.git_commit import (
        GitCommitError,
        commit_paths,
    )

    repo = _init_tmp_repo(tmp_path)
    (repo / "scratch.txt").write_text("x", encoding="utf-8")

    # Mock only `git add` to fail (simulating an impossible state).
    real_run = subprocess.run

    def fake_run(argv, *args, **kwargs):  # type: ignore[no-untyped-def]
        if argv[:2] == ["git", "add"] or (
            len(argv) > 2 and argv[1] == "add"
        ):
            raise subprocess.CalledProcessError(
                returncode=1, cmd=argv, output="", stderr="nothing to add"
            )
        return real_run(argv, *args, **kwargs)

    with (
        mock.patch("subprocess.run", side_effect=fake_run),
        pytest.raises(GitCommitError) as excinfo,
    ):
        commit_paths(
            ["scratch.txt"],
            message="test: dirty subprocess",
            repo_root=repo,
        )

    # Carry stderr.
    assert "nothing to add" in excinfo.value.stderr or (
        "nothing to add" in str(excinfo.value)
    )


def test_commit_paths_allow_empty(tmp_path: Path) -> None:
    """allow_empty=True -> commit_paths succeeds with no staged changes."""
    from book_pipeline.chapter_assembler.git_commit import commit_paths

    repo = _init_tmp_repo(tmp_path)
    # Seed one commit so HEAD exists.
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )

    sha = commit_paths(
        [],
        message="chore(rag): reindex after ch01",
        repo_root=repo,
        allow_empty=True,
    )
    assert re.fullmatch(r"[0-9a-f]{40}", sha)
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in log.stdout.splitlines() if line.strip()]
    assert len(lines) == 2  # seed + empty commit


def test_check_worktree_dirty_returns_porcelain_lines(tmp_path: Path) -> None:
    """check_worktree_dirty returns list[str] from `git status --porcelain`."""
    from book_pipeline.chapter_assembler.git_commit import (
        check_worktree_dirty,
    )

    repo = _init_tmp_repo(tmp_path)
    # Seed a commit so status output is meaningful.
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )

    # Clean.
    assert check_worktree_dirty(repo_root=repo) == []

    # Modify a tracked file + add an untracked file.
    (repo / "seed.txt").write_text("seed-modified\n", encoding="utf-8")
    (repo / "new.txt").write_text("n", encoding="utf-8")

    dirty = check_worktree_dirty(repo_root=repo)
    assert isinstance(dirty, list)
    joined = "\n".join(dirty)
    assert "seed.txt" in joined
    assert "new.txt" in joined
