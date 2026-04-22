"""Tests for book_pipeline.rag.bundler.ContextPackBundlerImpl.

Per 02-05-PLAN.md Task 2 <behavior>:
  Test A: 5 fake retrievers, 3 hits each; bundle() emits exactly 6 Events
          (5 retriever + 1 bundler); total_bytes <= HARD_CAP; conflicts None
          when retrievals are disjoint.
  Test B: 2 retrievers with contradiction — ContextPack.conflicts populated AND
          drafts/retrieval_conflicts/<scene_id>.json written with valid JSON.
  Test C: retrievers whose total > 40KB — trim_log non-empty + total <= 40KB.
  Test D: retrievers don't emit events (fake retriever would emit if allowed);
          assert exactly 6 events total.
  Test E: ContextPackBundlerImpl structurally satisfies ContextPackBundler Protocol.
  Test F: Phase 1 Event schema v1.0 unbroken — all 18 fields present in emitted Event.
  Test G (W-1): entity_list detection catches Motecuhzoma / Nahuatl names that
          regex-only would miss.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from book_pipeline.interfaces.types import (
    Event,
    RetrievalHit,
    RetrievalResult,
    SceneRequest,
)

# --- Fakes ------------------------------------------------------------------


class _FakeEventLogger:
    """Captures emitted Events in-memory for assertion."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class _FakeRetriever:
    """Minimal retriever that returns a pre-built RetrievalResult.

    Would-be-leak behavior (Test D): has access to a logger reference passed at
    construction; if it *tried* to emit it would be counted. We never call it.
    """

    def __init__(
        self,
        name: str,
        hits: list[tuple[str, str, float]],
        index_fp: str = "fake-idx",
    ) -> None:
        self.name = name
        self._hits = [
            RetrievalHit(
                text=text,
                source_path=f"fixture_{name}.md",
                chunk_id=cid,
                score=score,
                metadata={"rule_type": "rule", "heading_path": "h"},
            )
            for (cid, text, score) in hits
        ]
        self._index_fp = index_fp

    def retrieve(self, request: SceneRequest) -> RetrievalResult:
        return RetrievalResult(
            retriever_name=self.name,
            hits=list(self._hits),
            bytes_used=sum(len(h.text.encode("utf-8")) for h in self._hits),
            query_fingerprint="q-" + self.name,
        )

    def reindex(self) -> None:
        pass  # no-op

    def index_fingerprint(self) -> str:
        return self._index_fp


def _five_disjoint_retrievers() -> list[_FakeRetriever]:
    return [
        _FakeRetriever(
            "historical",
            [("h1", "dawn marched west", 0.9), ("h2", "dusk returns east", 0.5), ("h3", "night camps", 0.1)],
        ),
        _FakeRetriever(
            "metaphysics",
            [("m1", "rule of rotation invariant", 0.8), ("m2", "second rule permits", 0.4), ("m3", "third rule says", 0.2)],
        ),
        _FakeRetriever(
            "entity_state",
            [("e1", "character alpha rested", 0.7), ("e2", "character beta returned", 0.6), ("e3", "character gamma slept", 0.3)],
        ),
        _FakeRetriever(
            "arc_position",
            [("a1", "inciting moment", 0.95), ("a2", "rising action cue", 0.55), ("a3", "turning pt", 0.25)],
        ),
        _FakeRetriever(
            "negative_constraint",
            [("n1", "avoid gunpowder", 0.85), ("n2", "avoid anachronism", 0.45), ("n3", "avoid modern slang", 0.15)],
        ),
    ]


def _scene_request() -> SceneRequest:
    return SceneRequest(
        chapter=1,
        scene_index=2,
        pov="Andrés",
        date_iso="1519-03-25",
        location="Potonchán",
        beat_function="inciting",
    )


# --- Tests ------------------------------------------------------------------


