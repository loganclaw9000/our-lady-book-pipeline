"""Tests for 12 Protocol interfaces + 13 stub implementations (FOUND-04).

Covers:
- Each Protocol imports from book_pipeline.interfaces
- Each Protocol is @runtime_checkable (isinstance works)
- Each stub satisfies `isinstance(stub, Protocol)` (structural typing)
- Each stub method raises NotImplementedError with descriptive message
- Each Protocol has a non-empty docstring
"""

from __future__ import annotations

import pytest

from book_pipeline.interfaces import (
    ChapterAssembler,
    ContextPackBundler,
    Critic,
    DigestGenerator,
    Drafter,
    EntityExtractor,
    EventLogger,
    Orchestrator,
    Regenerator,
    Retriever,
    RetrospectiveWriter,
    ThesisMatcher,
)
from book_pipeline.stubs import (
    StubChapterAssembler,
    StubContextPackBundler,
    StubCritic,
    StubDigestGenerator,
    StubDrafter,
    StubEntityExtractor,
    StubEventLogger,
    StubOrchestrator,
    StubRegenerator,
    StubRetriever,
    StubRetrospectiveWriter,
    StubSceneStateMachine,
    StubThesisMatcher,
)

PROTOCOL_STUB_PAIRS = [
    (ChapterAssembler, StubChapterAssembler),
    (ContextPackBundler, StubContextPackBundler),
    (Critic, StubCritic),
    (DigestGenerator, StubDigestGenerator),
    (Drafter, StubDrafter),
    (EntityExtractor, StubEntityExtractor),
    (EventLogger, StubEventLogger),
    (Orchestrator, StubOrchestrator),
    (Regenerator, StubRegenerator),
    (Retriever, StubRetriever),
    (RetrospectiveWriter, StubRetrospectiveWriter),
    (ThesisMatcher, StubThesisMatcher),
]


@pytest.mark.parametrize("protocol,stub_cls", PROTOCOL_STUB_PAIRS)
def test_stub_satisfies_protocol_isinstance(protocol: type, stub_cls: type) -> None:
    """FOUND-04 SC-4: stubs satisfy isinstance() for their Protocol."""
    assert isinstance(stub_cls(), protocol), (
        f"{stub_cls.__name__} does not satisfy {protocol.__name__}"
    )


@pytest.mark.parametrize("protocol,stub_cls", PROTOCOL_STUB_PAIRS)
def test_protocol_has_docstring(protocol: type, stub_cls: type) -> None:
    """FOUND-04: each Protocol has a docstring contract."""
    assert protocol.__doc__ is not None and len(protocol.__doc__.strip()) > 0, (
        f"{protocol.__name__} missing docstring"
    )


def test_stub_drafter_raises_not_implemented() -> None:
    from book_pipeline.interfaces.types import ContextPack, DraftRequest, SceneRequest

    sr = SceneRequest(
        chapter=1,
        scene_index=1,
        pov="P",
        date_iso="1519-01-01",
        location="L",
        beat_function="b",
    )
    cp = ContextPack(scene_request=sr, retrievals={}, total_bytes=0, fingerprint="h")
    req = DraftRequest(context_pack=cp)
    with pytest.raises(NotImplementedError, match="Phase 3"):
        StubDrafter().draft(req)


def test_stub_retriever_raises_not_implemented() -> None:
    from book_pipeline.interfaces.types import SceneRequest

    sr = SceneRequest(
        chapter=1,
        scene_index=1,
        pov="P",
        date_iso="1519-01-01",
        location="L",
        beat_function="b",
    )
    with pytest.raises(NotImplementedError):
        StubRetriever().retrieve(sr)
    with pytest.raises(NotImplementedError):
        StubRetriever().reindex()
    with pytest.raises(NotImplementedError):
        StubRetriever().index_fingerprint()


