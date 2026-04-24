"""httpx+tenacity vLLM client with voice-pin SHA boot handshake (V-3 mitigation).

This module is the kernel-clean HTTP seam between the Mode-A drafter and a
locally served voice-FT LoRA adapter. Two invariants:

1. **V-3 pitfall is enforced at boot.** ``boot_handshake`` recomputes
   ``compute_adapter_sha(pin.checkpoint_path)`` and compares to
   ``pin.checkpoint_sha``; any drift raises ``VoicePinMismatch`` (and emits
   an error-status telemetry Event first, so observability records the
   attempted pin check — ADR-003 load-bearing).

2. **Kernel discipline.** This file carries NO book-domain constants
   (base URL, LoRA-module name, poll timeouts). The CLI composition layer
   (``src/book_pipeline/cli/vllm_bootstrap.py``) injects them via constructor
   args. import-linter contract 1 guards this boundary on every commit.

Retry semantics (ARCHITECTURE.md §3.4 retry boundary 2 for Mode A):
``_http_get`` + ``_http_post`` are wrapped by ``tenacity.retry`` with
``stop_after_attempt(3)`` + exponential backoff 1→4s. Transient transport
errors (``httpx.TimeoutException``, ``httpx.ConnectError``,
``httpx.RequestError``) retry; other exceptions propagate. After exhaustion,
the private methods raise the terminal underlying error; public methods
translate to ``VllmUnavailable``.

Event emission on boot handshake (role=``vllm_boot_handshake``):

- happy path: one success Event with ``checkpoint_sha=actual_sha``,
  ``mode='A'``, ``caller_context.served_model_id``, ``base_url``, ``base_model``,
  ``vllm_version`` (from /v1/models response).
- SHA mismatch: one Event with ``extra={status:'error',
  error:'voice_pin_mismatch', expected_sha, actual_sha}`` emitted BEFORE
  raising VoicePinMismatch.

When ``self.event_logger`` is None, no emission is attempted (tests inject a
FakeEventLogger; production CLI wires ``JsonlEventLogger``).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
import tenacity

from book_pipeline.config.voice_pin import VoicePinData
from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.types import Event
from book_pipeline.observability.hashing import event_id, hash_text
from book_pipeline.voice_fidelity.sha import VoicePinMismatch, compute_adapter_sha

_DEFAULT_TIMEOUT_S = 300.0  # 5min - bumped 60->300 for V6 27B bnb-quant ~5tok/s on Spark (incident 2026-04-24)
_DEFAULT_LORA_MODULE_NAME = "paul-voice"


class VllmUnavailable(Exception):
    """Raised when the vLLM HTTP endpoint is unreachable after retry exhaustion."""


class VllmHandshakeError(Exception):
    """Raised when /v1/models does not advertise the expected LoRA module.

    This is distinct from ``VoicePinMismatch`` (from voice_fidelity.sha):
    - VllmHandshakeError: vLLM is up but the wrong (or no) LoRA is loaded.
    - VoicePinMismatch:   vLLM loaded the LoRA, but its weight SHA differs
      from voice_pin.yaml.

    Both are caught by the Plan 03-03 orchestrator and routed to
    ``HARD_BLOCKED``.
    """


def _retry_transport() -> tenacity.Retrying:
    """Tenacity retry config for transient HTTP transport errors.

    3 attempts, exponential backoff 1s → 2s → 4s, retry on
    httpx.TimeoutException / ConnectError / RequestError.
    """
    return tenacity.Retrying(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=4),
        retry=tenacity.retry_if_exception_type(
            (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError)
        ),
        reraise=True,
    )


class VllmClient:
    """httpx+tenacity client against a vLLM OpenAI-compatible endpoint.

    Usage (CLI composition — kernel does not know about endpoints):

        # CLI composition layer imports the book-domain constants and injects
        # them here. See cli/vllm_bootstrap.py for the sanctioned bridge.
        client = VllmClient(
            base_url=...,
            event_logger=JsonlEventLogger(),
            lora_module_name="paul-voice",
        )
        client.boot_handshake(pin)  # V-3 enforcement
        client.chat_completion(messages=..., model="paul-voice", ...)

    Test seam: pass ``_http_client`` to inject an httpx.Client built on a
    MockTransport. Production code leaves this None and the client builds
    its own.
    """

    def __init__(
        self,
        base_url: str,
        *,
        event_logger: EventLogger | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        lora_module_name: str = _DEFAULT_LORA_MODULE_NAME,
        _http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.event_logger = event_logger
        self.timeout_s = timeout_s
        self.lora_module_name = lora_module_name
        if _http_client is not None:
            self._client = _http_client
            self._owns_client = False
        else:
            self._client = httpx.Client(base_url=self.base_url, timeout=timeout_s)
            self._owns_client = True

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------------ #
    # Private transport — tenacity-wrapped; translates transport errors. #
    # ------------------------------------------------------------------ #
    def _http_get(self, path: str) -> httpx.Response:
        for attempt in _retry_transport():
            with attempt:
                # Tests may pass a client bound to a different base_url; prefer
                # an absolute URL if path looks absolute, else join to self.base_url.
                url = path if path.startswith("http") else f"{self.base_url}{path}"
                return self._client.get(url)
        # Unreachable — reraise=True guarantees the last exception bubbles.
        raise VllmUnavailable(f"unreachable: exhausted retries for GET {path}")

    def _http_post(self, path: str, json: dict[str, Any]) -> httpx.Response:
        for attempt in _retry_transport():
            with attempt:
                url = path if path.startswith("http") else f"{self.base_url}{path}"
                return self._client.post(url, json=json)
        raise VllmUnavailable(f"unreachable: exhausted retries for POST {path}")

    # ------------- Public API -------------- #
    def get_models(self) -> dict[str, Any]:
        """GET {base_url}/models, retry-wrapped. Returns parsed JSON."""
        try:
            response = self._http_get("/models")
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RequestError,
        ) as exc:
            raise VllmUnavailable(f"vLLM unreachable at {self.base_url}: {exc}") from exc
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise VllmHandshakeError(
                f"/v1/models returned non-dict payload: {type(payload).__name__}"
            )
        return payload

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        temperature: float,
        top_p: float,
        max_tokens: int,
        repetition_penalty: float | None = None,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST {base_url}/chat/completions (OpenAI-compatible schema).

        vLLM-specific sampling params (repetition_penalty) live under
        ``extra_body`` per vLLM's OpenAI server convention. ``stop`` sits at
        the top level when provided.
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if stop is not None:
            body["stop"] = stop
        if repetition_penalty is not None:
            body["extra_body"] = {"repetition_penalty": repetition_penalty}
        try:
            response = self._http_post("/chat/completions", body)
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RequestError,
        ) as exc:
            raise VllmUnavailable(
                f"vLLM chat_completion unreachable at {self.base_url}: {exc}"
            ) from exc
        response.raise_for_status()
        out = response.json()
        if not isinstance(out, dict):
            raise VllmHandshakeError(
                f"/v1/chat/completions returned non-dict: {type(out).__name__}"
            )
        return out

    def health_ok(self) -> bool:
        """Non-raising probe — True iff get_models() succeeds."""
        try:
            self.get_models()
        except (VllmUnavailable, VllmHandshakeError, httpx.HTTPStatusError):
            return False
        return True

    def boot_handshake(self, pin: VoicePinData) -> None:
        """Assert vLLM is serving the pinned LoRA at the pinned SHA (V-3 live).

        Steps:
          1. GET /v1/models (tenacity-retried). On exhausted retries → VllmUnavailable.
          2. Assert a model with id == self.lora_module_name is in data[].
             Otherwise → VllmHandshakeError.
          3. actual_sha = compute_adapter_sha(pin.checkpoint_path).
          4. On mismatch: emit one Event(status=error, error=voice_pin_mismatch)
             then raise VoicePinMismatch.
          5. On match: emit one Event(role='vllm_boot_handshake', mode='A',
             checkpoint_sha=actual_sha, caller_context.served_model_id, base_url,
             base_model, vllm_version).
        """
        t0_ns = time.monotonic_ns()
        models_payload = self.get_models()
        served_ids = [m.get("id") for m in models_payload.get("data", []) if isinstance(m, dict)]
        if not any(
            mid == self.lora_module_name or (isinstance(mid, str) and mid.endswith(f"/{self.lora_module_name}"))
            for mid in served_ids
        ):
            raise VllmHandshakeError(
                f"vLLM at {self.base_url} does not serve LoRA module "
                f"{self.lora_module_name!r}; got served_ids={served_ids!r}"
            )

        vllm_version_val = models_payload.get("vllm_version")
        vllm_version = str(vllm_version_val) if isinstance(vllm_version_val, str) else "unknown"
        actual_sha = compute_adapter_sha(Path(pin.checkpoint_path).expanduser())
        latency_ms = max(1, (time.monotonic_ns() - t0_ns) // 1_000_000)

        if actual_sha != pin.checkpoint_sha:
            self._emit_handshake_event(
                pin=pin,
                served_model_id=self.lora_module_name,
                vllm_version=vllm_version,
                actual_sha=actual_sha,
                latency_ms=int(latency_ms),
                status="error",
                error="voice_pin_mismatch",
                expected_sha=pin.checkpoint_sha,
            )
            raise VoicePinMismatch(
                expected_sha=pin.checkpoint_sha,
                actual_sha=actual_sha,
                adapter_dir=Path(pin.checkpoint_path).expanduser(),
            )

        self._emit_handshake_event(
            pin=pin,
            served_model_id=self.lora_module_name,
            vllm_version=vllm_version,
            actual_sha=actual_sha,
            latency_ms=int(latency_ms),
            status="ok",
            error=None,
            expected_sha=pin.checkpoint_sha,
        )
        return None

    def _emit_handshake_event(
        self,
        *,
        pin: VoicePinData,
        served_model_id: str,
        vllm_version: str,
        actual_sha: str,
        latency_ms: int,
        status: str,
        error: str | None,
        expected_sha: str,
    ) -> None:
        if self.event_logger is None:
            return
        from datetime import UTC, datetime

        ts_iso = datetime.now(UTC).isoformat(timespec="milliseconds")
        prompt_h = hash_text(pin.checkpoint_path)
        eid = event_id(ts_iso, "vllm_boot_handshake", "drafter.vllm_client:boot_handshake", prompt_h)
        extra: dict[str, Any] = {}
        if status != "ok":
            extra["status"] = status
        if error is not None:
            extra["error"] = error
            extra["expected_sha"] = expected_sha
            extra["actual_sha"] = actual_sha
        event = Event(
            event_id=eid,
            ts_iso=ts_iso,
            role="vllm_boot_handshake",
            model=served_model_id,
            prompt_hash=prompt_h,
            input_tokens=0,
            cached_tokens=0,
            output_tokens=0,
            latency_ms=latency_ms,
            temperature=None,
            top_p=None,
            caller_context={
                "module": "drafter.vllm_client",
                "function": "boot_handshake",
                "served_model_id": served_model_id,
                "base_url": self.base_url,
                "vllm_version": vllm_version,
                "base_model": pin.base_model,
            },
            output_hash=actual_sha,
            mode="A",
            rubric_version=None,
            checkpoint_sha=actual_sha,
            extra=extra,
        )
        self.event_logger.emit(event)


__all__ = [
    "VllmClient",
    "VllmHandshakeError",
    "VllmUnavailable",
]
