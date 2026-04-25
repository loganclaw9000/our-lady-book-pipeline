"""Plan 03-07 scene-loop integration tests — MOCKED components only.

11 tests cover Task 2's acceptance criteria:

  A. `book-pipeline draft --help` prints usage with all 4 args.
  B. `book-pipeline draft ch01_sc01 --dry-run` exits 0 without LLM calls.
  C. Happy path: critic passes attempt 1 → COMMITTED.
  D. Regen-then-pass: critic fails attempt 1 (1 mid issue), passes attempt 2.
  E. R-exhaustion: critic fails all 4 attempts → HARD_BLOCKED.
  F. Drafter block: ModeADrafterBlocked('training_bleed') → HARD_BLOCKED.
  G. Critic block: SceneCriticError('anthropic_unavailable') → HARD_BLOCKED.
  H. B-3 invariant: voice_pin_sha == checkpoint_sha == draft.voice_pin_sha
     in committed frontmatter.
  I. _persist atomic write — tmp failure leaves state.json unchanged.
  J. Protocol conformance — FakeDrafter/FakeCritic/FakeRegenerator satisfy
     isinstance(..., Drafter/Critic/Regenerator).
  K. Word-count regen drift — RegenWordCountDrift counts toward R.

All tests use fake components (no real vLLM / no real Anthropic); the CLI
composition root layer is exercised end-to-end via `run_draft_loop`.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from book_pipeline.interfaces.critic import Critic
from book_pipeline.interfaces.drafter import Drafter
from book_pipeline.interfaces.regenerator import Regenerator
from book_pipeline.interfaces.types import (
    ContextPack,
    CriticIssue,
    CriticResponse,
    DraftResponse,
    RetrievalResult,
    SceneRequest,
    SceneState,
    SceneStateRecord,
)
from book_pipeline.regenerator.scene_local import (
    RegenWordCountDrift,
)

# --------------------------------------------------------------------------- #
# Fake components                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class _EmittedEvent:
    role: str
    extra: dict[str, Any]


class _FakeEventLogger:
    """Minimal EventLogger — records emit() calls for later inspection."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


@dataclass
class _FakeDraftResponse:
    """Structural substitute for DraftResponse — Tests E/F/G avoid constructing
    the real Pydantic model for non-COMMITTED paths."""

    scene_text: str
    voice_pin_sha: str | None
    attempt_number: int = 1
    mode: str = "A"
    model_id: str = "paul-voice"
    tokens_in: int = 100
    tokens_out: int = 200
    latency_ms: int = 1
    output_sha: str = "fakehash"


