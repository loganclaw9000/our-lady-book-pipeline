"""Alerts kernel package (Phase 5 Plan 03).

ADR-004 clean boundary — book-domain-free. Imports from
``book_pipeline.book_specifics`` are prohibited by import-linter contract 1;
imports into ``book_pipeline.interfaces`` are prohibited by contract 2.

Single-file modules per ADR-004 ("single file unless proven otherwise"):

- ``taxonomy.py`` — ``HARD_BLOCK_CONDITIONS`` frozenset (D-12) +
  ``MESSAGE_TEMPLATES`` dict + ``ALLOWED_DETAIL_KEYS`` whitelist.
- ``cooldown.py`` — ``CooldownCache`` class (LRU + TTL + atomic JSON
  persistence) for ALERT-02 dedup.
- ``telegram.py`` — ``TelegramAlerter`` class posting to the Telegram Bot API
  via httpx, with tenacity 429-aware retry (added in Task 2).
"""

from book_pipeline.alerts.cooldown import CooldownCache
from book_pipeline.alerts.taxonomy import (
    ALLOWED_DETAIL_KEYS,
    HARD_BLOCK_CONDITIONS,
    MESSAGE_TEMPLATES,
)

__all__ = [
    "ALLOWED_DETAIL_KEYS",
    "HARD_BLOCK_CONDITIONS",
    "MESSAGE_TEMPLATES",
    "CooldownCache",
]
