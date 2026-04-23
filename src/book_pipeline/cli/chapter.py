"""`book-pipeline chapter <N>` — full Phase 4 chapter-DAG composition root.

Plan 04-05. Composes the 11 Phase 4 kernel components (ConcatAssembler +
ChapterCritic + OpusEntityExtractor + OpusRetrospectiveWriter + bundler + 5
retrievers + event logger + state-machine paths) into a single CLI
invocation that drives the 4-step post-commit DAG for a single chapter_num.

Mirrors the Plan 03-07 `cli/draft.py` composition pattern: load 4 typed
configs → build LLM client via factory → construct ChapterDagOrchestrator
with all injected deps → call `orchestrator.run(chapter_num,
expected_scene_count=EXPECTED_SCENE_COUNTS[chapter_num])`.

This module is the ONE site that wires the Phase 4 kernel into the
book-domain scene-count table + corpus paths + Nahuatl entity list. The
book-domain imports below (`outline_scene_counts`, `corpus_paths`) are
documented import-linter composition seams (pyproject.toml ignore_imports
entries added in Plan 04-05); Nahuatl entities are reached indirectly via
`cli/_entity_list.build_nahuatl_entity_set()` (which owns its own
exemption — same Plan 03-07 pattern).

Flags:
  chapter_num              Positional, 1-indexed; 1-27 for real chapters,
                           99 reserved for the Plan 04-06 integration test.
  --expected-scene-count N Override the outline-derived scene count
                           (bypasses EXPECTED_SCENE_COUNTS lookup).
  --no-archive             Skip scene-buffer archival post-DAG
                           (for Plan 04-06 integration-test idempotency).

Exit codes:
  0  DAG_COMPLETE         — all 4 DAG steps committed.
  2  gate fail            — scene_count mismatch, invalid chapter_num,
                           config validation error, composition failure.
  3  CHAPTER_FAIL         — chapter critic rejected (< 3/5 on any axis).
  4  DAG_BLOCKED          — post-commit DAG step (entity, rag, commit) failed.
  5  unreachable          — defensive; logs "unknown terminal state".
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from book_pipeline.cli.main import register_subcommand

if TYPE_CHECKING:  # pragma: no cover
    from book_pipeline.chapter_assembler.dag import ChapterDagOrchestrator


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Module-level re-exports for test monkeypatching                              #
# --------------------------------------------------------------------------- #
# Tests monkeypatch these attributes on the `book_pipeline.cli.chapter`
# module namespace (test_build_orchestrator_wires_all_deps). Import them at
# module load so `monkeypatch.setattr(chapter_mod, "BgeM3Embedder", ...)`
# has a target to rebind.

from book_pipeline.config.mode_thresholds import ModeThresholdsConfig  # noqa: E402
from book_pipeline.config.rag_retrievers import RagRetrieversConfig  # noqa: E402
from book_pipeline.config.rubric import RubricConfig  # noqa: E402
from book_pipeline.config.voice_pin import VoicePinConfig  # noqa: E402
from book_pipeline.llm_clients import build_llm_client  # noqa: E402
from book_pipeline.rag import BgeM3Embedder, build_retrievers_from_config  # noqa: E402
from book_pipeline.rag.reranker import BgeReranker  # noqa: E402

# --------------------------------------------------------------------------- #
# Argparse wiring                                                              #
# --------------------------------------------------------------------------- #


def _add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser(
        "chapter",
        help=(
            "Run the full Phase 4 loop for <chapter_num>: gate-check scenes, "
            "assemble, chapter-critic, commit canon, then the 4-step post-commit "
            "DAG (entity extract → rag reindex → retrospective)."
        ),
    )
    p.add_argument(
        "chapter_num",
        type=int,
        help="Chapter number (1-27 for real chapters; 99 reserved for tests).",
    )
    p.add_argument(
        "--expected-scene-count",
        type=int,
        default=None,
        help=(
            "Override the outline-derived scene count "
            "(default: EXPECTED_SCENE_COUNTS[chapter_num])."
        ),
    )
    p.add_argument(
        "--no-archive",
        action="store_true",
        help="Skip post-DAG scene-buffer archival (for integration tests).",
    )
    p.set_defaults(_handler=_run)


# --------------------------------------------------------------------------- #
# _read_latest_ingestion_run_id                                                 #
# --------------------------------------------------------------------------- #


def _read_latest_ingestion_run_id(indexes_dir: Path) -> str:
    """Load indexes/resolved_model_revision.json for the baseline run id.

    Fail-fast if absent — Phase 2 ingest must have run. Mirrors the shape
    used by `cli/draft.py` so Phase 4 DAG writes the same ingestion_run_id
    into its Events.
    """
    path = indexes_dir / "resolved_model_revision.json"
    if not path.exists():
        raise RuntimeError(
            f"No baseline ingestion run id at {path} — run "
            f"`book-pipeline ingest` first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    run_id = data.get("ingestion_run_id") or data.get("sha") or "unknown"
    return str(run_id)


# --------------------------------------------------------------------------- #
# _build_dag_orchestrator — the composition root                                #
# --------------------------------------------------------------------------- #


def _build_dag_orchestrator(chapter_num: int) -> ChapterDagOrchestrator:
    """Wire all Phase 4 kernel components for a real CLI invocation.

    Book-domain imports inside this function are documented CLI-composition
    seams (pyproject.toml ignore_imports). Every other kernel module stays
    ignorant of book_specifics.
    """
    # --- Book-domain composition seams (documented exemptions) ---
    from book_pipeline.book_specifics.corpus_paths import OUTLINE
    from book_pipeline.cli._entity_list import build_nahuatl_entity_set

    # --- Typed config loaders (fail-fast on validation errors) ---
    voice_pin_cfg = VoicePinConfig()  # type: ignore[call-arg]
    rubric_cfg = RubricConfig()  # type: ignore[call-arg]
    rag_cfg = RagRetrieversConfig()  # type: ignore[call-arg]
    mode_thresholds_cfg = ModeThresholdsConfig()  # type: ignore[call-arg]

    pin_data = voice_pin_cfg.voice_pin

    # --- Shared observability ---
    from book_pipeline.observability import JsonlEventLogger

    event_logger = JsonlEventLogger()
    indexes_dir = Path("indexes")
    ingestion_run_id = _read_latest_ingestion_run_id(indexes_dir)

    # --- Embedder + reranker (local kernel; no book-domain) ---
    embedder = BgeM3Embedder(
        model_name=rag_cfg.embeddings.model,
        revision=None,
        device=rag_cfg.embeddings.device,
    )
    reranker = BgeReranker(
        model_name=rag_cfg.reranker.model, device=rag_cfg.reranker.device
    )

    # --- 5 typed retrievers (W-1 factory shared with cli/draft.py) ---
    retrievers_dict = build_retrievers_from_config(
        cfg=rag_cfg,
        embedder=embedder,
        reranker=reranker,
        indexes_dir=indexes_dir,
        ingestion_run_id=ingestion_run_id,
        outline_path=OUTLINE,
    )
    retrievers_list = list(retrievers_dict.values())

    # --- Bundler (W-1 entity_list DI seam) ---
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    bundler = ContextPackBundlerImpl(
        event_logger=event_logger,
        entity_list=build_nahuatl_entity_set(),
        ingestion_run_id=ingestion_run_id,
    )

    # --- LLM client (ONE client shared across all 3 Phase 4 Opus calls;
    # 1h prompt cache amortizes across chapter critic + entity extractor +
    # retrospective writer invocations) ---
    critic_backend_cfg = mode_thresholds_cfg.critic_backend
    llm_client = build_llm_client(critic_backend_cfg)

    # --- Phase 4 concretes ---
    from book_pipeline.chapter_assembler import ConcatAssembler
    from book_pipeline.chapter_assembler.dag import ChapterDagOrchestrator
    from book_pipeline.critic.chapter import ChapterCritic
    from book_pipeline.entity_extractor import OpusEntityExtractor
    from book_pipeline.retrospective import OpusRetrospectiveWriter

    # pin_data is reserved for a future Phase 5 extension that threads
    # voice_pin.checkpoint_sha into the chapter critic audit record; silence
    # the linter for now.
    _ = pin_data

    assembler = ConcatAssembler()
    chapter_critic = ChapterCritic(
        anthropic_client=llm_client,
        event_logger=event_logger,
        rubric=rubric_cfg,
        model_id=critic_backend_cfg.model,
    )
    entity_extractor = OpusEntityExtractor(
        anthropic_client=llm_client,
        event_logger=event_logger,
        model_id=critic_backend_cfg.model,
    )
    retrospective_writer = OpusRetrospectiveWriter(
        anthropic_client=llm_client,
        event_logger=event_logger,
        model_id=critic_backend_cfg.model,
    )

    # --- Orchestrator (12 injected components) ---
    # All directory anchors are resolved to ABSOLUTE paths against repo_root
    # so the orchestrator's `canon_path.relative_to(repo_root)` logic works
    # regardless of the caller's working directory (04-06 deviation: Plan
    # 04-05 passed bare relative paths, which failed `.relative_to(cwd)`
    # inside the DAG when `Path("canon/chapter_99.md").relative_to(cwd_abs)`
    # raised ValueError). Rule 1 bug-fix.
    repo_root = Path.cwd()
    return ChapterDagOrchestrator(
        assembler=assembler,
        chapter_critic=chapter_critic,
        entity_extractor=entity_extractor,
        retrospective_writer=retrospective_writer,
        bundler=bundler,
        retrievers=retrievers_list,
        embedder=embedder,
        event_logger=event_logger,
        repo_root=repo_root,
        canon_dir=repo_root / "canon",
        entity_state_dir=repo_root / "entity-state",
        retros_dir=repo_root / "retrospectives",
        scene_buffer_dir=repo_root / "drafts" / "scene_buffer",
        chapter_buffer_dir=repo_root / "drafts" / "chapter_buffer",
        commit_dir=repo_root / "drafts",
        indexes_dir=repo_root / "indexes",
        pipeline_state_path=repo_root / ".planning" / "pipeline_state.json",
        events_jsonl_path=repo_root / "runs" / "events.jsonl",
    )


# --------------------------------------------------------------------------- #
# _run — CLI entry point                                                        #
# --------------------------------------------------------------------------- #


def _run(args: argparse.Namespace) -> int:
    from book_pipeline.book_specifics.outline_scene_counts import (
        expected_scene_count as _lookup_scene_count,
    )
    from book_pipeline.chapter_assembler.dag import ChapterGateError
    from book_pipeline.interfaces.types import ChapterState

    chapter_num = int(args.chapter_num)
    if chapter_num <= 0:
        print(
            f"Error: chapter_num must be a positive integer (got {chapter_num})",
            file=sys.stderr,
        )
        return 2

    # Build orchestrator.
    try:
        orchestrator = _build_dag_orchestrator(chapter_num)
    except Exception as exc:
        print(
            f"Error: failed to build chapter orchestrator: {exc}",
            file=sys.stderr,
        )
        return 2

    # Resolve expected scene count (book-domain lookup).
    expected = args.expected_scene_count
    if expected is None:
        expected = _lookup_scene_count(chapter_num)

    # Run the DAG.
    try:
        record = orchestrator.run(
            chapter_num, expected_scene_count=expected
        )
    except ChapterGateError as exc:
        print(
            f"Error: chapter gate failed: {exc.reason} "
            f"(expected={exc.expected}, actual={exc.actual}, missing={exc.missing})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        logger.exception("chapter DAG failed unexpectedly")
        print(
            f"Error: chapter DAG failed unexpectedly: {exc}",
            file=sys.stderr,
        )
        return 2

    # Summary print.
    _print_summary(record, chapter_num)

    # Map terminal state to exit code.
    terminal_map = {
        ChapterState.DAG_COMPLETE: 0,
        ChapterState.CHAPTER_FAIL: 3,
        ChapterState.DAG_BLOCKED: 4,
    }
    rc = terminal_map.get(record.state, 5)
    if rc == 5:
        logger.error(
            "orchestrator returned unknown terminal state: %s", record.state
        )
    return rc


def _print_summary(record: Any, chapter_num: int) -> None:
    """Emit the 5-line summary block per plan spec."""
    state_value = getattr(record.state, "value", str(record.state))
    chapter_sha = record.chapter_sha or "-"
    state_path = Path("drafts/chapter_buffer") / f"ch{chapter_num:02d}.state.json"
    print(f"[chapter] chapter_num={chapter_num} terminal_state={state_value}")
    print(f"[chapter] chapter_sha={chapter_sha} dag_step={record.dag_step}")
    print(f"[chapter] state_path={state_path}")

    canon_path = Path("canon") / f"chapter_{chapter_num:02d}.md"
    if canon_path.exists():
        print(f"[chapter] canon={canon_path}")

    entity_path = (
        Path("entity-state") / f"chapter_{chapter_num:02d}_entities.json"
    )
    if entity_path.exists():
        print(f"[chapter] entity_state={entity_path}")

    retro_path = Path("retrospectives") / f"chapter_{chapter_num:02d}.md"
    if retro_path.exists():
        print(f"[chapter] retrospective={retro_path}")


register_subcommand("chapter", _add_parser)


__all__: list[str] = [
    "_build_dag_orchestrator",
    "_run",
]
