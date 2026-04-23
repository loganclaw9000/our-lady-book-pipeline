"""Atomic git-commit helpers for the Phase 4 chapter DAG orchestrator.

`commit_paths(paths, *, message, repo_root, ...)` stages the given paths,
commits with the given message, and returns the resulting HEAD sha. It's a
thin wrapper over `subprocess.run(..., shell=False)` so injection is blocked
by argv-list discipline (T-04-04 threat model).

Per CLAUDE.md: NEVER pass `--no-verify`. Pre-commit hooks are REQUIRED to
pass. Hook failure propagates to the caller as GitCommitError; Plan 04-04's
orchestrator catches it and transitions to DAG_BLOCKED.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitCommitError(RuntimeError):
    """Raised on any non-zero exit from `git add`/`git commit`/`git rev-parse`.

    Carries the raw stderr text + returncode for diagnosis + logging.
    """

    def __init__(
        self, message: str, *, stderr: str = "", returncode: int = 1
    ) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


def commit_paths(
    paths: list[str],
    *,
    message: str,
    repo_root: Path,
    git_binary: str = "git",
    allow_empty: bool = False,
) -> str:
    """Stage `paths`, commit with `message`, return HEAD sha (40-char hex).

    Args:
        paths: List of paths (relative to `repo_root`) to stage. May be
            empty if `allow_empty=True`.
        message: Commit message (single -m string; newlines preserved).
        repo_root: Absolute path to the repo's working tree.
        git_binary: Binary name (default "git"). Overridable for tests.
        allow_empty: Pass `--allow-empty` to `git commit`. Used for the RAG
            reindex step when only gitignored files changed.

    Returns:
        The 40-char lowercase hex sha from `git rev-parse HEAD`.

    Raises:
        GitCommitError: on any non-zero exit from git. The pre-commit hook
            failure path falls in here (never skipped with --no-verify).
    """
    repo = Path(repo_root)
    # Stage paths. Empty paths list is legal for allow_empty=True.
    if paths:
        try:
            subprocess.run(
                [git_binary, "add", *paths],
                check=True,
                cwd=repo,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise GitCommitError(
                f"git add failed: {exc.stderr or exc}",
                stderr=exc.stderr or "",
                returncode=exc.returncode,
            ) from exc

    commit_argv = [git_binary, "commit", "-m", message]
    if allow_empty:
        commit_argv.append("--allow-empty")

    try:
        subprocess.run(
            commit_argv,
            check=True,
            cwd=repo,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise GitCommitError(
            f"git commit failed: {exc.stderr or exc}",
            stderr=exc.stderr or "",
            returncode=exc.returncode,
        ) from exc

    try:
        head = subprocess.run(
            [git_binary, "rev-parse", "HEAD"],
            check=True,
            cwd=repo,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise GitCommitError(
            f"git rev-parse HEAD failed: {exc.stderr or exc}",
            stderr=exc.stderr or "",
            returncode=exc.returncode,
        ) from exc

    sha = head.stdout.strip()
    logger.info("git commit landed: %s | %s", sha, message.splitlines()[0])
    return sha


def check_worktree_dirty(
    *, repo_root: Path, git_binary: str = "git"
) -> list[str]:
    """Return a list of `git status --porcelain` lines; empty if clean.

    Helper for pre-flight sanity checks in Plan 04-04's DAG orchestrator.
    """
    repo = Path(repo_root)
    result = subprocess.run(
        [git_binary, "status", "--porcelain"],
        check=True,
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


__all__ = ["GitCommitError", "check_worktree_dirty", "commit_paths"]