def test_a_bundle_emits_exactly_six_events_and_enforces_cap(tmp_path: Path) -> None:
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger,
        conflicts_dir=tmp_path / "conflicts",
    )
    pack = bundler.bundle(_scene_request(), _five_disjoint_retrievers())

    # Exactly 6 events (5 retriever + 1 bundler).
    assert len(logger.events) == 6, f"expected 6 events; got {len(logger.events)}"
    retriever_events = [e for e in logger.events if e.role == "retriever"]
    bundler_events = [e for e in logger.events if e.role == "context_pack_bundler"]
    assert len(retriever_events) == 5
    assert len(bundler_events) == 1

    # All 5 retriever names represented.
    retriever_names = {e.caller_context["retriever_name"] for e in retriever_events}
    assert retriever_names == {
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
    }

    # Pack contract.
    from book_pipeline.rag.budget import HARD_CAP

    assert pack.total_bytes <= HARD_CAP
    # Disjoint retrievers → no conflicts.
    assert pack.conflicts is None or pack.conflicts == []


def test_b_bundle_surfaces_conflicts_and_persists_artifact(tmp_path: Path) -> None:
    """Contradictory retrievers produce a ConflictReport AND a JSON artifact."""
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    conflicts_dir = tmp_path / "retrieval_conflicts"
    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger,
        conflicts_dir=conflicts_dir,
    )

    # 5 retrievers required by the bundler contract; 2 contradict on location.
    retrievers = [
        _FakeRetriever(
            "historical",
            [("h1", "Andrés is at Cempoala on 1519-06-02.", 0.9)],
        ),
        _FakeRetriever(
            "metaphysics",
            [("m1", "rule of rotation invariant", 0.8)],
        ),
        _FakeRetriever(
            "entity_state",
            [("e1", "Andrés is at Cerro Gordo on 1519-06-02.", 0.7)],
        ),
        _FakeRetriever(
            "arc_position",
            [("a1", "inciting moment", 0.95)],
        ),
        _FakeRetriever(
            "negative_constraint",
            [("n1", "avoid gunpowder", 0.85)],
        ),
    ]
    pack = bundler.bundle(_scene_request(), retrievers)

    assert pack.conflicts is not None
    assert len(pack.conflicts) >= 1
    # Artifact written.
    scene_id = f"ch{_scene_request().chapter:02d}_sc{_scene_request().scene_index:02d}"
    matching = list(conflicts_dir.glob(f"*{scene_id}*.json"))
    assert len(matching) == 1, (
        f"expected one conflict artifact matching {scene_id}; got {matching}"
    )
    data = json.loads(matching[0].read_text())
    assert isinstance(data, list)
    assert len(data) >= 1


def test_c_bundle_trims_when_total_exceeds_hard_cap(tmp_path: Path) -> None:
    """5 axes x 15KB each = 75KB; bundler must trim to <= 40KB."""
    from book_pipeline.rag.budget import HARD_CAP
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger, conflicts_dir=tmp_path / "conflicts"
    )

    def _heavy(prefix: str) -> list[tuple[str, str, float]]:
        return [
            (f"{prefix}1", "x" * 5000, 0.9),
            (f"{prefix}2", "y" * 5000, 0.5),
            (f"{prefix}3", "z" * 5000, 0.1),
        ]

    retrievers = [
        _FakeRetriever("historical", _heavy("h")),
        _FakeRetriever("metaphysics", _heavy("m")),
        _FakeRetriever("entity_state", _heavy("e")),
        _FakeRetriever("arc_position", _heavy("a")),
        _FakeRetriever("negative_constraint", _heavy("n")),
    ]
    pack = bundler.bundle(_scene_request(), retrievers)

    assert pack.total_bytes <= HARD_CAP, (
        f"bundler failed to enforce HARD_CAP; total_bytes={pack.total_bytes}"
    )
    # Bundler event's extra should carry a trim_log with at least one entry.
    bundler_event = next(e for e in logger.events if e.role == "context_pack_bundler")
    trim_log = bundler_event.extra.get("trim_log")
    assert isinstance(trim_log, list)
    assert len(trim_log) > 0


def test_d_retrievers_do_not_emit_events(tmp_path: Path) -> None:
    """Bundler is the SOLE emission site — exactly 6 events; retrievers silent."""
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger, conflicts_dir=tmp_path / "conflicts"
    )
    bundler.bundle(_scene_request(), _five_disjoint_retrievers())

    # Exactly 6 events. No more (retrievers would otherwise add their own).
    assert len(logger.events) == 6


