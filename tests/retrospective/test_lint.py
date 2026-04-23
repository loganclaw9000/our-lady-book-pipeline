"""Tests for lint_retrospective (Plan 04-03 Task 2 — TEST-01 success criterion 5).

Rule 1: MUST contain >=1 match of r"\\bch\\d+_sc\\d+\\b" (scene_id citation).
Rule 2: MUST contain >=1 of: axis word (historical/metaphysics/entity/arc/donts),
        chunk_id (r"\\bchunk_[0-9a-f]+\\b"), OR evidence quote (r'"[^"]{20,}"').

Fail reason tags (lower-snake): missing_scene_id_citation, missing_critic_artifact.
"""
from __future__ import annotations

from book_pipeline.interfaces.types import Retrospective
from book_pipeline.retrospective.lint import lint_retrospective


def _retro(
    *,
    what_worked: str = "",
    what_didnt: str = "",
    pattern: str = "",
    candidate_theses: list[dict[str, object]] | None = None,
) -> Retrospective:
    return Retrospective(
        chapter_num=1,
        what_worked=what_worked,
        what_didnt=what_didnt,
        pattern=pattern,
        candidate_theses=candidate_theses or [],
    )


def test_lint_passes_with_scene_id_and_axis() -> None:
    retro = _retro(
        pattern="ch01_sc02 had historical drift midway.",
    )
    passed, reasons = lint_retrospective(retro)
    assert passed is True
    assert reasons == []


def test_lint_fails_missing_scene_id() -> None:
    retro = _retro(
        what_worked="Historical grounding was strong throughout.",
    )
    passed, reasons = lint_retrospective(retro)
    assert passed is False
    assert "missing_scene_id_citation" in reasons


def test_lint_fails_missing_critic_artifact() -> None:
    retro = _retro(
        what_worked="ch01_sc01 was generally OK, nothing to flag.",
    )
    passed, reasons = lint_retrospective(retro)
    assert passed is False
    assert "missing_critic_artifact" in reasons


def test_lint_passes_with_chunk_id_or_quote() -> None:
    # chunk_id citation counts as a critic artifact.
    retro_chunk = _retro(
        pattern="ch01_sc01 referenced chunk_abc1234 in its RAG pack.",
    )
    passed, reasons = lint_retrospective(retro_chunk)
    assert passed is True, reasons

    # Evidence quote of >=20 chars counts as a critic artifact.
    retro_quote = _retro(
        pattern='ch01_sc01 ended with "Malintzin translated the envoys word".',
    )
    passed2, reasons2 = lint_retrospective(retro_quote)
    assert passed2 is True, reasons2
