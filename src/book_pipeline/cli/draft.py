"""`book-pipeline draft <scene_id>` — full Phase 3 scene-loop composition root.

Plan 03-07. Composes (bundler + retrievers via W-1 factory + drafter +
critic + regenerator + SceneStateMachine) into a single CLI invocation that
consumes a hand-authored SceneRequest stub (scenes/ch{NN}/{scene_id}.yaml)
and produces either a COMMITTED scene on disk (drafts/ch{NN}/{scene_id}.md
with YAML frontmatter) or a HARD_BLOCKED SceneStateRecord (in
drafts/scene_buffer/ch{NN}/{scene_id}.state.json).

This module is the ONE composition site that wires the 6 Phase 3 kernel
components together. Every other module in book_pipeline.{drafter, critic,
regenerator, rag, voice_fidelity} stays kernel-clean; the 3 direct book-domain
imports below (vllm_endpoints, training_corpus, corpus_paths) are documented
composition seams via pyproject.toml import-linter ignore_imports (ADR-004 /
Plan 02-06 precedent). The Nahuatl entity set is accessed indirectly via the
cli/_entity_list.build_nahuatl_entity_set() bridge which owns its own
exemption — no duplicate cli.draft → nahuatl_entities edge is needed.

Flags:
  scene_id                Positional, e.g. "ch01_sc01".
  --max-regen N           Regen budget R (default 3 = 1 original + 3 regens = 4 total).
  --scene-yaml PATH       Override auto-resolved scenes/{chapter}/{scene_id}.yaml.
  --dry-run               Load stub + bundle ContextPack + print fingerprint; NO LLM calls.

Exit codes:
  0  COMMITTED          — scene passed critic; md written with frontmatter.
  2  drafter_blocked    — ModeADrafterBlocked (training_bleed / invalid_scene_type / ...).
  3  critic_blocked     — SceneCriticError (anthropic_unavailable).
  4  hard_blocked       — failed_critic_after_R_attempts OR regen-unavailable at R.
  5  unreachable        — defensive, should never fire.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from book_pipeline.cli.main import register_subcommand
from book_pipeline.interfaces.scene_state_machine import transition
from book_pipeline.interfaces.types import (
    CriticRequest,
    DraftRequest,
    Event,
    RegenRequest,
    SceneRequest,
    SceneState,
    SceneStateRecord,
)
from book_pipeline.observability.hashing import event_id, hash_text

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

_SCENE_ID_RE = re.compile(r"^ch(\d+)_sc(\d+)$")


# --------------------------------------------------------------------------- #
# Composition root dataclass                                                   #
# --------------------------------------------------------------------------- #


@dataclass
class CompositionRoot:
    """Bag of fully-constructed Phase 3 components for run_draft_loop.

    Built once per CLI invocation by _build_composition_root; tests override
    individual components via the _make_composition_root helper.
    """

    bundler: Any
    retrievers: list[Any]
    drafter: Any
    critic: Any
    regenerator: Any
    scene_request: SceneRequest
    rubric: Any
    state_dir: Path
    commit_dir: Path
    ingestion_run_id: str | None = None
    anchor_set_sha: str | None = None
    event_logger: Any | None = None


# --------------------------------------------------------------------------- #
# Argparse wiring                                                              #
# --------------------------------------------------------------------------- #


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "draft",
        help=(
            "Run the full Phase 3 scene loop for <scene_id>: bundle ContextPack, "
            "draft (Mode-A), critic, regen (up to --max-regen), commit or hard-block."
        ),
    )
    p.add_argument(
        "scene_id",
        help="Scene identifier matching ch(\\d+)_sc(\\d+), e.g. ch01_sc01.",
    )
    p.add_argument(
        "--max-regen",
        type=int,
        default=3,
        help="Regen budget R (default 3; total attempts = 1 + max_regen).",
    )
    p.add_argument(
        "--scene-yaml",
        type=str,
        default=None,
        help="Override auto-resolved scenes/{chapter}/{scene_id}.yaml path.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Load stub + build SceneRequest + call bundler.bundle + print pack "
            "fingerprint. Does NOT call any LLM. Returns 0 on success."
        ),
    )
    p.set_defaults(_handler=_run)


# --------------------------------------------------------------------------- #
# Scene-id parse + stub load                                                   #
# --------------------------------------------------------------------------- #


def _parse_scene_id(scene_id: str) -> tuple[int, int]:
    """Parse a scene_id like 'ch01_sc01' into (chapter, scene_index).

    T-03-07-01 mitigation: strict regex + int cast guards against path
    traversal (e.g., "../evil" fails the regex).
    """
    m = _SCENE_ID_RE.match(scene_id)
    if m is None:
        raise ValueError(
            f"scene_id {scene_id!r} does not match ch(\\d+)_sc(\\d+) pattern"
        )
    return int(m.group(1)), int(m.group(2))


def _resolve_scene_yaml(scene_id: str, override: str | None = None) -> Path:
    """Find the SceneRequest yaml for scene_id."""
    if override is not None:
        return Path(override)
    chapter, _ = _parse_scene_id(scene_id)
    return Path(f"scenes/ch{chapter:02d}/{scene_id}.yaml")


def _load_scene_request(yaml_path: Path) -> SceneRequest:
    """Load a SceneRequest from a hand-authored YAML stub."""
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    # Field name normalization — some yaml stubs may use 'pov' whilst the
    # Pydantic model enforces 'pov' already. Keep explicit so Plan 04's
    # outline-parser output maps cleanly.
    return SceneRequest(
        chapter=int(data["chapter"]),
        scene_index=int(data["scene_index"]),
        pov=str(data["pov"]),
        date_iso=str(data["date_iso"]),
        location=str(data["location"]),
        beat_function=str(data["beat_function"]),
        preceding_scene_summary=data.get("preceding_scene_summary"),
    )


# --------------------------------------------------------------------------- #
# State persistence (atomic tmp+rename)                                        #
# --------------------------------------------------------------------------- #


def _state_path_for(scene_id: str, state_dir: Path) -> Path:
    chapter, _ = _parse_scene_id(scene_id)
    return state_dir / f"ch{chapter:02d}" / f"{scene_id}.state.json"


def _load_or_init_record(scene_id: str, state_path: Path) -> SceneStateRecord:
    """Load an existing SceneStateRecord or initialize a PENDING one."""
    if state_path.exists():
        return SceneStateRecord.model_validate_json(state_path.read_text())
    return SceneStateRecord(
        scene_id=scene_id,
        state=SceneState.PENDING,
        attempts={},
        mode_tag=None,
        history=[],
        blockers=[],
    )


def _persist(record: SceneStateRecord, state_path: Path) -> None:
    """Atomic tmp+rename write of a SceneStateRecord.

    Test I invariant: if the tmp write raises, the existing state.json is
    NOT clobbered — os.replace is only reached on successful tmp write.
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    # This line raises PermissionError in Test I; os.replace never fires.
    tmp_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp_path, state_path)


