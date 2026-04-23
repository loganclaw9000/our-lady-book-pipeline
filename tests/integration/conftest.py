"""Integration-test fixtures for Plan 04-06 end-to-end DAG tests.

Shared fixtures:
  - tmp_repo          — tmp_path with `git init` + user.name/user.email configured,
                        real config/*.yaml copied from the repo root, 3 scene md
                        fixtures seeded into drafts/ch99/, indexes/ +
                        scene_buffer/ + chapter_buffer/ pre-created, an empty
                        initial git commit, and `monkeypatch.chdir(tmp_path)`
                        so all relative-path config loads resolve inside the
                        tmp repo.
  - mock_llm_client   — a MockLLMClient with scripted .messages.parse + .create
                        returning valid CriticResponse / EntityExtractionResponse
                        / lint-passing retrospective markdown on demand. Shared
                        across all 3 Phase 4 Opus callers.
  - mock_retrievers_factory — monkeypatches
                        book_pipeline.cli.chapter.build_retrievers_from_config
                        to return 5 FakeRetrievers keyed by axis name.
  - mock_embedder_and_reranker — no-op __init__ on BgeM3Embedder + BgeReranker
                        (avoids the 2GB model download at test time).
  - bundler_fingerprint_spy — wraps ContextPackBundlerImpl.bundle to record
                        every (scene_request, fingerprint) pair into a module
                        list, enabling fresh-pack-invariant assertions.

Hard constraint (plan prompt): NO vLLM boot, NO real Anthropic / claude CLI,
NO real git push. Every seam above is purely in-process.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from book_pipeline.entity_extractor.schema import EntityExtractionResponse
from book_pipeline.interfaces.types import (
    CriticResponse,
    EntityCard,
    SceneState,
    SceneStateRecord,
)
from book_pipeline.llm_clients.claude_code import (
    CreateResponse,
    ParseResponse,
    _TextBlock,
    _Usage,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# 64-char voice-pin sha matching the scene md fixtures (B-3 invariant — all
# three scenes share the same sha in the happy-path variant).
DEFAULT_VOICE_PIN_SHA = "abcd1234abcd5678abcd1234abcd5678abcd1234abcd5678abcd1234abcd5678"
ALT_VOICE_PIN_SHA = "ffff5678ffff5678ffff5678ffff5678ffff5678ffff5678ffff5678ffff5678"

# Lint-passing retrospective markdown — references ch99_sc01 + "entity" axis +
# an evidence quote (>=20 chars) so `lint_retrospective` returns (True, []).
_GOOD_RETRO_MD = """---
chapter_num: 99
candidate_theses:
  - id: q1
    description: "ch99_sc02 showed borderline entity drift; check Tlaxcala arc."
---

# Chapter 99 Retrospective

## What Worked
The historical axis held across ch99_sc01 and ch99_sc02; Marina's translation bridge stayed consistent through the Cempoala beat.

## What Drifted
ch99_sc02 showed a borderline entity-axis wobble on Motecuhzoma's tax-gatherers — "the tribute that Motecuhzoma's tax-gatherers demanded each season" reads cleanly but may foreshadow the later arc faster than outlined.

## Emerging Patterns
Early Cempoala beats may benefit from tighter metaphysics axis guidance before the Tlaxcalan frontier in ch99_sc03.

