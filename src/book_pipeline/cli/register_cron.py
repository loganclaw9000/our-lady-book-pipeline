"""book-pipeline register-cron — openclaw cron registration helper.

Plan 05-04 Task 2. Implements D-14 (stale-cron detector at 08:00 PT) and
D-15 (nightly run at 02:00 PT) via `openclaw cron add` invocations.

Idempotent: probes `openclaw cron list` first; if the job name already
appears in stdout, skip the add.

OPENCLAW_GATEWAY_TOKEN is a documented prerequisite (per Plan 01-04 deferral
+ RESEARCH.md § Environment Availability). When unset, the CLI exits 2 with
an actionable stderr message referencing `openclaw auth setup`.

NO real subprocess.run invocation happens in tests — the module-level
subprocess + shutil references are monkeypatched by the test suite.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from book_pipeline.cli.main import register_subcommand

# D-15 nightly run configuration.
NIGHTLY_JOB_NAME = "book-pipeline:nightly-run"
NIGHTLY_CRON = "0 2 * * *"  # 02:00
NIGHTLY_TZ = "America/Los_Angeles"
NIGHTLY_AGENT = "nightly-runner"
NIGHTLY_MESSAGE = "book-pipeline nightly-run --max-scenes 10"

# D-14 stale-cron detector configuration (independent 08:00 PT job so it
# can't self-silence when the 02:00 nightly breaks).
FRESHNESS_JOB_NAME = "book-pipeline:check-cron-freshness"
FRESHNESS_CRON = "0 8 * * *"  # 08:00
FRESHNESS_TZ = "America/Los_Angeles"
FRESHNESS_AGENT = "nightly-runner"
FRESHNESS_MESSAGE = "book-pipeline check-cron-freshness"


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "register-cron",
        help=(
            "Register book-pipeline's openclaw crons (D-14 freshness "
            "detector + D-15 nightly run)."
        ),
    )
    mx = p.add_mutually_exclusive_group(required=True)
    mx.add_argument(
        "--nightly",
        action="store_true",
        help=(
            "Register book-pipeline:nightly-run at 02:00 America/Los_Angeles "
            "per D-15 (scene loop + chapter DAG driver)."
        ),
    )
    mx.add_argument(
        "--cron-freshness",
        action="store_true",
        help=(
            "Register book-pipeline:check-cron-freshness at 08:00 "
            "America/Los_Angeles per D-14 (stale-nightly detector)."
        ),
    )
    p.set_defaults(_handler=_run)


def _cron_list_contains(name: str) -> bool:
    """Return True if `openclaw cron list` output contains `name` as a job name.

    Defensive: returns False on any subprocess failure so we err on the side
    of trying to register (add is idempotent enough via openclaw semantics,
    but duplicate registration attempts just re-write the same job).
    """
    try:
        result = subprocess.run(
            ["openclaw", "cron", "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    if result.returncode != 0:
        return False
    return name in result.stdout


def _register(
    name: str, cron_expr: str, tz: str, agent: str, message: str
) -> tuple[int, str]:
    """Issue `openclaw cron add ...`. Returns (exit_code, diagnostic)."""
    cmd = [
        "openclaw",
        "cron",
        "add",
        "--name",
        name,
        "--cron",
        cron_expr,
        "--tz",
        tz,
        "--session",
        "isolated",
        "--agent",
        agent,
        "--message",
        message,
        "--wake",
        "now",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return 2, "openclaw cron add timed out after 30s"
    if result.returncode != 0:
        return 2, (
            f"openclaw cron add failed (rc={result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return 0, result.stdout.strip()


def _run(args: argparse.Namespace) -> int:
    # Gateway-token precondition (RESEARCH.md § Environment Availability).
    if not os.environ.get("OPENCLAW_GATEWAY_TOKEN"):
        print(
            "Error: OPENCLAW_GATEWAY_TOKEN is not set. "
            "Run `openclaw auth setup` (see openclaw 2026.4.5 docs) to "
            "generate a gateway token, then re-invoke "
            "`book-pipeline register-cron`.",
            file=sys.stderr,
        )
        return 2

    if shutil.which("openclaw") is None:
        print(
            "Error: `openclaw` CLI not on PATH. Install via "
            "`npm install -g openclaw` (expected at "
            "~/.npm-global/lib/node_modules/openclaw), then re-run.",
            file=sys.stderr,
        )
        return 2

    if args.nightly:
        job_name = NIGHTLY_JOB_NAME
        cron_expr = NIGHTLY_CRON
        tz = NIGHTLY_TZ
        agent = NIGHTLY_AGENT
        message = NIGHTLY_MESSAGE
    elif args.cron_freshness:
        job_name = FRESHNESS_JOB_NAME
        cron_expr = FRESHNESS_CRON
        tz = FRESHNESS_TZ
        agent = FRESHNESS_AGENT
        message = FRESHNESS_MESSAGE
    else:  # pragma: no cover — argparse requires one or the other
        print("Error: pass --nightly or --cron-freshness.", file=sys.stderr)
        return 2

    if _cron_list_contains(job_name):
        print(f"[register-cron] already registered: {job_name} (idempotent skip).")
        return 0

    rc, msg = _register(job_name, cron_expr, tz, agent, message)
    if rc != 0:
        print(f"[register-cron] {msg}", file=sys.stderr)
        return rc
    print(
        f"[register-cron] registered {job_name}: cron={cron_expr!r} tz={tz!r} "
        f"agent={agent!r}"
    )
    return 0


register_subcommand("register-cron", _add_parser)


__all__ = ["_run"]