# --------------------------------------------------------------------------- #
# Plan 05-02 escalation helpers                                                #
# --------------------------------------------------------------------------- #


def _now_iso() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _emit_mode_escalation(
    event_logger: Any,
    scene_id: str,
    from_mode: str,
    to_mode: str,
    trigger: str,
    issue_ids: list[str],
) -> None:
    """Emit exactly one role='mode_escalation' Event (D-08).

    No-op when event_logger is None (test fixtures may pass None).
    """
    if event_logger is None:
        return
    ts_iso = _now_iso()
    caller = f"cli.draft.run_draft_loop:{scene_id}"
    prompt_h = hash_text(f"mode_escalation:{scene_id}:{trigger}:{from_mode}:{to_mode}")
    eid = event_id(ts_iso, "mode_escalation", caller, prompt_h)
    event = Event(
        event_id=eid,
        ts_iso=ts_iso,
        role="mode_escalation",
        model="n/a",
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        latency_ms=0,
        caller_context={
            "module": "cli.draft",
            "function": "run_draft_loop",
            "scene_id": scene_id,
        },
        output_hash=hash_text(f"mode_escalation:{trigger}"),
        extra={
            "from_mode": from_mode,
            "to_mode": to_mode,
            "trigger": trigger,
            "issue_ids": list(issue_ids),
        },
    )
    event_logger.emit(event)


def _scene_events(event_logger: Any, scene_id: str) -> list[Event]:
    """Filter event_logger.events to those tagged caller_context.scene_id=scene_id.

    Defensive: handles loggers that don't expose an .events list (production
    JsonlEventLogger doesn't) — returns [] in that case, so spend-cap +
    oscillation never fire on those paths (test-only observables).
    """
    evs = getattr(event_logger, "events", None)
    if evs is None:
        return []
    out: list[Event] = []
    for e in evs:
        if not isinstance(e, Event):
            continue
        if e.caller_context.get("scene_id") == scene_id:
            out.append(e)
    return out