class _FakeDrafter:
    """Protocol-conformant Mode-A drafter stand-in — configurable behavior.

    Initialized with either a DraftResponse to return OR an exception to raise
    on .draft() invocation. `calls` records every draft() call for assertions.
    """

    mode: str = "A"

    def __init__(
        self,
        *,
        response: DraftResponse | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._response = response
        self._raise_exc = raise_exc
        self.calls: list[Any] = []

    def draft(self, request: Any) -> DraftResponse:
        self.calls.append(request)
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._response is not None, "_FakeDrafter needs a response"
        return self._response


class _FakeCritic:
    """Protocol-conformant SceneCritic stand-in — scripted pass/fail sequence.

    Constructor:
      pass_sequence: list[bool]. One entry per expected review() call.
      issues_sequence: list[list[CriticIssue]] matching pass_sequence.
      raise_exc: optionally raise on the first review() call.

    `calls` records every review() invocation.
    """

    level: str = "scene"

    def __init__(
        self,
        *,
        pass_sequence: list[bool] | None = None,
        issues_sequence: list[list[CriticIssue]] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._pass_sequence = pass_sequence or []
        self._issues_sequence = issues_sequence or []
        self._raise_exc = raise_exc
        self._call_idx = 0
        self.calls: list[Any] = []

    def review(self, request: Any) -> CriticResponse:
        self.calls.append(request)
        if self._raise_exc is not None and self._call_idx == 0:
            raise self._raise_exc
        idx = self._call_idx
        self._call_idx += 1
        if idx >= len(self._pass_sequence):
            raise RuntimeError(
                f"_FakeCritic ran out of scripted responses at call {idx + 1}"
            )
        overall_pass = self._pass_sequence[idx]
        issues = self._issues_sequence[idx] if idx < len(self._issues_sequence) else []
        return CriticResponse(
            pass_per_axis={
                "historical": overall_pass,
                "metaphysics": overall_pass,
                "entity": overall_pass,
                "arc": overall_pass,
                "donts": overall_pass,
            },
            scores_per_axis={
                "historical": 85.0 if overall_pass else 55.0,
                "metaphysics": 88.0 if overall_pass else 60.0,
                "entity": 90.0 if overall_pass else 65.0,
                "arc": 87.0 if overall_pass else 58.0,
                "donts": 92.0 if overall_pass else 70.0,
            },
            issues=issues,
            overall_pass=overall_pass,
            model_id="claude-opus-4-7",
            rubric_version="v1",
            output_sha="critic_fake_sha",
        )


class _FakeRegenerator:
    """Protocol-conformant SceneLocalRegenerator stand-in.

    response_sequence: list where each entry is EITHER a DraftResponse to return
    OR an Exception to raise on that attempt. Index = regen call number (0-indexed).
    """

    def __init__(
        self,
        *,
        response_sequence: list[Any] | None = None,
    ) -> None:
        self._response_sequence = response_sequence or []
        self._call_idx = 0
        self.calls: list[Any] = []

    def regenerate(self, request: Any) -> DraftResponse:
        self.calls.append(request)
        idx = self._call_idx
        self._call_idx += 1
        if idx >= len(self._response_sequence):
            raise RuntimeError(
                f"_FakeRegenerator exhausted at call {idx + 1}"
            )
        item = self._response_sequence[idx]
        if isinstance(item, Exception):
            raise item
        return item


class _FakeBundler:
    """Bundler stand-in — returns a canned ContextPack with fingerprint."""

    def __init__(self, pack: ContextPack) -> None:
        self._pack = pack
        self.calls: list[Any] = []

    def bundle(self, request: Any, retrievers: list[Any]) -> ContextPack:
        self.calls.append((request, retrievers))
        return self._pack


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def scene_request() -> SceneRequest:
    return SceneRequest(
        chapter=1,
        scene_index=1,
        pov="Andrés de Mora",
        date_iso="1519-02-18",
        location="Chapel of Havana",
        beat_function="first contact — opening voyage tension",
    )


@pytest.fixture
def context_pack(scene_request: SceneRequest) -> ContextPack:
    """Test pack with one dummy hit per axis to clear the empty-pack
    preflight gate added 2026-04-24. Production preflight requires
    each axis to have >=1 hit AND total_bytes >= 1000."""
    from book_pipeline.interfaces.types import RetrievalHit

    axes = (
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
    )
    dummy_text = "test corpus hit " * 30  # ~480 chars per hit, 5 axes => ~2.4KB
    retrievals = {}
    for axis in axes:
        hit = RetrievalHit(
            text=dummy_text,
            source_path=f"~/test/{axis}.md",
            chunk_id=f"test_{axis}_001",
            score=0.9,
        )
        retrievals[axis] = RetrievalResult(
            retriever_name=axis,
            hits=[hit],
            bytes_used=len(dummy_text),
            query_fingerprint="fp_" + axis,
        )
    return ContextPack(
        scene_request=scene_request,
        retrievals=retrievals,
        total_bytes=len(dummy_text) * len(axes),
        assembly_strategy="round_robin",
        fingerprint="ctxpack_fp_ch01_sc01",
        ingestion_run_id="ing_test_001",
    )


@pytest.fixture
def canonical_draft() -> DraftResponse:
    return DraftResponse(
        scene_text="Andrés knelt in the chapel. " * 50,  # ~150 words
        mode="A",
        model_id="paul-voice",
        voice_pin_sha="sha_voice_pin_v6",
        tokens_in=500,
        tokens_out=200,
        latency_ms=1234,
        output_sha="draft_sha_canonical",
        attempt_number=1,
    )


@pytest.fixture
def mid_issue() -> CriticIssue:
    return CriticIssue(
        axis="historical",
        severity="mid",
        location="para 2",
        claim="Havana departure date off by a week",
        evidence="outline says Feb 18 1519; scene says Feb 25",
    )


@pytest.fixture
def low_issue() -> CriticIssue:
    return CriticIssue(
        axis="donts",
        severity="low",
        location="para 4",
        claim="mild genre trope — 'crossed himself'",
        evidence="style gate warns, not bans",
    )


def _make_composition_root(
    *,
    tmp_path: Path,
    bundler: Any,
    drafter: Any,
    critic: Any,
    regenerator: Any,
    scene_request: SceneRequest,
) -> SimpleNamespace:
    """Build a composition-root namespace for run_draft_loop."""
    return SimpleNamespace(
        bundler=bundler,
        retrievers=[],  # fake bundler ignores retrievers arg
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        rubric=SimpleNamespace(rubric_version="v1"),
        state_dir=tmp_path / "scene_buffer",
        commit_dir=tmp_path / "drafts",
        ingestion_run_id="ing_test_001",
        anchor_set_sha=None,
        event_logger=_FakeEventLogger(),
    )


# --------------------------------------------------------------------------- #
# Test A: --help                                                                #
# --------------------------------------------------------------------------- #


def test_A_draft_help_prints_usage() -> None:
    """Test A: `book-pipeline draft --help` mentions scene_id + --max-regen +
    --scene-yaml + --dry-run (all 4 args).

    Uses `uv run book-pipeline` so the project-installed console script
    provides the argparse surface (main.py has no __main__ hook).
    """
    result = subprocess.run(
        ["uv", "run", "book-pipeline", "draft", "--help"],
        capture_output=True,
        text=True,
        cwd="/home/admin/Source/our-lady-book-pipeline",
    )
    assert result.returncode == 0, (
        f"draft --help failed: stdout={result.stdout} stderr={result.stderr}"
    )
    out = result.stdout.lower()
    assert "scene_id" in out
    assert "--max-regen" in out
    assert "--scene-yaml" in out
    assert "--dry-run" in out


# --------------------------------------------------------------------------- #
# Test B: --dry-run (NO LLM calls)                                             #
# --------------------------------------------------------------------------- #


def test_B_draft_dry_run_no_llm_calls(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    capsys: Any,
) -> None:
    """Test B: --dry-run loads stub yaml, calls bundler.bundle (real), prints
    pack.fingerprint, exits 0. No drafter/critic/regenerator calls fire."""
    import book_pipeline.cli.draft as draft_mod

    # Write a stub scene yaml into tmp_path so --scene-yaml points at it.
    stub_path = tmp_path / "ch01_sc01.yaml"
    stub_path.write_text(
        yaml.safe_dump(
            {
                "chapter": 1,
                "scene_index": 1,
                "beat_function": "first contact — opening voyage tension",
                "pov": "Andrés de Mora",
                "date_iso": "1519-02-18",
                "location": "Chapel of Havana",
                "word_target": 1000,
                "scene_type": "prose",
            }
        )
    )
    bundler = _FakeBundler(context_pack)

    drafter = _FakeDrafter(response=None, raise_exc=RuntimeError("must not be called"))
    critic = _FakeCritic(raise_exc=RuntimeError("must not be called"))

    composition_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=_FakeRegenerator(),
        scene_request=scene_request,
    )

    rc = draft_mod.run_dry_run(
        scene_id="ch01_sc01",
        composition_root=composition_root,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "ctxpack_fp_ch01_sc01" in out
    assert len(bundler.calls) == 1
    # Drafter/critic never invoked.
    assert drafter.calls == []
    assert critic.calls == []


# --------------------------------------------------------------------------- #
# Test C: Happy path (attempt 1 passes)                                         #
# --------------------------------------------------------------------------- #


def test_C_happy_path_critic_passes_first_attempt(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
) -> None:
    """Test C: PENDING → RAG_READY → DRAFTED_A → CRITIC_PASS → COMMITTED."""
    import book_pipeline.cli.draft as draft_mod

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    critic = _FakeCritic(pass_sequence=[True], issues_sequence=[[]])
    regenerator = _FakeRegenerator()

    composition_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
    )

    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01",
        max_regen=3,
        composition_root=composition_root,
    )
    assert rc == 0
    # State file: terminal state COMMITTED.
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    assert state_path.exists()
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.COMMITTED
    # drafts/ch01/ch01_sc01.md written.
    md_path = tmp_path / "drafts" / "ch01" / "ch01_sc01.md"
    assert md_path.exists()
    # Drafter called once; regenerator never called.
    assert len(drafter.calls) == 1
    assert len(critic.calls) == 1
    assert regenerator.calls == []


