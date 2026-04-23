"""Tests for ConcatAssembler (Plan 04-02 Task 1).

Covers 6 tests per plan <behavior>:
  1 — Protocol conformance (isinstance(ConcatAssembler(), ChapterAssembler)).
  2 — 3-scene happy path: chapter frontmatter + HTML comment markers + section separators.
  3 — Deterministic re-run: two calls on identical inputs → byte-identical output.
  4 — Dedup voice_pin_shas preserving order (mid-chapter pin upgrade flag).
  5 — Single-scene chapter: one HTML marker, zero separators, valid frontmatter.
  6 — from_committed_scenes: parses scene md frontmatter, sorts by scene_index, assembles.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from book_pipeline.interfaces.chapter_assembler import ChapterAssembler
from book_pipeline.interfaces.types import DraftResponse


def _make_draft(
    *,
    scene_text: str,
    voice_pin_sha: str = "shaX",
    voice_fidelity_score: float | None = 0.85,
    attempt_number: int = 1,
) -> DraftResponse:
    """Build a DraftResponse with a test-injected voice_fidelity_score attr.

    DraftResponse is Pydantic v2; extra attrs don't stick via construction,
    so we set the sibling attribute on the instance after build. The assembler
    reads it via getattr(d, 'voice_fidelity_score', None).
    """
    d = DraftResponse(
        scene_text=scene_text,
        mode="A",
        model_id="paul-voice",
        voice_pin_sha=voice_pin_sha,
        tokens_in=0,
        tokens_out=0,
        latency_ms=0,
        output_sha="shaout",
        attempt_number=attempt_number,
    )
    # Pydantic v2 defaults are strict; use object.__setattr__ to attach the
    # optional sibling attribute (getattr(d, 'voice_fidelity_score', None)).
    object.__setattr__(d, "voice_fidelity_score", voice_fidelity_score)
    return d


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a `---\\n<yaml>---\\n<body>` document into (frontmatter, body)."""
    assert text.startswith("---\n"), f"expected leading `---\\n`, got: {text[:50]!r}"
    _, rest = text.split("---\n", 1)
    yaml_block, body = rest.split("\n---\n", 1)
    fm: dict[str, Any] = yaml.safe_load(yaml_block)
    return fm, body


def test_concat_satisfies_protocol() -> None:
    """Test 1: ConcatAssembler instance is runtime-checkable as ChapterAssembler."""
    from book_pipeline.chapter_assembler.concat import ConcatAssembler

    a = ConcatAssembler()
    assert isinstance(a, ChapterAssembler)


def test_concat_three_scenes_happy_path() -> None:
    """Test 2: 3 scenes → chapter frontmatter + 3 HTML markers + 2 separators."""
    from book_pipeline.chapter_assembler.concat import ConcatAssembler

    drafts = [
        _make_draft(scene_text="scene one body"),
        _make_draft(scene_text="scene two body"),
        _make_draft(scene_text="scene three body"),
    ]
    a = ConcatAssembler()
    out = a.assemble(drafts, 1)

    fm, body = _split_frontmatter(out)
    assert fm["chapter_num"] == 1
    assert fm["assembled_from_scenes"] == ["ch01_sc01", "ch01_sc02", "ch01_sc03"]
    # 3 scenes × 3 words = 9; but plan example says 6 for "scene-1 body" style.
    # Our scene texts: "scene one body" / "scene two body" / "scene three body"
    # = 3 + 3 + 3 = 9 words. Spec: sum(len(d.scene_text.split()) for d in drafts).
    assert fm["word_count"] == 9
    assert fm["voice_pin_shas"] == ["shaX"]
    assert fm["voice_fidelity_aggregate"] == 0.85
    assert fm["chapter_critic_pass"] is None
    assert fm["thesis_events"] == []

    # 3 HTML comment markers
    for i in (1, 2, 3):
        assert f"<!-- scene: ch01_sc{i:02d} -->" in body, (
            f"missing HTML marker for sc{i:02d} in body"
        )

    # 2 section separators between 3 scenes
    assert body.count("\n\n---\n\n") == 2


def test_concat_is_deterministic() -> None:
    """Test 3: two assemble() calls on identical inputs → byte-identical."""
    from book_pipeline.chapter_assembler.concat import ConcatAssembler

    drafts = [
        _make_draft(scene_text="a b"),
        _make_draft(scene_text="c d"),
    ]
    a = ConcatAssembler()
    out1 = a.assemble(drafts, 1)
    out2 = a.assemble(drafts, 1)
    assert out1 == out2, "ConcatAssembler must be byte-deterministic"


