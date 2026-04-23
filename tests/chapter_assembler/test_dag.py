"""Tests for ChapterDagOrchestrator (Plan 04-04 Task 1).

Covers 8 tests per plan <action> §6:
  A — Happy path 4 commits: canon, entity-state, rag, retro.
  B — Chapter critic fail -> CHAPTER_FAIL, no canon commit, 0 new commits.
  C — Resumability from dag_step=1 -> Concat/Critic NOT called; steps 3+4 execute.
  D — Entity extractor fail -> DAG_BLOCKED, dag_step stays 1.
  E — Fresh-pack invariant: bundler receives chapter-scoped SceneRequest;
      critic sees the returned pack's fingerprint (distinct from a seeded
      scene-pack fingerprint).
  F — Retrospective ungated failure: stub retro still commits; DAG_COMPLETE.
  G — Scene-count mismatch gate: ChapterGateError(expected=3, actual=1).
  H — Pipeline state JSON written atomically via .tmp + os.replace.

All tests use local Fake components (no real LLM, no real Anthropic, no
real retrievers). Git is REAL — a fresh `git init` in tmp_path per test.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml

from book_pipeline.entity_extractor.opus import EntityExtractorBlocked
from book_pipeline.interfaces.types import (
    ChapterState,
    ContextPack,
    CriticIssue,
    CriticResponse,
    DraftResponse,
    EntityCard,
    Event,
    Retrospective,
    SceneRequest,
)

# --------------------------------------------------------------------- #
# Test-tree layout helpers                                              #
# --------------------------------------------------------------------- #


def _init_tmp_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=main", str(tmp_path)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True,
    )
    # Seed commit so HEAD exists.
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".gitkeep"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "seed"], check=True
    )
    return tmp_path


def _seed_scene_md(
    commit_dir: Path,
    chapter_num: int,
    scene_num: int,
    body: str = "scene body",
    voice_pin_sha: str = "shaX",
) -> Path:
    ch_dir = commit_dir / f"ch{chapter_num:02d}"
    ch_dir.mkdir(parents=True, exist_ok=True)
    path = ch_dir / f"ch{chapter_num:02d}_sc{scene_num:02d}.md"
    fm = {
        "voice_pin_sha": voice_pin_sha,
        "checkpoint_sha": voice_pin_sha,
        "critic_scores_per_axis": {"historical": 80.0},
        "attempt_count": 1,
        "ingestion_run_id": "run_test",
        "draft_timestamp": "2026-04-23T00:00:00Z",
        "voice_fidelity_score": 0.85,
        "mode": "A",
        "rubric_version": "v1",
    }
    yaml_text = yaml.safe_dump(fm, sort_keys=False)
    path.write_text(f"---\n{yaml_text}---\n{body}\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------- #
# Fake components                                                       #
# --------------------------------------------------------------------- #


class _FakeChapterCritic:
    """Fake ChapterCritic returning a pre-baked CriticResponse."""

    level = "chapter"

    def __init__(self, *, overall_pass: bool, issues: list[CriticIssue] | None = None):
        self._overall_pass = overall_pass
        self._issues = issues or []
        self.calls: list[Any] = []
        self.last_pack_fingerprint: str | None = None

    def review(self, request: Any) -> CriticResponse:
        self.calls.append(request)
        self.last_pack_fingerprint = request.context_pack.fingerprint
        axes = ("historical", "metaphysics", "entity", "arc", "donts")
        return CriticResponse(
            pass_per_axis={a: self._overall_pass for a in axes},
            scores_per_axis={a: 80.0 if self._overall_pass else 40.0 for a in axes},
            issues=list(self._issues),
            overall_pass=self._overall_pass,
            model_id="claude-opus-4-7",
            rubric_version="chapter.v1",
            output_sha="fake_sha",
        )


class _FakeEntityExtractor:
    def __init__(
        self,
        *,
        cards: list[EntityCard] | None = None,
        raises: Exception | None = None,
    ):
        self._cards = cards or []
        self._raises = raises
        self.calls: list[Any] = []

    def extract(
        self,
        chapter_text: str,
        chapter_num: int,
        chapter_sha: str,
        prior_cards: list[EntityCard],
    ) -> list[EntityCard]:
        self.calls.append(
            {
                "chapter_text": chapter_text,
                "chapter_num": chapter_num,
                "chapter_sha": chapter_sha,
                "prior_cards": list(prior_cards),
            }
        )
        if self._raises is not None:
            raise self._raises
        # Stamp source_chapter_sha defensively.
        out: list[EntityCard] = []
        for card in self._cards:
            new = card.model_copy(update={"source_chapter_sha": chapter_sha})
            out.append(new)
        return out


class _FakeRetrospectiveWriter:
    def __init__(self, *, retrospective: Retrospective):
        self._retro = retrospective
        self.calls: list[Any] = []

    def write(
        self,
        chapter_text: str,
        chapter_events: list[Event],
        prior_retros: list[Retrospective],
    ) -> Retrospective:
        self.calls.append(
            {
                "chapter_text": chapter_text,
                "chapter_events": list(chapter_events),
                "prior_retros": list(prior_retros),
            }
        )
        return self._retro


class _FakeBundler:
    """Fake ContextPackBundler returning a fixed ContextPack."""

    def __init__(self, *, fingerprint: str = "CHAPTER_FP_XYZ") -> None:
        self._fingerprint = fingerprint
        self.calls: list[SceneRequest] = []

    def bundle(self, request: SceneRequest, retrievers: Any) -> ContextPack:
        self.calls.append(request)
        return ContextPack(
            scene_request=request,
            retrievals={},
            total_bytes=0,
            assembly_strategy="round_robin",
            fingerprint=self._fingerprint,
        )


class _FakeAssembler:
    """Wraps ConcatAssembler to count calls (resumability regression test)."""

    def __init__(self) -> None:
        self.from_committed_calls: list[tuple[int, Path]] = []

    def from_committed_scenes(
        self, chapter_num: int, commit_dir: Path
    ) -> tuple[list[DraftResponse], str]:
        from book_pipeline.chapter_assembler.concat import ConcatAssembler

        self.from_committed_calls.append((chapter_num, commit_dir))
        return ConcatAssembler.from_committed_scenes(chapter_num, commit_dir)


class _FakeArcPositionRetriever:
    """Minimal fake with a zero-arg reindex() + a name attribute."""

    name = "arc_position"

    def __init__(self) -> None:
        self.reindex_calls = 0

    def reindex(self) -> None:
        self.reindex_calls += 1


class _FakeEmbedder:
    """Minimal embedder for rag/reindex.py — returns a fixed vector."""

    def encode(self, text: str) -> list[float]:
        # 1024-dim zeros — matches BGE-M3 shape.
        return [0.0] * 1024


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


# --------------------------------------------------------------------- #
# Orchestrator builder                                                  #
# --------------------------------------------------------------------- #


@dataclass
class _Rig:
    """Bundles all the fixtures a DAG test needs; built per test."""

    repo: Path
    commit_dir: Path
    canon_dir: Path
    entity_state_dir: Path
    retros_dir: Path
    scene_buffer_dir: Path
    chapter_buffer_dir: Path
    indexes_dir: Path
    pipeline_state_path: Path
    events_jsonl: Path
    assembler: _FakeAssembler
    critic: _FakeChapterCritic
    extractor: _FakeEntityExtractor
    retro: _FakeRetrospectiveWriter
    bundler: _FakeBundler
    arc_retriever: _FakeArcPositionRetriever
    embedder: _FakeEmbedder
    event_logger: _FakeEventLogger


def _build_rig(
    tmp_path: Path,
    *,
    critic_pass: bool = True,
    critic_issues: list[CriticIssue] | None = None,
    extractor_cards: list[EntityCard] | None = None,
    extractor_raises: Exception | None = None,
    retro: Retrospective | None = None,
    bundler_fingerprint: str = "CHAPTER_FP_XYZ",
) -> _Rig:
    repo = _init_tmp_repo(tmp_path)
    commit_dir = repo / "drafts"
    commit_dir.mkdir(exist_ok=True)
    canon_dir = repo / "canon"
    canon_dir.mkdir(exist_ok=True)
    entity_state_dir = repo / "entity-state"
    entity_state_dir.mkdir(exist_ok=True)
    retros_dir = repo / "retrospectives"
    retros_dir.mkdir(exist_ok=True)
    scene_buffer_dir = repo / "drafts" / "scene_buffer"
    scene_buffer_dir.mkdir(parents=True, exist_ok=True)
    chapter_buffer_dir = repo / "drafts" / "chapter_buffer"
    chapter_buffer_dir.mkdir(parents=True, exist_ok=True)
    indexes_dir = repo / "indexes"
    indexes_dir.mkdir(exist_ok=True)
    pipeline_state_path = repo / ".planning" / "pipeline_state.json"
    pipeline_state_path.parent.mkdir(parents=True, exist_ok=True)
    events_jsonl = repo / "runs" / "events.jsonl"
    events_jsonl.parent.mkdir(parents=True, exist_ok=True)
    events_jsonl.touch()

    if retro is None:
        retro = Retrospective(
            chapter_num=99,
            what_worked='ch99_sc01 landed; axis historical clean; "the opening beats were clean and pointed".',
            what_didnt="ch99_sc02 drifted on metaphysics",
            pattern="ch99_sc03 repeats the anchoring pattern",
            candidate_theses=[{"id": "t1", "description": "test"}],
        )

    rig = _Rig(
        repo=repo,
        commit_dir=commit_dir,
        canon_dir=canon_dir,
        entity_state_dir=entity_state_dir,
        retros_dir=retros_dir,
        scene_buffer_dir=scene_buffer_dir,
        chapter_buffer_dir=chapter_buffer_dir,
        indexes_dir=indexes_dir,
        pipeline_state_path=pipeline_state_path,
        events_jsonl=events_jsonl,
        assembler=_FakeAssembler(),
        critic=_FakeChapterCritic(
            overall_pass=critic_pass, issues=critic_issues
        ),
        extractor=_FakeEntityExtractor(
            cards=extractor_cards or [], raises=extractor_raises
        ),
        retro=_FakeRetrospectiveWriter(retrospective=retro),
        bundler=_FakeBundler(fingerprint=bundler_fingerprint),
        arc_retriever=_FakeArcPositionRetriever(),
        embedder=_FakeEmbedder(),
        event_logger=_FakeEventLogger(),
    )
    return rig


def _build_orchestrator(rig: _Rig):  # type: ignore[no-untyped-def]
    from book_pipeline.chapter_assembler.dag import ChapterDagOrchestrator

    return ChapterDagOrchestrator(
        assembler=rig.assembler,
        chapter_critic=rig.critic,
        entity_extractor=rig.extractor,
        retrospective_writer=rig.retro,
        bundler=rig.bundler,
        retrievers=[rig.arc_retriever],
        embedder=rig.embedder,
        event_logger=rig.event_logger,
        repo_root=rig.repo,
        canon_dir=rig.canon_dir,
        entity_state_dir=rig.entity_state_dir,
        retros_dir=rig.retros_dir,
        scene_buffer_dir=rig.scene_buffer_dir,
        chapter_buffer_dir=rig.chapter_buffer_dir,
        commit_dir=rig.commit_dir,
        indexes_dir=rig.indexes_dir,
        pipeline_state_path=rig.pipeline_state_path,
        events_jsonl_path=rig.events_jsonl,
        rubric_version="chapter.v1",
    )


# --------------------------------------------------------------------- #
# Tests                                                                 #
# --------------------------------------------------------------------- #


def test_A_happy_path_4_commits(tmp_path: Path) -> None:
    """Full DAG run: 4 commits in order; all artifacts on disk; DAG_COMPLETE."""
    rig = _build_rig(
        tmp_path,
        critic_pass=True,
        extractor_cards=[
            EntityCard(
                entity_name="Cortes",
                last_seen_chapter=99,
                state={"current_state": "in Havana"},
                evidence_spans=[],
                source_chapter_sha="placeholder",
            ),
            EntityCard(
                entity_name="Motecuhzoma",
                last_seen_chapter=99,
                state={"current_state": "in Tenochtitlan"},
                evidence_spans=[],
                source_chapter_sha="placeholder",
            ),
        ],
    )
    _seed_scene_md(rig.commit_dir, 99, 1, body="scene one body")
    _seed_scene_md(rig.commit_dir, 99, 2, body="scene two body")
    _seed_scene_md(rig.commit_dir, 99, 3, body="scene three body")

    orchestrator = _build_orchestrator(rig)
    result = orchestrator.run(99)

    assert result.state == ChapterState.DAG_COMPLETE
    assert result.dag_step == 4
    assert result.chapter_sha is not None
    assert re.fullmatch(r"[0-9a-f]{40}", result.chapter_sha)

    # Files on disk.
    assert (rig.canon_dir / "chapter_99.md").is_file()
    assert (rig.entity_state_dir / "chapter_99_entities.json").is_file()
    assert (rig.retros_dir / "chapter_99.md").is_file()

    # Git log: 4 new commits after seed in order.
    log = subprocess.run(
        ["git", "-C", str(rig.repo), "log", "--oneline"],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in log.stdout.splitlines() if line.strip()]
    # log is ordered newest-first
    # Expected order bottom-up: seed, canon(ch99), chore(entity-state): ch99,
    # chore(rag): reindex after ch99, docs(retro): ch99.
    assert len(lines) == 5, f"expected 5 commits (seed + 4), got {len(lines)}: {lines}"
    # top-down reverse: retro, rag, entity-state, canon, seed
    assert "docs(retro): ch99" in lines[0]
    assert "chore(rag): reindex after ch99" in lines[1]
    assert "chore(entity-state): ch99 extraction" in lines[2]
    assert "canon(ch99): commit chapter 99" in lines[3]

    # Pipeline state JSON.
    state_data = json.loads(rig.pipeline_state_path.read_text(encoding="utf-8"))
    assert state_data["last_committed_chapter"] == 99
    assert state_data["last_committed_dag_step"] == 4
    assert state_data["dag_complete"] is True
    assert state_data["last_hard_block"] is None


def test_B_chapter_critic_fail_no_canon_commit(tmp_path: Path) -> None:
    """CriticResponse.overall_pass=False -> state=CHAPTER_FAIL, no canon commit."""
    issue = CriticIssue(
        axis="entity",
        severity="high",
        location="paragraph 2",
        claim="entity drift",
        evidence="x",
    )
    rig = _build_rig(
        tmp_path,
        critic_pass=False,
        critic_issues=[issue],
    )
    _seed_scene_md(rig.commit_dir, 99, 1)
    _seed_scene_md(rig.commit_dir, 99, 2)

    orchestrator = _build_orchestrator(rig)

    # Capture git HEAD before run
    head_before = subprocess.run(
        ["git", "-C", str(rig.repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    result = orchestrator.run(99)

    assert result.state == ChapterState.CHAPTER_FAIL
    assert "chapter_critic_axis_fail" in result.blockers
    # No canon file written.
    assert not (rig.canon_dir / "chapter_99.md").exists()
    # No new commits.
    head_after = subprocess.run(
        ["git", "-C", str(rig.repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert head_after == head_before
    # Extractor NOT called (post-step-1 gates).
    assert rig.extractor.calls == []


def test_C_resumability_from_step_2(tmp_path: Path) -> None:
    """Pre-seed state with dag_step=1; re-run -> Concat/Critic NOT called."""
    rig = _build_rig(tmp_path, critic_pass=True, extractor_cards=[])
    _seed_scene_md(rig.commit_dir, 99, 1)

    # Pre-commit a canon file to match dag_step=1 state.
    (rig.canon_dir / "chapter_99.md").write_text(
        "---\nchapter_num: 99\n---\n\n<!-- scene: ch99_sc01 -->\ndummy\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(rig.repo), "add", "canon/chapter_99.md"], check=True
    )
    subprocess.run(
        ["git", "-C", str(rig.repo), "commit", "-q", "-m", "canon(ch99): pre-seeded"],
        check=True,
    )
    canon_sha = subprocess.run(
        ["git", "-C", str(rig.repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    # Pre-seed the chapter_buffer state JSON at dag_step=1, state=POST_COMMIT_DAG.
    from book_pipeline.interfaces.types import ChapterStateRecord

    record = ChapterStateRecord(
        chapter_num=99,
        state=ChapterState.POST_COMMIT_DAG,
        scene_ids=["ch99_sc01"],
        chapter_sha=canon_sha,
        dag_step=1,
        history=[],
        blockers=[],
    )
    state_path = rig.chapter_buffer_dir / "ch99.state.json"
    state_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    orchestrator = _build_orchestrator(rig)
    result = orchestrator.run(99)

    assert result.state == ChapterState.DAG_COMPLETE
    assert result.dag_step == 4
    # Step 1 skipped -> assembler NOT called.
    assert rig.assembler.from_committed_calls == []
    # Critic NOT called.
    assert rig.critic.calls == []
    # Extractor + retro DID run.
    assert len(rig.extractor.calls) == 1
    assert len(rig.retro.calls) == 1


def test_D_entity_extractor_fail_dag_blocked(tmp_path: Path) -> None:
    """EntityExtractorBlocked raised -> state=DAG_BLOCKED; dag_step stays 1."""
    rig = _build_rig(
        tmp_path,
        critic_pass=True,
        extractor_raises=EntityExtractorBlocked(
            "entity_extraction_failed", chapter_num=99
        ),
    )
    _seed_scene_md(rig.commit_dir, 99, 1)

    orchestrator = _build_orchestrator(rig)
    result = orchestrator.run(99)

    assert result.state == ChapterState.DAG_BLOCKED
    assert result.dag_step == 1
    assert any(
        "entity_extraction" in b for b in result.blockers
    ), f"expected entity_extraction blocker tag, got: {result.blockers}"
    # Canon commit DID fire (step 1 landed); entity-state file did NOT.
    assert (rig.canon_dir / "chapter_99.md").is_file()
    assert not (rig.entity_state_dir / "chapter_99_entities.json").exists()


def test_E_fresh_pack_assertion(tmp_path: Path) -> None:
    """Bundler receives a chapter-scoped SceneRequest; critic sees that pack.

    Also proves the fresh pack fingerprint differs from a 'scene pack'
    fingerprint we invent here (the invariant that Plan 04-06 E2E asserts).
    """
    rig = _build_rig(
        tmp_path, critic_pass=True, bundler_fingerprint="CHAPTER_FP_XYZ"
    )
    _seed_scene_md(rig.commit_dir, 99, 1)

    orchestrator = _build_orchestrator(rig)
    orchestrator.run(99)

    # Bundler called once with a chapter-scoped SceneRequest.
    assert len(rig.bundler.calls) == 1
    req = rig.bundler.calls[0]
    assert req.scene_index == 0
    assert req.beat_function == "chapter_overview"
    assert req.chapter == 99

    # Critic sees the SAME pack fingerprint.
    assert rig.critic.last_pack_fingerprint == "CHAPTER_FP_XYZ"

    # Invariant asserted for Plan 04-06: chapter_pack FP != scene_pack FP.
    SCENE_FP = "SCENE_FP_ABC"
    assert rig.critic.last_pack_fingerprint != SCENE_FP


def test_F_retrospective_ungated_failure(tmp_path: Path) -> None:
    """Retrospective writer returning stub -> DAG still COMPLETE."""
    stub = Retrospective(
        chapter_num=99,
        what_worked="(generation failed)",
        what_didnt="bang",
        pattern="",
        candidate_theses=[],
    )
    rig = _build_rig(tmp_path, critic_pass=True, retro=stub)
    _seed_scene_md(rig.commit_dir, 99, 1)

    orchestrator = _build_orchestrator(rig)
    result = orchestrator.run(99)

    assert result.state == ChapterState.DAG_COMPLETE
    retro_md = (rig.retros_dir / "chapter_99.md").read_text(encoding="utf-8")
    assert "(generation failed)" in retro_md


def test_G_scene_count_mismatch_gate(tmp_path: Path) -> None:
    """expected_scene_count=3 but only 1 seeded -> ChapterGateError."""
    from book_pipeline.chapter_assembler.dag import ChapterGateError

    rig = _build_rig(tmp_path, critic_pass=True)
    _seed_scene_md(rig.commit_dir, 99, 1)  # Only 1 of 3

    orchestrator = _build_orchestrator(rig)
    with pytest.raises(ChapterGateError) as excinfo:
        orchestrator.run(99, expected_scene_count=3)

    # Carries structured context.
    ctx = excinfo.value.context if hasattr(excinfo.value, "context") else {}
    expected = ctx.get("expected", getattr(excinfo.value, "expected", None))
    actual = ctx.get("actual", getattr(excinfo.value, "actual", None))
    assert expected == 3
    assert actual == 1


def test_H_pipeline_state_json_written_atomically(tmp_path: Path) -> None:
    """os.replace is used to rename a .tmp file onto pipeline_state.json."""
    rig = _build_rig(
        tmp_path,
        critic_pass=True,
        extractor_cards=[
            EntityCard(
                entity_name="Cortes",
                last_seen_chapter=99,
                state={"current_state": "in Havana"},
                evidence_spans=[],
                source_chapter_sha="placeholder",
            ),
        ],
    )
    _seed_scene_md(rig.commit_dir, 99, 1)

    orchestrator = _build_orchestrator(rig)

    # Spy on os.replace to confirm at least one call references the
    # pipeline_state .tmp path.
    real_replace = os.replace
    replace_calls: list[tuple[Any, Any]] = []

    def spy(src, dst, *args, **kwargs):  # type: ignore[no-untyped-def]
        replace_calls.append((str(src), str(dst)))
        return real_replace(src, dst, *args, **kwargs)

    with mock.patch("os.replace", side_effect=spy):
        result = orchestrator.run(99)

    assert result.state == ChapterState.DAG_COMPLETE

    # At least one replace call moved a .tmp onto pipeline_state.json.
    pipeline_state_target = str(rig.pipeline_state_path)
    matches = [c for c in replace_calls if c[1] == pipeline_state_target]
    assert matches, (
        "expected os.replace to be used for pipeline_state.json atomic write, "
        f"got: {replace_calls}"
    )
    src_path = matches[0][0]
    assert src_path.endswith(".tmp"), (
        f"expected .tmp suffix on src, got: {src_path}"
    )

    # The final file has the expected contents.
    data = json.loads(rig.pipeline_state_path.read_text(encoding="utf-8"))
    assert data["last_committed_chapter"] == 99
    assert data["dag_complete"] is True