def _compute_scene_spent_usd(
    event_logger: Any, scene_id: str, pricing_by_model: Any
) -> float:
    """Sum event_cost_usd across all scene events. 0.0 if logger lacks events."""
    # Lazy import to avoid eager-loading the pricing kernel for callers that
    # don't exercise spend-cap.
    from book_pipeline.observability.pricing import event_cost_usd

    total = 0.0
    for e in _scene_events(event_logger, scene_id):
        total += event_cost_usd(e, pricing_by_model)
    return total


def _critic_events_for_scene(
    event_logger: Any, scene_id: str
) -> list[Event]:
    """Subset of scene events with role='critic', oldest→newest."""
    return [e for e in _scene_events(event_logger, scene_id) if e.role == "critic"]


def _synth_critic_events_from_severities(
    scene_id: str, attempt_severities: list[dict[str, str]]
) -> list[Event]:
    """Build synthetic role='critic' Events from per-attempt severity maps.

    Used by the oscillation detector so the signal is independent of whether
    the critic concrete emitted OBS-01 events to the logger (production
    SceneCritic does; unit tests often stub it).
    """
    out: list[Event] = []
    for idx, sev_map in enumerate(attempt_severities, start=1):
        out.append(
            Event(
                event_id=f"synth_{scene_id}_{idx}",
                ts_iso="1970-01-01T00:00:00Z",
                role="critic",
                model="synthetic",
                prompt_hash="p",
                input_tokens=0,
                cached_tokens=0,
                output_tokens=0,
                latency_ms=0,
                caller_context={"scene_id": scene_id, "attempt_number": idx},
                output_hash="o",
                extra={"severities": dict(sev_map)},
            )
        )
    return out


def _run_mode_b_attempt(
    *,
    scene_id: str,
    chapter: int,
    pack: Any,
    mode_b_drafter: Any,
    critic: Any,
    rubric: Any,
    state_path: Path,
    commit_dir: Path,
    ingestion_run_id: str | None,
    record: SceneStateRecord,
) -> int:
    """Run one Mode-B draft attempt; on success critic-gate; else HARD_BLOCK.

    Returns:
        0 on Mode-B COMMITTED, 3 on Mode-B critic FAIL or ModeBDrafterBlocked.
    """
    # Lazy import so the Phase 3 scene-loop paths don't pull mode_b eagerly
    # (not every CLI invocation needs it).
    from book_pipeline.drafter.mode_b import ModeBDrafterBlocked

    record = transition(record, SceneState.ESCALATED_B, "mode_b_attempt_start")
    _persist(record, state_path)
    try:
        draft_request = DraftRequest(
            context_pack=pack,
            prior_scenes=[],
            generation_config={"attempt_number": 1},
        )
        b_draft = mode_b_drafter.draft(draft_request)
    except ModeBDrafterBlocked:
        # TODO(05-03): alerter.send_alert('mode_b_exhausted', {...})
        record = transition(record, SceneState.HARD_BLOCKED, "mode_b_exhausted")
        record.blockers.append("mode_b_exhausted")
        _persist(record, state_path)
        return 3

    # Critic-gate the Mode-B draft.
    critic_req = CriticRequest(
        scene_text=b_draft.scene_text,
        context_pack=pack,
        rubric_id="scene.v1",
        rubric_version=getattr(rubric, "rubric_version", "v1"),
        chapter_context={"attempt_number": 1, "mode": "B"},
    )
    try:
        b_critic_resp = critic.review(critic_req)
    except Exception:
        record = transition(record, SceneState.HARD_BLOCKED, "mode_b_critic_error")
        record.blockers.append("mode_b_critic_error")
        _persist(record, state_path)
        return 3

    if not b_critic_resp.overall_pass:
        # TODO(05-03): alerter.send_alert('mode_b_critic_fail', {...})
        record = transition(record, SceneState.HARD_BLOCKED, "mode_b_critic_fail")
        record.blockers.append("mode_b_critic_fail")
        _persist(record, state_path)
        return 3

    # Mode-B PASS — commit.
    record = transition(record, SceneState.CRITIC_PASS, "mode_b passed critic")
    _persist(record, state_path)
    _commit_scene(
        draft=b_draft,
        critic_response=b_critic_resp,
        pack=pack,
        scene_id=scene_id,
        chapter=chapter,
        commit_dir=commit_dir,
        ingestion_run_id=ingestion_run_id,
        attempt_count=1,
    )
    record = transition(record, SceneState.COMMITTED, "mode_b committed")
    _persist(record, state_path)
    return 0


# --------------------------------------------------------------------------- #
# Scene commit (B-3 invariant)                                                 #
# --------------------------------------------------------------------------- #