def test_concat_handles_pin_upgrade() -> None:
    """Test 4: voice_pin_shas are deduplicated preserving order; size>1 = upgrade."""
    from book_pipeline.chapter_assembler.concat import ConcatAssembler

    drafts = [
        _make_draft(scene_text="s1", voice_pin_sha="sha1"),
        _make_draft(scene_text="s2", voice_pin_sha="sha1"),
        _make_draft(scene_text="s3", voice_pin_sha="sha2"),
    ]
    out = ConcatAssembler().assemble(drafts, 2)
    fm, _ = _split_frontmatter(out)
    assert fm["voice_pin_shas"] == ["sha1", "sha2"]


def test_concat_single_scene() -> None:
    """Test 5: single scene → one HTML marker, zero separators, valid frontmatter."""
    from book_pipeline.chapter_assembler.concat import ConcatAssembler

    drafts = [_make_draft(scene_text="alone")]
    out = ConcatAssembler().assemble(drafts, 1)

    fm, body = _split_frontmatter(out)
    assert fm["chapter_num"] == 1
    assert fm["assembled_from_scenes"] == ["ch01_sc01"]

    assert body.count("<!-- scene: ch01_sc01 -->") == 1
    assert "\n\n---\n\n" not in body, "single-scene chapter must have no separators"


def test_from_committed_scenes_happy_path(tmp_path: Path) -> None:
    """Test 6: from_committed_scenes reads .md with frontmatter, sorts by
    scene_index, builds DraftResponse list, calls assemble, returns both."""
    from book_pipeline.chapter_assembler.concat import ConcatAssembler

    chapter_dir = tmp_path / "ch01"
    chapter_dir.mkdir()

    def _write_scene(idx: int, body: str, pin: str = "shaX") -> None:
        fm = {
            "voice_pin_sha": pin,
            "checkpoint_sha": pin,  # B-3 invariant
            "critic_scores_per_axis": {
                "historical": 85.0,
                "metaphysics": 80.0,
                "entity": 80.0,
                "arc": 80.0,
                "donts": 80.0,
            },
            "attempt_count": 1,
            "ingestion_run_id": "ing_test",
            "draft_timestamp": "2026-04-22T00:00:00Z",
            "voice_fidelity_score": 0.85,
            "mode": "A",
            "rubric_version": "v1",
        }
        md = f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n{body}\n"
        (chapter_dir / f"ch01_sc{idx:02d}.md").write_text(md, encoding="utf-8")

    # Intentionally write sc02 first to prove ordering is filename-regex-driven
    _write_scene(2, "scene two body")
    _write_scene(1, "scene one body")

    drafts, chapter_text = ConcatAssembler.from_committed_scenes(1, tmp_path)

    assert len(drafts) == 2
    assert drafts[0].scene_text.strip() == "scene one body"
    assert drafts[1].scene_text.strip() == "scene two body"
    # Both scene markers appear in assembled text
    assert "<!-- scene: ch01_sc01 -->" in chapter_text
    assert "<!-- scene: ch01_sc02 -->" in chapter_text
    # Frontmatter carries chapter_num
    fm, _ = _split_frontmatter(chapter_text)
    assert fm["chapter_num"] == 1


def test_from_committed_scenes_missing_voice_pin_sha_raises(tmp_path: Path) -> None:
    """B-3 invariant: scene md missing voice_pin_sha → RuntimeError."""
    from book_pipeline.chapter_assembler.concat import ConcatAssembler

    chapter_dir = tmp_path / "ch01"
    chapter_dir.mkdir()
    fm_missing = {
        # no voice_pin_sha
        "checkpoint_sha": "shaX",
        "attempt_count": 1,
    }
    md = f"---\n{yaml.safe_dump(fm_missing, sort_keys=False)}---\nbody\n"
    (chapter_dir / "ch01_sc01.md").write_text(md, encoding="utf-8")

    import pytest

    with pytest.raises(RuntimeError, match="voice_pin_sha"):
        ConcatAssembler.from_committed_scenes(1, tmp_path)


def test_from_committed_scenes_missing_dir_raises(tmp_path: Path) -> None:
    """Missing drafts/ch{NN}/ directory raises FileNotFoundError (fail-fast)."""
    from book_pipeline.chapter_assembler.concat import ConcatAssembler

    import pytest

    with pytest.raises(FileNotFoundError):
        ConcatAssembler.from_committed_scenes(99, tmp_path)
