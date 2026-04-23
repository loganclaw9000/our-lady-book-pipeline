"""Pricing kernel — token → USD conversion (Plan 05-01 D-17).

Pure, dependency-free cost math. ``ModelPricing`` is a frozen dataclass so
rates are immutable per-process (a concurrent hot-swap of rates mid-run would
invalidate spend-cap accounting — avoid that class of bug by construction).

``event_cost_usd(event, pricing_by_model)`` converts one OBS-01 Event's token
counts to USD. Unknown model_id returns 0.0 (permissive — operator catches
the miss via the weekly digest rather than crashing a nightly run).

Caveat per RESEARCH.md Pattern 3: cache-write tokens are billed at the write
rate (2x input for 1h, 1.25x input for 5m) but the Phase 1 Event schema
(frozen) does not distinguish writes from uncached inputs. Cache writes are
thus counted at the uncached-input rate -- a slight underestimate on cold-
cache calls, mean-reverting over many calls. Phase 6 OBS-04 may add an
optional ``cache_creation_input_tokens`` field.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from book_pipeline.interfaces.types import Event


@dataclass(frozen=True)
class ModelPricing:
    """USD per 1_000_000 tokens for one model. Source: config/pricing.yaml.

    Opus 4.7 reference values (verified 2026-04-23):
      input_usd_per_mtok         = 5.0
      output_usd_per_mtok        = 25.0
      cache_read_usd_per_mtok    = 0.5  (10% of input)
      cache_write_1h_usd_per_mtok = 10.0 (2x input)
      cache_write_5m_usd_per_mtok = 6.25 (1.25x input)
    """

    input_usd_per_mtok: float
    output_usd_per_mtok: float
    cache_read_usd_per_mtok: float
    cache_write_1h_usd_per_mtok: float
    cache_write_5m_usd_per_mtok: float


def event_cost_usd(
    event: Event,
    pricing_by_model: Mapping[str, ModelPricing],
) -> float:
    """Convert one Event's token counts into USD. 0.0 if model unknown.

    Args:
        event: OBS-01 Event with input_tokens (uncached), cached_tokens
            (cache reads), output_tokens populated.
        pricing_by_model: model_id → ModelPricing lookup (typically
            ``PricingConfig().by_model``).

    Returns:
        USD cost as float. Returns 0.0 if event.model not in the table.
    """
    pricing = pricing_by_model.get(event.model)
    if pricing is None:
        return 0.0
    uncached_input = event.input_tokens
    cached_reads = event.cached_tokens
    output = event.output_tokens
    return (
        uncached_input * pricing.input_usd_per_mtok
        + cached_reads * pricing.cache_read_usd_per_mtok
        + output * pricing.output_usd_per_mtok
    ) / 1_000_000.0


__all__ = ["ModelPricing", "event_cost_usd"]
