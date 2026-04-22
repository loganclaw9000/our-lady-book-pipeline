"""CRIT-04 audit log — per-invocation disk record of every SceneCritic call.

Every critic invocation (success OR tenacity-exhaustion failure, W-7) writes
one JSON file to ``runs/critic_audit/{scene_id}_{attempt:02d}_{timestamp}.json``
so Phase 6 OBS-02 ingester can reconstruct per-axis score trends keyed by
rubric_version.

Writes are atomic (tmp + os.replace); the audit dir is created on demand.

The ``AuditRecord`` Pydantic model mirrors the record shape for type-safety
on the caller side, but we do NOT serialize through it — ``raw_anthropic_response``
is a generic dict that may carry extra SDK fields, so we json.dumps a plain
dict built by the caller to avoid Pydantic's schema squeeze.

This module lives in the kernel. It MUST NOT carry project-specific logic.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

_TIMESTAMP_FMT = "%Y%m%dT%H%M%S%f"


class AuditRecord(BaseModel):
    """Type contract for CRIT-04 audit record shape.

    Caller typically builds a plain dict and passes it to ``write_audit_record``;
    ``AuditRecord`` is provided for callers that want a typed handle (e.g. the
    Plan 03-06 scene-loop orchestrator re-reading the file for retry decisions).

    Note that ``raw_anthropic_response`` and ``parsed_critic_response`` are
    ``dict | None`` (not strict schemas) so the raw SDK payload and the failure-
    path ``None`` both fit.
    """

    model_config = ConfigDict(extra="allow")

    event_id: str
    scene_id: str
    attempt_number: int
    timestamp_iso: str
    rubric_version: str
    model_id: str
    opus_model_id_response: str | None
    caching_cache_control_applied: bool
    cached_input_tokens: int
    system_prompt_sha: str
    user_prompt_sha: str
    context_pack_fingerprint: str | None
    raw_anthropic_response: dict[str, Any] | None
    parsed_critic_response: dict[str, Any] | None


def write_audit_record(
    audit_dir: Path,
    scene_id: str,
    attempt: int,
    record: dict[str, Any],
) -> Path:
    """Atomically write ``record`` to ``audit_dir/{scene_id}_{attempt:02d}_{ts}.json``.

    Args:
        audit_dir: Directory to write into. Created (with parents) if missing.
        scene_id: "chXX_scYY" identifier; becomes the filename prefix.
        attempt: 1-based attempt number; zero-padded to 2 digits in the filename.
        record: Plain dict. Serialized via ``json.dumps(..., indent=2, ensure_ascii=False)``.

    Returns:
        The final Path that was written (not the tmp file).

    Atomicity:
        Writes to ``{path}.tmp`` first, then ``os.replace(tmp, path)``. Callers
        that crash mid-write leave a stray ``.tmp`` file; never a half-written
        final file.
    """
    audit_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime(_TIMESTAMP_FMT)
    path = audit_dir / f"{scene_id}_{attempt:02d}_{ts}.json"
    tmp_path = path.with_suffix(".json.tmp")

    serialized = json.dumps(record, indent=2, ensure_ascii=False)
    tmp_path.write_text(serialized, encoding="utf-8")
    os.replace(tmp_path, path)
    return path


__all__ = ["AuditRecord", "write_audit_record"]
