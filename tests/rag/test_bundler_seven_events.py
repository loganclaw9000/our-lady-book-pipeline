"""7-event bundler invariant test (Plan 07-02 PHYSICS-04).

After Plan 07-02 lands the 6th retriever (continuity_bible / CB-01), the
bundler's per-call event-count invariant grows from 6 → 7:
  - 6 retriever events (one per retriever) + 1 bundler event = 7 total.

The bundler's `bundle()` body does NOT change — it loops over whatever
retriever list it receives. This file exercises the new invariant by
passing 6 fake retrievers (the 5 frozen names + continuity_bible) and
asserting the event count and role partition.

This test is sibling to tests/rag/test_bundler.py::test_a (which still
asserts 6 events under the legacy 5-retriever call shape — both are
correct: the invariant is "1 event per retriever + 1 bundler event").
"""
from __future__ import annotations

from pathlib import Path

from book_pipeline.interfaces.types import (
    Event,
    RetrievalHit,
    RetrievalResult,
    SceneRequest,
)


class _FakeEventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class _FakeRetriever:
    def __init__(
        self, name: str, hits: list[tuple[str, str, float]]
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

    def retrieve(self, request: SceneRequest) -> RetrievalResult:
        return RetrievalResult(
            retriever_name=self.name,
            hits=list(self._hits),
            bytes_used=sum(len(h.text.encode("utf-8")) for h in self._hits),
            query_fingerprint="q-" + self.name,
        )

    def reindex(self) -> None:
        pass

    def index_fingerprint(self) -> str:
        return f"fake-{self.name}-idx"


def _six_retrievers() -> list[_FakeRetriever]:
    """5 frozen retrievers + the new 6th (continuity_bible / CB-01)."""
    return [
        _FakeRetriever(
            "historical",
            [("h1", "march at dawn", 0.9), ("h2", "bivouac at dusk", 0.5)],
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
            [("a1", "inciting moment", 0.95)],
        ),
        _FakeRetriever(
            "negative_constraint",
            [("n1", "avoid gunpowder", 0.85)],
        ),
        _FakeRetriever(
            "continuity_bible",
            [
                (
                    "canonical:andres_age",
                    "Andrés Olivares: age 23 throughout the campaign window.",
                    0.92,
                )
            ],
        ),
    ]


def _scene_request() -> SceneRequest:
    return SceneRequest(
        chapter=15,
        scene_index=2,
        pov="Andrés",
        date_iso="1519-08-30",
        location="Cempoala fortress",
        beat_function="warning",
    )


def test_bundle_emits_exactly_seven_events_with_six_retrievers(
    tmp_path: Path,
) -> None:
    """Plan 07-02: 6 retriever events + 1 bundler event = 7 events total."""
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    logger = _FakeEventLogger()
    bundler = ContextPackBundlerImpl(
        event_logger=logger,
        conflicts_dir=tmp_path / "conflicts",
    )
    pack = bundler.bundle(_scene_request(), _six_retrievers())

    assert len(logger.events) == 7, (
        f"expected 7 events with 6 retrievers; got {len(logger.events)}"
    )

    retriever_events = [e for e in logger.events if e.role == "retriever"]
    bundler_events = [
        e for e in logger.events if e.role == "context_pack_bundler"
    ]
    assert len(retriever_events) == 6
    assert len(bundler_events) == 1

    # All 6 retriever names represented (including the new continuity_bible).
    retriever_names = {
        e.caller_context["retriever_name"] for e in retriever_events
    }
    assert retriever_names == {
        "historical",
        "metaphysics",
        "entity_state",
        "arc_position",
        "negative_constraint",
        "continuity_bible",
    }

    # Pack must include the continuity_bible axis hits.
    assert "continuity_bible" in pack.retrievals
    cb_hits = pack.retrievals["continuity_bible"].hits
    assert len(cb_hits) == 1
    assert "Andrés" in cb_hits[0].text or "23" in cb_hits[0].text


def test_bundler_docstring_documents_seven_event_invariant() -> None:
    """Plan 07-02: bundler's bundle() docstring updated to 'emit 7 events'.

    Defense against accidental regression to the old 6-event count.
    """
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    doc = ContextPackBundlerImpl.bundle.__doc__ or ""
    assert "7 events" in doc, (
        f"bundle() docstring must mention '7 events'; got: {doc!r}"
    )
