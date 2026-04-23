"""Surgical scene-kick helpers for CHAPTER_FAIL routing (LOOP-04 / Phase 4 SC4).

Plan 05-02 Task 2. When a ChapterCritic fails with issues citing specific
``ch{NN}_sc{II}`` scenes, the DAG's step 1 does NOT terminate at CHAPTER_FAIL —
it routes through this module to reset ONLY the implicated scenes and preserve
the rest of the committed chapter buffer.

Two pure-ish helpers:

- ``extract_implicated_scene_ids(response)`` — parses CriticIssue.location (and
  evidence as defensive fallback) for ``ch(\\d+)_sc(\\d+)`` refs, canonicalizes
  to ``ch{NN:02d}_sc{II:02d}``. Widened vs ``cli/draft.py::_SCENE_ID_RE``
  (which is anchored) because ``CriticIssue.location`` is free-text with
  embedded refs.

- ``kick_implicated_scenes(...)`` — archives the scene markdown to
  ``drafts/ch{NN}/archive/{scene_id}_rev{K:02d}.md`` (A8 decision), resets the
  SceneStateRecord to PENDING via
  ``book_pipeline.interfaces.scene_state_machine.transition``, emits exactly
  ONE ``role='scene_kick'`` Event per invocation.

Threat mitigations (per plan <threat_model>):
- T-05-02-01 (regex injection): numeric-only match-space + int-cast + canonical
  re-format blocks path traversal via malicious location strings.
- T-05-02-03 (atomicity): atomic tmp+rename (Plan 03-07 _persist pattern);
  archive happens BEFORE state reset so partial-kick recovery is possible.
"""
from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.scene_state_machine import transition
from book_pipeline.interfaces.types import (
    CriticResponse,
    Event,
    SceneState,
    SceneStateRecord,
)
from book_pipeline.observability.hashing import event_id, hash_text

# Widened vs cli/draft.py::_SCENE_ID_RE (which is ^ch(\d+)_sc(\d+)$) because
# CriticIssue.location is free-text with embedded refs.
_SCENE_REF_RE = re.compile(r"\bch(\d+)_sc(\d+)\b")

# Matches files like "ch99_sc02_rev07.md" — extract the rev integer.
_REV_SUFFIX_RE = re.compile(r"_rev(\d+)\.md$")


def extract_implicated_scene_ids(
    response: CriticResponse,
) -> tuple[set[str], list[str]]:
    """Return ``(implicated_scene_ids, non_specific_claims)``.

    ``implicated_scene_ids`` is a set of canonical ``ch{NN:02d}_sc{II:02d}``
    strings (zero-padded — defensive int-cast + re-format matches Plan 03-07
    ``_parse_scene_id`` + Plan 04-04 path sanitization precedent).

    ``non_specific_claims`` is the list of ``issue.claim`` strings for issues
    that cite no scene reference in either ``location`` OR ``evidence``.
    """
    implicated: set[str] = set()
    non_specific: list[str] = []
    for issue in response.issues:
        matches = _SCENE_REF_RE.findall(issue.location or "")
        if not matches and issue.evidence:
            # Defensive fallback: some critics cite ch/sc only in evidence.
            matches = _SCENE_REF_RE.findall(issue.evidence)
        if matches:
            for ch_str, sc_str in matches:
                ch, sc = int(ch_str), int(sc_str)
                implicated.add(f"ch{ch:02d}_sc{sc:02d}")
        else:
            non_specific.append(issue.claim)
    return implicated, non_specific


def _next_archive_rev(archive_dir: Path, scene_id: str) -> int:
    """Find the next available rev-integer in archive/{scene_id}_rev{K:02d}.md."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    existing = list(archive_dir.glob(f"{scene_id}_rev*.md"))
    if not existing:
        return 1
    revs: list[int] = []
    for p in existing:
        m = _REV_SUFFIX_RE.search(p.name)
        if m is not None:
            revs.append(int(m.group(1)))
    return (max(revs) + 1) if revs else 1


def _persist_scene_state(record: SceneStateRecord, state_path: Path) -> None:
    """Atomic tmp+rename write — reuse Plan 03-07 _persist pattern."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    tmp_path.replace(state_path)


def _now_iso() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _emit_scene_kick_event(
    event_logger: EventLogger,
    *,
    kicked_scenes: list[str],
    chapter_num: int,
    issue_refs: list[str],
) -> None:
    """Emit exactly one role='scene_kick' Event per invocation."""
    ts_iso = _now_iso()
    caller = f"chapter_assembler.scene_kick:ch{chapter_num:02d}"
    prompt_h = hash_text(f"scene_kick:ch{chapter_num}:{','.join(kicked_scenes)}")
    eid = event_id(ts_iso, "scene_kick", caller, prompt_h)
    caller_context: dict[str, Any] = {
        "module": "chapter_assembler.scene_kick",
        "function": "kick_implicated_scenes",
        "chapter_num": chapter_num,
    }
    extra: dict[str, Any] = {
        "kicked_scenes": list(kicked_scenes),
        "chapter_num": chapter_num,
        "issue_refs": list(issue_refs),
    }
    event = Event(
        event_id=eid,
        ts_iso=ts_iso,
        role="scene_kick",
        model="n/a",
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        latency_ms=0,
        caller_context=caller_context,
        output_hash=hash_text("scene_kick"),
        extra=extra,
    )
    event_logger.emit(event)


def kick_implicated_scenes(
    implicated: set[str],
    state_dir: Path,
    drafts_dir: Path,
    event_logger: EventLogger | None,
    chapter_num: int,
    issue_refs: list[str],
) -> None:
    """Reset implicated scenes to PENDING; archive their md; emit one Event.

    Args:
        implicated: canonical scene_ids to reset.
        state_dir: root of scene state records (e.g. ``drafts/scene_buffer/``).
        drafts_dir: root of scene markdown buffer (e.g. ``drafts/``).
        event_logger: may be None; tests use fakes or pass None.
        chapter_num: authoritative chapter number (defensive int-cast).
        issue_refs: list of issue identifiers for the Event trail (axis:severity
            or free-text descriptors; not semantically load-bearing).
    """
    ch = int(chapter_num)
    kicked_actual: list[str] = []
    ch_drafts = drafts_dir / f"ch{ch:02d}"

    for scene_id in sorted(implicated):
        state_path = state_dir / f"ch{ch:02d}" / f"{scene_id}.state.json"
        if not state_path.exists():
            # Scene not in buffer; nothing to kick. (Defensive — happens if
            # the critic cites a scene id that never committed.)
            continue
        record = SceneStateRecord.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
        # Archive markdown FIRST (Pitfall 7 mitigation — preserve recovery
        # artifact before mutating state).
        md_path = ch_drafts / f"{scene_id}.md"
        if md_path.exists():
            archive_dir = ch_drafts / "archive"
            rev = _next_archive_rev(archive_dir, scene_id)
            shutil.move(
                str(md_path),
                str(archive_dir / f"{scene_id}_rev{rev:02d}.md"),
            )
        # Reset state record to PENDING via pure transition() helper.
        record = transition(
            record,
            SceneState.PENDING,
            f"scene_kick from ch{ch}_fail",
        )
        _persist_scene_state(record, state_path)
        kicked_actual.append(scene_id)

    if event_logger is not None and kicked_actual:
        _emit_scene_kick_event(
            event_logger,
            kicked_scenes=kicked_actual,
            chapter_num=ch,
            issue_refs=issue_refs,
        )


__all__ = [
    "extract_implicated_scene_ids",
    "kick_implicated_scenes",
]