## Open Questions for Next Chapter
- Does the Tlaxcala alliance scene require a pre-flagged Mode-B escape?
"""


# --------------------------------------------------------------------------- #
# Mock LLM client                                                             #
# --------------------------------------------------------------------------- #


@dataclass
class _MockMessages:
    """Scripted messages.parse + .create for the 3 Phase 4 Opus callers."""

    parse_calls: list[tuple[str, Any]] = field(default_factory=list)
    create_calls: list[tuple[str, Any]] = field(default_factory=list)
    # Optional overrides — tests may set these to control failure branches.
    critic_overall_pass: bool = True
    entity_cards: list[EntityCard] | None = None
    retrospective_text: str = _GOOD_RETRO_MD

    def parse(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        output_format: Any,
        system: Any = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> ParseResponse:
        self.parse_calls.append((output_format.__name__, messages))
        if output_format.__name__ == "CriticResponse":
            axes = ("historical", "metaphysics", "entity", "arc", "donts")
            passing = self.critic_overall_pass
            return ParseResponse(
                parsed_output=CriticResponse(
                    pass_per_axis={a: passing for a in axes},
                    scores_per_axis={
                        a: 80.0 if passing else 40.0 for a in axes
                    },
                    issues=[],
                    overall_pass=passing,
                    model_id=model,
                    rubric_version="chapter.v1",
                    output_sha="mock_critic_output_sha",
                ),
                usage=_Usage(input_tokens=1, output_tokens=1),
                model=model,
            )
        if output_format.__name__ == "EntityExtractionResponse":
            cards = (
                list(self.entity_cards)
                if self.entity_cards is not None
                else [
                    EntityCard(
                        entity_name="Cortes",
                        last_seen_chapter=99,
                        state={
                            "aliases": [],
                            "entity_type": "person",
                            "first_mentioned_chapter": 99,
                            "current_state": "at Cempoala",
                            "relationships": [],
                            "confidence_score": 0.9,
                        },
                        evidence_spans=[
                            '"Cortes rode at the head of his column"'
                        ],
                        source_chapter_sha="WILL_BE_OVERRIDDEN",
                    )
                ]
            )
            return ParseResponse(
                parsed_output=EntityExtractionResponse(
                    entities=cards,
                    chapter_num=99,
                    extraction_timestamp="2026-04-22T12:00:00Z",
                ),
                usage=_Usage(input_tokens=1, output_tokens=1),
                model=model,
            )
        raise ValueError(
            f"Unexpected output_format: {output_format.__name__}"
        )

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: Any = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> CreateResponse:
        self.create_calls.append((model, messages))
        return CreateResponse(
            content=[_TextBlock(text=self.retrospective_text)],
            usage=_Usage(input_tokens=1, output_tokens=1),
            model=model,
        )


class MockLLMClient:
    """Drop-in LLMMessagesClient fake — parse + create on .messages."""

    def __init__(self) -> None:
        self.messages = _MockMessages()


# --------------------------------------------------------------------------- #
# Fake retrievers + embedder/reranker                                          #
# --------------------------------------------------------------------------- #


class _FakeRetriever:
    """Minimal retriever covering the surface the bundler + DAG step 3 touch."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.reindex_calls = 0

    def retrieve(self, request: Any) -> Any:
        # Lazy import to keep conftest import-cheap.
        from book_pipeline.interfaces.types import RetrievalResult

        return RetrievalResult(
            retriever_name=self.name,
            hits=[],
            bytes_used=0,
            query_fingerprint=f"fake_{self.name}_qfp",
        )

    def reindex(self) -> None:
        self.reindex_calls += 1

    def index_fingerprint(self) -> str:
        return f"fake_{self.name}_fp"


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def tmp_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """tmp_path with a real git repo, seeded scene md files, and configs.

    Layout after fixture setup:
      <tmp_path>/
        .git/               (git init)
        config/             (copied from repo root; all 4 yaml files)
          voice_pin.yaml
          rubric.yaml
          rag_retrievers.yaml
          mode_thresholds.yaml
        drafts/
          ch99/
            ch99_sc01.md
            ch99_sc02.md
            ch99_sc03.md
          scene_buffer/
            ch99/
              ch99_sc01.state.json   (state=COMMITTED)
              ch99_sc02.state.json
              ch99_sc03.state.json
          chapter_buffer/             (empty; DAG writes here)
        canon/                        (empty)
        entity-state/                 (empty)
        retrospectives/               (empty)
        indexes/
          resolved_model_revision.json
        runs/
          events.jsonl                (empty touch)
        .planning/                    (empty; DAG writes pipeline_state.json)
    """
    # --- git init ---------------------------------------------------------- #
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=main", str(tmp_path)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test User"],
        check=True,
    )
    # Disable pre-commit hooks so real repo hooks don't fire inside tmp_path.
    hooks_dir = tmp_path / ".git" / "hooks"
    for hook in hooks_dir.glob("*"):
        if hook.is_file():
            with contextlib.suppress(OSError):
                hook.unlink()

    # --- copy configs from the real repo --------------------------------- #
    cfg_src = REPO_ROOT / "config"
    cfg_dst = tmp_path / "config"
    cfg_dst.mkdir(exist_ok=True)
    for name in (
        "voice_pin.yaml",
        "rubric.yaml",
        "rag_retrievers.yaml",
        "mode_thresholds.yaml",
    ):
        shutil.copy2(cfg_src / name, cfg_dst / name)

    # --- symlink src/ so relative template paths resolve --------------- #
    # DEFAULT_{CHAPTER,EXTRACTOR,RETROSPECTIVE}_TEMPLATE_PATH are relative
    # ("src/book_pipeline/.../templates/*.j2"); after monkeypatch.chdir(tmp_path)
    # they'd fail to resolve without this symlink.
    (tmp_path / "src").symlink_to(REPO_ROOT / "src")

    # --- seed scene md files --------------------------------------------- #
    drafts_dir = tmp_path / "drafts"
    ch_dir = drafts_dir / "ch99"
    ch_dir.mkdir(parents=True, exist_ok=True)
    for name in ("ch99_sc01.md", "ch99_sc02.md", "ch99_sc03.md"):
        shutil.copy2(FIXTURES_DIR / name, ch_dir / name)

    # --- seed scene_buffer state records --------------------------------- #
    sb_dir = drafts_dir / "scene_buffer" / "ch99"
    sb_dir.mkdir(parents=True, exist_ok=True)
    for i in (1, 2, 3):
        record = SceneStateRecord(
            scene_id=f"ch99_sc{i:02d}",
            state=SceneState.COMMITTED,
            attempts={"mode_a_regens": 0, "mode_b_attempts": 0},
            mode_tag="A",
            history=[],
            blockers=[],
        )
        (sb_dir / f"ch99_sc{i:02d}.state.json").write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )

    # --- pre-create chapter_buffer/, canon/, entity-state/, retros/, runs/ # #
    (drafts_dir / "chapter_buffer").mkdir(parents=True, exist_ok=True)
    (tmp_path / "canon").mkdir(exist_ok=True)
    (tmp_path / "entity-state").mkdir(exist_ok=True)
    (tmp_path / "retrospectives").mkdir(exist_ok=True)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(exist_ok=True)
    (runs_dir / "events.jsonl").touch()
    (tmp_path / ".planning").mkdir(exist_ok=True)

    # --- resolved_model_revision.json ------------------------------------ #
    indexes_dir = tmp_path / "indexes"
    indexes_dir.mkdir(exist_ok=True)
    import json as _json

    (indexes_dir / "resolved_model_revision.json").write_text(
        _json.dumps(
            {
                "ingestion_run_id": "ing_test_20260422",
                "sha": "abcdef",
                "model": "BAAI/bge-m3",
                "resolved_at_iso": "2026-04-22T12:00:00Z",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # --- seed commit (so HEAD exists before DAG's canon commit) ----------- #
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "config"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"],
        check=True,
    )

    # --- belt-and-suspenders: no API key leaks into the mock path --------- #
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    # chdir so config loaders + relative paths resolve inside tmp_path.
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """A MockLLMClient shared across chapter-critic/extractor/retro."""
    return MockLLMClient()


@pytest.fixture
def mock_retrievers_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, _FakeRetriever]:
    """Monkeypatch build_retrievers_from_config to return 5 fakes.

    Returns the dict so tests can inspect reindex_calls, etc.
    """
    import book_pipeline.cli.chapter as chapter_mod

    fakes: dict[str, _FakeRetriever] = {
        "historical": _FakeRetriever("historical"),
        "metaphysics": _FakeRetriever("metaphysics"),
        "entity_state": _FakeRetriever("entity_state"),
        "arc_position": _FakeRetriever("arc_position"),
        "negative_constraint": _FakeRetriever("negative_constraint"),
    }

    def _fake_factory(**_kw: Any) -> dict[str, _FakeRetriever]:
        return dict(fakes)

    monkeypatch.setattr(
        chapter_mod, "build_retrievers_from_config", _fake_factory
    )
    return fakes


@pytest.fixture
def mock_embedder_and_reranker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace BgeM3Embedder + BgeReranker with no-op ctor fakes.

    The real classes eagerly load ~2GB of model weights from HuggingFace at
    __init__ time; that's unacceptable for a unit-grain integration test.
    """
    import book_pipeline.cli.chapter as chapter_mod

    class _FakeEmbedder:
        def __init__(self, **_kw: Any) -> None:
            self.model_name = "mock-bge-m3"

        def encode(self, text: str) -> list[float]:
            return [0.0] * 1024

    class _FakeReranker:
        def __init__(self, **_kw: Any) -> None:
            self.model_name = "mock-bge-reranker"

        def rerank(self, *a: Any, **kw: Any) -> list[Any]:
            return []

    monkeypatch.setattr(chapter_mod, "BgeM3Embedder", _FakeEmbedder)
    monkeypatch.setattr(chapter_mod, "BgeReranker", _FakeReranker)


@dataclass
class BundlerSpy:
    """Records every ContextPackBundlerImpl.bundle() call for later assertion."""

    calls: list[tuple[Any, str]] = field(default_factory=list)

    def record(self, scene_request: Any, fingerprint: str) -> None:
        self.calls.append((scene_request, fingerprint))


@pytest.fixture
def bundler_fingerprint_spy(
    monkeypatch: pytest.MonkeyPatch,
) -> BundlerSpy:
    """Wrap ContextPackBundlerImpl.bundle to tee every call into a spy list.

    Returns a BundlerSpy. After orchestrator.run(), tests assert:
      - At least one call where scene_request.scene_index == 0 AND
        .beat_function == 'chapter_overview' (the chapter critic's fresh
        pack).
      - That call's fingerprint is NOT in the set of fingerprints returned
        by any OTHER bundle() call (future-proof proxy for the end-to-end
        "chapter_pack.fingerprint NOT IN {scene_pack.fingerprint}" rule).
    """
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    spy = BundlerSpy()
    real_bundle = ContextPackBundlerImpl.bundle

    def _spy_bundle(self: Any, request: Any, retrievers: Any) -> Any:
        # Bundler iterates retrievers.values() if handed a dict; our mock
        # returns a list already. Use whichever path works.
        if hasattr(retrievers, "values"):
            retriever_list = list(retrievers.values())
        else:
            retriever_list = list(retrievers)
        # Replace with a minimal result that skips the real conflict
        # detector / budget enforcer — those need real RetrievalResults,
        # which our fakes don't produce.
        from book_pipeline.interfaces.types import ContextPack

        result = ContextPack(
            scene_request=request,
            retrievals={},
            total_bytes=0,
            assembly_strategy="round_robin",
            fingerprint=f"chapter_pack_fp_{request.scene_index}_{request.beat_function}",
            conflicts=None,
            ingestion_run_id="ing_test_20260422",
        )
        spy.record(request, result.fingerprint)
        # Silence unused vars.
        _ = (real_bundle, retriever_list)
        return result

    monkeypatch.setattr(
        ContextPackBundlerImpl, "bundle", _spy_bundle
    )
    return spy


# --------------------------------------------------------------------------- #
# Helper exported to tests                                                     #
# --------------------------------------------------------------------------- #


def install_llm_client_monkeypatch(
    monkeypatch: pytest.MonkeyPatch, mock_client: MockLLMClient
) -> None:
    """Patch build_llm_client where cli.chapter imported it.

    The CLI module does `from book_pipeline.llm_clients import build_llm_client`
    at module load, so the monkeypatch target is the *cli.chapter* module
    attribute, not the llm_clients source module.
    """
    import book_pipeline.cli.chapter as chapter_mod

    monkeypatch.setattr(
        chapter_mod, "build_llm_client", lambda cfg: mock_client
    )


# Re-export convenience for tests.
__all__ = [
    "ALT_VOICE_PIN_SHA",
    "DEFAULT_VOICE_PIN_SHA",
    "BundlerSpy",
    "MockLLMClient",
    "install_llm_client_monkeypatch",
]

# Silence Ruff's "imported but unused" on os (kept for future use / symmetry).
_ = os
