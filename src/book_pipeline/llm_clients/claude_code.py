"""``claude -p`` CLI subprocess backend for SceneCritic + SceneLocalRegenerator.

Drop-in duck-typed replacement for ``anthropic.Anthropic().messages``. Shells
out to the ``claude`` CLI (Claude Code) with ``--output-format json`` + (for
structured responses) ``--json-schema <schema>`` so the model's reply is
validated against the Pydantic schema on the CLI side; we then parse it on
the Python side.

Why OAuth-not-API-key:
  The operator is on a Claude Max subscription. The ``claude`` CLI, when
  invoked WITHOUT ``--bare``, reads OAuth credentials from ``~/.claude/`` and
  inference is billed against the subscription at zero marginal cost. We
  avoid ``--bare`` (which forces ``ANTHROPIC_API_KEY`` and per-call billing).
  The ``total_cost_usd`` field in the CLI's JSON response is subscription-
  internal accounting telemetry, not a charge.

Retry semantics:
  ``SceneLocalRegenerator`` wraps its call in ``tenacity.retry_if_exception_type
  ((APIConnectionError, APIStatusError))``. To keep the regen retry loop
  identical across backends, this shim raises the same anthropic exception
  classes on equivalent failure modes:
    - Subprocess TimeoutExpired OR non-zero exit with transient-looking stderr
      → ``APIConnectionError``.
    - JSON response with ``is_error: true`` → ``APIStatusError``.
  Any other failure (malformed JSON, schema-validation errors on our side)
  surfaces as ``ClaudeCodeCliError`` — these are NOT retry-worthy.

Security:
  - User-supplied prompt content is passed via a CLI positional argument.
    ``subprocess.run`` with a list argv (no ``shell=True``) does NOT interpret
    shell metacharacters, so shell injection is structurally prevented. The
    caller is still responsible for wrapping untrusted content in semantic
    fences (SceneCritic already wraps scene text in ``<scene_text>`` XML
    tags in its system prompt).
  - We do NOT set ``CLAUDE_CODE_SIMPLE=1`` on the subprocess env. Empirical
    verification (2026-04-21): that env var disables OAuth keychain reads
    exactly the same way ``--bare`` does — which would force the shim back
    onto ``ANTHROPIC_API_KEY`` and defeat the entire purpose of this
    backend (subscription-covered OAuth). CLAUDE.md auto-discovery is an
    interactive-session concern; in ``-p`` mode with explicit
    ``--append-system-prompt`` the local CLAUDE.md is not injected, so the
    hermeticity cost is nil.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

import httpx
from anthropic import APIConnectionError, APIStatusError
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class ClaudeCodeCliError(RuntimeError):
    """Raised on non-retryable CLI failures: malformed JSON, schema mismatch,
    missing ``claude`` binary, etc.

    Retry-eligible failures (network-flavored) surface as anthropic's
    ``APIConnectionError``/``APIStatusError`` so SceneLocalRegenerator's
    ``tenacity.retry_if_exception_type`` catches them unchanged.
    """


# ---------------------------------------------------------------------- #
# Response shapes (mimic the anthropic SDK surface SceneCritic + SLR read)
# ---------------------------------------------------------------------- #


@dataclass
class _Usage:
    """Mimics ``anthropic.types.Usage``.

    Only the 3 fields SceneCritic reads: input_tokens, output_tokens,
    cache_read_input_tokens.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0

    def model_dump(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }


@dataclass
class _TextBlock:
    """Mimics ``anthropic.types.TextBlock``."""

    text: str
    type: str = "text"


@dataclass
class ParseResponse:
    """Mimics ``anthropic.types.ParsedMessage`` — shape SceneCritic expects.

    SceneCritic reads: ``.parsed_output``, ``.usage`` (with input_tokens /
    output_tokens / cache_read_input_tokens), ``.model``, and calls
    ``.model_dump()`` on the whole thing for the CRIT-04 audit record.
    """

    parsed_output: Any
    usage: _Usage = field(default_factory=_Usage)
    model: str = "claude-opus-4-7"
    id: str = "msg_claude_code_01"
    type: str = "message"
    role: str = "assistant"
    stop_reason: str = "end_turn"

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        parsed_dump: Any = None
        if self.parsed_output is not None:
            dumper = getattr(self.parsed_output, "model_dump", None)
            parsed_dump = dumper() if callable(dumper) else self.parsed_output
        return {
            "id": self.id,
            "type": self.type,
            "role": self.role,
            "model": self.model,
            "stop_reason": self.stop_reason,
            "usage": self.usage.model_dump(),
            "parsed_output_dump": parsed_dump,
            "_backend": "claude_code_cli",
        }


