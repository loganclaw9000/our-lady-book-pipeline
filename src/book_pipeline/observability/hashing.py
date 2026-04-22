"""Hashing helpers — xxhash64 (non-cryptographic, dedup-grade).

STACK.md rationale: xxhash is faster than SHA256 for prompt/output fingerprints.
ADR-003 requires dedup-grade fingerprinting, not crypto. Do NOT use these
helpers for security-sensitive integrity checks.
"""

from __future__ import annotations

import xxhash


def hash_text(s: str) -> str:
    """Return hex xxh64 digest of s (UTF-8 encoded). Stable across processes."""
    return xxhash.xxh64(s.encode("utf-8")).hexdigest()


def event_id(ts_iso: str, role: str, caller: str, prompt_hash: str) -> str:
    """Deterministic per-event id: xxh64 over (ts|role|caller|prompt_hash)."""
    return xxhash.xxh64(f"{ts_iso}|{role}|{caller}|{prompt_hash}".encode()).hexdigest()
