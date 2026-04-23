"""Tests for ClaudeCodeMessagesClient — the ``claude -p`` CLI backend shim.

Phase 3 gap-closure (2026-04-21). The shim provides a drop-in replacement
for the minimum ``anthropic.Anthropic().messages`` surface that SceneCritic
(``.parse``) and SceneLocalRegenerator (``.create``) consume, driven by
``subprocess.run`` against the ``claude`` CLI.

All unit tests here mock ``subprocess.run`` so nothing actually shells out;
one ``@pytest.mark.slow`` integration test at the bottom of this file does
hit the real CLI when the operator runs ``pytest -m slow``.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import patch

import pytest
from anthropic import APIConnectionError, APIStatusError
from pydantic import BaseModel, Field

from book_pipeline.llm_clients.claude_code import (
    ClaudeCodeCliError,
    ClaudeCodeMessagesClient,
    CreateResponse,
    ParseResponse,
    _flatten_messages,
    _flatten_system,
    _model_from_payload,
    _usage_from_payload,
)

# --------------------------------------------------------------------- #
# Test fixtures / helpers                                                #
# --------------------------------------------------------------------- #


class _SimpleAnswer(BaseModel):
    """Minimal Pydantic model for exercising --json-schema path."""

    answer: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def _cli_success_payload(
    structured: dict[str, Any] | None = None,
    result_text: str = "hello",
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read_input_tokens: int = 200,
) -> dict[str, Any]:
    """Build a canonical claude -p JSON success payload."""
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "api_error_status": None,
        "duration_ms": 1234,
        "result": result_text,
        "stop_reason": "end_turn",
        "session_id": "sess_test_01",
        "total_cost_usd": 0.12,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
        },
        "modelUsage": {
            "claude-opus-4-7[1m]": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
            }
        },
        "structured_output": structured if structured is not None else {},
    }


def _mk_completed(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["claude", "-p"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# --------------------------------------------------------------------- #
# 1. parse() builds correct argv                                          #
# --------------------------------------------------------------------- #


def test_parse_builds_expected_argv_with_schema_and_system() -> None:
    """parse() invokes subprocess.run with --json-schema + --append-system-prompt
    + model + the user prompt as the final positional arg."""
    structured = {"answer": "forty-two", "confidence": 0.9}
    payload = _cli_success_payload(structured=structured)

    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ) as mock_run:
        client = ClaudeCodeMessagesClient(timeout_s=30)
        resp = client.messages.parse(
            model="claude-opus-4-7",
            messages=[{"role": "user", "content": "what is the answer?"}],
            output_format=_SimpleAnswer,
            system=[
                {"type": "text", "text": "You answer succinctly.",
                 "cache_control": {"type": "ephemeral", "ttl": "1h"}},
            ],
            max_tokens=1024,
        )

    assert mock_run.call_count == 1
    argv: list[str] = mock_run.call_args.args[0]
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "--output-format" in argv
    out_fmt_idx = argv.index("--output-format")
    assert argv[out_fmt_idx + 1] == "json"
    assert "--json-schema" in argv
    schema_idx = argv.index("--json-schema")
    schema = json.loads(argv[schema_idx + 1])
    # Pydantic schema includes both our fields
    assert "answer" in schema["properties"]
    assert "confidence" in schema["properties"]
    # Model flag
    assert "--model" in argv
    model_idx = argv.index("--model")
    assert argv[model_idx + 1] == "claude-opus-4-7"
    # System prompt flattened
    assert "--append-system-prompt" in argv
    sp_idx = argv.index("--append-system-prompt")
    assert argv[sp_idx + 1] == "You answer succinctly."
    # User prompt is final arg
    assert argv[-1] == "what is the answer?"

    # Timeout matches constructor
    assert mock_run.call_args.kwargs["timeout"] == 30

    # Response roundtrips the structured output through Pydantic
    assert isinstance(resp, ParseResponse)
    assert isinstance(resp.parsed_output, _SimpleAnswer)
    assert resp.parsed_output.answer == "forty-two"
    assert resp.parsed_output.confidence == pytest.approx(0.9)

    # Usage fields land on the ParseResponse
    assert resp.usage.input_tokens == 100
    assert resp.usage.output_tokens == 50
    assert resp.usage.cache_read_input_tokens == 200


def test_parse_flattens_multi_block_system() -> None:
    """Multiple system blocks get joined with double-newlines."""
    payload = _cli_success_payload(structured={"answer": "x"})
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ) as mock_run:
        client = ClaudeCodeMessagesClient()
        client.messages.parse(
            model="claude-opus-4-7",
            messages=[{"role": "user", "content": "q"}],
            output_format=_SimpleAnswer,
            system=[
                {"type": "text", "text": "First block."},
                {"type": "text", "text": "Second block."},
            ],
        )
    argv: list[str] = mock_run.call_args.args[0]
    sp = argv[argv.index("--append-system-prompt") + 1]
    assert sp == "First block.\n\nSecond block."


def test_parse_omits_system_flag_when_none() -> None:
    """If system=None, --append-system-prompt is not in argv."""
    payload = _cli_success_payload(structured={"answer": "x"})
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ) as mock_run:
        client = ClaudeCodeMessagesClient()
        client.messages.parse(
            model="claude-opus-4-7",
            messages=[{"role": "user", "content": "q"}],
            output_format=_SimpleAnswer,
            system=None,
        )
    argv: list[str] = mock_run.call_args.args[0]
    assert "--append-system-prompt" not in argv


# --------------------------------------------------------------------- #
# 2. create() — free-text response path (no schema)                       #
# --------------------------------------------------------------------- #


def test_create_builds_argv_without_schema_and_returns_content_text() -> None:
    """create() does NOT pass --json-schema; response.content[0].text
    carries the CLI's 'result' field."""
    payload = _cli_success_payload(result_text="a fresh revised scene")
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ) as mock_run:
        client = ClaudeCodeMessagesClient()
        resp = client.messages.create(
            model="claude-opus-4-7",
            messages=[{"role": "user", "content": "rewrite this scene"}],
            system="You rewrite scenes.",
            max_tokens=2048,
        )
    argv: list[str] = mock_run.call_args.args[0]
    assert "--json-schema" not in argv
    assert argv[-1] == "rewrite this scene"
    # System-string path flows through correctly
    sp_idx = argv.index("--append-system-prompt")
    assert argv[sp_idx + 1] == "You rewrite scenes."

    assert isinstance(resp, CreateResponse)
    assert len(resp.content) == 1
    assert resp.content[0].text == "a fresh revised scene"
    assert resp.content[0].type == "text"


