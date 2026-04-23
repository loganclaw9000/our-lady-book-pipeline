"""Retrospective output lint (Plan 04-03 Task 2 — TEST-01 success criterion 5).

Rules:
  1. The combined text of what_worked + what_didnt + pattern + candidate_theses
     descriptions MUST contain >=1 scene_id citation (regex ``\\bch\\d+_sc\\d+\\b``).
     Fail reason: ``missing_scene_id_citation``.
  2. Combined text MUST contain >=1 critic-issue artifact:
       (a) axis word (bounded: historical, metaphysics, entity, arc, donts), OR
       (b) chunk_id (``\\bchunk_[0-9a-f]+\\b``), OR
       (c) evidence quote (``"[^"]{20,}"``).
     Fail reason: ``missing_critic_artifact``.

Implementation note: this module is kernel-clean — no book-domain imports,
no LLM calls, no disk I/O. Pure function against a Retrospective instance.
"""
from __future__ import annotations

import re

from book_pipeline.interfaces.types import Retrospective

_SCENE_ID_RE = re.compile(r"\bch\d+_sc\d+\b")
_CHUNK_ID_RE = re.compile(r"\bchunk_[0-9a-f]+\b")
_EVIDENCE_QUOTE_RE = re.compile(r'"[^"]{20,}"')
_AXIS_WORDS_RE = re.compile(
    r"\b(historical|metaphysics|entity|arc|donts)\b",
    re.IGNORECASE,
)


def lint_retrospective(retro: Retrospective) -> tuple[bool, list[str]]:
    """Return (pass, reasons). reasons is [] on pass."""
    theses_text = " ".join(
        str(t.get("description", "")) for t in retro.candidate_theses
    )
    combined = " ".join(
        [
            retro.what_worked or "",
            retro.what_didnt or "",
            retro.pattern or "",
            theses_text,
        ]
    )
    reasons: list[str] = []
    if not _SCENE_ID_RE.search(combined):
        reasons.append("missing_scene_id_citation")
    has_axis = bool(_AXIS_WORDS_RE.search(combined))
    has_chunk = bool(_CHUNK_ID_RE.search(combined))
    has_quote = bool(_EVIDENCE_QUOTE_RE.search(combined))
    if not (has_axis or has_chunk or has_quote):
        reasons.append("missing_critic_artifact")
    return (not reasons, reasons)


__all__ = ["lint_retrospective"]
