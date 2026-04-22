"""Tests for book_pipeline.config — 4 YAML configs + Pydantic-Settings models + SecretsConfig."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


# ---------------------------------------------------------------------------
# Test 1 — each of the 4 YAML files exists and yaml.safe_loads without error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    ["voice_pin.yaml", "rubric.yaml", "rag_retrievers.yaml", "mode_thresholds.yaml"],
)
def test_yaml_file_exists_and_parses(filename: str) -> None:
    path = CONFIG_DIR / filename
    assert path.is_file(), f"Missing config file: {path}"
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), f"{filename} must deserialize to a mapping"


# ---------------------------------------------------------------------------
# Test 2 — VoicePinConfig loads and base_model == "Qwen/Qwen3-32B"
# ---------------------------------------------------------------------------


def test_voice_pin_loads_with_qwen3_32b() -> None:
    from book_pipeline.config.voice_pin import VoicePinConfig

    cfg = VoicePinConfig()
    assert cfg.voice_pin.base_model == "Qwen/Qwen3-32B"
    assert cfg.voice_pin.vllm_serve_config.port == 8002
    assert cfg.voice_pin.vllm_serve_config.dtype == "bfloat16"


# ---------------------------------------------------------------------------
# Test 3 — RubricConfig rejects axes != the required 5 names
# ---------------------------------------------------------------------------


def test_rubric_rejects_wrong_axes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use monkeypatch.chdir so pydantic-settings resolves the relative
    yaml_file="config/rubric.yaml" path against tmp_path (NOT the real repo).

    This is the working pydantic-settings override pattern. An earlier
    draft used RubricConfig(_yaml_file=str(bad)), which is NOT a valid
    BaseSettings constructor kwarg — pydantic-settings would silently
    ignore it and load the real config/rubric.yaml from the repo.
    """
    from book_pipeline.config.rubric import RubricConfig

    (tmp_path / "config").mkdir()
    bad = tmp_path / "config" / "rubric.yaml"
    bad.write_text(
        "rubric_version: v1\n"
        "axes:\n"
        "  historical:\n"
        "    description: x\n"
        "    severity_thresholds:\n"
        "      low: 0.4\n"
        "      mid: 0.6\n"
        "      high: 0.8\n"
        "    weight: 1.0\n"
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as exc:
        RubricConfig()
    assert "axes" in str(exc.value)


def test_rubric_accepts_valid_5_axes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity counterpart — confirms monkeypatch.chdir actually loads the tmp
    file (not the real repo config) by making a valid 5-axis rubric at
    tmp_path and asserting it loads.
    """
    from book_pipeline.config.rubric import RubricConfig

    (tmp_path / "config").mkdir()
    good = tmp_path / "config" / "rubric.yaml"
    axis_block = (
        "    description: x\n"
        "    severity_thresholds:\n"
        "      low: 0.4\n"
        "      mid: 0.6\n"
        "      high: 0.8\n"
        "    weight: 1.0\n"
    )
    good.write_text(
        "rubric_version: v1\n"
        "axes:\n"
        f"  historical:\n{axis_block}"
        f"  metaphysics:\n{axis_block}"
        f"  entity:\n{axis_block}"
        f"  arc:\n{axis_block}"
        f"  donts:\n{axis_block}"
    )
    monkeypatch.chdir(tmp_path)
    cfg = RubricConfig()
    assert set(cfg.axes.keys()) == {"historical", "metaphysics", "entity", "arc", "donts"}


def test_rubric_real_config_has_5_axes() -> None:
    from book_pipeline.config.rubric import RubricConfig

    cfg = RubricConfig()
    assert set(cfg.axes.keys()) == {"historical", "metaphysics", "entity", "arc", "donts"}
    assert cfg.rubric_version == "v1"


# ---------------------------------------------------------------------------
# Test 4 — RagRetrieversConfig.retrievers has exactly the 5 required keys
# ---------------------------------------------------------------------------


def test_rag_retrievers_has_5_required_names() -> None:
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig

    cfg = RagRetrieversConfig()
    assert set(cfg.retrievers.keys()) == {
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
    }
    assert cfg.bundler.max_bytes == 40960


def test_rag_retrievers_rejects_wrong_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig

    (tmp_path / "config").mkdir()
    bad = tmp_path / "config" / "rag_retrievers.yaml"
    bad.write_text(
        "embeddings:\n"
        "  model: BAAI/bge-m3\n"
        "  model_revision: TBD\n"
        "  dim: 1024\n"
        "  device: cpu\n"
        "bundler:\n"
        "  max_bytes: 40960\n"
        "  assembly_strategy: round_robin\n"
        "  enforce_cap: true\n"
        "  emit_conflicts_to: drafts/retrieval_conflicts/\n"
        "retrievers:\n"
        "  only_one:\n"
        "    index_path: indexes/only_one/\n"
        "    source_files: []\n"
        "    chunk_strategy: paragraph\n"
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as exc:
        RagRetrieversConfig()
    assert "retrievers" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 5 — ModeThresholdsConfig.mode_a.regen_budget_R == 3
# ---------------------------------------------------------------------------


def test_mode_thresholds_regen_budget_is_3() -> None:
    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig

    cfg = ModeThresholdsConfig()
    assert cfg.mode_a.regen_budget_R == 3
    assert cfg.mode_b.prompt_cache_ttl == "1h"
    assert cfg.oscillation.enabled is True
    assert cfg.alerts.telegram_cool_down_seconds == 3600


# ---------------------------------------------------------------------------
# Test 6 — load_all_configs() returns the expected 5-key dict
# ---------------------------------------------------------------------------


def test_load_all_configs_returns_5_keys() -> None:
    from book_pipeline.config.loader import load_all_configs

    cfg = load_all_configs()
    assert set(cfg.keys()) == {
        "voice_pin",
        "rubric",
        "rag_retrievers",
        "mode_thresholds",
        "secrets",
    }


# ---------------------------------------------------------------------------
# Test 7 — Missing required field raises ValidationError mentioning the field
# ---------------------------------------------------------------------------


def test_missing_field_in_voice_pin_raises_with_field_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from book_pipeline.config.voice_pin import VoicePinConfig

    (tmp_path / "config").mkdir()
    bad = tmp_path / "config" / "voice_pin.yaml"
    # Missing 'base_model' field.
    bad.write_text(
        "voice_pin:\n"
        "  source_repo: paul-thinkpiece-pipeline\n"
        "  source_commit_sha: TBD\n"
        "  ft_run_id: v9\n"
        "  checkpoint_path: /tmp/foo\n"
        "  checkpoint_sha: TBD\n"
        # base_model intentionally missing
        "  trained_on_date: TBD\n"
        "  pinned_on_date: 2026-04-21\n"
        "  pinned_reason: test\n"
        "  vllm_serve_config:\n"
        "    port: 8002\n"
        "    max_model_len: 8192\n"
        "    dtype: bfloat16\n"
        "    tensor_parallel_size: 1\n"
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as exc:
        VoicePinConfig()
    assert "base_model" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 8 — Malformed YAML produces a clear error mentioning the file path
# ---------------------------------------------------------------------------


def test_malformed_yaml_raises_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from book_pipeline.config.rubric import RubricConfig

    (tmp_path / "config").mkdir()
    bad = tmp_path / "config" / "rubric.yaml"
    # Malformed YAML — unclosed bracket
    bad.write_text("rubric_version: v1\naxes: {historical:\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises((yaml.YAMLError, ValueError)):
        RubricConfig()


# ---------------------------------------------------------------------------
# Test 9 — SecretsConfig reads ANTHROPIC_API_KEY from env via alias
# ---------------------------------------------------------------------------


def test_secrets_reads_anthropic_key_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Isolate from any real .env in the repo so the env var is the source.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123")
    from book_pipeline.config.secrets import SecretsConfig

    s = SecretsConfig()
    assert s.is_anthropic_present() is True


# ---------------------------------------------------------------------------
# Test 10 — SecretsConfig never exposes the raw secret value via repr
# ---------------------------------------------------------------------------


def test_secrets_does_not_leak_value_in_repr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leaky-xyz")
    from book_pipeline.config.secrets import SecretsConfig

    s = SecretsConfig()
    assert s.is_anthropic_present() is True
    assert "sk-ant-leaky-xyz" not in repr(s)
    assert "sk-ant-leaky-xyz" not in str(s)


def test_secrets_absent_when_env_unset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    from book_pipeline.config.secrets import SecretsConfig

    s = SecretsConfig()
    assert s.is_anthropic_present() is False
    assert s.is_openclaw_present() is False
    assert s.is_telegram_present() is False