# --------------------------------------------------------------------- #
# 3. Error paths                                                          #
# --------------------------------------------------------------------- #


def test_parse_raises_api_connection_error_on_timeout() -> None:
    """subprocess.TimeoutExpired → anthropic.APIConnectionError (retry-eligible)."""
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=5),
    ):
        client = ClaudeCodeMessagesClient(timeout_s=5)
        with pytest.raises(APIConnectionError):
            client.messages.parse(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
                output_format=_SimpleAnswer,
            )


def test_parse_raises_claude_code_cli_error_when_binary_missing() -> None:
    """FileNotFoundError from subprocess.run (no claude binary) →
    ClaudeCodeCliError (non-retryable)."""
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        side_effect=FileNotFoundError("no such file"),
    ):
        client = ClaudeCodeMessagesClient()
        with pytest.raises(ClaudeCodeCliError) as excinfo:
            client.messages.parse(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
                output_format=_SimpleAnswer,
            )
        assert "binary not found" in str(excinfo.value).lower()


def test_parse_raises_api_connection_error_on_transient_nonzero_exit() -> None:
    """Non-zero exit with 'connection' / '502' in stderr → APIConnectionError
    (retry-eligible)."""
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(
            returncode=1, stderr="upstream 502 connection reset"
        ),
    ):
        client = ClaudeCodeMessagesClient()
        with pytest.raises(APIConnectionError):
            client.messages.parse(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
                output_format=_SimpleAnswer,
            )


def test_parse_raises_claude_code_cli_error_on_terminal_nonzero_exit() -> None:
    """Non-zero exit with non-transient stderr → ClaudeCodeCliError
    (not retry-eligible)."""
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(
            returncode=2, stderr="invalid argument: --bogus-flag"
        ),
    ):
        client = ClaudeCodeMessagesClient()
        with pytest.raises(ClaudeCodeCliError) as excinfo:
            client.messages.parse(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
                output_format=_SimpleAnswer,
            )
        assert "exit=2" in str(excinfo.value)


