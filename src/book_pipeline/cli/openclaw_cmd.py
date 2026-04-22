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
from book_pipeline.openclaw.bootstrap import BootstrapReport, bootstrap, register_placeholder_cron


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
        help="Install Phase 1 placeholder nightly cron via `openclaw cron add`",
    )
    r.set_defaults(_handler=_run_register_cron)

    p.set_defaults(_handler=lambda _a: (p.print_help(), 0)[1])


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


def _run_register_cron(_args: argparse.Namespace) -> int:
    ok, out, err = register_placeholder_cron()
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return 0 if ok else 1


register_subcommand("openclaw", _add_parser)