def _commit_scene(
    *,
    draft: Any,
    critic_response: Any,
    pack: Any,
    scene_id: str,
    chapter: int,
    commit_dir: Path,
    ingestion_run_id: str | None,
    attempt_count: int,
) -> Path:
    """Write drafts/ch{NN}/{scene_id}.md with full YAML frontmatter.

    B-3 INVARIANT (SINGLE SOURCE OF TRUTH):
      frontmatter['voice_pin_sha'] = frontmatter['checkpoint_sha']
                                  = draft.voice_pin_sha

    Both keys hold the SAME value — Phase 4 ChapterAssembler trusts this
    invariant. Do NOT diverge. If draft.voice_pin_sha is None, raise
    RuntimeError — a COMMITTED scene requires a pinned checkpoint.
    """
    if draft.voice_pin_sha is None:
        raise RuntimeError(
            "COMMITTED scene requires draft.voice_pin_sha; ModeADrafter must "
            "have populated it before the scene reached _commit_scene."
        )

    # B-3 invariant: single source of truth — do not diverge.
    shared_sha = draft.voice_pin_sha
    voice_fidelity_score = None
    # Best-effort extraction of voice_fidelity_score from drafter Event context;
    # the actual score is emitted on the drafter Event (caller_context), not
    # the DraftResponse. For Phase 3 we persist whatever was stamped on
    # draft.output_sha's sibling attributes if available; fall through to None.
    voice_fidelity_score = getattr(draft, "voice_fidelity_score", None)

    frontmatter: dict[str, Any] = {
        "voice_pin_sha": shared_sha,         # B-3 invariant
        "checkpoint_sha": shared_sha,         # B-3 invariant — MUST equal voice_pin_sha
        "critic_scores_per_axis": dict(critic_response.scores_per_axis),
        "attempt_count": attempt_count,
        "ingestion_run_id": ingestion_run_id or (
            getattr(pack, "ingestion_run_id", None) or "unknown"
        ),
        "draft_timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "voice_fidelity_score": voice_fidelity_score,
        # Plan 05-02: Mode-B commits use draft.mode='B'; Mode-A commits keep 'A'.
        "mode": getattr(draft, "mode", "A"),
        "rubric_version": critic_response.rubric_version,
    }

    chapter_dir = commit_dir / f"ch{chapter:02d}"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    md_path = chapter_dir / f"{scene_id}.md"

    yaml_text = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    md_path.write_text(
        f"---\n{yaml_text}---\n{draft.scene_text}\n", encoding="utf-8"
    )
    return md_path


# --------------------------------------------------------------------------- #
# Scene loop (run_draft_loop)                                                  #
# --------------------------------------------------------------------------- #