def test_parse_raises_api_status_error_on_is_error_true() -> None:
    """is_error=true in the CLI JSON response → APIStatusError."""
    payload = {
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "result": "rate limit exceeded",
        "stop_reason": "end_turn",
    }
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ):
        client = ClaudeCodeMessagesClient()
        with pytest.raises(APIStatusError):
            client.messages.parse(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
                output_format=_SimpleAnswer,
            )


def test_parse_raises_on_malformed_json_stdout() -> None:
    """Non-JSON stdout → ClaudeCodeCliError."""
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout="this is not json at all"),
    ):
        client = ClaudeCodeMessagesClient()
        with pytest.raises(ClaudeCodeCliError) as excinfo:
            client.messages.parse(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
                output_format=_SimpleAnswer,
            )
        assert "not valid json" in str(excinfo.value).lower()


def test_parse_raises_on_structured_output_validation_failure() -> None:
    """structured_output that doesn't satisfy Pydantic → ClaudeCodeCliError."""
    # confidence=2.0 violates the ge=0.0 le=1.0 constraint on _SimpleAnswer.
    payload = _cli_success_payload(
        structured={"answer": "x", "confidence": 2.0}
    )
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ):
        client = ClaudeCodeMessagesClient()
        with pytest.raises(ClaudeCodeCliError) as excinfo:
            client.messages.parse(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
                output_format=_SimpleAnswer,
            )
        assert "validation" in str(excinfo.value).lower()


def test_parse_raises_when_structured_output_missing() -> None:
    """structured_output missing from payload → ClaudeCodeCliError."""
    payload = _cli_success_payload(structured=None)
    payload.pop("structured_output")
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ):
        client = ClaudeCodeMessagesClient()
        with pytest.raises(ClaudeCodeCliError) as excinfo:
            client.messages.parse(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
                output_format=_SimpleAnswer,
            )
        assert "structured_output" in str(excinfo.value)


def test_create_raises_on_missing_result_field() -> None:
    """result string missing from payload (but is_error=false) → ClaudeCodeCliError."""
    payload = _cli_success_payload()
    payload.pop("result")
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ):
        client = ClaudeCodeMessagesClient()
        with pytest.raises(ClaudeCodeCliError) as excinfo:
            client.messages.create(
                model="claude-opus-4-7",
                messages=[{"role": "user", "content": "x"}],
            )
        assert "result" in str(excinfo.value)


# --------------------------------------------------------------------- #
# 4. Env + hermeticity                                                    #
# --------------------------------------------------------------------- #


def test_parse_does_not_set_claude_code_simple_env() -> None:
    """The subprocess env must NOT carry CLAUDE_CODE_SIMPLE=1.

    Empirical verification (2026-04-21): setting that env var disables OAuth
    keychain reads in the same way ``--bare`` does — which would force
    per-call ANTHROPIC_API_KEY billing and defeat the whole point of this
    backend. This regression test asserts we don't reintroduce the env var.
    """
    payload = _cli_success_payload(structured={"answer": "x"})
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ) as mock_run:
        client = ClaudeCodeMessagesClient()
        client.messages.parse(
            model="claude-opus-4-7",
            messages=[{"role": "user", "content": "x"}],
            output_format=_SimpleAnswer,
        )
    env = mock_run.call_args.kwargs["env"]
    # If operator's ambient env somehow had CLAUDE_CODE_SIMPLE pre-set, we
    # pass it through — the shim is responsible for not ADDING it.
    import os as _os
    ambient = _os.environ.get("CLAUDE_CODE_SIMPLE")
    assert env.get("CLAUDE_CODE_SIMPLE") == ambient


