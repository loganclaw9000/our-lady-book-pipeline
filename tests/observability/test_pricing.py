"""Tests for book_pipeline.observability.pricing + book_pipeline.config.pricing.

Plan 05-01 Task 1 — pricing kernel + PricingConfig loader.

Pitfall 5 drift detector: openclaw/cron_jobs.json carries outdated $15/$75 Opus
4.7 pricing. config/pricing.yaml ships the authoritative $5/$25 numbers;
test_pricing_yaml_loads hard-codes that 5.0 number as the canary.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from book_pipeline.interfaces.types import Event


def _opus_event(
    *,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    model: str = "claude-opus-4-7",
) -> Event:
    return Event(
        event_id="e" * 16,
        ts_iso="2026-04-23T00:00:00.000Z",
        role="drafter",
        model=model,
        prompt_hash="0" * 16,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
        latency_ms=100,
        caller_context={},
        output_hash="1" * 16,
        mode="B",
    )


def test_event_cost_usd_uncached_only() -> None:
    """Opus 4.7: 1000 input uncached + 500 output = (1000*5 + 500*25)/1e6 = 0.0175 USD."""
    from book_pipeline.config.pricing import PricingConfig
    from book_pipeline.observability.pricing import event_cost_usd

    event = _opus_event(input_tokens=1000, cached_tokens=0, output_tokens=500)
    pricing = PricingConfig().by_model
    cost = event_cost_usd(event, pricing)
    assert cost == pytest.approx(0.0175, rel=1e-6)


def test_event_cost_usd_with_cache_reads() -> None:
    """200 uncached + 3000 cached reads + 400 output =
    (200*5 + 3000*0.5 + 400*25)/1e6 = (1000 + 1500 + 10000)/1e6 = 0.0125 USD."""
    from book_pipeline.config.pricing import PricingConfig
    from book_pipeline.observability.pricing import event_cost_usd

    event = _opus_event(input_tokens=200, cached_tokens=3000, output_tokens=400)
    pricing = PricingConfig().by_model
    cost = event_cost_usd(event, pricing)
    assert cost == pytest.approx(0.0125, rel=1e-6)


def test_event_cost_usd_unknown_model() -> None:
    """Unknown model id → 0.0 (permissive; operator discovers miss via digest)."""
    from book_pipeline.config.pricing import PricingConfig
    from book_pipeline.observability.pricing import event_cost_usd

    event = _opus_event(
        input_tokens=1000, cached_tokens=0, output_tokens=500, model="gpt-5-turbo"
    )
    pricing = PricingConfig().by_model
    assert event_cost_usd(event, pricing) == 0.0


def test_ModelPricing_frozen_dataclass() -> None:
    """ModelPricing must be frozen dataclass — immutable rates per-process."""
    from book_pipeline.observability.pricing import ModelPricing

    assert dataclasses.is_dataclass(ModelPricing)
    assert ModelPricing.__dataclass_params__.frozen is True  # type: ignore[attr-defined]


def test_pricing_yaml_loads() -> None:
    """Pitfall 5 drift canary: config/pricing.yaml ships authoritative $5/$25
    for claude-opus-4-7. If this test fails, somebody propagated the outdated
    $15/$75 numbers from openclaw/cron_jobs.json."""
    from book_pipeline.config.pricing import PricingConfig

    cfg = PricingConfig()
    opus = cfg.by_model["claude-opus-4-7"]
    assert opus.input_usd_per_mtok == 5.0, (
        "Opus 4.7 input price must be $5/MTok. $15/MTok is the outdated "
        "openclaw/cron_jobs.json value — see Pitfall 5."
    )
    assert opus.output_usd_per_mtok == 25.0
    assert opus.cache_read_usd_per_mtok == 0.5
    # Sonnet sanity
    sonnet = cfg.by_model["claude-sonnet-4-6"]
    assert sonnet.input_usd_per_mtok == 3.0
    assert sonnet.output_usd_per_mtok == 15.0


def test_pricing_yaml_rejects_negative_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pydantic field_validator rejects negative USD rates at load time."""
    from pydantic import ValidationError

    bad_yaml = tmp_path / "pricing.yaml"
    bad_yaml.write_text(
        """
by_model:
  claude-opus-4-7:
    input_usd_per_mtok: -1.0
    output_usd_per_mtok: 25.0
    cache_read_usd_per_mtok: 0.5
    cache_write_1h_usd_per_mtok: 10.0
    cache_write_5m_usd_per_mtok: 6.25
""",
        encoding="utf-8",
    )
    # chdir so the YamlConfigSettingsSource default path "config/pricing.yaml"
    # resolves to our fixture via os.chdir → symlink trick: instead, load the
    # module and assert ValidationError by pointing Pydantic to the file.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "pricing.yaml").write_text(
        bad_yaml.read_text(encoding="utf-8"), encoding="utf-8"
    )

    from book_pipeline.config.pricing import PricingConfig

    with pytest.raises(ValidationError):
        PricingConfig()


def test_preflag_yaml_loads() -> None:
    """config/mode_preflags.yaml ships with >=3 seed beats per D-04."""
    from book_pipeline.config.mode_preflags import PreflagConfig

    cfg = PreflagConfig()
    assert len(cfg.preflagged_beats) >= 3


def test_voice_samples_yaml_loads() -> None:
    """config/voice_samples.yaml is loadable via VoiceSamplesConfig.

    Task 1 ships placeholders; curate CLI in Task 3 replaces them. The loader
    must accept an empty passages list (validation of non-empty happens in
    ModeBDrafter.__init__, not in the config shape)."""
    from book_pipeline.config.voice_samples import VoiceSamplesConfig

    cfg = VoiceSamplesConfig()
    # passages is a list — may be empty (Task 1 placeholders) or populated
    # (after Task 3 runs).
    assert isinstance(cfg.passages, list)