def run_draft_loop(
    scene_id: str,
    max_regen: int,
    *,
    composition_root: Any,
) -> int:
    """Execute the Phase 3 scene loop per Plan 03-07 <scene_loop_state_machine>.

    Returns an exit code:
      0 on COMMITTED, 2 on drafter-blocked, 3 on critic-blocked,
      4 on R-exhaustion or regen-unavailable, 5 if unreachable.
    """
    # Lazy imports so the exception types are available without eagerly
    # pulling drafter/critic/regenerator at module-import time for unrelated
    # tests.
    from book_pipeline.critic.scene import SceneCriticError
    from book_pipeline.drafter.mode_a import ModeADrafterBlocked
    from book_pipeline.regenerator.scene_local import (
        RegeneratorUnavailable,
        RegenWordCountDrift,
    )

    chapter, _ = _parse_scene_id(scene_id)
    state_dir = Path(composition_root.state_dir)
    commit_dir = Path(composition_root.commit_dir)
    state_path = _state_path_for(scene_id, state_dir)

    record = _load_or_init_record(scene_id, state_path)
    scene_request: SceneRequest = composition_root.scene_request
    rubric = composition_root.rubric
    ingestion_run_id = getattr(composition_root, "ingestion_run_id", None)
    event_logger = getattr(composition_root, "event_logger", None)

    # Plan 05-02 composition-root additions (optional; default-safe for
    # existing Phase 3 callers that don't supply them).
    preflag_set: frozenset[str] = getattr(
        composition_root, "preflag_set", frozenset()
    )
    mode_b_drafter = getattr(composition_root, "mode_b_drafter", None)
    pricing_by_model: Any = getattr(
        composition_root, "pricing_by_model", {}
    )
    spend_cap_usd: float = float(
        getattr(composition_root, "spend_cap_usd_per_scene", 0.0)
    )

    # --- PENDING → RAG_READY ---
    pack = composition_root.bundler.bundle(scene_request, composition_root.retrievers)
    record = transition(record, SceneState.RAG_READY, "bundler returned pack")
    _persist(record, state_path)

    # --- Plan 05-02 D-09 step (a): preflag check BEFORE first drafter call. ---
    from book_pipeline.drafter.preflag import is_preflagged

    if mode_b_drafter is not None and is_preflagged(scene_id, preflag_set):
        _emit_mode_escalation(
            event_logger, scene_id, "A", "B", "preflag", []
        )
        return _run_mode_b_attempt(
            scene_id=scene_id,
            chapter=chapter,
            pack=pack,
            mode_b_drafter=mode_b_drafter,
            critic=composition_root.critic,
            rubric=rubric,
            state_path=state_path,
            commit_dir=commit_dir,
            ingestion_run_id=ingestion_run_id,
            record=record,
        )

    prior_draft: Any = None
    critic_resp: Any = None
    # Plan 05-02: accumulate per-attempt critic severities so the oscillation
    # detector can compare attempts N vs N-2 independently of the event-logger
    # surface (production emits critic events via SceneCritic; tests inject
    # fake critics that don't emit — this local tracking keeps both paths
    # deterministic).
    attempt_severities: list[dict[str, str]] = []

    for attempt in range(1, max_regen + 2):  # 1..R+1
        # --- DRAFTING / REGENERATING → DRAFTED_A (via exception on failure) ---
        try:
            if attempt == 1:
                draft_request = DraftRequest(
                    context_pack=pack,
                    prior_scenes=[],
                    generation_config={"attempt_number": 1},
                )
                draft = composition_root.drafter.draft(draft_request)
            else:
                assert critic_resp is not None, "regen path requires critic_resp"
                regen_request = RegenRequest(
                    prior_draft=prior_draft,
                    context_pack=pack,
                    issues=[
                        i for i in critic_resp.issues
                        if i.severity in ("mid", "high")
                    ],
                    attempt_number=attempt,
                    max_attempts=max_regen + 1,
                )
                try:
                    draft = composition_root.regenerator.regenerate(regen_request)
                except (RegenWordCountDrift, RegeneratorUnavailable) as e:
                    note = f"regen_failed:{type(e).__name__}"
                    record = transition(record, SceneState.CRITIC_FAIL, note)
                    if record.history:
                        record.history[-1]["regen_failure"] = str(e)
                    _persist(record, state_path)
                    if attempt >= max_regen + 1:
                        record = transition(
                            record,
                            SceneState.HARD_BLOCKED,
                            "failed_critic_after_R_attempts",
                        )
                        record.blockers.append("failed_critic_after_R_attempts")
                        _persist(record, state_path)
                        return 4
                    record = transition(
                        record,
                        SceneState.REGENERATING,
                        f"retry regen attempt {attempt + 1}",
                    )
                    _persist(record, state_path)
                    continue
            prior_draft = draft
        except ModeADrafterBlocked as e:
            record = transition(
                record, SceneState.HARD_BLOCKED, f"drafter_blocked:{e.reason}"
            )
            record.blockers.append(e.reason)
            _persist(record, state_path)
            return 2

        record = transition(record, SceneState.DRAFTED_A, f"attempt {attempt}")
        record.attempts["mode_a_regens"] = attempt - 1
        record.mode_tag = "A"
        _persist(record, state_path)

        # --- DRAFTED_A → CRITIC_PASS or CRITIC_FAIL ---
        try:
            critic_req = CriticRequest(
                scene_text=draft.scene_text,
                context_pack=pack,
                rubric_id="scene.v1",
                rubric_version=getattr(rubric, "rubric_version", "v1"),
                chapter_context={"attempt_number": attempt},
            )
            critic_resp = composition_root.critic.review(critic_req)
        except SceneCriticError as e:
            record = transition(
                record, SceneState.HARD_BLOCKED, f"critic_blocked:{e.reason}"
            )
            record.blockers.append(e.reason)
            _persist(record, state_path)
            return 3

        if critic_resp.overall_pass:
            record = transition(
                record, SceneState.CRITIC_PASS, f"attempt {attempt} passed"
            )
            _persist(record, state_path)
            # --- CRITIC_PASS → COMMITTED ---
            _commit_scene(
                draft=draft,
                critic_response=critic_resp,
                pack=pack,
                scene_id=scene_id,
                chapter=chapter,
                commit_dir=commit_dir,
                ingestion_run_id=ingestion_run_id,
                attempt_count=attempt,
            )
            record = transition(
                record, SceneState.COMMITTED, f"committed after attempt {attempt}"
            )
            _persist(record, state_path)
            return 0

        # Critic FAIL — any mid/high actionable?
        actionable = [i for i in critic_resp.issues if i.severity in ("mid", "high")]
        if not actionable:
            raise RuntimeError(
                "unreachable: overall_pass=False but no actionable issues"
            )

        record = transition(
            record,
            SceneState.CRITIC_FAIL,
            f"attempt {attempt}: {len(actionable)} actionable issues",
        )
        _persist(record, state_path)

        # Plan 05-02: record this attempt's worst-severity-per-axis map so the
        # oscillation detector can compare N vs N-2 axis+severity sets (D-07).
        severities_this_attempt: dict[str, str] = {}
        _SEV_RANK = {"low": 1, "mid": 2, "high": 3}
        for issue in critic_resp.issues:
            prior = severities_this_attempt.get(issue.axis)
            if prior is None or _SEV_RANK.get(issue.severity, 0) > _SEV_RANK.get(prior, 0):
                severities_this_attempt[issue.axis] = issue.severity
        attempt_severities.append(severities_this_attempt)

        # --- Plan 05-02 D-09 step (c): spend-cap check (cheapest + most-
        # severe — $0.75 is unrecoverable, so it runs before oscillation). ---
        if spend_cap_usd > 0.0 and pricing_by_model:
            spent = _compute_scene_spent_usd(
                event_logger, scene_id, pricing_by_model
            )
            if spent >= spend_cap_usd:
                _emit_mode_escalation(
                    event_logger, scene_id, "A", "A", "spend_cap_exceeded", []
                )
                # TODO(05-03): alerter.send_alert('spend_cap_exceeded', {...})
                record = transition(
                    record,
                    SceneState.HARD_BLOCKED,
                    f"spend_cap_exceeded ${spent:.3f}",
                )
                record.blockers.append("spend_cap_exceeded")
                _persist(record, state_path)
                return 4

        # --- Plan 05-02 D-09 step (b): oscillation check. ---
        if mode_b_drafter is not None:
            from book_pipeline.regenerator.oscillation import (
                detect_oscillation,
            )

            # Synthesize in-memory critic Events from attempt_severities so the
            # detector is fed the same shape regardless of whether the critic
            # concrete actually emitted OBS-01 events to the logger. Production
            # SceneCritic does emit; unit tests often stub it.
            critic_events = _synth_critic_events_from_severities(
                scene_id, attempt_severities
            )
            fired, common = detect_oscillation(critic_events)
            if fired:
                issue_ids = (
                    [f"{a}:{s}" for a, s in sorted(common)]
                    if common
                    else []
                )
                _emit_mode_escalation(
                    event_logger, scene_id, "A", "B", "oscillation", issue_ids
                )
                return _run_mode_b_attempt(
                    scene_id=scene_id,
                    chapter=chapter,
                    pack=pack,
                    mode_b_drafter=mode_b_drafter,
                    critic=composition_root.critic,
                    rubric=rubric,
                    state_path=state_path,
                    commit_dir=commit_dir,
                    ingestion_run_id=ingestion_run_id,
                    record=record,
                )

        # --- Plan 05-02 D-09 step (d): R-cap exhausted. ---
        if attempt >= max_regen + 1:
            if mode_b_drafter is not None:
                issue_ids = [
                    f"{i.axis}:{i.severity}" for i in critic_resp.issues
                ]
                _emit_mode_escalation(
                    event_logger,
                    scene_id,
                    "A",
                    "B",
                    "r_cap_exhausted",
                    issue_ids,
                )
                return _run_mode_b_attempt(
                    scene_id=scene_id,
                    chapter=chapter,
                    pack=pack,
                    mode_b_drafter=mode_b_drafter,
                    critic=composition_root.critic,
                    rubric=rubric,
                    state_path=state_path,
                    commit_dir=commit_dir,
                    ingestion_run_id=ingestion_run_id,
                    record=record,
                )
            # Legacy Phase 3 path (no Mode-B wired) — preserve HARD_BLOCKED.
            record = transition(
                record, SceneState.HARD_BLOCKED, "failed_critic_after_R_attempts"
            )
            record.blockers.append("failed_critic_after_R_attempts")
            _persist(record, state_path)
            return 4

        record = transition(
            record,
            SceneState.REGENERATING,
            f"starting regen attempt {attempt + 1}",
        )
        _persist(record, state_path)

    return 5  # unreachable