# --------------------------------------------------------------------------- #
# Test D: Regen-then-pass                                                       #
# --------------------------------------------------------------------------- #


def test_D_regen_then_pass(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mid_issue: CriticIssue,
) -> None:
    """Test D: critic fails attempt 1 (1 mid issue) → regen → passes attempt 2."""
    import book_pipeline.cli.draft as draft_mod

    regen_draft = canonical_draft.model_copy(
        update={"attempt_number": 2, "scene_text": canonical_draft.scene_text}
    )
    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    critic = _FakeCritic(
        pass_sequence=[False, True],
        issues_sequence=[[mid_issue], []],
    )
    regenerator = _FakeRegenerator(response_sequence=[regen_draft])

    composition_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
    )

    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=composition_root
    )
    assert rc == 0
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.COMMITTED
    # History must contain the full transition sequence.
    transitions = [h["to"] for h in rec.history]
    assert SceneState.RAG_READY.value in transitions
    assert SceneState.DRAFTED_A.value in transitions
    assert SceneState.CRITIC_FAIL.value in transitions
    assert SceneState.REGENERATING.value in transitions
    assert SceneState.CRITIC_PASS.value in transitions
    assert SceneState.COMMITTED.value in transitions
    # mode_a_regens counter: 1 regen fired.
    assert rec.attempts.get("mode_a_regens") == 1
    # Regenerator called exactly once.
    assert len(regenerator.calls) == 1


