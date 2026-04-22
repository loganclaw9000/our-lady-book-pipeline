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

import json
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
    ) -> None:
        self.event_logger = event_logger
        self.conflicts_dir = Path(conflicts_dir)
        self.ingestion_run_id = ingestion_run_id
        self.per_axis_caps = per_axis_caps
        self.hard_cap = hard_cap
        # W-1: DI entity_list from the CLI layer. None = regex-only fallback.
        self.entity_list = entity_list

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
        """
        start_ns = time.monotonic_ns()
        error_msg: str | None = None
        rr: RetrievalResult
        try:
            rr = retriever.retrieve(request)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            rr = RetrievalResult(
                retriever_name=retriever.name,
                hits=[],
                bytes_used=0,
                query_fingerprint=request_fp,
            )
        latency_ms = max(1, (time.monotonic_ns() - start_ns) // 1_000_000)

        # index_fingerprint may raise on some backends; tolerate.
        try:
            idx_fp = retriever.index_fingerprint()
        except Exception as exc:
            idx_fp = f"error:{type(exc).__name__}"

        output_hash_input = rr.model_dump_json()
        output_hash = hash_text(output_hash_input)
        ts_iso = _now_iso()
        caller = f"rag.bundler.bundle:{retriever.name}"
        extra: dict[str, Any] = {
            "bytes_used": rr.bytes_used,
            "num_hits": len(rr.hits),
        }
        if error_msg is not None:
            extra["error"] = error_msg

        event = Event(
            event_id=event_id(ts_iso, "retriever", caller, rr.query_fingerprint),
            ts_iso=ts_iso,
            role="retriever",
            model=retriever.name,
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
                "retriever_name": retriever.name,
                "index_fingerprint": idx_fp,
            },
            output_hash=output_hash,
            extra=extra,
        )
        self._emit(event)
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


__all__ = ["ContextPackBundlerImpl"]

# Silence unused-import analyzer: ContextPackBundler is referenced only for
# structural conformance tests; keep the explicit import so readers see the
# Protocol the class satisfies.
_ = ContextPackBundler
