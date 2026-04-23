"""Tests for surgical scene-kick helpers (Plan 05-02 Task 2 / LOOP-04 + SC4 closure).

extract_implicated_scene_ids() parses CriticIssue.location via widened regex
r'\\bch(\\d+)_sc(\\d+)\\b' (NOT the anchored cli/draft.py _SCENE_ID_RE) with
defensive int-cast + zero-pad canonicalization.

kick_implicated_scenes() archives drafts/ch{NN}/{scene_id}.md to
drafts/ch{NN}/archive/{scene_id}_rev{K:02d}.md, resets the scene state record
to PENDING via interfaces.scene_state_machine.transition, emits ONE
role='scene_kick' Event per invocation.
"""
from __future__ import annotations

from pathlib import Path

from book_pipeline.chapter_assembler.scene_kick import (
    extract_implicated_scene_ids,
    kick_implicated_scenes,
)
from book_pipeline.interfaces.types import (
    CriticIssue,
    CriticResponse,
    Event,
    SceneState,
    SceneStateRecord,
)


def _make_response(issues: list[CriticIssue]) -> CriticResponse:
    """Build a minimal CriticResponse for extract tests."""
    return CriticResponse(
        pass_per_axis={
            "historical": False,
            "metaphysics": True,
            "entity": True,
            "arc": True,
            "donts": True,
        },
        scores_per_axis={
            "historical": 40.0,
            "metaphysics": 80.0,
            "entity": 80.0,
            "arc": 80.0,
            "donts": 80.0,
        },
        issues=issues,
        overall_pass=False,
        model_id="claude-opus-4-7",
        rubric_version="chapter.v1",
        output_sha="sha",
    )


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


# --- extract_implicated_scene_ids ------------------------------------------- #


def test_extract_implicated_scenes_single_ref() -> None:
    """One issue citing 'ch01_sc02' → implicated={'ch01_sc02'}, non_specific empty."""
    issue = CriticIssue(
        axis="historical",
        severity="high",
        location="ch01_sc02; Cortés's horse line",
        claim="anachronism",
        evidence="no Spanish horses landed by Feb 1519",
    )
    implicated, non_specific = extract_implicated_scene_ids(_make_response([issue]))
    assert implicated == {"ch01_sc02"}
    assert non_specific == []


def test_extract_implicated_scenes_multiple_refs() -> None:
    """One issue citing two scenes in the same location field → both implicated."""
    issue = CriticIssue(
        axis="entity",
        severity="mid",
        location="mid-paragraph 2 of ch01_sc02 and ch01_sc03 boundary",
        claim="entity drift across scenes",
        evidence="Motecuhzoma name spelling inconsistent",
    )
    implicated, non_specific = extract_implicated_scene_ids(_make_response([issue]))
    assert implicated == {"ch01_sc02", "ch01_sc03"}
    assert non_specific == []


def test_extract_non_specific_only() -> None:
    """Issue with no ch/sc reference → non_specific non-empty, implicated empty."""
    issue = CriticIssue(
        axis="arc",
        severity="high",
        location="arc pacing too fast",
        claim="arc beat flattens in final third",
        evidence="outline says rising action peaks at scene 3",
    )
    implicated, non_specific = extract_implicated_scene_ids(_make_response([issue]))
    assert implicated == set()
    assert non_specific == [issue.claim]


def test_extract_ref_from_evidence_field() -> None:
    """location empty-ish but evidence contains ch/sc ref → implicated via evidence."""
    issue = CriticIssue(
        axis="metaphysics",
        severity="mid",
        location="paragraph 1",  # no scene ref here
        claim="metaphysics rule violation",
        evidence="contradicts ch02_sc01 description of Tepeyac hill",
    )
    implicated, non_specific = extract_implicated_scene_ids(_make_response([issue]))
    assert implicated == {"ch02_sc01"}
    assert non_specific == []


def test_extract_canonical_zero_padding() -> None:
    """Non-zero-padded ch/sc refs canonicalize to ch{NN:02d}_sc{II:02d}."""
    issue = CriticIssue(
        axis="historical",
        severity="high",
        location="see ch1_sc2 paragraph 3",
        claim="date drift",
        evidence="gregorian date off by 4 days",
    )
    implicated, non_specific = extract_implicated_scene_ids(_make_response([issue]))
    assert implicated == {"ch01_sc02"}
    assert non_specific == []