def test_parse_does_not_use_shell() -> None:
    """subprocess.run called with argv-as-list and no shell=True — protects
    against shell metachar injection in user prompt content."""
    payload = _cli_success_payload(structured={"answer": "x"})
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ) as mock_run:
        client = ClaudeCodeMessagesClient()
        # Prompt contains shell-metacharacter-ish content
        evil_prompt = 'text with `rm -rf /` and $(whoami) and ; and |'
        client.messages.parse(
            model="claude-opus-4-7",
            messages=[{"role": "user", "content": evil_prompt}],
            output_format=_SimpleAnswer,
        )
    # subprocess.run never called with shell=True
    assert mock_run.call_args.kwargs.get("shell", False) is False
    # The dangerous content appears as a literal argv element (safe)
    argv: list[str] = mock_run.call_args.args[0]
    assert argv[-1] == evil_prompt


# --------------------------------------------------------------------- #
# 5. Helper-function unit tests                                           #
# --------------------------------------------------------------------- #


def test_flatten_system_string_passthrough() -> None:
    assert _flatten_system("raw text") == "raw text"


def test_flatten_system_none_returns_empty() -> None:
    assert _flatten_system(None) == ""


def test_flatten_system_skips_empty_text() -> None:
    blocks = [
        {"type": "text", "text": ""},
        {"type": "text", "text": "kept"},
    ]
    assert _flatten_system(blocks) == "kept"


def test_flatten_messages_preserves_user_only_content() -> None:
    msgs = [{"role": "user", "content": "hi"}]
    assert _flatten_messages(msgs) == "hi"


def test_flatten_messages_marks_non_user_roles() -> None:
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    out = _flatten_messages(msgs)
    assert "q" in out
    assert "[assistant] a" in out


def test_flatten_messages_handles_block_content_list() -> None:
    msgs = [
        {"role": "user", "content": [
            {"type": "text", "text": "block1"},
            {"type": "text", "text": "block2"},
        ]}
    ]
    assert _flatten_messages(msgs) == "block1\nblock2"


def test_usage_from_payload_handles_missing_fields() -> None:
    usage = _usage_from_payload({"usage": {"input_tokens": 10}})
    assert usage.input_tokens == 10
    assert usage.output_tokens == 0
    assert usage.cache_read_input_tokens == 0


def test_usage_from_payload_handles_missing_usage() -> None:
    usage = _usage_from_payload({})
    assert usage.input_tokens == 0


def test_model_from_payload_strips_bracket_decoration() -> None:
    payload = {"modelUsage": {"claude-opus-4-7[1m]": {}}}
    assert _model_from_payload(payload, fallback="x") == "claude-opus-4-7"


def test_model_from_payload_falls_back_when_missing() -> None:
    assert _model_from_payload({}, fallback="claude-opus-4-7") == "claude-opus-4-7"


# --------------------------------------------------------------------- #
# 6. Factory                                                              #
# --------------------------------------------------------------------- #


def test_build_llm_client_defaults_to_claude_code_cli() -> None:
    from book_pipeline.config.mode_thresholds import CriticBackendConfig
    from book_pipeline.llm_clients import build_llm_client

    client = build_llm_client(CriticBackendConfig())
    assert isinstance(client, ClaudeCodeMessagesClient)


def test_build_llm_client_selects_anthropic_sdk_when_configured() -> None:
    from anthropic import Anthropic

    from book_pipeline.config.mode_thresholds import CriticBackendConfig
    from book_pipeline.llm_clients import build_llm_client

    client = build_llm_client(CriticBackendConfig(kind="anthropic_sdk"))
    assert isinstance(client, Anthropic)


def test_build_llm_client_raises_on_unknown_kind() -> None:
    """If the config object somehow carries an unknown kind (e.g. a test
    fake that bypasses Pydantic validation), the factory raises."""
    from book_pipeline.llm_clients import build_llm_client

    class _Fake:
        kind = "does_not_exist"
        timeout_s = 1

    with pytest.raises(ValueError) as excinfo:
        build_llm_client(_Fake())
    assert "does_not_exist" in str(excinfo.value)


def test_build_llm_client_honors_timeout_from_config() -> None:
    from book_pipeline.config.mode_thresholds import CriticBackendConfig
    from book_pipeline.llm_clients import build_llm_client

    client = build_llm_client(CriticBackendConfig(timeout_s=42))
    assert isinstance(client, ClaudeCodeMessagesClient)
    # Timeout is stashed on the inner _Messages object
    assert client.messages._timeout_s == 42  # type: ignore[attr-defined]


