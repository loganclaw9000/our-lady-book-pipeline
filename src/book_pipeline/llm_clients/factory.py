"""Factory for picking between the claude-code CLI backend and the Anthropic SDK.

Entry point: ``build_llm_client(backend_config)`` — returns a client whose
``.messages.parse()`` / ``.messages.create()`` surface matches what
SceneCritic + SceneLocalRegenerator consume.

Backend selection lives in ``config/mode_thresholds.yaml`` under
``critic_backend.kind`` (see ``book_pipeline.config.mode_thresholds.CriticBackendConfig``).
Default is ``claude_code_cli`` — operator is on a Claude Max subscription
and flat-rate inference via the CLI is strictly cheaper than per-call API
billing.
"""
from __future__ import annotations

from typing import Any, Literal, Protocol

CriticBackendKind = Literal["claude_code_cli", "anthropic_sdk"]


class _Messages(Protocol):
    """Minimum surface SceneCritic + SceneLocalRegenerator touch on
    ``client.messages``. Used for mypy documentation, not runtime isinstance
    (existing tests rely on duck-typed fakes that do not inherit from this
    Protocol)."""

    def parse(self, **kwargs: Any) -> Any: ...

    def create(self, **kwargs: Any) -> Any: ...


class LLMMessagesClient(Protocol):
    """Top-level surface: a ``.messages`` attribute that supports parse+create.

    Concrete conformants:
      - ``anthropic.Anthropic()`` (native SDK)
      - ``book_pipeline.llm_clients.ClaudeCodeMessagesClient`` (CLI subprocess)
      - Test fakes (``FakeAnthropicClient`` in ``tests/critic/fixtures.py``
        and the ``_FakeAnthropicClient`` in ``tests/regenerator/test_scene_local.py``)
    """

    messages: _Messages


def build_llm_client(backend_config: Any) -> Any:
    """Return a messages-client for the given backend config.

    Args:
        backend_config: A ``CriticBackendConfig`` instance (or any object
            exposing ``.kind``, ``.timeout_s``, ``.model`` attributes). We
            accept ``Any`` to keep ``book_pipeline.llm_clients`` independent
            of ``book_pipeline.config``; the config module imports the
            factory, not vice-versa.

    Returns:
        A client with a ``.messages`` attribute. SceneCritic and
        SceneLocalRegenerator take ``anthropic_client: Any`` — passing the
        returned value directly works regardless of which backend was chosen.

    Raises:
        ValueError: Unknown backend kind.
    """
    kind: CriticBackendKind = getattr(backend_config, "kind", "claude_code_cli")
    timeout_s: int = int(getattr(backend_config, "timeout_s", 180))

    if kind == "claude_code_cli":
        from book_pipeline.llm_clients.claude_code import ClaudeCodeMessagesClient

        return ClaudeCodeMessagesClient(timeout_s=timeout_s)
    if kind == "anthropic_sdk":
        # Lazy import so the factory itself has no hard dep surface on the
        # anthropic SDK for anyone instantiating the CLI backend.
        from anthropic import Anthropic

        return Anthropic()
    raise ValueError(
        f"Unknown critic_backend.kind={kind!r}; "
        f"expected 'claude_code_cli' or 'anthropic_sdk'"
    )


__all__ = ["CriticBackendKind", "LLMMessagesClient", "build_llm_client"]
