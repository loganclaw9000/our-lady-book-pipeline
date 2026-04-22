"""`book-pipeline validate-config` — load all 4 YAML configs + secrets, report status.

Per FOUND-02: startup fails with a clear error if any field is missing/malformed.
This CLI surfaces that check standalone — runnable against uncommitted config
drafts before they ever hit the orchestrator.

Exit codes:
  0 — all 4 configs validated; .env secrets reported as PRESENT/MISSING.
  1 — pydantic ValidationError (fields missing or malformed).
  2 — a config file is missing on disk.
  3 — other load-time errors (malformed YAML, OS errors).

Security: secret values are NEVER printed. ``SecretStr`` masks them in repr,
and the CLI only prints presence booleans per ``is_*_present()``.
"""

from __future__ import annotations

import argparse
import sys

import yaml
from pydantic import ValidationError

from book_pipeline.cli.main import register_subcommand
from book_pipeline.config.loader import load_all_configs


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "validate-config",
        help="Load and validate all 4 config YAMLs + secrets from .env; exit non-zero on failure",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print loaded config summary (secrets always masked)",
    )
    p.set_defaults(_handler=_run)


def _run(_args: argparse.Namespace) -> int:
    try:
        cfg = load_all_configs()
    except ValidationError as exc:
        print("[FAIL] Configuration validation failed:", file=sys.stderr)
        for err in exc.errors():
            loc = " -> ".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg", "validation error")
            print(f"  {loc}: {msg}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"[FAIL] Config file missing: {exc}", file=sys.stderr)
        return 2
    except (yaml.YAMLError, ValueError, OSError) as exc:
        print(f"[FAIL] Config load error: {exc}", file=sys.stderr)
        return 3

    voice_pin = cfg["voice_pin"].voice_pin  # type: ignore[attr-defined]
    rubric = cfg["rubric"]
    rag = cfg["rag_retrievers"]
    modes = cfg["mode_thresholds"]
    secrets = cfg["secrets"]

    print("[OK] All 4 configs validated successfully.")
    print(f"  voice_pin.base_model        = {voice_pin.base_model}")
    print(f"  voice_pin.ft_run_id         = {voice_pin.ft_run_id}")
    print(f"  rubric.rubric_version       = {rubric.rubric_version}")  # type: ignore[attr-defined]
    print(f"  rubric.axes                 = {sorted(rubric.axes.keys())}")  # type: ignore[attr-defined]
    print(f"  rag_retrievers              = {sorted(rag.retrievers.keys())}")  # type: ignore[attr-defined]
    print(f"  rag_retrievers.bundler_cap  = {rag.bundler.max_bytes} bytes")  # type: ignore[attr-defined]
    print(f"  mode_thresholds.regen_R     = {modes.mode_a.regen_budget_R}")  # type: ignore[attr-defined]
    print(f"  mode_thresholds.mode_b_ttl  = {modes.mode_b.prompt_cache_ttl}")  # type: ignore[attr-defined]

    print("  secrets (values never printed):")
    anthropic_status = "PRESENT" if secrets.is_anthropic_present() else "MISSING"  # type: ignore[attr-defined]
    openclaw_status = "PRESENT" if secrets.is_openclaw_present() else "MISSING"  # type: ignore[attr-defined]
    telegram_status = (
        "PRESENT"
        if secrets.is_telegram_present()  # type: ignore[attr-defined]
        else "MISSING (ok for Phase 1)"
    )
    print(f"    ANTHROPIC_API_KEY        = {anthropic_status}")
    print(f"    OPENCLAW_GATEWAY_TOKEN   = {openclaw_status}")
    print(f"    TELEGRAM (bot+chat_id)   = {telegram_status}")

    return 0


register_subcommand("validate-config", _add_parser)