# --------------------------------------------------------------------------- #
# Test E: R-exhaustion                                                           #
# --------------------------------------------------------------------------- #


def test_E_r_exhaustion_hard_blocked(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mid_issue: CriticIssue,
) -> None:
    """Test E: critic fails all 4 attempts → HARD_BLOCKED('failed_critic_after_R_attempts').

    max_regen=3 means 1 original + 3 regens = 4 total attempts.
    """
    import book_pipeline.cli.draft as draft_mod

    regen_draft = canonical_draft.model_copy(update={"attempt_number": 2})

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    # All 4 attempts fail.
    critic = _FakeCritic(
        pass_sequence=[False, False, False, False],
        issues_sequence=[[mid_issue], [mid_issue], [mid_issue], [mid_issue]],
    )
    regenerator = _FakeRegenerator(response_sequence=[regen_draft, regen_draft, regen_draft])

    composition_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
    )

    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=composition_root
    )
    assert rc == 4
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.HARD_BLOCKED
    assert "failed_critic_after_R_attempts" in rec.blockers
    # No committed md.
    md_path = tmp_path / "drafts" / "ch01" / "ch01_sc01.md"
    assert not md_path.exists()


# --------------------------------------------------------------------------- #
# Test F: Drafter block                                                          #
# --------------------------------------------------------------------------- #


def test_F_drafter_block_hard_blocked(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
) -> None:
    """Test F: drafter raises ModeADrafterBlocked('training_bleed') → HARD_BLOCKED."""
    import book_pipeline.cli.draft as draft_mod
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(
        response=None,
        raise_exc=ModeADrafterBlocked("training_bleed", hits=["ngram1"]),
    )
    critic = _FakeCritic(pass_sequence=[], issues_sequence=[])
    regenerator = _FakeRegenerator()

    composition_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
    )

    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=composition_root
    )
    assert rc == 2
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.HARD_BLOCKED
    assert "training_bleed" in rec.blockers


# --------------------------------------------------------------------------- #
# Test G: Critic block                                                            #
# --------------------------------------------------------------------------- #


def test_G_critic_block_hard_blocked(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
) -> None:
    """Test G: critic raises SceneCriticError('anthropic_unavailable') → HARD_BLOCKED."""
    import book_pipeline.cli.draft as draft_mod
    from book_pipeline.critic.scene import SceneCriticError

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    critic = _FakeCritic(raise_exc=SceneCriticError("anthropic_unavailable"))
    regenerator = _FakeRegenerator()

    composition_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
    )

    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=composition_root
    )
    assert rc == 3
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.HARD_BLOCKED
    assert "anthropic_unavailable" in rec.blockers


# --------------------------------------------------------------------------- #
# Test H: B-3 invariant — voice_pin_sha == checkpoint_sha == draft.voice_pin_sha #
# --------------------------------------------------------------------------- #


def test_H_b3_invariant_voice_pin_sha_equals_checkpoint_sha(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
) -> None:
    """Test H (B-3 INVARIANT): committed frontmatter must have
    voice_pin_sha == checkpoint_sha == draft.voice_pin_sha.
    Both fields hold the SAME value; Phase 4 ChapterAssembler trusts this.
    """
    import book_pipeline.cli.draft as draft_mod

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    critic = _FakeCritic(pass_sequence=[True], issues_sequence=[[]])
    regenerator = _FakeRegenerator()

    composition_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
    )

    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=composition_root
    )
    assert rc == 0

    md_path = tmp_path / "drafts" / "ch01" / "ch01_sc01.md"
    content = md_path.read_text()
    assert content.startswith("---\n")
    # Extract YAML frontmatter.
    parts = content.split("---\n", 2)
    assert len(parts) == 3, f"Unexpected md structure: {parts[:2]}"
    frontmatter = yaml.safe_load(parts[1])
    # All 9 required keys present.
    required_keys = {
        "voice_pin_sha",
        "checkpoint_sha",
        "critic_scores_per_axis",
        "attempt_count",
        "ingestion_run_id",
        "draft_timestamp",
        "voice_fidelity_score",
        "mode",
        "rubric_version",
    }
    missing = required_keys - set(frontmatter.keys())
    assert not missing, f"frontmatter missing keys: {missing}"
    # B-3 INVARIANT: both fields hold draft.voice_pin_sha.
    assert frontmatter["voice_pin_sha"] == canonical_draft.voice_pin_sha
    assert frontmatter["checkpoint_sha"] == canonical_draft.voice_pin_sha
    assert frontmatter["voice_pin_sha"] == frontmatter["checkpoint_sha"]
    assert frontmatter["mode"] == "A"


