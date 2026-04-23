"""Tests for cli/draft.py per-scene USD spend cap (Plan 05-02 Task 3 / D-06).

Cumulative sum of event_cost_usd(event, pricing) across scene events reaches
threshold -> HARD_BLOCKED('spend_cap_exceeded') + role='mode_escalation' with
trigger='spend_cap_exceeded'. Mode-A attempt budget is independent of R-cap;
spend-cap fires first when it trips.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

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


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)

    def preseed(self, event: Event) -> None:
        """Inject a synthetic event into the scene trail (no emit)."""
        self.events.append(event)


class _FakeDrafter:
    mode: str = "A"

    def __init__(self, *, response: DraftResponse) -> None:
        self._response = response
        self.calls: list[Any] = []

    def draft(self, request: Any) -> DraftResponse:
        self.calls.append(request)
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
            output_sha="sha",
        )


class _FakeRegenerator:
    def __init__(self, *, response_sequence: list[Any] | None = None) -> None:
        self._response_sequence = response_sequence or []
        self._call_idx = 0
        self.calls: list[Any] = []

    def regenerate(self, request: Any) -> DraftResponse:
        self.calls.append(request)
        idx = self._call_idx
        self._call_idx += 1
        return self._response_sequence[idx]


class _FakeBundler:
    def __init__(self, pack: ContextPack) -> None:
        self._pack = pack

    def bundle(self, request: Any, retrievers: list[Any]) -> ContextPack:
        return self._pack


@dataclass
class _FakeModeBDrafter:
    mode: str = "B"

    def __post_init__(self) -> None:
        self.calls: list[Any] = []

    def draft(self, request: Any) -> DraftResponse:
        self.calls.append(request)
        raise RuntimeError("mode-B must not fire when spend-cap fires first")


# --- Fixtures -------------------------------------------------------------- #


@pytest.fixture
def scene_request() -> SceneRequest:
    return SceneRequest(
        chapter=1,
        scene_index=1,
        pov="Andrés",
        date_iso="1519-02-18",
        location="Havana",
        beat_function="bf",
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
                query_fingerprint="fp",
            )
            for axis in ("historical", "metaphysics", "entity_state", "arc_position", "negative_constraint")
        },
        total_bytes=0,
        assembly_strategy="round_robin",
        fingerprint="ctxfp_ch01_sc01",
    )


@pytest.fixture
def canonical_draft() -> DraftResponse:
    return DraftResponse(
        scene_text="x" * 100,
        mode="A",
        model_id="paul-voice",
        voice_pin_sha="sha",
        tokens_in=500,
        tokens_out=200,
        latency_ms=1,
        output_sha="draft",
        attempt_number=1,
    )


@pytest.fixture
def mid_issue() -> CriticIssue:
    return CriticIssue(
        axis="historical",
        severity="mid",
        location="para 1",
        claim="x",
        evidence="y",
    )


def _expensive_event(
    *, scene_id: str, usd_share: float, model: str = "claude-opus-4-7"
) -> Event:
    """Forge an Event whose tokens convert (via pricing) to ~usd_share USD.

    Opus 4.7: input=$5/MTok, output=$25/MTok. 50k input + 20k output = $0.25 + $0.50 = $0.75.
    For a $0.60 single event: input_tokens=60_000, output_tokens=19_200 -> $0.30+$0.48 = $0.78 (close enough).
    We aim for usd_share via output tokens alone for simplicity.
    """
    output_tokens = int(usd_share * 1_000_000 / 25.0)
    return Event(
        event_id=f"seed_{scene_id}_{output_tokens}",
        ts_iso="2026-04-23T00:00:00Z",
        role="critic",
        model=model,
        prompt_hash="p",
        input_tokens=0,
        cached_tokens=0,
        output_tokens=output_tokens,
        latency_ms=10,
        caller_context={"scene_id": scene_id},
        output_hash="o",
        extra={},
    )


def _make_composition_root(
    *,
    tmp_path: Path,
    bundler: Any,
    drafter: Any,
    critic: Any,
    regenerator: Any,
    scene_request: SceneRequest,
    event_logger: Any,
    spend_cap_usd: float = 0.75,
    pricing_by_model: dict[str, Any] | None = None,
    mode_b_drafter: Any | None = None,
    preflag_set: frozenset[str] = frozenset(),
) -> SimpleNamespace:
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
        event_logger=event_logger,
        preflag_set=preflag_set,
        mode_b_drafter=mode_b_drafter if mode_b_drafter is not None else _FakeModeBDrafter(),
        pricing_by_model=pricing_by_model,
        spend_cap_usd_per_scene=spend_cap_usd,
    )


# --- Tests ----------------------------------------------------------------- #


def test_spend_cap_fires_at_cumulative_threshold(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mid_issue: CriticIssue,
) -> None:
    """Seed event logger with ~$0.60 of prior scene events; after a failing
    critic attempt that adds more cost, total exceeds $0.75 -> HARD_BLOCKED."""
    import book_pipeline.cli.draft as draft_mod

    regen_draft = canonical_draft.model_copy(update={"attempt_number": 2})
    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    # First critic attempt fails with mid issue; loop should spend-cap before
    # reaching the R-cap boundary. We seed lots of prior cost so attempt 1's
    # critic Event alone pushes us past $0.75.
    critic = _FakeCritic(pass_sequence=[False], issues_sequence=[[mid_issue]])
    regenerator = _FakeRegenerator(response_sequence=[regen_draft, regen_draft, regen_draft])
    logger = _FakeEventLogger()
    # Pre-seed $0.80 worth of events for ch01_sc01 — trips cap immediately.
    logger.preseed(_expensive_event(scene_id="ch01_sc01", usd_share=0.80))

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        event_logger=logger,
        spend_cap_usd=0.75,
    )
    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    assert rc == 4  # hard-block exit
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.HARD_BLOCKED
    assert "spend_cap_exceeded" in rec.blockers
    # mode_escalation event with trigger='spend_cap_exceeded'.
    escalations = [e for e in logger.events if e.role == "mode_escalation"]
    assert len(escalations) == 1
    assert escalations[0].extra.get("trigger") == "spend_cap_exceeded"
    # Mode-B drafter NOT called (spend-cap = dead stop, not escalation).
    assert comp_root.mode_b_drafter.calls == []


def test_spend_cap_below_threshold_no_trip(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
) -> None:
    """Cumulative $0.10 << $0.75 — loop proceeds normally (COMMITTED)."""
    import book_pipeline.cli.draft as draft_mod

    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    critic = _FakeCritic(pass_sequence=[True], issues_sequence=[[]])
    regenerator = _FakeRegenerator()
    logger = _FakeEventLogger()
    # Seed tiny amount.
    logger.preseed(_expensive_event(scene_id="ch01_sc01", usd_share=0.10))

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        event_logger=logger,
        spend_cap_usd=0.75,
    )
    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    assert rc == 0  # COMMITTED
    # No mode_escalation with spend_cap_exceeded trigger.
    escalations = [
        e for e in logger.events
        if e.role == "mode_escalation" and e.extra.get("trigger") == "spend_cap_exceeded"
    ]
    assert escalations == []


def test_spend_cap_respects_config(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mid_issue: CriticIssue,
) -> None:
    """Configure spend_cap=$0.10; first fail trips immediately."""
    import book_pipeline.cli.draft as draft_mod

    regen_draft = canonical_draft.model_copy(update={"attempt_number": 2})
    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    critic = _FakeCritic(pass_sequence=[False], issues_sequence=[[mid_issue]])
    regenerator = _FakeRegenerator(response_sequence=[regen_draft] * 3)
    logger = _FakeEventLogger()
    # Pre-seed $0.15 (> $0.10 cap).
    logger.preseed(_expensive_event(scene_id="ch01_sc01", usd_share=0.15))

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        event_logger=logger,
        spend_cap_usd=0.10,  # tight cap
    )
    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    assert rc == 4
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.HARD_BLOCKED


def test_spend_cap_counts_prior_events_across_roles(
    tmp_path: Path,
    scene_request: SceneRequest,
    context_pack: ContextPack,
    canonical_draft: DraftResponse,
    mid_issue: CriticIssue,
) -> None:
    """Cumulative sum includes drafter + critic + regenerator + mode_b events
    (all events tagged caller_context.scene_id)."""
    import book_pipeline.cli.draft as draft_mod

    regen_draft = canonical_draft.model_copy(update={"attempt_number": 2})
    bundler = _FakeBundler(context_pack)
    drafter = _FakeDrafter(response=canonical_draft)
    critic = _FakeCritic(pass_sequence=[False], issues_sequence=[[mid_issue]])
    regenerator = _FakeRegenerator(response_sequence=[regen_draft] * 3)
    logger = _FakeEventLogger()
    # 3 events across different roles summing to $0.80.
    for role_name, share in (
        ("drafter", 0.30),
        ("critic", 0.30),
        ("regenerator", 0.20),
    ):
        e = _expensive_event(scene_id="ch01_sc01", usd_share=share)
        # Clone shape but set role:
        e2 = e.model_copy(update={"role": role_name})
        logger.preseed(e2)

    comp_root = _make_composition_root(
        tmp_path=tmp_path,
        bundler=bundler,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        event_logger=logger,
        spend_cap_usd=0.75,
    )
    rc = draft_mod.run_draft_loop(
        scene_id="ch01_sc01", max_regen=3, composition_root=comp_root
    )
    assert rc == 4  # spend cap trips (seeded $0.80 > $0.75)
    state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
    rec = SceneStateRecord.model_validate_json(state_path.read_text())
    assert rec.state == SceneState.HARD_BLOCKED
    assert "spend_cap_exceeded" in rec.blockers
