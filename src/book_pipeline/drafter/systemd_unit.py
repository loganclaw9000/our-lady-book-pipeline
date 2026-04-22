"""systemd --user unit helpers for the vLLM paul-voice service.

render_unit / write_unit / systemctl_user / daemon_reload / poll_health
form the minimum surface the CLI composition layer needs to (a) materialize
a Jinja2-templated systemd unit on disk, (b) drive `systemctl --user`
idempotently, and (c) confirm the served endpoint is healthy before the
boot_handshake (VllmClient) runs.

Kernel discipline: this module takes all book-domain knobs as arguments.
The CLI injects the template path, adapter path, port, etc. import-linter
contract 1 guards that this file never names the banned book-domain module.

Subprocess timeouts: systemctl_user + daemon_reload both use a 60s timeout
and check=False so failures return (ok=False, stderr=...) instead of
raising. That shape matches openclaw/bootstrap.py BootstrapReport semantics.

poll_health: pure-httpx loop (does NOT use VllmClient — the retry/backoff
there is tuned for the handshake path, not the "is the server up yet"
poll). Returns False on persistent failure so the CLI can decide whether
to attempt boot_handshake.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import jinja2


def render_unit(template_path: Path, **kwargs: Any) -> str:
    """Render the Jinja2 template at `template_path` with `kwargs`.

    StrictUndefined elevates undefined-variable references to a render-time
    error; we wrap that as a KeyError naming the missing variable so callers
    get a clear signal.
    """
    template_path = Path(template_path)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template(template_path.name)
    try:
        return template.render(**kwargs)
    except jinja2.UndefinedError as exc:
        # jinja2.UndefinedError's message starts with the variable name; wrap
        # it as KeyError so callers can catch + inspect uniformly.
        raise KeyError(f"missing template var: {exc}") from exc


def write_unit(unit_dir: Path, unit_name: str, content: str) -> Path:
    """Atomically write `content` to unit_dir/unit_name via tmp+rename."""
    unit_dir = Path(unit_dir)
    unit_dir.mkdir(parents=True, exist_ok=True)
    final = unit_dir / unit_name
    tmp = unit_dir / (unit_name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, final)
    return final


def systemctl_user(action: str, unit: str, *, timeout_s: int = 60) -> tuple[bool, str, str]:
    """Run `systemctl --user <action> <unit>` with check=False + timeout.

    Returns (ok, stdout, stderr). ok == True iff returncode == 0. On timeout
    or FileNotFoundError (systemctl not on PATH), returns (False, "", <reason>).
    """
    try:
        result = subprocess.run(
            ["systemctl", "--user", action, unit],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        return (False, "", "systemctl not found on PATH")
    except subprocess.TimeoutExpired as exc:
        return (False, "", f"systemctl --user {action} {unit} timed out: {exc}")
    return (result.returncode == 0, result.stdout, result.stderr)


def daemon_reload(*, timeout_s: int = 60) -> tuple[bool, str, str]:
    """Run `systemctl --user daemon-reload` with the same shape as systemctl_user."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        return (False, "", "systemctl not found on PATH")
    except subprocess.TimeoutExpired as exc:
        return (False, "", f"systemctl --user daemon-reload timed out: {exc}")
    return (result.returncode == 0, result.stdout, result.stderr)


def _probe_models(url: str, timeout: float) -> httpx.Response:
    """One-shot GET of {url}/models. Factored out so tests can monkeypatch."""
    return httpx.get(url.rstrip("/") + "/models", timeout=timeout)


def poll_health(base_url: str, timeout_s: float, interval_s: float) -> bool:
    """Poll {base_url}/models until 200 or timeout. Return True on success.

    Does NOT use VllmClient — the handshake client has its own retry/backoff
    for the *handshake* call, tuned for post-up responsiveness. This poll
    wants "keep trying, quietly" semantics for a cold-booting server.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            response = _probe_models(base_url, timeout=2.0)
            if response.status_code == 200:
                return True
        except (httpx.HTTPError, httpx.RequestError):
            pass
        time.sleep(interval_s)
    return False


__all__ = [
    "daemon_reload",
    "poll_health",
    "render_unit",
    "systemctl_user",
    "write_unit",
]