@dataclass
class CreateResponse:
    """Mimics ``anthropic.types.Message`` — shape SceneLocalRegenerator expects.

    SceneLocalRegenerator reads: ``.content[0].text`` (via ``_extract_text``)
    and ``.usage`` (input_tokens, output_tokens).
    """

    content: list[_TextBlock]
    usage: _Usage = field(default_factory=_Usage)
    model: str = "claude-opus-4-7"
    id: str = "msg_claude_code_01"
    type: str = "message"
    role: str = "assistant"
    stop_reason: str = "end_turn"

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "role": self.role,
            "model": self.model,
            "stop_reason": self.stop_reason,
            "usage": self.usage.model_dump(),
            "content": [{"type": b.type, "text": b.text} for b in self.content],
            "_backend": "claude_code_cli",
        }


# ---------------------------------------------------------------------- #
# Messages shim
# ---------------------------------------------------------------------- #


class _Messages:
    """Mimics ``client.messages`` — exposes ``parse`` + ``create``."""

    def __init__(
        self,
        *,
        cli_binary: str,
        timeout_s: int,
        extra_args: list[str] | None = None,
    ) -> None:
        self._cli_binary = cli_binary
        self._timeout_s = timeout_s
        self._extra_args = list(extra_args) if extra_args else []

    # -- parse (SceneCritic surface) -- #

    def parse(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        output_format: type[BaseModel],
        system: list[dict[str, Any]] | str | None = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> ParseResponse:
        """Invoke ``claude -p --json-schema ...`` and parse the response.

        Args:
            model: Model id (e.g. "claude-opus-4-7"). Passed to ``--model``.
            messages: Anthropic-style messages list. Currently we concatenate
                all user-role messages into a single prompt; we do not maintain
                multi-turn state because SceneCritic's only message is a
                single user turn.
            output_format: Pydantic BaseModel subclass. ``model_json_schema()``
                is passed to ``--json-schema``; the CLI returns a
                ``structured_output`` dict that we validate via the model.
            system: Anthropic-style system blocks list (with
                ``cache_control``) OR a plain string. We flatten to text for
                ``--append-system-prompt``. cache_control is irrelevant to
                the CLI backend (the CLI manages prompt caching against the
                OAuth session, not via ephemeral cache hints).
            max_tokens / temperature: Accepted for SDK parity but ignored —
                the CLI does not expose these knobs in ``-p`` mode.

        Returns:
            ``ParseResponse`` with ``parsed_output`` populated from the CLI's
            ``structured_output`` field, validated through ``output_format``.

        Raises:
            APIConnectionError: Subprocess timed out or failed transiently.
            APIStatusError: CLI returned ``is_error: true``.
            ClaudeCodeCliError: Malformed JSON, schema validation failed,
                ``claude`` binary not found.
        """
        schema = output_format.model_json_schema()
        schema_json = json.dumps(schema, ensure_ascii=False)
        system_text = _flatten_system(system)
        user_prompt = _flatten_messages(messages)

        argv: list[str] = [
            self._cli_binary,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            schema_json,
            "--model",
            model,
        ]
        if system_text:
            argv += ["--append-system-prompt", system_text]
        argv += list(self._extra_args)

        # Long prompts (e.g. full chapter text for entity_extractor) overflow
        # OS ARG_MAX when passed as positional argv → subprocess hangs and hits
        # 180s timeout (HANDOFF Known Issue #3). Pipe via stdin instead. The
        # ``-`` positional tells ``claude -p`` to read prompt from stdin.
        argv += ["-"]

        payload = _invoke_claude_cli(
            argv=argv,
            timeout_s=self._timeout_s,
            stdin_input=user_prompt,
        )

        structured = payload.get("structured_output")
        if not isinstance(structured, dict):
            raise ClaudeCodeCliError(
                "claude -p response missing 'structured_output' dict; "
                f"got keys={sorted(payload.keys())!r}"
            )

        try:
            parsed_obj = output_format.model_validate(structured)
        except ValidationError as exc:
            raise ClaudeCodeCliError(
                f"claude -p structured_output failed Pydantic validation "
                f"against {output_format.__name__}: {exc}"
            ) from exc

        return ParseResponse(
            parsed_output=parsed_obj,
            usage=_usage_from_payload(payload),
            model=_model_from_payload(payload, fallback=model),
            stop_reason=str(payload.get("stop_reason", "end_turn")),
        )

    # -- create (SceneLocalRegenerator surface) -- #

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: list[dict[str, Any]] | str | None = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> CreateResponse:
        """Invoke ``claude -p --output-format json`` (no schema) and return
        ``.content[0].text``.

        SceneLocalRegenerator wants free-text prose (a revised scene), not a
        structured JSON object, so we do NOT pass ``--json-schema``.

        Returns:
            ``CreateResponse`` with ``content=[_TextBlock(text=<result>)]``.
        """
        system_text = _flatten_system(system)
        user_prompt = _flatten_messages(messages)

        argv: list[str] = [
            self._cli_binary,
            "-p",
            "--output-format",
            "json",
            "--model",
            model,
        ]
        if system_text:
            argv += ["--append-system-prompt", system_text]
        argv += list(self._extra_args)

        # Long prompts via stdin (HANDOFF Known Issue #3 — ARG_MAX overflow).
        argv += ["-"]

        payload = _invoke_claude_cli(
            argv=argv,
            timeout_s=self._timeout_s,
            stdin_input=user_prompt,
        )

        result_text = payload.get("result")
        if not isinstance(result_text, str):
            raise ClaudeCodeCliError(
                "claude -p response missing 'result' string; "
                f"got keys={sorted(payload.keys())!r}"
            )

        return CreateResponse(
            content=[_TextBlock(text=result_text)],
            usage=_usage_from_payload(payload),
            model=_model_from_payload(payload, fallback=model),
            stop_reason=str(payload.get("stop_reason", "end_turn")),
        )


class ClaudeCodeMessagesClient:
    """Top-level shim — ``messages.parse`` / ``messages.create`` attrs.

    Mimics ``anthropic.Anthropic()``: only the ``messages`` attribute is
    populated; that's the only surface SceneCritic and SceneLocalRegenerator
    touch.
    """

    def __init__(
        self,
        *,
        timeout_s: int = 180,
        cli_binary: str = "claude",
        extra_args: list[str] | None = None,
    ) -> None:
        self.messages = _Messages(
            cli_binary=cli_binary,
            timeout_s=timeout_s,
            extra_args=extra_args,
        )


# ---------------------------------------------------------------------- #
# Subprocess dispatch
# ---------------------------------------------------------------------- #


# Transient stderr signatures that SHOULD retry. Treat missing-binary,
# permission-denied, schema-validation as terminal (non-retry).
_TRANSIENT_STDERR_SIGNATURES: tuple[str, ...] = (
    "connection",
    "timeout",
    "rate limit",
    "rate_limit",
    "overloaded",
    "unavailable",
    "503",
    "502",
    "504",
    "529",
)


def _synthetic_anthropic_transport() -> tuple[httpx.Request, httpx.Response]:
    """Build a minimal (Request, Response) pair for anthropic exceptions.

    anthropic's ``APIStatusError`` and ``APIConnectionError`` constructors
    dereference attributes on a real httpx.Response / httpx.Request; None is
    not accepted. We synthesise a tiny transport pair so our shim raises
    the exact exception classes SceneLocalRegenerator's
    ``tenacity.retry_if_exception_type`` is watching for.
    """
    request = httpx.Request("POST", "https://claude-code/cli")
    response = httpx.Response(status_code=500, request=request)
    return request, response


def _invoke_claude_cli(
    *,
    argv: list[str],
    timeout_s: int,
    stdin_input: str | None = None,
) -> dict[str, Any]:
    """Run ``claude -p ...`` and return the parsed JSON payload.

    When ``stdin_input`` is provided, the prompt content is piped via stdin
    instead of an argv positional. Required for long prompts (e.g. chapter
    text >~100KB) that would otherwise hit the OS ARG_MAX limit and timeout
    silently. Per HANDOFF Known Issue #3 (entity_extractor argv overflow on
    long chapters).

    Raises:
        APIConnectionError (anthropic): transient subprocess failure
            (timeout / non-zero exit with transient-looking stderr).
        APIStatusError (anthropic): payload has ``is_error: true``.
        ClaudeCodeCliError: binary missing / non-JSON stdout / unexpected
            shape / terminal (non-retryable) error.
    """
    env = _hermetic_env()
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            check=False,
            input=stdin_input,
        )
    except FileNotFoundError as exc:
        raise ClaudeCodeCliError(
            f"claude CLI binary not found on PATH (argv[0]={argv[0]!r}). "
            f"Install Claude Code or set critic_backend.cli_binary in "
            f"config/mode_thresholds.yaml."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        synthetic_request, _ = _synthetic_anthropic_transport()
        raise APIConnectionError(
            message=(
                f"claude -p timed out after {timeout_s}s "
                f"(argv_head={argv[:4]!r})"
            ),
            request=synthetic_request,
        ) from exc

    if completed.returncode != 0:
        stderr_lower = (completed.stderr or "").lower()
        is_transient = any(
            sig in stderr_lower for sig in _TRANSIENT_STDERR_SIGNATURES
        )
        summary = (
            f"claude -p exit={completed.returncode} "
            f"stderr={(completed.stderr or '').strip()[:400]!r}"
        )
        if is_transient:
            synthetic_request, _ = _synthetic_anthropic_transport()
            raise APIConnectionError(
                message=summary,
                request=synthetic_request,
            )
        raise ClaudeCodeCliError(summary)

    stdout = completed.stdout or ""
    if not stdout.strip():
        raise ClaudeCodeCliError(
            "claude -p returned empty stdout; "
            f"stderr={(completed.stderr or '').strip()[:200]!r}"
        )

    try:
        payload: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeCodeCliError(
            f"claude -p stdout was not valid JSON: {exc}; "
            f"stdout_head={stdout[:200]!r}"
        ) from exc

    if payload.get("is_error") is True:
        _, synthetic_response = _synthetic_anthropic_transport()
        raise APIStatusError(
            message=(
                "claude -p returned is_error=true; "
                f"subtype={payload.get('subtype')!r} "
                f"result_head={str(payload.get('result', ''))[:200]!r}"
            ),
            response=synthetic_response,
            body=payload,
        )

    if payload.get("type") != "result":
        raise ClaudeCodeCliError(
            f"claude -p payload has unexpected type={payload.get('type')!r}"
        )

    return payload


def _hermetic_env() -> dict[str, str]:
    """Build the subprocess env.

    Deliberately returns a copy of ``os.environ`` unmodified — empirical
    verification (2026-04-21) showed that setting ``CLAUDE_CODE_SIMPLE=1``
    disables OAuth keychain reads (same effect as ``--bare``), which forces
    per-call ``ANTHROPIC_API_KEY`` billing and defeats the whole point of
    this backend. If a defensive caller wants to strip
    ``ANTHROPIC_API_KEY`` from the subprocess env (so an accidental local
    ``.env`` can't flip the shim onto per-call billing), they should do so
    at the CLI composition root, not here — the shim itself must leave
    credentials alone.
    """
    return dict(os.environ)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _flatten_system(
    system: list[dict[str, Any]] | str | None,
) -> str:
    """Flatten Anthropic-style system blocks to a single string.

    The CLI's ``--append-system-prompt`` takes one string. SceneCritic
    passes a list of ``{type, text, cache_control}`` blocks; we join by
    double-newline and discard cache_control (the OAuth session handles
    caching for us).
    """
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    parts: list[str] = []
    for block in system:
        text = block.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n\n".join(parts)


def _flatten_messages(messages: list[dict[str, Any]]) -> str:
    """Flatten Anthropic-style messages list to a single prompt string.

    SceneCritic sends exactly ONE user message per review() call. The
    regenerator's user message is the rendered regen.j2 user block. We
    concatenate all user-role messages with double-newlines — defensive in
    case a future caller sends multi-turn content, but primary path is
    single-user-message.
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            sub: list[str] = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    sub.append(block["text"])
            text = "\n".join(sub)
        else:
            text = ""
        if text:
            if role != "user":
                parts.append(f"[{role}] {text}")
            else:
                parts.append(text)
    return "\n\n".join(parts)


def _usage_from_payload(payload: dict[str, Any]) -> _Usage:
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        return _Usage()
    return _Usage(
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        cache_read_input_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
    )


def _model_from_payload(payload: dict[str, Any], *, fallback: str) -> str:
    """Extract the model id from the payload's ``modelUsage`` dict.

    claude -p's JSON has no top-level ``model`` field but does carry
    ``modelUsage: {"claude-opus-4-7[1m]": {...}}`` — one key per model used.
    We pull the first key and strip any ``[1m]``-style decoration.
    """
    model_usage = payload.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        raw_key = next(iter(model_usage.keys()))
        key: str = str(raw_key)
        # Strip "[...]" decoration: "claude-opus-4-7[1m]" → "claude-opus-4-7"
        bracket = key.find("[")
        if bracket > 0:
            return key[:bracket]
        return key
    return fallback


__all__ = [
    "ClaudeCodeCliError",
    "ClaudeCodeMessagesClient",
    "CreateResponse",
    "ParseResponse",
]
