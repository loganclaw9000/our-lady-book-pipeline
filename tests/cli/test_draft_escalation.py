"""Tests for cli/draft.py scene-loop escalation routing (Plan 05-02 Task 3).

Unit-level — mocked drafter / critic / regenerator / mode_b_drafter. No real
Anthropic / no real vLLM / no real network. All 4 escalation triggers
(preflag, oscillation, spend_cap, r_cap_exhausted) funnel through a single
canonical role='mode_escalation' Event per D-08.

tests/cli/test_draft_spend_cap.py carries the 4 spend-cap specific tests;
tests/integration/test_scene_loop_escalation.py carries the end-to-end
parametrized branch coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from book_pipeline.drafter.mode_b import ModeBDrafterBlocked
from book_pipeline.interfaces.types import (
    ContextPack,
    CriticIssue,
    CriticResponse,
    DraftResponse,
    Event,
    RetrievalResult,
    SceneRequest,
    SceneState,
    SceneStateRecord,
)


# --- Fake components (kept local so we don't couple to test_draft_loop) ----- #


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


@dataclass
class _FakeDraftResponse:
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
        assert self._response is not None
        return self._response


class _FakeCritic:
    level: str = "scene"

    def __init__(
        self,
        *,
        pass_sequence: list[bool] | None = None,
        issues_sequence: list[list[CriticIssue]] | None = None,
    ) -> None:
        self._pass_sequence = pass_sequence or []
        self._issues_sequence = issues_sequence or []
        self._call_idx = 0
        self.calls: list[Any] = []

    def review(self, request: Any) -> CriticResponse:
        self.calls.append(request)
        idx = self._call_idx
        self._call_idx += 1
        if idx >= len(self._pass_sequence):
            raise RuntimeError(f"_FakeCritic exhausted at call {idx + 1}")
        overall_pass = self._pass_sequence[idx]
        issues = self._issues_sequence[idx] if idx < len(self._issues_sequence) else []
        return CriticResponse(
            pass_per_axis={a: overall_pass for a in ("historical", "metaphysics", "entity", "arc", "donts")},
            scores_per_axis={a: 80.0 if overall_pass else 55.0 for a in ("historical", "metaphysics", "entity", "arc", "donts")},
            issues=issues,
            overall_pass=overall_pass,
            model_id="claude-opus-4-7",
            rubric_version="v1",
            output_sha="critic_fake_sha",
        )


class _FakeRegenerator:
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
            raise RuntimeError(f"_FakeRegenerator exhausted at call {idx + 1}")
        item = self._response_sequence[idx]
        if isinstance(item, Exception):
            raise item
        return item


class _FakeBundler:
    def __init__(self, pack: ContextPack) -> None:
        self._pack = pack
        self.calls: list[Any] = []

    def bundle(self, request: Any, retrievers: list[Any]) -> ContextPack:
        self.calls.append((request, retrievers))
        return self._pack


class _FakeModeBDrafter:
    """Fake ModeBDrafter — Protocol-conformant stub."""

    mode: str = "B"

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
        assert self._response is not None
        return self._response


# --- Fixtures -------------------------------------------------------------- #


@pytest.fixture
def scene_request() -> SceneRequest:
    return SceneRequest(
        chapter=1,
        scene_index=1,
        pov="Andrés de Mora",
        date_iso="1519-02-18",
        location="Chapel of Havana",
        beat_function="first contact",
    )


@pytest.fixture
def context_pack(scene_request: SceneRequest) -> ContextPack:
    return ContextPack(
        scene_request=scene_request,
        retrievals={
            axis: RetrievalResult(
                retriever_name=axis,
                hits=[],
                bytes_used=0,
                query_fingerprint="fp_" + axis,
            )
            for axis in ("historical", "metaphysics", "entity_state", "arc_position", "negative_constraint")
        },
        total_bytes=0,
        assembly_strategy="round_robin",
        fingerprint="ctxpack_fp_ch01_sc01",
    )


@pytest.fixture
def canonical_draft() -> DraftResponse:
    return DraftResponse(
        scene_text="Andrés knelt in the chapel. " * 50,
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
def mode_b_draft() -> DraftResponse:
    return DraftResponse(
        scene_text="Opus-rendered scene. " * 50,
        mode="B",
        model_id="claude-opus-4-7",
        voice_pin_sha="sha_voice_pin_v6",
        tokens_in=1200,
        tokens_out=800,
        latency_ms=3000,
        output_sha="mode_b_sha",
        attempt_number=1,
    )


@pytest.fixture
def mid_issue() -> CriticIssue:
    return CriticIssue(
        axis="historical",
        severity="mid",
        location="paragraph 2",
        claim="date off",
        evidence="outline says Feb 18",
    )


def _make_composition_root(
    *,
    tmp_path: Path,
    bundler: Any,
    drafter: Any,
    critic: Any,
    regenerator: Any,
    scene_request: SceneRequest,
    preflag_set: frozenset[str] = frozenset(),
    mode_b_drafter: Any | None = None,
    spend_cap_usd: float = 0.75,
    pricing_by_model: dict[str, Any] | None = None,
    event_logger: Any | None = None,
) -> SimpleNamespace:
    """Composition-root stub with Plan 05-02 additions (preflag/pricing/mode_b)."""
    from book_pipeline.config.pricing import PricingConfig

    if pricing_by_model is None:
        pricing_by_model = PricingConfig().by_model
    return SimpleNamespace(
        bundler=bundler,
        retrievers=[],
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        rubric=SimpleNamespace(rubric_version="v1"),
        state_dir=tmp_path / "scene_buffer",
        commit_dir=tmp_path / "drafts",
        ingestion_run_id="ing_test_001",
        anchor_set_sha=None,
        event_logger=event_logger if event_logger is not None else _FakeEventLogger(),
        # Plan 05-02 additions:
        preflag_set=preflag_set,
        mode_b_drafter=mode_b_drafter,
        pricing_by_model=pricing_by_model,
        spend_cap_usd_per_scene=spend_cap_usd,
    )


# --- Tests ----------------------------------------------------------------- #


def test_preflag_routes_to_mode_b_before_mode_a(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mode_b_draft: DraftResponse,
) -> None:
    """scene_id in preflag_set → ModeBDrafter.draft() called; Mode-A skipped."""
    import book_pipeline.cli.draft as draft_mod

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft, raise_exc=RuntimeError("mode-A must not fire"))
    # Mode-B critic path needs 1 PASS
    critic = _FakeCritic(pass_sequence=[True], issues_sequence=[[]])
    regenerator = _FakeRegenerator()
    mode_b = _FakeModeBDrafter(response=mode_b_draft)
    logger = _FakeEventLogger()

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        preflag_set=frozenset({"ch01_sc01"}),
        mode_b_drafter=mode_b,
        event_logger=logger,
    )
    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    # Mode-B drafter called exactly once; Mode-A never called.
    assert len(mode_b.calls) == 1
    assert drafter.calls == []
    # Exactly one role='mode_escalation' Event with trigger='preflag'.
    escalations = [e for e in logger.events if e.role == "mode_escalation"]
    assert len(escalations) == 1
    assert escalations[0].extra.get("trigger") == "preflag"
    assert escalations[0].extra.get("from_mode") == "A"
    assert escalations[0].extra.get("to_mode") == "B"
    # Terminal state COMMITTED (Mode-B passed critic on attempt 1).
    assert rc == 0


def test_r_cap_exhaust_escalates_to_mode_b(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mode_b_draft: DraftResponse,
    mid_issue: CriticIssue,
) -> None:
    """4 critic fails (1 initial + 3 regens) -> Mode-B escalation."""
    import book_pipeline.cli.draft as draft_mod

    regen_draft = canonical_draft.model_copy(update={"attempt_number": 2})
    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    # 4 Mode-A critic fails + 1 Mode-B critic pass = 5 review calls total.
    critic = _FakeCritic(
        pass_sequence=[False, False, False, False, True],
        issues_sequence=[[mid_issue], [mid_issue], [mid_issue], [mid_issue], []],
    )
    regenerator = _FakeRegenerator(response_sequence=[regen_draft, regen_draft, regen_draft])
    mode_b = _FakeModeBDrafter(response=mode_b_draft)
    logger = _FakeEventLogger()

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        mode_b_drafter=mode_b,
        event_logger=logger,
    )
    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    assert rc == 0  # Mode-B passed
    # Exactly one mode_escalation Event with trigger='r_cap_exhausted'.
    escalations = [e for e in logger.events if e.role == "mode_escalation"]
    assert len(escalations) == 1
    assert escalations[0].extra.get("trigger") == "r_cap_exhausted"
    # issue_ids extracted from last critic response (historical:mid).
    issue_ids = escalations[0].extra.get("issue_ids") or []
    assert "historical:mid" in issue_ids
    # Mode-B drafter called exactly once.
    assert len(mode_b.calls) == 1


def test_oscillation_escalates_before_r_exhausted(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mode_b_draft: DraftResponse,
    mid_issue: CriticIssue,
) -> None:
    """Attempts 1 and 3 share identical axis+severity -> oscillation fires at
    attempt 3; Mode-B fires immediately; attempt 4 never runs."""
    import book_pipeline.cli.draft as draft_mod

    # Issue 1 + 3 share (historical, mid); issue 2 is (arc, high).
    issue_a = mid_issue  # (historical, mid)
    issue_b = CriticIssue(
        axis="arc",
        severity="high",
        location="paragraph 3",
        claim="arc issue",
        evidence="x",
    )
    regen_draft = canonical_draft.model_copy(update={"attempt_number": 2})
    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    # Attempts 1, 2, 3 fail with respective issues; attempt 4 would be issue_a again.
    # Mode-B pass is the 4th critic call (mid-sequence).
    critic = _FakeCritic(
        pass_sequence=[False, False, False, True],
        issues_sequence=[[issue_a], [issue_b], [issue_a], []],
    )
    regenerator = _FakeRegenerator(response_sequence=[regen_draft, regen_draft, regen_draft])
    mode_b = _FakeModeBDrafter(response=mode_b_draft)
    logger = _FakeEventLogger()

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        mode_b_drafter=mode_b,
        event_logger=logger,
    )
    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    assert rc == 0  # Mode-B passed
    escalations = [e for e in logger.events if e.role == "mode_escalation"]
    assert len(escalations) == 1
    assert escalations[0].extra.get("trigger") == "oscillation"
    # Mode-A drafter was called once (attempt 1); regen called 2 times
    # (attempts 2 + 3); NO 4th regen (oscillation fires first).
    assert len(drafter.calls) == 1
    assert len(regenerator.calls) == 2
    # Mode-B fired exactly once.
    assert len(mode_b.calls) == 1


def test_mode_b_exhaustion_triggers_hard_block(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
) -> None:
    """ModeBDrafter raises ModeBDrafterBlocked -> HARD_BLOCKED('mode_b_exhausted')."""
    import book_pipeline.cli.draft as draft_mod

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft, raise_exc=RuntimeError("must not fire"))
    critic = _FakeCritic(pass_sequence=[], issues_sequence=[])
    regenerator = _FakeRegenerator()
    # ModeBDrafter raises on first call.
    mode_b = _FakeModeBDrafter(
        raise_exc=ModeBDrafterBlocked(
            "anthropic_transient_exhausted", scene_id="ch01_sc01", attempt_number=1
        ),
    )
    logger = _FakeEventLogger()

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        preflag_set=frozenset({"ch01_sc01"}),  # route direct to Mode-B
        mode_b_drafter=mode_b,
        event_logger=logger,
    )
    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    assert rc == 3  # hard-block exit
    # Scene state HARD_BLOCKED with 'mode_b_exhausted' blocker.
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.HARD_BLOCKED
    assert "mode_b_exhausted" in rec.blockers
    # Mode-B called once; no subsequent attempts.
    assert len(mode_b.calls) == 1


def test_mode_escalation_event_shape(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mode_b_draft: DraftResponse,
) -> None:
    """Verify exact Event structure per D-08: role='mode_escalation',
    extra = {from_mode, to_mode, trigger, issue_ids}."""
    import book_pipeline.cli.draft as draft_mod

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft, raise_exc=RuntimeError("mode-A must not fire"))
    critic = _FakeCritic(pass_sequence=[True], issues_sequence=[[]])
    regenerator = _FakeRegenerator()
    mode_b = _FakeModeBDrafter(response=mode_b_draft)
    logger = _FakeEventLogger()

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        preflag_set=frozenset({"ch01_sc01"}),
        mode_b_drafter=mode_b,
        event_logger=logger,
    )
    draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    escalations = [e for e in logger.events if e.role == "mode_escalation"]
    assert len(escalations) == 1
    event = escalations[0]
    # Exact shape per D-08.
    assert event.role == "mode_escalation"
    assert event.extra.get("from_mode") == "A"
    assert event.extra.get("to_mode") == "B"
    assert event.extra.get("trigger") in ("preflag", "oscillation", "spend_cap_exceeded", "r_cap_exhausted")
    assert isinstance(event.extra.get("issue_ids"), list)
    # caller_context.scene_id populated.
    assert event.caller_context.get("scene_id") == "ch01_sc01"
