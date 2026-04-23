"""ContextPackBundlerImpl — orchestrates 5 typed retrievers; THE event-emission site.

Per the frozen Retriever Protocol docstring: "EventLogger is NOT directly called
here; retriever events are emitted by the ContextPackBundler that orchestrates
all 5 retrievers." This module is that bundler.

Per bundle() call:
  1. For each retriever: time the call; invoke retrieve(request); emit ONE
     role="retriever" Event carrying retriever metadata.
  2. After all 5 retrievals: run detect_conflicts (W-1: pass injected entity_list).
  3. Run enforce_budget to shrink the retrievals under the 40KB hard cap.
  4. Assemble ContextPack; if conflicts present, persist to
     drafts/retrieval_conflicts/<scene_id>.json for Phase 3 critic consumption.
  5. Emit ONE role="context_pack_bundler" Event carrying the bundle metadata
     (trim_log, num_conflicts, total_bytes).

Dependency injection:
  - event_logger: required (Protocol-typed; concrete JsonlEventLogger in CLI wiring).
  - conflicts_dir: default `drafts/retrieval_conflicts`; override for tests.
  - ingestion_run_id: optional pin for the pack's ingestion_run_id field.
  - entity_list: W-1 optional canonical name set for conflict detection.
    Kernel stays free of book-domain imports — the CLI composition layer
    passes the Mesoamerican canonical-names set in.

Event caller_context carries {module, function, scene_id, chapter_num, pov,
beat_function, retriever_name?, index_fingerprint?, num_conflicts?, num_trims?}.

Threat mitigations:
  - T-02-05-01 (path traversal): scene_id built from int-cast chapter/scene_index.
  - T-02-05-04 (repudiation): retriever exceptions caught; bundler still emits
    a retriever event with output_tokens=0 + extra={"error": ...} and continues.
  - T-02-05-05 (EoP): bundler imports zero symbols from book-domain modules.
  - T-02-05-06 (Event schema drift): no Event field added/renamed; schema v1.0 held.
  - T-02-05-07 (regex injection via entity_list): entity_list is used only in
    substring `in` checks in conflict_detector, never compiled as regex.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from book_pipeline.interfaces.context_pack_bundler import ContextPackBundler
from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.retriever import Retriever
from book_pipeline.interfaces.types import (
    ConflictReport,
    ContextPack,
    Event,
    RetrievalResult,
    SceneRequest,
)
from book_pipeline.observability.hashing import event_id, hash_text
from book_pipeline.rag.budget import HARD_CAP, enforce_budget
from book_pipeline.rag.conflict_detector import detect_conflicts


def _now_iso() -> str:
    """RFC3339-ish UTC timestamp. Uses time.time_ns for monotonic-ish ordering."""
    ns = time.time_ns()
    s = ns // 1_000_000_000
    us = (ns // 1_000) % 1_000_000
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(s))
        + f".{us:06d}Z"
    )


def _git_sha_for_chapter(chapter_num: int, repo_root: Path) -> str | None:
    """Return git SHA of latest commit touching canon/chapter_{NN:02d}.md.

    Returns None on any failure (non-git repo, file missing, git unavailable,
    timeout) — Pitfall 6 graceful-degrade behavior. Callers treat None as
    "cannot determine, assume non-stale".

    T-05-03-05 EoP mitigation: chapter_num is int-cast before f-string
    formatting (no shell injection possible); subprocess.run uses list args
    (not shell=True).
    """
    path = f"canon/chapter_{int(chapter_num):02d}.md"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "-1", "HEAD", "--", path],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        OSError,
    ):
        return None
    sha = result.stdout.strip()
    return sha or None


def scan_for_stale_cards(
    entity_state_result: RetrievalResult,
    repo_root: Path,
) -> list[ConflictReport]:
    """Compare each entity_state hit's source_chapter_sha to current canon SHA.

    Plan 05-03 / D-11 (Phase 4 SC6 closure). Only the entity_state axis carries
    source_chapter_sha (stamped at extraction time by Plan 04-03's defense-in-
    depth override). Mismatch between the stamped SHA and the current HEAD SHA
    for canon/chapter_NN.md means the card body is stale — the chapter has
    been rewritten since the card was extracted. Surface as ConflictReport
    with dimension='stale_card' so the Phase 3 critic sees the drift.

    Per-bundle memoization via a local dict (NOT lru_cache — A6 RESEARCH.md:
    lru_cache at module scope would persist across bundles and miss new
    commits between runs).
    """
    stale: list[ConflictReport] = []
    sha_by_chapter: dict[int, str | None] = {}
    for hit in entity_state_result.hits:
        card_sha = hit.metadata.get("source_chapter_sha")
        chapter = hit.metadata.get("chapter")
        if not card_sha or chapter is None:
            continue
        try:
            chapter_int = int(chapter)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            continue
        if chapter_int not in sha_by_chapter:
            sha_by_chapter[chapter_int] = _git_sha_for_chapter(
                chapter_int, repo_root
            )
        current_sha = sha_by_chapter[chapter_int]
        # None → Pitfall 6 graceful-degrade; match → no conflict.
        if current_sha is None or current_sha == card_sha:
            continue
        stale.append(
            ConflictReport(
                entity=hit.chunk_id,
                dimension="stale_card",
                severity="mid",
                values_by_retriever={
                    "entity_state.card_sha": str(card_sha),
                    "canon.head_sha": current_sha,
                },
                source_chunk_ids_by_retriever={
                    "entity_state": [hit.chunk_id],
                },
            )
        )
    return stale


class ContextPackBundlerImpl:
    """Concrete ContextPackBundler — implements the frozen Protocol.

    Constructor params are keyword-only (except event_logger) to surface misuse
    at call-site; matches the W-2 pattern from Plan 02-03 retrievers.
    """

    def __init__(
        self,
        event_logger: EventLogger | None,
        *,
        conflicts_dir: Path = Path("drafts/retrieval_conflicts"),
        ingestion_run_id: str | None = None,
        per_axis_caps: dict[str, int] | None = None,
        hard_cap: int = HARD_CAP,
        entity_list: set[str] | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.event_logger = event_logger
        self.conflicts_dir = Path(conflicts_dir)
        self.ingestion_run_id = ingestion_run_id
        self.per_axis_caps = per_axis_caps
        self.hard_cap = hard_cap
        # W-1: DI entity_list from the CLI layer. None = regex-only fallback.
        self.entity_list = entity_list
        # Plan 05-03: repo_root for the stale-card scan's git SHA lookup.
        # Defaults to Path.cwd() so production call sites (cli/draft.py +
        # cli/chapter.py composition roots) need no changes. Tests inject
        # a tmp_path-rooted git repo.
        self.repo_root = Path(repo_root) if repo_root is not None else Path.cwd()

    # --- Protocol impl -----------------------------------------------------

    def bundle(
        self, request: SceneRequest, retrievers: list[Retriever]
    ) -> ContextPack:
        """Run all retrievers; detect conflicts; enforce budget; emit 6 events; return pack.

        Returns a ContextPack with optional `conflicts` + `ingestion_run_id` fields
        (new in Plan 02-05; additive under Phase 1 freeze).
        """
        bundle_start_ns = time.monotonic_ns()
        # T-02-05-01: int-cast sanitization for filesystem path assembly.
        scene_id = (
            f"ch{int(request.chapter):02d}_sc{int(request.scene_index):02d}"
        )
        request_fp = hash_text(request.model_dump_json())

        retrievals: dict[str, RetrievalResult] = {}
        for retriever in retrievers:
            retrievals[retriever.name] = self._run_one_retriever(
                retriever, request, request_fp, scene_id
            )

        # Conflict detection BEFORE budget trimming so we see the full data.
        # W-1: pass entity_list injected at __init__ time.
        conflicts: list[ConflictReport] = detect_conflicts(
            retrievals, entity_list=self.entity_list
        )

        # Plan 05-03 (D-11 / SC6 closure): stale-card scan on entity_state
        # hits only. Append to conflicts; Phase 3 critic sees drift via the
        # unified conflicts list + the persisted conflicts JSON artifact.
        entity_state_result = retrievals.get("entity_state")
        if entity_state_result is not None and entity_state_result.hits:
            stale_conflicts = scan_for_stale_cards(
                entity_state_result, self.repo_root
            )
            if stale_conflicts:
                conflicts.extend(stale_conflicts)

        # Budget enforcement. Returns a new dict + trim_log; never mutates input.
        trimmed, trim_log = enforce_budget(
            retrievals, per_axis_caps=self.per_axis_caps, hard_cap=self.hard_cap
        )
        total_bytes = sum(rr.bytes_used for rr in trimmed.values())
        assert total_bytes <= self.hard_cap, (
            f"bundler: total_bytes {total_bytes} exceeds hard_cap {self.hard_cap}"
        )

        # Assemble pack.
        pack_content_for_fp = json.dumps(
            {k: v.model_dump(mode="json") for k, v in trimmed.items()},
            sort_keys=True,
        )
        pack_fingerprint = hash_text(pack_content_for_fp)

        pack = ContextPack(
            scene_request=request,
            retrievals=trimmed,
            total_bytes=total_bytes,
            assembly_strategy="round_robin",
            fingerprint=pack_fingerprint,
            conflicts=conflicts if conflicts else None,
            ingestion_run_id=self.ingestion_run_id,
        )

        # Persist conflicts to drafts/retrieval_conflicts/*.json for Phase 3.
        if conflicts:
            self._persist_conflicts(scene_id, conflicts)

        # Emit the bundler Event.
        bundle_latency_ms = max(
            1, (time.monotonic_ns() - bundle_start_ns) // 1_000_000
        )
        self._emit_bundler_event(
            request=request,
            request_fp=request_fp,
            pack_fingerprint=pack_fingerprint,
            total_bytes=total_bytes,
            conflicts=conflicts,
            trim_log=trim_log,
            latency_ms=int(bundle_latency_ms),
            scene_id=scene_id,
        )
        return pack

    # --- Helpers -----------------------------------------------------------

    def _run_one_retriever(
        self,
        retriever: Retriever,
        request: SceneRequest,
        request_fp: str,
        scene_id: str,
    ) -> RetrievalResult:
        """Invoke retriever.retrieve(); emit ONE retriever Event; return result.

        On exception: emit event with output_tokens=0 + extra['error'] set, and
        return an empty RetrievalResult so the bundle still completes
        (T-02-05-04 repudiation mitigation).

        BL-01: the ENTIRE emission path (retrieval + metadata + Event
        construction + emit) is wrapped so that exactly ONE retriever event
        is always emitted per call — even if model_dump_json(), Event(...)
        validation, or the injected event_logger raise. A degraded fallback
        event is assembled + emitted from a last-resort block so the
        bundler's 6-event invariant holds under adverse conditions.
        """
        start_ns = time.monotonic_ns()
        # Safe defaults so the fallback path can always produce an Event.
        retriever_name = getattr(retriever, "name", "unknown") or "unknown"
        error_class: str | None = None
        error_message: str | None = None
        rr: RetrievalResult = RetrievalResult(
            retriever_name=retriever_name,
            hits=[],
            bytes_used=0,
            query_fingerprint=request_fp,
        )
        idx_fp = "unresolved"
        output_hash = "error"
        try:
            try:
                rr = retriever.retrieve(request)
            except Exception as exc:
                error_class = type(exc).__name__
                error_message = str(exc)
                # rr retains the safe empty default.

            # index_fingerprint may raise on some backends; tolerate.
            try:
                idx_fp = retriever.index_fingerprint()
            except Exception as exc:
                idx_fp = f"error:{type(exc).__name__}"

            try:
                output_hash = hash_text(rr.model_dump_json())
            except Exception as exc:
                output_hash = "error"
                if error_class is None:
                    error_class = type(exc).__name__
                    error_message = f"serialize failure: {exc}"
                else:
                    error_message = (
                        f"{error_message}; serialize failure: "
                        f"{type(exc).__name__}: {exc}"
                    )

            latency_ms = max(1, (time.monotonic_ns() - start_ns) // 1_000_000)
            ts_iso = _now_iso()
            caller = f"rag.bundler.bundle:{retriever_name}"
            extra: dict[str, Any] = {
                "bytes_used": rr.bytes_used,
                "num_hits": len(rr.hits),
            }
            if error_class is not None:
                extra["status"] = "error"
                extra["error_class"] = error_class
                extra["error_message"] = error_message or ""
                # Back-compat with pre-BL-01 consumers that read extra['error'].
                extra["error"] = f"{error_class}: {error_message}"

            event = Event(
                event_id=event_id(
                    ts_iso, "retriever", caller, rr.query_fingerprint
                ),
                ts_iso=ts_iso,
                role="retriever",
                model=retriever_name,
                prompt_hash=rr.query_fingerprint,
                input_tokens=0,
                output_tokens=len(rr.hits),
                latency_ms=int(latency_ms),
                caller_context={
                    "module": "rag.bundler",
                    "function": "bundle",
                    "scene_id": scene_id,
                    "chapter_num": request.chapter,
                    "pov": request.pov,
                    "beat_function": request.beat_function,
                    "retriever_name": retriever_name,
                    "index_fingerprint": idx_fp,
                },
                output_hash=output_hash,
                extra=extra,
            )
            self._emit(event)
            return rr
        except Exception as outer_exc:
            # BL-01 last-resort: something raised while building or emitting
            # the per-retriever event (Event validation, logger disk-full,
            # etc). Synthesize a minimal Event and try again. If even THIS
            # fails we must still return rr so the bundle can complete with
            # the other retrievers — never let one retriever's failure
            # erase the 6-event invariant for the scene.
            outer_class = type(outer_exc).__name__
            outer_msg = str(outer_exc)
            combined_error = (
                f"{error_class}: {error_message}"
                if error_class is not None
                else f"{outer_class}: {outer_msg}"
            )
            fallback_extra: dict[str, Any] = {
                "bytes_used": 0,
                "num_hits": 0,
                "status": "error",
                "error_class": error_class or outer_class,
                "error_message": error_message or outer_msg,
                "error": combined_error,
                "emission_error_class": outer_class,
                "emission_error_message": outer_msg,
            }
            latency_ms = max(1, (time.monotonic_ns() - start_ns) // 1_000_000)
            ts_iso = _now_iso()
            try:
                fallback_event = Event(
                    event_id=event_id(
                        ts_iso,
                        "retriever",
                        f"rag.bundler.bundle:{retriever_name}",
                        request_fp,
                    ),
                    ts_iso=ts_iso,
                    role="retriever",
                    model=retriever_name,
                    prompt_hash=request_fp,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=int(latency_ms),
                    caller_context={
                        "module": "rag.bundler",
                        "function": "bundle",
                        "scene_id": scene_id,
                        "chapter_num": request.chapter,
                        "pov": request.pov,
                        "beat_function": request.beat_function,
                        "retriever_name": retriever_name,
                        "index_fingerprint": "unresolved",
                    },
                    output_hash="error",
                    extra=fallback_extra,
                )
                # Last-resort swallow: we CANNOT let an emit failure abort
                # the bundle loop. Downstream will miss this one event but
                # the bundler event still emits.
                with contextlib.suppress(Exception):
                    self._emit(fallback_event)
            except Exception:
                # Even Event() construction failed. Nothing left to do — do
                # NOT propagate; the bundle must continue so remaining
                # retrievers + the bundler event still emit.
                pass
            return rr

    def _emit_bundler_event(
        self,
        *,
        request: SceneRequest,
        request_fp: str,
        pack_fingerprint: str,
        total_bytes: int,
        conflicts: list[ConflictReport],
        trim_log: list[dict[str, Any]],
        latency_ms: int,
        scene_id: str,
    ) -> None:
        ts_iso = _now_iso()
        caller = "rag.bundler.bundle"
        conflicts_summary = [f"{c.entity}/{c.dimension}" for c in conflicts]
        event = Event(
            event_id=event_id(ts_iso, "context_pack_bundler", caller, request_fp),
            ts_iso=ts_iso,
            role="context_pack_bundler",
            model="ContextPackBundlerImpl",
            prompt_hash=request_fp,
            input_tokens=0,
            output_tokens=total_bytes,
            latency_ms=latency_ms,
            caller_context={
                "module": "rag.bundler",
                "function": "bundle",
                "scene_id": scene_id,
                "chapter_num": request.chapter,
                "pov": request.pov,
                "beat_function": request.beat_function,
                "num_conflicts": len(conflicts),
                "num_trims": len(trim_log),
            },
            output_hash=pack_fingerprint,
            extra={
                "trim_log": trim_log,
                "conflicts": conflicts_summary,
                "total_bytes": total_bytes,
            },
        )
        self._emit(event)

    def _emit(self, event: Event) -> None:
        if self.event_logger is not None:
            self.event_logger.emit(event)

    def _persist_conflicts(
        self, scene_id: str, conflicts: list[ConflictReport]
    ) -> None:
        """Write conflicts JSON to drafts/retrieval_conflicts/.

        Filename shape: `{ingestion_run_id}__{scene_id}.json` when an
        ingestion_run_id is present; otherwise `{scene_id}.json`. Both include
        the scene_id token so downstream consumers (Phase 3 critic) can glob
        by scene_id regardless of ingestion pin.
        """
        self.conflicts_dir.mkdir(parents=True, exist_ok=True)
        stem = (
            f"{self.ingestion_run_id}__{scene_id}"
            if self.ingestion_run_id
            else scene_id
        )
        path = self.conflicts_dir / f"{stem}.json"
        payload = [c.model_dump() for c in conflicts]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


__all__ = ["ContextPackBundlerImpl", "scan_for_stale_cards"]

# Silence unused-import analyzer: ContextPackBundler is referenced only for
# structural conformance tests; keep the explicit import so readers see the
# Protocol the class satisfies.
_ = ContextPackBundler