def test_stub_critic_raises_not_implemented() -> None:
    from book_pipeline.interfaces.types import ContextPack, CriticRequest, SceneRequest

    sr = SceneRequest(
        chapter=1,
        scene_index=1,
        pov="P",
        date_iso="1519-01-01",
        location="L",
        beat_function="b",
    )
    cp = ContextPack(scene_request=sr, retrievals={}, total_bytes=0, fingerprint="h")
    req = CriticRequest(scene_text="scene", context_pack=cp, rubric_id="r", rubric_version="v")
    with pytest.raises(NotImplementedError):
        StubCritic().review(req)


def test_stub_event_logger_raises_not_implemented() -> None:
    from book_pipeline.interfaces.types import Event

    e = Event(
        event_id="x",
        ts_iso="2026-04-21T00:00:00Z",
        role="drafter",
        model="m",
        prompt_hash="p",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
        output_hash="o",
    )
    with pytest.raises(NotImplementedError, match="plan 05"):
        StubEventLogger().emit(e)


def test_stub_orchestrator_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        StubOrchestrator().run_cycle(budget={})


def test_stub_scene_state_machine_transition_is_wrapper() -> None:
    """StubSceneStateMachine.transition delegates to interfaces helper (not NotImplementedError).

    SceneStateMachine is not an LLM-calling Protocol; the transition function is
    pure-Python and ready today. The stub exposes it as a uniform method wrapper.
    """
    from book_pipeline.interfaces.types import SceneState, SceneStateRecord

    rec = SceneStateRecord(scene_id="ch01_sc01", state=SceneState.PENDING)
    new_rec = StubSceneStateMachine().transition(rec, SceneState.RAG_READY, "ok")
    assert new_rec.state == SceneState.RAG_READY


def test_all_protocols_importable_from_package() -> None:
    """FOUND-04 SC-4: 12 Protocols importable from book_pipeline.interfaces.

    13th "interface" — SceneStateMachine — is types.py exports (SceneState,
    SceneStateRecord, transition).
    """
    from book_pipeline.interfaces import (  # noqa: F401
        ChapterAssembler,
        ContextPackBundler,
        Critic,
        DigestGenerator,
        Drafter,
        EntityExtractor,
        EventLogger,
        Orchestrator,
        Regenerator,
        Retriever,
        RetrospectiveWriter,
        SceneState,
        SceneStateRecord,
        ThesisMatcher,
        transition,
    )


def test_all_protocol_names_in_package_all() -> None:
    """Package __all__ contains the 12 Protocol names plus type exports."""
    import book_pipeline.interfaces as iface

    for name in [
        "ChapterAssembler",
        "ContextPackBundler",
        "Critic",
        "DigestGenerator",
        "Drafter",
        "EntityExtractor",
        "EventLogger",
        "Orchestrator",
        "Regenerator",
        "Retriever",
        "RetrospectiveWriter",
        "ThesisMatcher",
    ]:
        assert name in iface.__all__, f"{name} missing from book_pipeline.interfaces.__all__"


def test_protocols_are_runtime_checkable() -> None:
    """Each Protocol uses @runtime_checkable — isinstance() must work without error.

    If any Protocol is missing @runtime_checkable, isinstance() raises TypeError.
    """
    for proto, stub_cls in PROTOCOL_STUB_PAIRS:
        try:
            result = isinstance(stub_cls(), proto)
        except TypeError as exc:
            pytest.fail(f"{proto.__name__} is not @runtime_checkable: {exc}")
        assert result is True


def test_stubs_module_exports() -> None:
    """book_pipeline.stubs.__all__ lists all 13 stubs."""
    import book_pipeline.stubs as stubs_mod

    expected = {
        "StubChapterAssembler",
        "StubContextPackBundler",
        "StubCritic",
        "StubDigestGenerator",
        "StubDrafter",
        "StubEntityExtractor",
        "StubEventLogger",
        "StubOrchestrator",
        "StubRegenerator",
        "StubRetriever",
        "StubRetrospectiveWriter",
        "StubSceneStateMachine",
        "StubThesisMatcher",
    }
    assert expected.issubset(set(stubs_mod.__all__))