# --------------------------------------------------------------------------- #
# Test I: _persist atomic write                                                 #
# --------------------------------------------------------------------------- #


def test_I_persist_atomic_write(
    tmp_path: Path,
    scene_request: SceneRequest,
) -> None:
    """Test I: if the tmp write fails (permission error), the existing
    state.json is NOT clobbered."""

    state_dir = tmp_path / "scene_buffer" / "ch01"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "ch01_sc01.state.json"

    # Pre-existing state.json we want to protect.
    original_record = SceneStateRecord(
        scene_id="ch01_sc01",
        state=SceneState.RAG_READY,
        attempts={},
        mode_tag=None,
        history=[],
        blockers=[],
    )
    state_path.write_text(original_record.model_dump_json(indent=2))
    original_content = state_path.read_text()

    # New record we try to persist — but tmp write will fail.
    new_record = SceneStateRecord(
        scene_id="ch01_sc01",
        state=SceneState.COMMITTED,
        attempts={},
        mode_tag="A",
        history=[],
        blockers=[],
    )

    # Monkeypatch Path.write_text to fail on the .tmp path.
    import book_pipeline.cli.draft as draft_module

    real_write_text = Path.write_text

    def failing_write(self: Path, data: str, *args: Any, **kwargs: Any) -> int:
        if str(self).endswith(".json.tmp"):
            raise PermissionError("simulated tmp-write failure")
        return real_write_text(self, data, *args, **kwargs)

    import pytest
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Path, "write_text", failing_write)
        with pytest.raises(PermissionError):
            draft_module._persist(new_record, state_path)

    # Original content unchanged.
    assert state_path.read_text() == original_content


# --------------------------------------------------------------------------- #
# Test J: Protocol conformance                                                   #
# --------------------------------------------------------------------------- #


def test_J_protocol_conformance() -> None:
    """Test J: FakeDrafter / FakeCritic / FakeRegenerator satisfy the FROZEN
    runtime_checkable Protocols."""
    drafter = _FakeDrafter(response=None, raise_exc=RuntimeError("unused"))
    critic = _FakeCritic(pass_sequence=[True], issues_sequence=[[]])
    regenerator = _FakeRegenerator(response_sequence=[])

    assert isinstance(drafter, Drafter)
    assert isinstance(critic, Critic)
    assert isinstance(regenerator, Regenerator)


# --------------------------------------------------------------------------- #
# Test K: regen word-count drift counts toward R                                 #
# --------------------------------------------------------------------------- #


def test_K_regen_word_count_drift_counts_toward_R(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mid_issue: CriticIssue,
) -> None:
    """Test K: regen raises RegenWordCountDrift on attempt 2; critic fails
    attempts 1/3/4 → HARD_BLOCKED('failed_critic_after_R_attempts').
    The drift counts toward R (does not reset the budget).
    """
    import book_pipeline.cli.draft as draft_mod

    regen_draft = canonical_draft.model_copy(update={"attempt_number": 3})

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    # Critic fails 1, 3, 4. Attempt 2 never reaches critic (regen drifted).
    critic = _FakeCritic(
        pass_sequence=[False, False, False],
        issues_sequence=[[mid_issue], [mid_issue], [mid_issue]],
    )
    drift_exc = RegenWordCountDrift(prior_word_count=1000, new_word_count=500, drift_pct=0.5)
    regenerator = _FakeRegenerator(
        response_sequence=[drift_exc, regen_draft, regen_draft]
    )

    composition_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
    )

    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=composition_root
    )
    assert rc == 4
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.HARD_BLOCKED
    assert "failed_critic_after_R_attempts" in rec.blockers
    # History records the regen failure.
    history_notes = [h.get("note", "") for h in rec.history]
    assert any(
        "RegenWordCountDrift" in n or "regen_failed" in n for n in history_notes
    ), f"expected regen failure note in history, got: {history_notes}"
