"""Tests for book_pipeline.drafter.vllm_client (Plan 03-03 Task 1).

VllmClient is an httpx+tenacity client with a boot_handshake that enforces
the voice_pin SHA (V-3 mitigation live). These tests use httpx.MockTransport
to avoid a real vLLM server.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from book_pipeline.config.voice_pin import VllmServeConfig, VoicePinData
from book_pipeline.interfaces.types import Event
from book_pipeline.voice_fidelity.sha import VoicePinMismatch


class _FakeEventLogger:
    """Captures emitted Events in-memory for test assertions."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


def _write_fake_adapter(adapter_dir: Path) -> str:
    """Materialize a tiny valid adapter dir; return the true SHA over the two files."""
    adapter_dir.mkdir(parents=True, exist_ok=True)
    safetensors_bytes = b"S" * 64
    config_bytes = b'{"peft_type":"LORA","r":16}'
    (adapter_dir / "adapter_model.safetensors").write_bytes(safetensors_bytes)
    (adapter_dir / "adapter_config.json").write_bytes(config_bytes)
    return hashlib.sha256(safetensors_bytes + config_bytes).hexdigest()


def _pin(adapter_dir: Path, sha: str) -> VoicePinData:
    return VoicePinData(
        source_repo="paul-thinkpiece-pipeline",
        source_commit_sha="deadbeef",
        ft_run_id="v6_qwen3_32b",
        checkpoint_path=str(adapter_dir),
        checkpoint_sha=sha,
        base_model="Qwen/Qwen3-32B",
        trained_on_date="2026-04-14",
        pinned_on_date="2026-04-22",
        pinned_reason="test",
        vllm_serve_config=VllmServeConfig(
            port=8002,
            max_model_len=8192,
            dtype="bfloat16",
            tensor_parallel_size=1,
        ),
    )


def _models_response(model_id: str = "paul-voice") -> dict:
    return {
        "object": "list",
        "data": [
            {"id": model_id, "object": "model", "created": 0, "owned_by": "vllm"},
        ],
        "vllm_version": "0.19.1",
    }


def test_get_models_returns_parsed_json() -> None:
    """Test 1: VllmClient.get_models() returns JSON payload from mocked httpx."""
    from book_pipeline.drafter.vllm_client import VllmClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json=_models_response())

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="http://test/v1", timeout=2.0)
    client = VllmClient(base_url="http://test/v1", _http_client=http_client)

    out = client.get_models()
    assert isinstance(out, dict)
    assert out["data"][0]["id"] == "paul-voice"


def test_get_models_raises_vllm_unavailable_after_retries() -> None:
    """Test 2: VllmClient.get_models() raises VllmUnavailable after 3 retries on ConnectError."""
    from book_pipeline.drafter.vllm_client import VllmClient, VllmUnavailable

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="http://test/v1", timeout=2.0)
    client = VllmClient(base_url="http://test/v1", _http_client=http_client)

    with pytest.raises(VllmUnavailable):
        client.get_models()
    assert call_count["n"] == 3, f"expected 3 retry attempts, got {call_count['n']}"


