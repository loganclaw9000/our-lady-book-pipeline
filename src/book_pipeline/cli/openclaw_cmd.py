"""`book-pipeline openclaw {bootstrap, status, register-cron}` subcommand group.

Three read-mostly actions against the openclaw integration:

- ``bootstrap`` validates ``openclaw.json`` at the repo root, verifies
  ``workspaces/drafter/*.md`` exist, and probes the gateway port. Exit 0
  means the config is structurally valid (warnings about the gateway not
  listening are allowed).
- ``status`` is a read-only alias for ``bootstrap`` (no writes anywhere —
  ``bootstrap`` is also read-only today; the split exists so future plans
  can attach side effects to ``bootstrap`` without breaking ``status``).
- ``register-cron`` shells out to ``openclaw cron add`` for the Phase 1
  no-op placeholder nightly; if the CLI is not on PATH, prints the exact
  command the user should run manually.
"""
from __future__ import annotations

import argparse
import sys

from book_pipeline.cli.main import register_subcommand
from book_pipeline.openclaw.bootstrap import (
    BootstrapReport,
    bootstrap,
    register_nightly_ingest,
    register_placeholder_cron,
)


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "openclaw",
        help="openclaw bootstrap / status / register-cron",
    )
    sub = p.add_subparsers(dest="action", metavar="ACTION")

    b = sub.add_parser(
        "bootstrap",
        help="Validate openclaw.json + probe gateway reachability",
    )
    b.set_defaults(_handler=_run_bootstrap)

    s = sub.add_parser(
        "status",
        help="Read-only status probe (alias for bootstrap)",
    )
    s.set_defaults(_handler=_run_bootstrap)

    r = sub.add_parser(
        "register-cron",
        help=(
            "Install cron entries via `openclaw cron add`: Phase 1 placeholder "
            "+ Phase 2 book-pipeline:nightly-ingest. Use --ingest-only to "
            "register just the nightly ingest."
        ),
    )
    r.add_argument(
        "--ingest-only",
        action="store_true",
        help=(
            "Skip the Phase 1 placeholder cron; only register the Phase 2 "
            "nightly ingest job."
        ),
    )
    r.set_defaults(_handler=_run_register_cron)

    def _show_help(_a: argparse.Namespace) -> int:
        p.print_help()
        return 0

    p.set_defaults(_handler=_show_help)


def _print_report(report: BootstrapReport) -> int:
    status = (
        "OK"
        if report.openclaw_json_exists and report.openclaw_json_valid
        else "MISSING/INVALID"
    )
    print(f"openclaw.json:         {status}")
    print(f"gateway.port:          {report.gateway_port}")
    print(f"gateway.listening:     {'YES' if report.gateway_port_listening else 'NO'}")
    print(f"vllm.baseUrl:          {report.vllm_base_url}")
    print(f"agents:                {report.agents}")
    for w in report.warnings:
        print(f"[WARN] {w}")
    for e in report.errors:
        print(f"[ERROR] {e}", file=sys.stderr)
    return 0 if report.ok else 1


def _run_bootstrap(_args: argparse.Namespace) -> int:
    return _print_report(bootstrap())


def _run_register_cron(args: argparse.Namespace) -> int:
    """Register Phase 1 placeholder + Phase 2 nightly-ingest cron jobs.

    By default invokes both `register_placeholder_cron` (Phase 1) and
    `register_nightly_ingest` (Phase 2). With `--ingest-only`, skips the
    Phase 1 placeholder and only registers the nightly ingest job.

    Returns 0 if all invocations succeeded; 1 otherwise. Prints stdout +
    stderr for each step so the operator can see the openclaw CLI's
    confirmation or the manual-fallback command.
    """
    overall_ok = True

    if not getattr(args, "ingest_only", False):
        print("[1] Phase 1 placeholder cron:")
        ok1, out1, err1 = register_placeholder_cron()
        if out1:
            print(out1)
        if err1:
            print(err1, file=sys.stderr)
        overall_ok = overall_ok and ok1

    print("[2] Phase 2 nightly-ingest cron:" if not getattr(args, "ingest_only", False) else "Phase 2 nightly-ingest cron:")
    ok2, out2, err2 = register_nightly_ingest()
    if out2:
        print(out2)
    if err2:
        print(err2, file=sys.stderr)
    overall_ok = overall_ok and ok2

    return 0 if overall_ok else 1


register_subcommand("openclaw", _add_parser)
