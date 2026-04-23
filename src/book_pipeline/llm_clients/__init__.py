"""Backend-agnostic LLM messages clients for SceneCritic + SceneLocalRegenerator.

Two backends are supported at this package level:

  - ``claude_code_cli`` — shells out to ``claude -p --output-format json`` using
    OAuth credentials from ``~/.claude/`` (subscription-covered; no API key).
    This is the DEFAULT backend per operator directive 2026-04-21: the
    pipeline should not consume pay-per-call Anthropic billing when the
    operator already has a Pro/Max subscription.

  - ``anthropic_sdk`` — the existing ``anthropic.Anthropic()`` client, used
    when the operator explicitly opts in via ``critic_backend.kind:
    anthropic_sdk`` in ``config/mode_thresholds.yaml``. Requires an
    ``ANTHROPIC_API_KEY`` environment variable.

Both backends expose the same minimal surface that SceneCritic and
SceneLocalRegenerator consume:

  client.messages.parse(model=..., system=..., messages=..., output_format=...)
  client.messages.create(model=..., system=..., messages=..., max_tokens=...)

Because the existing concrete classes take ``anthropic_client: Any`` (duck-
typed seam), swapping backends is a one-line construction change at the CLI
composition root — no edits to SceneCritic/SceneLocalRegenerator internals.

The ``LLMMessagesClient`` Protocol below documents the minimum surface for
mypy + reviewer reference; it is not enforced with ``@runtime_checkable``
because the existing SDK class and our test fakes would both need to
conform, and runtime-checking Protocols with ``parse``/``create`` semantics
fights the Any-typed constructor seams that Phase 3 already committed to.
"""
from __future__ import annotations

from book_pipeline.llm_clients.claude_code import (
    ClaudeCodeCliError,
    ClaudeCodeMessagesClient,
)
from book_pipeline.llm_clients.factory import (
    CriticBackendKind,
    LLMMessagesClient,
    build_llm_client,
)

__all__ = [
    "ClaudeCodeCliError",
    "ClaudeCodeMessagesClient",
    "CriticBackendKind",
    "LLMMessagesClient",
    "build_llm_client",
]