# --- kick_implicated_scenes ------------------------------------------------- #


def _seed_state(
    state_dir: Path, scene_id: str, chapter_num: int = 99
) -> Path:
    """Write a COMMITTED SceneStateRecord to state_dir/ch{NN}/{scene_id}.state.json."""
    ch_dir = state_dir / f"ch{chapter_num:02d}"
    ch_dir.mkdir(parents=True, exist_ok=True)
    path = ch_dir / f"{scene_id}.state.json"
    record = SceneStateRecord(
        scene_id=scene_id,
        state=SceneState.COMMITTED,
        attempts={"mode_a_regens": 0},
        mode_tag="A",
        history=[],
        blockers=[],
    )
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_kick_implicated_scenes_resets_pending(tmp_path: Path) -> None:
    """sc02 reset to PENDING; sc01 + sc03 untouched (stay COMMITTED)."""
    state_dir = tmp_path / "scene_buffer"
    drafts_dir = tmp_path / "drafts"
    for sc in ("ch99_sc01", "ch99_sc02", "ch99_sc03"):
        _seed_state(state_dir, sc, 99)

    kick_implicated_scenes(
        implicated={"ch99_sc02"},
        state_dir=state_dir,
        drafts_dir=drafts_dir,
        event_logger=None,
        chapter_num=99,
        issue_refs=["historical:high"],
    )

    sc01 = SceneStateRecord.model_validate_json(
        (state_dir / "ch99" / "ch99_sc01.state.json").read_text()
    )
    sc02 = SceneStateRecord.model_validate_json(
        (state_dir / "ch99" / "ch99_sc02.state.json").read_text()
    )
    sc03 = SceneStateRecord.model_validate_json(
        (state_dir / "ch99" / "ch99_sc03.state.json").read_text()
    )
    assert sc01.state == SceneState.COMMITTED
    assert sc02.state == SceneState.PENDING
    assert sc03.state == SceneState.COMMITTED
    # sc02 history has the scene_kick note:
    assert any("scene_kick" in (h.get("note") or "") for h in sc02.history)


def test_kick_implicated_archives_markdown(tmp_path: Path) -> None:
    """kicked scene's md moves to drafts/ch{NN}/archive/{scene_id}_rev01.md."""
    state_dir = tmp_path / "scene_buffer"
    drafts_dir = tmp_path / "drafts"
    _seed_state(state_dir, "ch99_sc02", 99)

    md_dir = drafts_dir / "ch99"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / "ch99_sc02.md"
    md_path.write_text("scene two body\n", encoding="utf-8")

    kick_implicated_scenes(
        implicated={"ch99_sc02"},
        state_dir=state_dir,
        drafts_dir=drafts_dir,
        event_logger=None,
        chapter_num=99,
        issue_refs=["historical:high"],
    )

    assert not md_path.exists()
    archive_path = md_dir / "archive" / "ch99_sc02_rev01.md"
    assert archive_path.exists()
    assert archive_path.read_text(encoding="utf-8") == "scene two body\n"


def test_kick_emits_single_scene_kick_event(tmp_path: Path) -> None:
    """Two scenes kicked → exactly 1 role='scene_kick' Event emitted."""
    state_dir = tmp_path / "scene_buffer"
    drafts_dir = tmp_path / "drafts"
    for sc in ("ch99_sc02", "ch99_sc03"):
        _seed_state(state_dir, sc, 99)

    logger = _FakeEventLogger()
    kick_implicated_scenes(
        implicated={"ch99_sc02", "ch99_sc03"},
        state_dir=state_dir,
        drafts_dir=drafts_dir,
        event_logger=logger,
        chapter_num=99,
        issue_refs=["historical:high", "entity:mid"],
    )
    kicks = [e for e in logger.events if e.role == "scene_kick"]
    assert len(kicks) == 1
    event = kicks[0]
    # Kicked scenes listed in sorted order.
    assert event.extra.get("kicked_scenes") == ["ch99_sc02", "ch99_sc03"]
    assert event.extra.get("chapter_num") == 99
    assert event.extra.get("issue_refs") == ["historical:high", "entity:mid"]