# --------------------------------------------------------------------------- #
# Dry-run                                                                       #
# --------------------------------------------------------------------------- #


def run_dry_run(
    scene_id: str,
    *,
    composition_root: Any,
) -> int:
    """Load stub + bundle ContextPack + print pack fingerprint. NO LLM calls."""
    pack = composition_root.bundler.bundle(
        composition_root.scene_request, composition_root.retrievers
    )
    num_conflicts = len(pack.conflicts) if pack.conflicts else 0
    per_axis_hits = {
        name: len(rr.hits) for name, rr in pack.retrievals.items()
    }
    print(f"[dry-run] scene_id = {scene_id}")
    print(f"[dry-run] pack.fingerprint = {pack.fingerprint}")
    print(f"[dry-run] total_bytes = {pack.total_bytes}")
    print(f"[dry-run] num_conflicts = {num_conflicts}")
    print(f"[dry-run] hits per axis = {per_axis_hits}")
    return 0


# --------------------------------------------------------------------------- #
# _build_composition_root — production CLI composition                          #
# --------------------------------------------------------------------------- #


def _build_composition_root(
    scene_id: str, scene_yaml_path: Path, *, max_regen: int
) -> CompositionRoot:
    """Wire the 6 Phase 3 components for a real CLI invocation.

    The 4 book_specifics imports here are documented CLI-composition seams
    (pyproject.toml ignore_imports; tests/test_import_contracts.py documented
    exemptions).
    """
    # --- Config loaders (all 4 typed loaders validate at startup) ---
    from book_pipeline.config.mode_thresholds import ModeThresholdsConfig
    from book_pipeline.config.rag_retrievers import RagRetrieversConfig
    from book_pipeline.config.rubric import RubricConfig
    from book_pipeline.config.voice_pin import VoicePinConfig

    voice_pin_cfg = VoicePinConfig()  # type: ignore[call-arg]
    rubric_cfg = RubricConfig()  # type: ignore[call-arg]
    rag_cfg = RagRetrieversConfig()  # type: ignore[call-arg]
    mode_thresholds_cfg = ModeThresholdsConfig()  # type: ignore[call-arg]

    pin_data = voice_pin_cfg.voice_pin

    # --- Scene request ---
    scene_request = _load_scene_request(scene_yaml_path)

    # --- Book-domain composition seams (ADR-004 / Plan 02-06 precedent) ---
    from book_pipeline.book_specifics.corpus_paths import OUTLINE
    from book_pipeline.book_specifics.training_corpus import TRAINING_CORPUS_DEFAULT
    from book_pipeline.book_specifics.vllm_endpoints import DEFAULT_BASE_URL
    from book_pipeline.cli._entity_list import build_nahuatl_entity_set

    # --- Shared observability + embedder + reranker ---
    from book_pipeline.observability import JsonlEventLogger
    from book_pipeline.rag import BgeM3Embedder, build_retrievers_from_config
    from book_pipeline.rag.bundler import ContextPackBundlerImpl
    from book_pipeline.rag.reranker import BgeReranker

    event_logger = JsonlEventLogger()
    indexes_dir = Path("indexes")
    ingestion_run_id = _read_latest_ingestion_run_id(indexes_dir)

    embedder = BgeM3Embedder(
        model_name=rag_cfg.embeddings.model,
        revision=None,
        device=rag_cfg.embeddings.device,
    )
    reranker = BgeReranker(
        model_name=rag_cfg.reranker.model, device=rag_cfg.reranker.device
    )

    retrievers_dict = build_retrievers_from_config(
        cfg=rag_cfg,
        embedder=embedder,
        reranker=reranker,
        indexes_dir=indexes_dir,
        ingestion_run_id=ingestion_run_id,
        outline_path=OUTLINE,
    )
    retrievers_list = list(retrievers_dict.values())

    bundler = ContextPackBundlerImpl(
        event_logger=event_logger,
        entity_list=build_nahuatl_entity_set(),
        ingestion_run_id=ingestion_run_id,
    )

    # --- Drafter (Plan 03-04) ---
    from book_pipeline.drafter.memorization_gate import TrainingBleedGate
    from book_pipeline.drafter.mode_a import ModeADrafter
    from book_pipeline.drafter.vllm_client import VllmClient
    from book_pipeline.voice_fidelity.pin import AnchorSetProvider

    anchor_provider = AnchorSetProvider(
        yaml_path=Path("config/voice_anchors/anchor_set_v1.yaml"),
        thresholds_path=Path("config/mode_thresholds.yaml"),
        embedder=embedder,
    )

    memorization_gate = TrainingBleedGate(TRAINING_CORPUS_DEFAULT, ngram=12)

    vllm_client = VllmClient(
        DEFAULT_BASE_URL, event_logger=event_logger, lora_module_name="paul-voice"
    )
    # Fail early if vLLM is not reachable — operator responsibility to start
    # the paul-voice unit via `book-pipeline vllm-bootstrap --start`.
    if not vllm_client.health_ok():
        raise RuntimeError(
            f"vLLM paul-voice not reachable at {DEFAULT_BASE_URL} — run "
            f"`book-pipeline vllm-bootstrap --start` first."
        )

    drafter = ModeADrafter(
        vllm_client=vllm_client,
        event_logger=event_logger,
        voice_pin=pin_data,
        anchor_provider=anchor_provider,
        memorization_gate=memorization_gate,
        sampling_profiles=mode_thresholds_cfg.sampling_profiles,
        embedder_for_fidelity=embedder,
    )

    # --- Critic (Plan 03-05) ---
    # Phase 3 gap-closure (2026-04-21): backend chosen via
    # mode_thresholds_cfg.critic_backend.kind. Default = claude_code_cli
    # (subscription-covered OAuth subprocess); alternative = anthropic_sdk
    # (requires ANTHROPIC_API_KEY). SceneCritic + SceneLocalRegenerator
    # take ``anthropic_client: Any`` — any client with a .messages.parse()/
    # .messages.create() surface works (see book_pipeline.llm_clients).
    from book_pipeline.critic.scene import SceneCritic
    from book_pipeline.llm_clients import build_llm_client

    critic_backend_cfg = mode_thresholds_cfg.critic_backend
    critic_client = build_llm_client(critic_backend_cfg)
    regen_client = build_llm_client(critic_backend_cfg)

    critic = SceneCritic(
        anthropic_client=critic_client,
        event_logger=event_logger,
        rubric=rubric_cfg,
        model_id=critic_backend_cfg.model,
    )

    # --- Regenerator (Plan 03-06) ---
    from book_pipeline.regenerator.scene_local import SceneLocalRegenerator

    regenerator = SceneLocalRegenerator(
        anthropic_client=regen_client,
        event_logger=event_logger,
        voice_pin=pin_data,
        model_id=critic_backend_cfg.model,
    )

    return CompositionRoot(
        bundler=bundler,
        retrievers=retrievers_list,
        drafter=drafter,
        critic=critic,
        regenerator=regenerator,
        scene_request=scene_request,
        rubric=rubric_cfg,
        state_dir=Path("drafts/scene_buffer"),
        commit_dir=Path("drafts"),
        ingestion_run_id=ingestion_run_id,
        event_logger=event_logger,
    )


