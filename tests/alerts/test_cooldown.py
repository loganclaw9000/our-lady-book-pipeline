"""Tests for book_pipeline.alerts.cooldown.CooldownCache (Plan 05-03 Task 1).

Behavior (D-13):
  - Key = (condition, scope); TTL = 1h default.
  - `is_suppressed` returns True within TTL; False once expired.
  - Persistence via atomic tmp+rename to runs/alert_cooldowns.json; survives
    process restart.
  - Atomic write: on mid-write interrupt, target file stays either fully-old
    or fully-new — never partial.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path


def test_cooldown_dedup_within_ttl(tmp_path: Path) -> None:
    from book_pipeline.alerts.cooldown import CooldownCache

    cc = CooldownCache(tmp_path / "alert_cooldowns.json", ttl_s=3600)
    assert cc.is_suppressed("spend_cap_exceeded", "ch01_sc02") is False
    cc.record("spend_cap_exceeded", "ch01_sc02")
    assert cc.is_suppressed("spend_cap_exceeded", "ch01_sc02") is True
    # Different scope is NOT suppressed.
    assert cc.is_suppressed("spend_cap_exceeded", "ch02_sc01") is False
    # Different condition is NOT suppressed.
    assert cc.is_suppressed("rubric_conflict", "ch01_sc02") is False


def test_cooldown_expires_after_ttl(tmp_path: Path) -> None:
    from book_pipeline.alerts.cooldown import CooldownCache

    clock = {"t": 1_000_000.0}
    now_fn = lambda: clock["t"]  # noqa: E731

    cc = CooldownCache(tmp_path / "alert_cooldowns.json", ttl_s=3600, now_fn=now_fn)
    cc.record("spend_cap_exceeded", "ch01_sc02")
    # Within TTL: suppressed.
    clock["t"] += 3599.0
    assert cc.is_suppressed("spend_cap_exceeded", "ch01_sc02") is True
    # Past TTL: not suppressed.
    clock["t"] += 2.0  # 3601s elapsed
    assert cc.is_suppressed("spend_cap_exceeded", "ch01_sc02") is False


def test_cooldown_persistence_across_instances(tmp_path: Path) -> None:
    from book_pipeline.alerts.cooldown import CooldownCache

    path = tmp_path / "alert_cooldowns.json"
    a = CooldownCache(path, ttl_s=3600)
    a.record("spend_cap_exceeded", "ch01_sc02")
    # File exists on disk.
    assert path.exists()
    # Instance B starts fresh from same path.
    b = CooldownCache(path, ttl_s=3600)
    assert b.is_suppressed("spend_cap_exceeded", "ch01_sc02") is True


def test_cooldown_atomic_write(tmp_path: Path, monkeypatch) -> None:
    """Atomic tmp+rename: a failed rename mid-persist does NOT corrupt the
    target file. The worst-case is the tmp file left behind; the target JSON
    is either fully-old or fully-new (never partial)."""
    from book_pipeline.alerts import cooldown as cooldown_mod
    from book_pipeline.alerts.cooldown import CooldownCache

    path = tmp_path / "alert_cooldowns.json"
    cc = CooldownCache(path, ttl_s=3600)
    cc.record("spend_cap_exceeded", "ch01_sc02")
    before = path.read_text()

    # Simulate a rename failure mid-way. The pre-existing target must be
    # unchanged (still the fully-old JSON).
    def _boom_replace(*_args, **_kwargs):
        raise OSError("simulated disk error during rename")

    monkeypatch.setattr(cooldown_mod.os, "replace", _boom_replace)
    with contextlib.suppress(OSError):
        cc.record("rubric_conflict", "ch02_sc03")
    after = path.read_text()
    # Target file unchanged — atomic tmp+rename held the invariant.
    assert json.loads(after) == json.loads(before)