def test_boot_handshake_success_emits_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 3: boot_handshake happy path — SHA matches, 'paul-voice' loaded, Event emitted."""
    from book_pipeline.drafter.vllm_client import VllmClient

    adapter_dir = tmp_path / "adapter"
    true_sha = _write_fake_adapter(adapter_dir)
    pin = _pin(adapter_dir, true_sha)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_models_response())

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="http://test/v1", timeout=2.0)
    logger = _FakeEventLogger()
    client = VllmClient(
        base_url="http://test/v1",
        event_logger=logger,
        _http_client=http_client,
    )

    result = client.boot_handshake(pin)
    assert result is None
    assert len(logger.events) == 1
    ev = logger.events[0]
    assert ev.role == "vllm_boot_handshake"
    assert ev.checkpoint_sha == true_sha
    assert ev.output_hash == true_sha
    assert ev.mode == "A"
    assert ev.caller_context["served_model_id"] == "paul-voice"
    assert ev.caller_context["base_url"] == "http://test/v1"
    assert ev.caller_context["base_model"] == "Qwen/Qwen3-32B"


def test_boot_handshake_sha_mismatch_emits_error_event_then_raises(
    tmp_path: Path,
) -> None:
    """Test 4: SHA mismatch → emit one Event with status=error, THEN raise VoicePinMismatch."""
    from book_pipeline.drafter.vllm_client import VllmClient

    adapter_dir = tmp_path / "adapter"
    true_sha = _write_fake_adapter(adapter_dir)
    wrong_sha = "0" * 64
    pin = _pin(adapter_dir, wrong_sha)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_models_response())

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="http://test/v1", timeout=2.0)
    logger = _FakeEventLogger()
    client = VllmClient(
        base_url="http://test/v1",
        event_logger=logger,
        _http_client=http_client,
    )

    with pytest.raises(VoicePinMismatch) as excinfo:
        client.boot_handshake(pin)
    assert excinfo.value.expected_sha == wrong_sha
    assert excinfo.value.actual_sha == true_sha
    # Exactly one telemetry event emitted BEFORE raise (observability trail).
    assert len(logger.events) == 1
    ev = logger.events[0]
    assert ev.role == "vllm_boot_handshake"
    assert ev.extra.get("status") == "error"
    assert ev.extra.get("error") == "voice_pin_mismatch"
    assert ev.extra.get("expected_sha") == wrong_sha
    assert ev.extra.get("actual_sha") == true_sha


def test_boot_handshake_model_not_loaded_raises_handshake_error(tmp_path: Path) -> None:
    """Test 5: /v1/models response without 'paul-voice' → raises VllmHandshakeError."""
    from book_pipeline.drafter.vllm_client import VllmClient, VllmHandshakeError

    adapter_dir = tmp_path / "adapter"
    true_sha = _write_fake_adapter(adapter_dir)
    pin = _pin(adapter_dir, true_sha)

    def handler(request: httpx.Request) -> httpx.Response:
        # Return a response without "paul-voice" loaded.
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "some-other-model"}]},
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="http://test/v1", timeout=2.0)
    client = VllmClient(base_url="http://test/v1", _http_client=http_client)

    with pytest.raises(VllmHandshakeError):
        client.boot_handshake(pin)


def test_chat_completion_payload_shape() -> None:
    """Test 6: chat_completion payload is OpenAI-compatible; repetition_penalty in extra_body."""
    from book_pipeline.drafter.vllm_client import VllmClient

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["path"] = request.url.path
        captured["body"] = _json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "cmpl-1",
                "object": "chat.completion",
                "choices": [
                    {"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="http://test/v1", timeout=2.0)
    client = VllmClient(base_url="http://test/v1", _http_client=http_client)

    out = client.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        model="paul-voice",
        temperature=0.85,
        top_p=0.92,
        max_tokens=128,
        repetition_penalty=1.05,
    )
    assert out["choices"][0]["message"]["content"] == "hi"
    assert captured["path"].endswith("/chat/completions")
    body = captured["body"]
    assert body["model"] == "paul-voice"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["temperature"] == 0.85
    assert body["top_p"] == 0.92
    assert body["max_tokens"] == 128
    # repetition_penalty MUST live under extra_body (vLLM-specific).
    assert "repetition_penalty" not in body
    assert body["extra_body"]["repetition_penalty"] == 1.05


def test_vllm_client_is_kernel_clean() -> None:
    """Test 7: drafter/vllm_client.py does NOT import from book_specifics."""
    import pathlib

    src = pathlib.Path("src/book_pipeline/drafter/vllm_client.py").read_text(encoding="utf-8")
    assert "book_specifics" not in src, (
        "vllm_client.py must not reference book_specifics — kernel discipline."
    )