def _read_latest_ingestion_run_id(indexes_dir: Path) -> str:
    """Reads indexes/resolved_model_revision.json for the baseline run id.

    Fail-fast if absent — Phase 2 ingest must have run.
    """
    path = indexes_dir / "resolved_model_revision.json"
    if not path.exists():
        raise RuntimeError(
            f"No baseline ingestion run id at {path} — run "
            f"`book-pipeline ingest` first."
        )
    import json as _json

    data = _json.loads(path.read_text())
    run_id = data.get("ingestion_run_id") or data.get("sha") or "unknown"
    return str(run_id)


# --------------------------------------------------------------------------- #
# CLI _run entry point                                                          #
# --------------------------------------------------------------------------- #


def _run(args: argparse.Namespace) -> int:
    scene_id = args.scene_id
    try:
        chapter, _ = _parse_scene_id(scene_id)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    yaml_path = _resolve_scene_yaml(scene_id, args.scene_yaml)
    if not yaml_path.exists():
        print(f"Error: scene yaml not found at {yaml_path}", file=sys.stderr)
        return 2

    try:
        composition_root = _build_composition_root(
            scene_id, yaml_path, max_regen=args.max_regen
        )
    except Exception as exc:
        print(f"Error: failed to build composition root: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        return run_dry_run(scene_id, composition_root=composition_root)

    rc = run_draft_loop(
        scene_id, args.max_regen, composition_root=composition_root
    )
    # Summary print.
    state_path = _state_path_for(scene_id, composition_root.state_dir)
    if state_path.exists():
        rec = SceneStateRecord.model_validate_json(state_path.read_text())
        print(f"[draft] scene_id={scene_id} terminal_state={rec.state.value}")
        print(f"[draft] state_path={state_path}")
        if rec.state == SceneState.COMMITTED:
            md_path = composition_root.commit_dir / f"ch{chapter:02d}" / f"{scene_id}.md"
            print(f"[draft] committed_md={md_path}")
    return rc


register_subcommand("draft", _add_parser)


__all__: list[str] = [
    "CompositionRoot",
    "run_draft_loop",
    "run_dry_run",
]
