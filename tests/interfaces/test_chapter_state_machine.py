"""Tests for book_pipeline.interfaces.chapter_state_machine (Phase 4 Plan 04-01).

Parallel to tests for scene_state_machine — ChapterStateMachine is the NEW
chapter-grain state machine that governs the Phase 4 assembly → chapter
critic → canon commit → post-commit DAG flow. SceneStateMachine stays
frozen; ChapterStateMachine is a separate module.

Covers:
- Test 1: ChapterState Enum has exactly 10 values (the state set from
  04-CONTEXT.md).
- Test 2: ChapterState is a str-subclass Enum (matches SceneState convention,
  not StrEnum; `# noqa: UP042`).
- Test 3: happy-path roundtrip PENDING_SCENES → ... → DAG_COMPLETE produces
  a 7-entry history with correct (from, to) pairs.
- Test 4: transition() is pure — input record not mutated after call.
- Test 5: failure-branch coverage for CHAPTER_CRITIQUING → CHAPTER_FAIL and
  POST_COMMIT_DAG → DAG_BLOCKED with caller-set blockers.
- Test 6: ChapterStateRecord JSON round-trips cleanly (Pydantic persistence
  parity with SceneStateRecord).
"""

from __future__ import annotations

from book_pipeline.interfaces.chapter_state_machine import (
    ChapterState,
    ChapterStateRecord,
    transition,
)


def test_chapter_state_enum_has_11_values() -> None:
    """ChapterState Enum carries the 10 Phase 4 states plus Phase 5's
    CHAPTER_FAIL_SCENE_KICKED substate (Plan 05-02 Task 2 / LOOP-04)."""
    expected = {
        "pending_scenes",
        "assembling",
        "assembled",
        "chapter_critiquing",
        "chapter_fail",
        "chapter_fail_scene_kicked",  # Phase 5 addition (LOOP-04)
        "chapter_pass",
        "committing_canon",
        "post_commit_dag",
        "dag_complete",
        "dag_blocked",
    }
    actual = {member.value for member in ChapterState}
    assert actual == expected
    assert len(list(ChapterState)) == 11


def test_chapter_state_is_str_enum() -> None:
    """ChapterState values are also strings (str-subclass Enum pattern —
    matches SceneState; `isinstance(value, str) is True`)."""
    assert isinstance(ChapterState.PENDING_SCENES, str)
    assert isinstance(ChapterState.DAG_COMPLETE, str)
    # And enum-coerces from its string value:
    assert ChapterState("pending_scenes") is ChapterState.PENDING_SCENES
    assert ChapterState("dag_complete") is ChapterState.DAG_COMPLETE


def test_transition_happy_path() -> None:
    """Walk a chapter from PENDING_SCENES to DAG_COMPLETE through the 7
    canonical happy-path transitions. Each transition appends exactly one
    history entry with the correct (from, to) pair."""
    record = ChapterStateRecord(
        chapter_num=1,
        state=ChapterState.PENDING_SCENES,
        scene_ids=["ch01_sc01", "ch01_sc02", "ch01_sc03"],
    )

    happy_path: list[tuple[ChapterState, str]] = [
        (ChapterState.ASSEMBLING, "start concat"),
        (ChapterState.ASSEMBLED, "concat ok"),
        (ChapterState.CHAPTER_CRITIQUING, "fresh pack"),
        (ChapterState.CHAPTER_PASS, "5/5 axes >=3"),
        (ChapterState.COMMITTING_CANON, "git commit"),
        (ChapterState.POST_COMMIT_DAG, "entity extraction"),
        (ChapterState.DAG_COMPLETE, "retro written"),
    ]

    expected_pairs: list[tuple[str, str]] = []
    prior_state = ChapterState.PENDING_SCENES
    for to_state, note in happy_path:
        expected_pairs.append((prior_state.value, to_state.value))
        record = transition(record, to_state, note)
        prior_state = to_state

    assert record.state is ChapterState.DAG_COMPLETE
    assert len(record.history) == 7

    for idx, (from_val, to_val) in enumerate(expected_pairs):
        entry = record.history[idx]
        assert entry["from"] == from_val, f"history[{idx}] from mismatch: {entry}"
        assert entry["to"] == to_val, f"history[{idx}] to mismatch: {entry}"
        assert "ts_iso" in entry
        assert "note" in entry


def test_transition_does_not_mutate_input() -> None:
    """transition() is pure: input record's history length stays unchanged
    after the call (model_copy produces a new instance)."""
    original = ChapterStateRecord(
        chapter_num=7,
        state=ChapterState.PENDING_SCENES,
    )
    history_len_before = len(original.history)

    new_record = transition(original, ChapterState.ASSEMBLING, "start")

    assert len(original.history) == history_len_before
    assert original.state is ChapterState.PENDING_SCENES  # input's state unchanged
    assert new_record is not original
    assert new_record.state is ChapterState.ASSEMBLING
    assert len(new_record.history) == history_len_before + 1


def test_transition_fail_branches() -> None:
    """Exercise the two chapter-level failure branches — CHAPTER_CRITIQUING
    → CHAPTER_FAIL and POST_COMMIT_DAG → DAG_BLOCKED — and show that callers
    can append to `blockers` on the returned record (caller concern)."""
    # Branch 1: chapter critic axis fail
    record = ChapterStateRecord(
        chapter_num=2,
        state=ChapterState.CHAPTER_CRITIQUING,
    )
    failed = transition(record, ChapterState.CHAPTER_FAIL, "axis=arc severity=high")
    # Caller decorates with a blocker marker:
    failed = failed.model_copy(
        update={"blockers": [*failed.blockers, "chapter_critic_axis_fail"]}
    )
    assert failed.state is ChapterState.CHAPTER_FAIL
    assert "chapter_critic_axis_fail" in failed.blockers

    # Branch 2: post-commit DAG block (entity extractor persistent failure)
    dag_record = ChapterStateRecord(
        chapter_num=3,
        state=ChapterState.POST_COMMIT_DAG,
        chapter_sha="deadbeef" * 5,
        dag_step=2,
    )
    blocked = transition(
        dag_record, ChapterState.DAG_BLOCKED, "entity_extractor_3x_retry_exhaust"
    )
    blocked = blocked.model_copy(
        update={"blockers": [*blocked.blockers, "entity_extractor_unavailable"]}
    )
    assert blocked.state is ChapterState.DAG_BLOCKED
    assert blocked.dag_step == 2  # DAG step carries through for resume
    assert blocked.chapter_sha == "deadbeef" * 5
    assert "entity_extractor_unavailable" in blocked.blockers


def test_record_json_roundtrip() -> None:
    """ChapterStateRecord serializes to JSON and back without loss (Pydantic
    persistence parity with SceneStateRecord — required by the atomic
    tmp+rename persistence contract)."""
    record = ChapterStateRecord(
        chapter_num=5,
        state=ChapterState.POST_COMMIT_DAG,
        scene_ids=["ch05_sc01", "ch05_sc02"],
        chapter_sha="abc123def456" * 4,
        dag_step=3,
        history=[
            {
                "from": "assembling",
                "to": "assembled",
                "ts_iso": "2026-04-21T00:00:00+00:00",
                "note": "concat ok",
            }
        ],
        blockers=[],
    )

    round_tripped = ChapterStateRecord.model_validate_json(record.model_dump_json())
    assert round_tripped == record
    assert round_tripped.state is ChapterState.POST_COMMIT_DAG
    assert round_tripped.chapter_sha == "abc123def456" * 4
    assert round_tripped.dag_step == 3
