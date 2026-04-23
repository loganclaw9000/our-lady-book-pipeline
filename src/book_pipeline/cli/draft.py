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
    RegenRequest,
    SceneRequest,
    SceneState,
    SceneStateRecord,
)

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
        "mode": "A",
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

    # --- PENDING → RAG_READY ---
    pack = composition_root.bundler.bundle(scene_request, composition_root.retrievers)
    record = transition(record, SceneState.RAG_READY, "bundler returned pack")
    _persist(record, state_path)

    prior_draft: Any = None
    critic_resp: Any = None

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

        if attempt >= max_regen + 1:
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
