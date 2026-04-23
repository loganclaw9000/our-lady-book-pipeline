"""Integration test covering all 4 Plan 05-02 scene-loop escalation branches.

Parametrized over (preflag, r_cap_exhausted, oscillation, spend_cap_exceeded):
each scenario reaches its expected terminal state AND emits exactly one
role='mode_escalation' Event with the matching trigger.

Fully in-process: no real vLLM, no real Anthropic, no real git push, no real
network. Uses tmp_path (git init) + shared fakes local to this test module.
Wall-time target <10s — no tenacity waits fire because no real client is
invoked from this test's fake drafters.
"""
from __future__ import annotations

import subprocess
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


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)

    def preseed(self, event: Event) -> None:
        self.events.append(event)


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
        pass_sequence: list[bool],
        issues_sequence: list[list[CriticIssue]],
    ) -> None:
        self._pass_sequence = pass_sequence
        self._issues_sequence = issues_sequence
        self._call_idx = 0
        self.calls: list[Any] = []

    def review(self, request: Any) -> CriticResponse:
        self.calls.append(request)
        idx = self._call_idx
        self._call_idx += 1
        if idx >= len(self._pass_sequence):
            raise RuntimeError(f"critic exhausted at call {idx + 1}")
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
    def __init__(self, *, response_sequence: list[Any]) -> None:
        self._response_sequence = response_sequence
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


class _FakeModeBDrafter:
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


def _expensive_critic_event(*, scene_id: str, usd_share: float) -> Event:
    output_tokens = int(usd_share * 1_000_000 / 25.0)
    return Event(
        event_id=f"seed_{scene_id}_{output_tokens}",
        ts_iso="2026-04-23T00:00:00Z",
        role="critic",
        model="claude-opus-4-7",
        prompt_hash="p",
        input_tokens=0,
        cached_tokens=0,
        output_tokens=output_tokens,
        latency_ms=10,
        caller_context={"scene_id": scene_id},
        output_hash="o",
        extra={},
    )


def _scene_request() -> SceneRequest:
    return SceneRequest(
        chapter=1,
        scene_index=1,
        pov="Andrés",
        date_iso="1519-02-18",
        location="Havana",
        beat_function="bf",
    )


def _context_pack() -> ContextPack:
    return ContextPack(
        scene_request=_scene_request(),
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
        fingerprint="fp",
    )


def _canonical_draft() -> DraftResponse:
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


def _mode_b_draft() -> DraftResponse:
    return DraftResponse(
        scene_text="mode-b prose " * 50,
        mode="B",
        model_id="claude-opus-4-7",
        voice_pin_sha="sha",
        tokens_in=1500,
        tokens_out=800,
        latency_ms=3000,
        output_sha="mb",
        attempt_number=1,
    )


def _make_composition_root(
    *,
    tmp_path: Path,
    bundler: Any,
    drafter: Any,
    critic: Any,
    regenerator: Any,
    event_logger: Any,
    mode_b_drafter: Any,
    preflag_set: frozenset[str] = frozenset(),
    spend_cap_usd: float = 0.75,
) -> SimpleNamespace:
    from book_pipeline.config.pricing import PricingConfig

    return SimpleNamespace(
        bundler=bundler,
        retrievers=[],
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=_scene_request(),
        rubric=SimpleNamespace(rubric_version="v1"),
        state_dir=tmp_path / "scene_buffer",
        commit_dir=tmp_path / "drafts",
        ingestion_run_id="ing",
        anchor_set_sha=None,
        event_logger=event_logger,
        preflag_set=preflag_set,
        mode_b_drafter=mode_b_drafter,
        pricing_by_model=PricingConfig().by_model,
        spend_cap_usd_per_scene=spend_cap_usd,
    )


def _init_git(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=main", str(tmp_path)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@e.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "T"],
        check=True,
    )


