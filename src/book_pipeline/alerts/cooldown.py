"""CooldownCache — LRU + TTL + atomic JSON persistence (ALERT-02 / D-13).

Key shape: ``(condition: str, scope: str)`` → last-send epoch seconds (float).

Persistence path: ``runs/alert_cooldowns.json`` (gitignored). Survives
process restart — loaded at ``__init__``, persisted after every ``record()``.
Atomic tmp+rename so a crash mid-write never leaves a partial JSON file.

Threat mitigation (T-05-03-02 Tampering): single-user pipeline; a local
attacker with filesystem access to ``runs/`` already controls the repo. The
cooldown file is advisory state — tampering only extends an attacker's own
dedup window (local DoS, out of scope).
"""

from __future__ import annotations

import json
import os
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any


class CooldownCache:
    """In-memory LRU keyed on (condition, scope) with TTL + JSON persistence.

    Args:
        cooldown_path: target JSON file. Parent dir auto-created on write.
        ttl_s: time-to-live in seconds (default 3600 per ALERT-02).
        now_fn: test seam for deterministic time control.
    """

    def __init__(
        self,
        cooldown_path: Path | str,
        *,
        ttl_s: int = 3600,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self.cooldown_path = Path(cooldown_path)
        self.ttl_s = ttl_s
        self._now = now_fn
        self._data: OrderedDict[tuple[str, str], float] = self._load()

    def is_suppressed(self, condition: str, scope: str) -> bool:
        """Return True if (condition, scope) is within the TTL window."""
        last = self._data.get((condition, scope))
        if last is None:
            return False
        return (self._now() - last) < self.ttl_s

    def record(self, condition: str, scope: str) -> None:
        """Mark (condition, scope) as just-sent and persist to disk."""
        key = (condition, scope)
        self._data[key] = self._now()
        self._data.move_to_end(key)
        self._persist()

    # --- Internal -----------------------------------------------------------

    def _load(self) -> OrderedDict[tuple[str, str], float]:
        if not self.cooldown_path.exists():
            return OrderedDict()
        try:
            raw: dict[str, Any] = json.loads(self.cooldown_path.read_text())
        except (json.JSONDecodeError, OSError):
            # Corrupt file — start fresh; operator sees a re-fire on next
            # alert but never a hard failure at alerter __init__.
            return OrderedDict()
        now = self._now()
        out: OrderedDict[tuple[str, str], float] = OrderedDict()
        for entry in raw.get("entries", []):
            try:
                c = str(entry["condition"])
                s = str(entry["scope"])
                t = float(entry["ts"])
            except (KeyError, TypeError, ValueError):
                continue
            # Prune expired on load — no need to re-rehydrate stale keys.
            if (now - t) < self.ttl_s:
                out[(c, s)] = t
        return out

    def _persist(self) -> None:
        """Atomic write: serialize → tmp file → os.replace to final path."""
        self.cooldown_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cooldown_path.with_suffix(
            self.cooldown_path.suffix + ".tmp"
        )
        payload = {
            "entries": [
                {"condition": c, "scope": s, "ts": t}
                for (c, s), t in self._data.items()
            ]
        }
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(str(tmp), str(self.cooldown_path))


__all__ = ["CooldownCache"]
