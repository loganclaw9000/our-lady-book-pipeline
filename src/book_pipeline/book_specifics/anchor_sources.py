"""Book-domain pointers into external corpora for OBS-03 anchor curation.

This module declares WHERE the anchor candidates live on disk (paul-thinkpiece-
pipeline training rows + held-out blog posts) and the heuristics that turn
each row into a sub-genre-tagged anchor. Kernel never imports this — the CLI
composition seam at src/book_pipeline/cli/curate_anchors.py is the ONE
sanctioned bridge (pyproject.toml ignore_imports).

Environment-variable overrides (for tests + alternate-path experimentation):
  OBS_CURATE_ANCHORS_THINKPIECE_PATH — override the thinkpiece jsonl path.
  OBS_CURATE_ANCHORS_BLOG_PATH       — override the held-out blog jsonl path.

Heuristic classifier (_classify_sub_genre) tags each candidate row as essay,
analytic, or narrative per PITFALLS V-1 two-tier policy:
  - essay:     writing/craft/reading/meta-author markers win first.
  - analytic:  dataset/benchmark/token/model/evaluation/score markers win next.
  - narrative: dialogue quote + motion verb wins last.
  - anchors with no match are classified essay by default (Paul's default register).

Selection filter (_select_thinkpiece_rows):
  - Row's gpt turn text is the candidate passage.
  - Word count ∈ [150, 400].
  - Contains ≥1 em-dash OR ≥1 numeric specificity (\\b\\d+[%$]|\\b\\d{2,}\\b).
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Literal, TypedDict

SubGenre = Literal["essay", "analytic", "narrative"]

_DEFAULT_THINKPIECE_PATH = Path(
    "/home/admin/paul-thinkpiece-pipeline/v3_data/train_filtered.jsonl"
)
_DEFAULT_BLOG_PATH = Path(
    "/home/admin/paul-thinkpiece-pipeline/v3_data/heldout_blogs.jsonl"
)

_ESSAY_KEYWORDS = (
    " writing",
    " craft",
    " reading",
    " what i ",
    " why i ",
    " how i ",
)
_ANALYTIC_KEYWORDS = (
    # Plan 03-02 original keyword set (narrow — too few hits on real corpus).
    "dataset",
    "benchmark",
    "token",
    " model ",
    "evaluation",
    " score",
    # Rule 2 extension: Paul's thinkpiece corpus is analytical more often than
    # it uses ML-jargon. Adding terms common to his tech-culture analysis lets
    # the quota check actually succeed against v3_data/train_filtered.jsonl
    # (pre-extension: 191 essay / 5 analytic / 22 narrative; insufficient for
    # V-1 minimum analytic>=6). These markers are deliberately broad but still
    # signal "analytic register" — structural analysis, system critique,
    # pattern-matching prose. Narrative-classifier runs AFTER essay so these
    # don't clobber essay-first-match-wins for passages carrying both.
    " metric",
    " metrics",
    " data ",
    " analysis",
    " system",
    " systems",
    " measure",
    " pattern",
    " signal",
    " framework",
    " tradeoff",
    " trade-off",
    " infrastructure",
    " protocol",
    " api",
    " algorithm",
)
_NARRATIVE_MOTION = (
    " she ",
    " he said",
    " walked",
    " turned",
    " looked",
)
_NUMERIC_RE = re.compile(r"\b\d+[%$]|\b\d{2,}\b")


class AnchorCandidateSource(TypedDict):
    """Pointer to a candidate corpus + metadata for curate_anchors."""

    source_label: str
    path: Path
    row_key: str  # how to extract text from each row
    selection: str  # 'heuristic_v1' | 'all'


def _resolve_thinkpiece_path() -> Path:
    override = os.environ.get("OBS_CURATE_ANCHORS_THINKPIECE_PATH")
    return Path(override) if override else _DEFAULT_THINKPIECE_PATH


def _resolve_blog_path() -> Path:
    override = os.environ.get("OBS_CURATE_ANCHORS_BLOG_PATH")
    return Path(override) if override else _DEFAULT_BLOG_PATH


def anchor_candidates() -> list[AnchorCandidateSource]:
    """Return the fresh (env-aware) list of candidate sources.

    Called at CLI start; env-var overrides take effect per-call rather than
    being snapshotted at import time (important for tests that set env via
    monkeypatch AFTER the module is imported).
    """
    return [
        AnchorCandidateSource(
            source_label="thinkpiece_v3",
            path=_resolve_thinkpiece_path(),
            row_key="conversations[-1].value",
            selection="heuristic_v1",
        ),
        AnchorCandidateSource(
            source_label="blog_heldout",
            path=_resolve_blog_path(),
            row_key="text",
            selection="all",
        ),
    ]


# Backwards-compat constant (referenced by plan acceptance criteria). The
# function above is the actual source of truth for tests; this constant
# evaluates at import time using whatever env is live at that point.
ANCHOR_CANDIDATES: list[AnchorCandidateSource] = anchor_candidates()


def _classify_sub_genre(text: str) -> SubGenre:
    """Classify a candidate passage into essay / analytic / narrative.

    First-match-wins across the three keyword sets. "Essay" is the default
    register (Paul's prose leans essayistic), so an unclassified passage
    falls into essay.
    """
    lowered = " " + text.lower() + " "

    for kw in _ESSAY_KEYWORDS:
        if kw in lowered:
            return "essay"
    for kw in _ANALYTIC_KEYWORDS:
        if kw in lowered:
            return "analytic"
    # Narrative requires BOTH a dialogue quote AND a motion marker.
    has_dialogue = ('"' in text) or ("“" in text) or ("”" in text)
    if has_dialogue:
        for marker in _NARRATIVE_MOTION:
            if marker in lowered:
                return "narrative"
    return "essay"


def _passes_voice_markers(text: str) -> bool:
    """Return True iff the text has ≥1 em-dash OR ≥1 numeric specificity marker."""
    if "—" in text or " -- " in text:
        return True
    return bool(_NUMERIC_RE.search(text))


def _word_count(text: str) -> int:
    return len(text.split())


def _extract_gpt_turn(row: dict[str, Any]) -> str | None:
    """Pull the gpt turn's value from an OpenAI-style conversations row.

    Returns None if the shape is unexpected (unknown rows silently skipped).
    """
    convs = row.get("conversations")
    if not isinstance(convs, list):
        return None
    for turn in reversed(convs):
        if isinstance(turn, dict) and turn.get("from") == "gpt":
            val = turn.get("value")
            if isinstance(val, str):
                return val
    return None


class CandidateRow(TypedDict):
    """One curated row passing the heuristic filter."""

    text: str
    sub_genre: SubGenre
    source_file: str
    source_line: int  # 1-indexed line number in the source jsonl
    row_json_bytes: bytes  # for provenance_sha


def _select_thinkpiece_rows(
    jsonl_path: Path, *, limit: int
) -> Iterator[CandidateRow]:
    """Yield up to `limit` candidate rows passing voice-marker + length filters.

    Rows are returned in source-order (stable w.r.t. the jsonl file), which
    gives the CLI a deterministic quality-proxy sort.
    """
    if not jsonl_path.is_file():
        return
    with jsonl_path.open("rb") as fh:
        line_no = 0
        yielded = 0
        for raw in fh:
            line_no += 1
            if yielded >= limit:
                break
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            gpt_text = _extract_gpt_turn(row)
            if gpt_text is None:
                continue
            wc = _word_count(gpt_text)
            if wc < 150 or wc > 400:
                continue
            if not _passes_voice_markers(gpt_text):
                continue
            sub_genre = _classify_sub_genre(gpt_text)
            yield CandidateRow(
                text=gpt_text,
                sub_genre=sub_genre,
                source_file=str(jsonl_path),
                source_line=line_no,
                row_json_bytes=raw,
            )
            yielded += 1


def _select_blog_rows(jsonl_path: Path, *, limit: int) -> Iterator[CandidateRow]:
    """Yield up to `limit` blog rows, applying the same word-count + voice filter.

    Blog rows have shape `{"text": <str>}`. Missing path → silent empty yield;
    the CLI wraps this to print a non-fatal warning.
    """
    if not jsonl_path.is_file():
        return
    with jsonl_path.open("rb") as fh:
        line_no = 0
        yielded = 0
        for raw in fh:
            line_no += 1
            if yielded >= limit:
                break
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            text = row.get("text") if isinstance(row, dict) else None
            if not isinstance(text, str):
                continue
            wc = _word_count(text)
            if wc < 150 or wc > 400:
                continue
            if not _passes_voice_markers(text):
                continue
            sub_genre = _classify_sub_genre(text)
            yield CandidateRow(
                text=text,
                sub_genre=sub_genre,
                source_file=str(jsonl_path),
                source_line=line_no,
                row_json_bytes=raw,
            )
            yielded += 1


def select_rows_from_candidate(
    candidate: AnchorCandidateSource, *, limit: int
) -> Iterable[CandidateRow]:
    """Dispatch by candidate.source_label to the right selector."""
    if candidate["source_label"] == "thinkpiece_v3":
        return list(_select_thinkpiece_rows(candidate["path"], limit=limit))
    if candidate["source_label"] == "blog_heldout":
        return list(_select_blog_rows(candidate["path"], limit=limit))
    return []


__all__ = [
    "ANCHOR_CANDIDATES",
    "AnchorCandidateSource",
    "CandidateRow",
    "SubGenre",
    "_classify_sub_genre",
    "_passes_voice_markers",
    "_select_blog_rows",
    "_select_thinkpiece_rows",
    "anchor_candidates",
    "select_rows_from_candidate",
]