# --------------------------------------------------------------------- #
# 7. Drop-in compatibility with SceneCritic + SceneLocalRegenerator       #
# --------------------------------------------------------------------- #


def test_scene_critic_drives_claude_code_client_end_to_end(tmp_path) -> None:
    """SceneCritic + ClaudeCodeMessagesClient compose correctly: one parse()
    call, one audit file, one 'critic' Event. No actual subprocess call —
    subprocess.run is mocked."""
    from book_pipeline.config.rubric import RubricConfig
    from book_pipeline.critic.scene import SceneCritic
    from tests.critic.fixtures import (
        FakeEventLogger,
        make_canonical_critic_response,
        make_critic_request,
    )

    canonical = make_canonical_critic_response()
    payload = _cli_success_payload(
        structured=canonical.model_dump(),
        input_tokens=1000,
        output_tokens=400,
        cache_read_input_tokens=500,
    )
    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ):
        client = ClaudeCodeMessagesClient()
        logger = FakeEventLogger()
        critic = SceneCritic(
            anthropic_client=client,
            event_logger=logger,
            rubric=RubricConfig(),
            audit_dir=tmp_path / "critic_audit",
        )
        response = critic.review(make_critic_request())
    assert response is not None
    assert response.overall_pass is True

    audit_files = list((tmp_path / "critic_audit").glob("*.json"))
    assert len(audit_files) == 1

    critic_events = [e for e in logger.events if e.role == "critic"]
    assert len(critic_events) == 1


def test_scene_local_regenerator_drives_claude_code_client_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SceneLocalRegenerator + ClaudeCodeMessagesClient compose correctly:
    one create() call, one success Event, DraftResponse returned with the
    regenerated text."""
    # Import locally to avoid polluting the module namespace.
    from book_pipeline.regenerator.scene_local import SceneLocalRegenerator
    from tests.regenerator.test_scene_local import (
        _FakeEventLogger,
        _FakeVoicePin,
        _make_prior_draft,
        _make_regen_request,
        _patch_tenacity_wait_fast,
        _scene_text_with_wc,
    )

    _patch_tenacity_wait_fast(monkeypatch)
    prior = _make_prior_draft(word_count=500)
    new_text = _scene_text_with_wc(500)
    payload = _cli_success_payload(result_text=new_text)

    with patch(
        "book_pipeline.llm_clients.claude_code.subprocess.run",
        return_value=_mk_completed(stdout=json.dumps(payload)),
    ):
        client = ClaudeCodeMessagesClient()
        logger = _FakeEventLogger()
        regenerator = SceneLocalRegenerator(
            anthropic_client=client,
            event_logger=logger,
            voice_pin=_FakeVoicePin(),
        )
        response = regenerator.regenerate(
            _make_regen_request(prior_draft=prior, attempt_number=2)
        )
    assert response.scene_text == new_text
    assert response.attempt_number == 2
    regen_events = [e for e in logger.events if e.role == "regenerator"]
    assert len(regen_events) == 1
    assert regen_events[0].extra.get("status") != "error"


# --------------------------------------------------------------------- #
# 8. Slow integration test — actual claude CLI                            #
# --------------------------------------------------------------------- #


@pytest.mark.slow
def test_real_claude_cli_roundtrip_with_schema() -> None:
    """Hits the real ``claude -p`` CLI via OAuth. Skipped by default; run
    via ``pytest -m slow``. Verifies the CLI hasn't drifted from the schema
    we depend on (structured_output present, is_error=false, usage dict)."""
    import shutil

    if shutil.which("claude") is None:
        pytest.skip("claude CLI not on PATH")

    client = ClaudeCodeMessagesClient(timeout_s=120)
    resp = client.messages.parse(
        model="claude-opus-4-7",
        messages=[{"role": "user", "content": "What is 2+2? Respond per the schema."}],
        output_format=_SimpleAnswer,
        system="You answer arithmetic questions tersely and fill the schema.",
    )
    assert isinstance(resp, ParseResponse)
    assert isinstance(resp.parsed_output, _SimpleAnswer)
    assert resp.parsed_output.answer  # non-empty string
    assert resp.usage.input_tokens >= 0
    assert resp.usage.output_tokens > 0