@pytest.mark.parametrize(
    "branch",
    ["preflag", "r_cap_exhausted", "oscillation", "spend_cap_exceeded"],
)
def test_all_four_branches_in_one_run(
    branch: str, tmp_path: Path
) -> None:
    """Each of the 4 triggers reaches its expected terminal state and emits
    exactly one mode_escalation Event with the matching trigger."""
    import book_pipeline.cli.draft as draft_mod

    _init_git(tmp_path)
    bundler = _FakeBundler(_context_pack())
    canonical = _canonical_draft()
    mode_b = _mode_b_draft()
    logger = _FakeEventLogger()

    if branch == "preflag":
        drafter = _FakeDrafter(response=canonical, raise_exc=RuntimeError("mode-A must not fire"))
        critic = _FakeCritic(pass_sequence=[True], issues_sequence=[[]])
        regenerator = _FakeRegenerator(response_sequence=[])
        mode_b_drafter = _FakeModeBDrafter(response=mode_b)
        comp_root = _make_composition_root(
            tmp_path=tmp_path,
            bundler=bundler, drafter=drafter, critic=critic, regenerator=regenerator,
            event_logger=logger, mode_b_drafter=mode_b_drafter,
            preflag_set=frozenset({"ch01_sc01"}),
        )
        rc = draft_mod.run_draft_loop("ch01_sc01", max_regen=3, composition_root=comp_root)
        assert rc == 0
        expected_trigger = "preflag"
    elif branch == "r_cap_exhausted":
        # Rotate axis+severity each attempt so oscillation doesn't fire
        # before R exhaustion.
        i1 = CriticIssue(axis="historical", severity="mid", location="p", claim="c", evidence="e")
        i2 = CriticIssue(axis="arc", severity="high", location="p", claim="c", evidence="e")
        i3 = CriticIssue(axis="metaphysics", severity="mid", location="p", claim="c", evidence="e")
        i4 = CriticIssue(axis="donts", severity="high", location="p", claim="c", evidence="e")
        regen = canonical.model_copy(update={"attempt_number": 2})
        drafter = _FakeDrafter(response=canonical)
        critic = _FakeCritic(
            pass_sequence=[False, False, False, False, True],
            issues_sequence=[[i1], [i2], [i3], [i4], []],
        )
        regenerator = _FakeRegenerator(response_sequence=[regen, regen, regen])
        mode_b_drafter = _FakeModeBDrafter(response=mode_b)
        comp_root = _make_composition_root(
            tmp_path=tmp_path,
            bundler=bundler, drafter=drafter, critic=critic, regenerator=regenerator,
            event_logger=logger, mode_b_drafter=mode_b_drafter,
        )
        rc = draft_mod.run_draft_loop("ch01_sc01", max_regen=3, composition_root=comp_root)
        assert rc == 0
        expected_trigger = "r_cap_exhausted"
    elif branch == "oscillation":
        issue_a = CriticIssue(
            axis="historical", severity="mid", location="p1",
            claim="hist", evidence="e",
        )
        issue_b = CriticIssue(
            axis="arc", severity="high", location="p2",
            claim="arc", evidence="e",
        )
        regen = canonical.model_copy(update={"attempt_number": 2})
        drafter = _FakeDrafter(response=canonical)
        # Attempt 1, 3 = issue_a (oscillation); attempt 2 = issue_b.
        critic = _FakeCritic(
            pass_sequence=[False, False, False, True],
            issues_sequence=[[issue_a], [issue_b], [issue_a], []],
        )
        regenerator = _FakeRegenerator(response_sequence=[regen, regen, regen])
        mode_b_drafter = _FakeModeBDrafter(response=mode_b)
        comp_root = _make_composition_root(
            tmp_path=tmp_path,
            bundler=bundler, drafter=drafter, critic=critic, regenerator=regenerator,
            event_logger=logger, mode_b_drafter=mode_b_drafter,
        )
        rc = draft_mod.run_draft_loop("ch01_sc01", max_regen=3, composition_root=comp_root)
        assert rc == 0
        expected_trigger = "oscillation"
    elif branch == "spend_cap_exceeded":
        issue = CriticIssue(
            axis="historical", severity="mid", location="p1",
            claim="c", evidence="e",
        )
        regen = canonical.model_copy(update={"attempt_number": 2})
        drafter = _FakeDrafter(response=canonical)
        critic = _FakeCritic(pass_sequence=[False], issues_sequence=[[issue]])
        regenerator = _FakeRegenerator(response_sequence=[regen, regen, regen])
        mode_b_drafter = _FakeModeBDrafter(raise_exc=ModeBDrafterBlocked("must not fire", scene_id="x"))
        # Pre-seed expensive events to trip cap on first boundary.
        logger.preseed(_expensive_critic_event(scene_id="ch01_sc01", usd_share=0.80))
        comp_root = _make_composition_root(
            tmp_path=tmp_path,
            bundler=bundler, drafter=drafter, critic=critic, regenerator=regenerator,
            event_logger=logger, mode_b_drafter=mode_b_drafter,
            spend_cap_usd=0.75,
        )
        rc = draft_mod.run_draft_loop("ch01_sc01", max_regen=3, composition_root=comp_root)
        assert rc == 4
        # scene_state HARD_BLOCKED
        state_path = tmp_path / "scene_buffer" / "ch01" / "ch01_sc01.state.json"
        rec = SceneStateRecord.model_validate_json(state_path.read_text())
        assert rec.state == SceneState.HARD_BLOCKED
        expected_trigger = "spend_cap_exceeded"
    else:
        raise AssertionError(f"bad branch: {branch}")

    # Common assertion: exactly 1 mode_escalation Event with expected trigger.
    escalations = [e for e in logger.events if e.role == "mode_escalation"]
    assert len(escalations) == 1, f"[{branch}] expected 1 escalation, got {len(escalations)}"
    assert escalations[0].extra.get("trigger") == expected_trigger