def test_e_bundler_satisfies_context_pack_bundler_protocol(tmp_path: Path) -> None:
    from book_pipeline.interfaces.context_pack_bundler import ContextPackBundler
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger, conflicts_dir=tmp_path / "conflicts"
    )
    assert isinstance(bundler, ContextPackBundler)


def test_f_event_schema_v1_fields_preserved(tmp_path: Path) -> None:
    """Regression guard: Phase 1 Event v1.0 schema — all 18 fields round-trip."""
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger, conflicts_dir=tmp_path / "conflicts"
    )
    bundler.bundle(_scene_request(), _five_disjoint_retrievers())

    expected_fields = {
        "schema_version",
        "event_id",
        "ts_iso",
        "role",
        "model",
        "prompt_hash",
        "input_tokens",
        "cached_tokens",
        "output_tokens",
        "latency_ms",
        "temperature",
        "top_p",
        "caller_context",
        "output_hash",
        "mode",
        "rubric_version",
        "checkpoint_sha",
        "extra",
    }
    for e in logger.events:
        dumped = e.model_dump(mode="json")
        assert set(dumped.keys()) == expected_fields, (
            f"Event schema drift; got {set(dumped.keys())}"
        )
        # Round-trip validation.
        Event.model_validate(dumped)


def test_g_w1_entity_list_catches_motecuhzoma_conflict(tmp_path: Path) -> None:
    """W-1: with entity_list supplied, Nahuatl-named conflicts surface."""
    # Tests may import book_specifics; only the kernel is forbidden.
    from book_pipeline.book_specifics.nahuatl_entities import NAHUATL_CANONICAL_NAMES
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    entity_list: set[str] = set(NAHUATL_CANONICAL_NAMES.keys())
    for variants in NAHUATL_CANONICAL_NAMES.values():
        entity_list.update(variants)

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger,
        conflicts_dir=tmp_path / "conflicts",
        entity_list=entity_list,
    )

    retrievers = [
        _FakeRetriever(
            "historical",
            [("h1", "Motecuhzoma in Tenochtitlan received the envoys.", 0.9)],
        ),
        _FakeRetriever(
            "metaphysics",
            [("m1", "rule of rotation invariant", 0.8)],
        ),
        _FakeRetriever(
            "entity_state",
            [("e1", "character alpha rested", 0.7)],
        ),
        _FakeRetriever(
            "arc_position",
            [("a1", "Motecuhzoma is at Cholula during reckoning.", 0.9)],
        ),
        _FakeRetriever(
            "negative_constraint",
            [("n1", "avoid gunpowder", 0.85)],
        ),
    ]
    pack = bundler.bundle(_scene_request(), retrievers)

    assert pack.conflicts is not None
    motecuh_conflicts = [c for c in pack.conflicts if c.entity == "Motecuhzoma"]
    assert len(motecuh_conflicts) >= 1, (
        f"W-1 entity_list did not surface Motecuhzoma conflict; got {pack.conflicts}"
    )


def test_bundler_ingestion_run_id_plumbed_to_pack(tmp_path: Path) -> None:
    """If bundler is constructed with ingestion_run_id, it lands on the pack."""
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger,
        conflicts_dir=tmp_path / "conflicts",
        ingestion_run_id="ing-test-42",
    )
    pack = bundler.bundle(_scene_request(), _five_disjoint_retrievers())
    assert pack.ingestion_run_id == "ing-test-42"


def test_bundler_retriever_event_caller_context_shape(tmp_path: Path) -> None:
    """Each retriever event carries scene_id, chapter_num, pov, beat_function, retriever_name."""
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger, conflicts_dir=tmp_path / "conflicts"
    )
    req = _scene_request()
    bundler.bundle(req, _five_disjoint_retrievers())

    retriever_events = [e for e in logger.events if e.role == "retriever"]
    for e in retriever_events:
        cc: dict[str, Any] = e.caller_context
        assert cc.get("scene_id") == f"ch{req.chapter:02d}_sc{req.scene_index:02d}"
        assert cc.get("chapter_num") == req.chapter
        assert cc.get("pov") == req.pov
        assert cc.get("beat_function") == req.beat_function
        assert "retriever_name" in cc
        assert "index_fingerprint" in cc
