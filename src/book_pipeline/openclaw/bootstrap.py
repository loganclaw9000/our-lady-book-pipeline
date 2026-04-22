"""Openclaw project bootstrap helpers.

bootstrap() — load openclaw.json, validate shape, probe gateway reachability,
              return a BootstrapReport (no side effects beyond HTTP probe).
register_placeholder_cron() — invoke `openclaw cron add ...` for a no-op
                              Phase 1 nightly; returns (ok, stdout, stderr).
register_nightly_ingest() — invoke `openclaw cron add ...` for the Phase 2
                            nightly `book-pipeline ingest` job; returns
                            (ok, stdout, stderr). Same shape as
                            register_placeholder_cron; user-aware fallback
                            when openclaw CLI is not on PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

OPENCLAW_JSON = Path("openclaw.json")


@dataclass
class BootstrapReport:
    openclaw_json_exists: bool = False
    openclaw_json_valid: bool = False
    gateway_port: int | None = None
    gateway_port_listening: bool = False
    vllm_base_url: str | None = None
    agents: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _probe_port(port: int, host: str = "127.0.0.1", timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def bootstrap(repo_root: Path | None = None) -> BootstrapReport:
    """Load openclaw.json, validate structure, probe gateway port. Read-only (no network writes)."""
    report = BootstrapReport()
    path = (repo_root or Path.cwd()) / OPENCLAW_JSON

    if not path.exists():
        report.errors.append(
            f"openclaw.json not found at {path} (must live at repo root, NOT in .openclaw/)"
        )
        return report

    report.openclaw_json_exists = True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.errors.append(f"openclaw.json invalid JSON: {exc}")
        return report

    report.openclaw_json_valid = True

    # Required keys
    for key in ("meta", "models", "agents", "gateway"):
        if key not in data:
            report.errors.append(f"openclaw.json missing top-level key: {key}")

    gw = data.get("gateway", {})
    port = gw.get("port")
    if not isinstance(port, int):
        report.errors.append("gateway.port missing or not int")
    else:
        report.gateway_port = port
        report.gateway_port_listening = _probe_port(port)
        if not report.gateway_port_listening:
            report.warnings.append(
                f"gateway.port {port} is not listening — start openclaw gateway "
                "(systemctl --user) before running the nightly cron."
            )

    vllm = data.get("models", {}).get("providers", {}).get("vllm", {})
    report.vllm_base_url = vllm.get("baseUrl")
    if report.vllm_base_url is None:
        report.warnings.append(
            "models.providers.vllm.baseUrl missing — Phase 3 drafter needs this."
        )

    agents = data.get("agents", {}).get("list", [])
    report.agents = [a.get("id", "<no-id>") for a in agents]
    if "drafter" not in report.agents:
        report.errors.append("agents.list must contain 'drafter' per FOUND-03")

    # Check workspaces/drafter/ exists
    drafter_ws = (repo_root or Path.cwd()) / "workspaces" / "drafter"
    required_md = ["AGENTS.md", "SOUL.md", "USER.md", "BOOT.md"]
    for fname in required_md:
        if not (drafter_ws / fname).exists():
            report.errors.append(f"workspaces/drafter/{fname} missing")

    # Check OPENCLAW_GATEWAY_TOKEN exposure (not value)
    if "OPENCLAW_GATEWAY_TOKEN" not in os.environ:
        report.warnings.append(
            "OPENCLAW_GATEWAY_TOKEN not in env — set from .env before bootstrap for "
            "full gateway auth probe (Phase 1 ok without)."
        )

    return report


def register_placeholder_cron() -> tuple[bool, str, str]:
    """Install the Phase 1 no-op nightly cron via `openclaw cron add`.

    Returns (ok, stdout, stderr). If openclaw CLI is not on PATH, returns
    (False, "", diagnostic) — user must install openclaw or run the command
    manually. Does NOT install a systemd timer (CONTEXT.md D-03 forbids).
    """
    if shutil.which("openclaw") is None:
        return (
            False,
            "",
            "openclaw CLI not on PATH. Expected (from STACK.md): "
            "~/.npm-global/lib/node_modules/openclaw installed via npm. "
            "Run manually:\n"
            '  openclaw cron add --name "book-pipeline:phase1-placeholder" '
            '--cron "0 2 * * *" --tz "America/New_York" --session isolated '
            '--agent drafter '
            '--message "Phase 1 placeholder. No-op tick. Phase 5 ORCH-01 replaces." '
            "--wake now",
        )
    cmd = [
        "openclaw",
        "cron",
        "add",
        "--name",
        "book-pipeline:phase1-placeholder",
        "--cron",
        "0 2 * * *",
        "--tz",
        "America/New_York",
        "--session",
        "isolated",
        "--agent",
        "drafter",
        # Plan 02-06 fix: openclaw 2026.4.5 rejects --system-event with
        # --session isolated + --agent <id>; agentTurn payloads must use
        # --message. Documented as Deviation in 02-06 SUMMARY (Rule 1 bug
        # in Phase 1 wiring; caught when the real CLI was exercised for
        # the first time in this plan).
        "--message",
        "Phase 1 placeholder. No-op tick. Phase 5 ORCH-01 replaces this with "
        "the real nightly drafter loop per workspaces/drafter/AGENTS.md.",
        "--wake",
        "now",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return (False, "", "openclaw cron add timed out after 30s")
    return (result.returncode == 0, result.stdout, result.stderr)


NIGHTLY_INGEST_JOB_NAME = "book-pipeline:nightly-ingest"
NIGHTLY_INGEST_CRON = "0 2 * * *"
NIGHTLY_INGEST_TZ = "America/New_York"
# openclaw 2026.4.5: --session isolated + --agent <id> requires --message
# (agentTurn payload). --system-event is rejected in this session mode.
NIGHTLY_INGEST_MESSAGE = (
    "Run nightly ingest: book-pipeline ingest; if any corpus file mtime "
    "changed, rebuild the 5 LanceDB tables. Details: Phase 2 Plan 06 "
    "(RAG-04 baseline maintenance + CORPUS-01 freshness)."
)


def register_nightly_ingest() -> tuple[bool, str, str]:
    """Install the Phase 2 nightly `book-pipeline ingest` cron via openclaw.

    Returns (ok, stdout, stderr). If openclaw CLI is not on PATH, returns
    (False, "", diagnostic with the exact manual command). Does NOT raise
    on subprocess failure — returns (False, stdout, stderr) so the CLI can
    display the diagnostic to the operator.

    The job is idempotent at the openclaw layer: re-running with the same
    --name invokes openclaw's dedupe semantics. No systemd timer is
    installed (STACK.md forbids; openclaw's persistent cron is the
    contract per ORCH-01).
    """
    manual_cmd = (
        "  openclaw cron add \\\n"
        f'    --name "{NIGHTLY_INGEST_JOB_NAME}" \\\n'
        f'    --cron "{NIGHTLY_INGEST_CRON}" \\\n'
        f'    --tz "{NIGHTLY_INGEST_TZ}" \\\n'
        "    --session isolated \\\n"
        "    --agent drafter \\\n"
        f'    --message "{NIGHTLY_INGEST_MESSAGE}" \\\n'
        "    --wake now"
    )
    if shutil.which("openclaw") is None:
        return (
            False,
            "",
            (
                "openclaw CLI not on PATH. Expected (from STACK.md): "
                "~/.npm-global/lib/node_modules/openclaw installed via npm. "
                "Run manually:\n" + manual_cmd
            ),
        )
    cmd = [
        "openclaw",
        "cron",
        "add",
        "--name",
        NIGHTLY_INGEST_JOB_NAME,
        "--cron",
        NIGHTLY_INGEST_CRON,
        "--tz",
        NIGHTLY_INGEST_TZ,
        "--session",
        "isolated",
        "--agent",
        "drafter",
        "--message",
        NIGHTLY_INGEST_MESSAGE,
        "--wake",
        "now",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return (False, "", "openclaw cron add timed out after 30s")
    return (result.returncode == 0, result.stdout, result.stderr)
