"""End-to-end integration test for Phase 4 (Plan 04-06).

Exercises Plans 04-01..04-05 composed end-to-end against a fully-mocked
LLM backend inside a tmp_path `git init`-ed repo. Regression-guards every
Phase 4 success criterion in a single test function:

  1. Deterministic assembly (3 scene fixtures -> canon/chapter_99.md with
     stable frontmatter + HTML scene markers + section separators).
  2. Fresh RAG pack for chapter critic (bundler_fingerprint_spy proves the
     chapter pack's fingerprint is not shared with any other bundle call).
  3. Atomic canon commit + 4-step post-commit DAG (git log shows 4 new
     commits in strict order; on-disk artifacts materialize).
  4. Surgical CHAPTER_FAIL routing (parametrized failure branch verifies
     no canon commit when critic rejects).
  5. Retrospective lint passes (`lint_retrospective` returns (True, [])).
  6. source_chapter_sha stamped and matches canon commit sha.
  7. Plan 03-07 B-3 invariant continues through chapter frontmatter
     (voice_pin_shas list size == 1 in happy path; size == 2 in the
     mid-chapter-pin-upgrade parametrize variant).
  8. LOOP-04 gate readiness (.planning/pipeline_state.json carries
     `dag_complete: True` and `last_committed_chapter: 99`).

All LLM surfaces are mocked via the conftest.MockLLMClient; retrievers +
embedder/reranker + bundler are monkey-patched. NO vLLM boot, NO real
Anthropic call, NO real git push.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from book_pipeline.entity_extractor.schema import EntityExtractionResponse
from book_pipeline.interfaces.types import ChapterState, ChapterStateRecord
from book_pipeline.retrospective.lint import lint_retrospective
from tests.integration.conftest import (
    ALT_VOICE_PIN_SHA,
    DEFAULT_VOICE_PIN_SHA,
    BundlerSpy,
    MockLLMClient,
    install_llm_client_monkeypatch,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _git_log_messages(repo: Path) -> list[str]:
    """Return `git log --pretty=%s` as a list, oldest-first."""
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--pretty=%s"],
        check=True,
        capture_output=True,
        text=True,
    )
    msgs = [line for line in out.stdout.splitlines() if line.strip()]
    return list(reversed(msgs))  # oldest-first


def _git_log_hashes(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--pretty=%H"],
        check=True,
        capture_output=True,
        text=True,
    )
    hashes = [h for h in out.stdout.splitlines() if h.strip()]
    return list(reversed(hashes))  # oldest-first


def _rewrite_scene_voice_pin(
    scene_path: Path, new_pin_sha: str
) -> None:
    """Rewrite a scene md fixture's voice_pin_sha (+ checkpoint_sha) in place.

    Used by the mid-chapter-pin-upgrade parametrize variant.
    """
    text = scene_path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"fixture {scene_path} must start with ---"
    _, rest = text.split("---\n", 1)
    fm_text, body = rest.split("\n---\n", 1)
    fm = yaml.safe_load(fm_text)
    fm["voice_pin_sha"] = new_pin_sha
    fm["checkpoint_sha"] = new_pin_sha
    scene_path.write_text(
        f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n{body}",
        encoding="utf-8",
    )


def _install_common_monkeypatches(
    monkeypatch: pytest.MonkeyPatch,
    mock_llm_client: MockLLMClient,
    mock_retrievers_factory: Any,
    mock_embedder_and_reranker: Any,
    bundler_fingerprint_spy: Any,
) -> None:
    """Single entry point that wires all the mock seams the test needs."""
    _ = (mock_retrievers_factory, mock_embedder_and_reranker, bundler_fingerprint_spy)
    install_llm_client_monkeypatch(monkeypatch, mock_llm_client)


# --------------------------------------------------------------------------- #
# Happy-path test                                                             #
# --------------------------------------------------------------------------- #


def test_end_to_end_3_scene_stub_chapter_dag(
    tmp_repo: Path,
    mock_llm_client: MockLLMClient,
    mock_retrievers_factory: Any,
    mock_embedder_and_reranker: Any,
    bundler_fingerprint_spy: BundlerSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full Phase 4 DAG exercised end-to-end against 3 scene fixtures."""
    import book_pipeline.cli.chapter as chapter_mod

    _install_common_monkeypatches(
        monkeypatch,
        mock_llm_client,
        mock_retrievers_factory,
        mock_embedder_and_reranker,
        bundler_fingerprint_spy,
    )

    # Capture initial commit count so we can assert the DAG added 4.
    pre_hashes = _git_log_hashes(tmp_repo)
    assert len(pre_hashes) == 1, (
        f"expected tmp_repo to have 1 seed commit, got {len(pre_hashes)}"
    )

    # Run the CLI entry point directly (bypasses argparse + subprocess).
    args = argparse.Namespace(
        chapter_num=99, expected_scene_count=3, no_archive=False
    )
    rc = chapter_mod._run(args)
    assert rc == 0, f"expected exit 0 (DAG_COMPLETE); got {rc}"

    # ---- Assertion group A: 4 new commits in strict order ---- #
    post_msgs = _git_log_messages(tmp_repo)
    new_msgs = post_msgs[len(pre_hashes):]  # oldest-first
    assert len(new_msgs) == 4, (
        f"expected exactly 4 new commits from the DAG; got {len(new_msgs)}: "
        f"{new_msgs!r}"
    )
    patterns = [
        re.compile(r"^canon\(ch99\):"),
        re.compile(r"^chore\(entity-state\):\s*ch99"),
        re.compile(r"^chore\(rag\):\s*reindex after ch99"),
        re.compile(r"^docs\(retro\):\s*ch99"),
    ]
    for i, (msg, pat) in enumerate(zip(new_msgs, patterns, strict=True)):
        assert pat.match(msg), (
            f"commit {i} ({msg!r}) does not match expected pattern {pat.pattern}"
        )

    # Capture the canon commit sha — used to verify source_chapter_sha stamping.
    post_hashes = _git_log_hashes(tmp_repo)
    canon_commit_sha = post_hashes[len(pre_hashes)]
    assert len(canon_commit_sha) == 40

    # ---- Assertion group B: on-disk artifacts + frontmatter shape ---- #
    canon_path = tmp_repo / "canon" / "chapter_99.md"
    assert canon_path.is_file(), f"expected {canon_path} to exist"
    canon_text = canon_path.read_text(encoding="utf-8")
    assert canon_text.startswith("---\n")
    _, rest = canon_text.split("---\n", 1)
    fm_text, body = rest.split("\n---\n", 1)
    chapter_fm = yaml.safe_load(fm_text)
    assert chapter_fm["chapter_num"] == 99
    assert chapter_fm["assembled_from_scenes"] == [
        "ch99_sc01",
        "ch99_sc02",
        "ch99_sc03",
    ]
    assert chapter_fm["chapter_critic_pass"] is True
    # B-3 invariant: all 3 scenes share the same pin sha -> size 1 dedup.
    assert chapter_fm["voice_pin_shas"] == [DEFAULT_VOICE_PIN_SHA], (
        f"expected single voice_pin_sha in happy path; got "
        f"{chapter_fm['voice_pin_shas']!r}"
    )
    assert chapter_fm["word_count"] > 0

    # 3 HTML scene markers + 2 section separators in body.
    assert body.count("<!-- scene: ch99_sc01 -->") == 1
    assert body.count("<!-- scene: ch99_sc02 -->") == 1
    assert body.count("<!-- scene: ch99_sc03 -->") == 1
    # Section separators between scenes.
    assert body.count("\n---\n") == 2, (
        f"expected 2 section separators between 3 scenes; got "
        f"{body.count(chr(10) + '---' + chr(10))}"
    )

    # ---- Assertion group C: entity-state JSON + source_chapter_sha ---- #
    entity_path = (
        tmp_repo / "entity-state" / "chapter_99_entities.json"
    )
    assert entity_path.is_file()
    entity_resp = EntityExtractionResponse.model_validate_json(
        entity_path.read_text(encoding="utf-8")
    )
    assert entity_resp.chapter_num == 99
    assert len(entity_resp.entities) >= 1
    for card in entity_resp.entities:
        assert card.source_chapter_sha == canon_commit_sha, (
            f"expected source_chapter_sha == {canon_commit_sha!r}; got "
            f"{card.source_chapter_sha!r}"
        )

    # ---- Assertion group D: retrospective lints clean ---- #
    retro_path = tmp_repo / "retrospectives" / "chapter_99.md"
    assert retro_path.is_file()
    from book_pipeline.chapter_assembler.dag import _parse_retro_md

    retro = _parse_retro_md(retro_path)
    assert retro.chapter_num == 99
    passed, reasons = lint_retrospective(retro)
    assert passed, f"lint failed; reasons: {reasons!r}"
    assert reasons == []

    # ---- Assertion group E: pipeline_state.json LOOP-04 gate ---- #
    pipeline_state = json.loads(
        (tmp_repo / ".planning" / "pipeline_state.json").read_text(
            encoding="utf-8"
        )
    )
    assert pipeline_state["last_committed_chapter"] == 99
    assert pipeline_state["last_committed_dag_step"] == 4
    assert pipeline_state["dag_complete"] is True
    assert pipeline_state["last_hard_block"] is None

    # ---- Assertion group F: chapter state record ---- #
    cs_path = tmp_repo / "drafts" / "chapter_buffer" / "ch99.state.json"
    assert cs_path.is_file()
    cs_record = ChapterStateRecord.model_validate_json(
        cs_path.read_text(encoding="utf-8")
    )
    assert cs_record.state == ChapterState.DAG_COMPLETE
    assert cs_record.dag_step == 4
    assert cs_record.chapter_sha == canon_commit_sha

    # ---- Assertion group G: fresh-pack invariant ---- #
    # There should be at least 1 bundler call with chapter-scoped request.
    chapter_pack_calls = [
        (req, fp)
        for (req, fp) in bundler_fingerprint_spy.calls
        if req.scene_index == 0 and req.beat_function == "chapter_overview"
    ]
    assert len(chapter_pack_calls) >= 1, (
        f"expected >=1 chapter-scoped bundle call; got calls="
        f"{[(c[0].scene_index, c[0].beat_function) for c in bundler_fingerprint_spy.calls]!r}"
    )
    chapter_fp = chapter_pack_calls[0][1]
    other_fps = {
        fp
        for (req, fp) in bundler_fingerprint_spy.calls
        if not (
            req.scene_index == 0 and req.beat_function == "chapter_overview"
        )
    }
    assert chapter_fp not in other_fps, (
        f"fresh-pack invariant violated: chapter_fp={chapter_fp!r} appears in "
        f"other_fps={other_fps!r}"
    )

    # ---- Assertion group H: events.jsonl role shape ---- #
    events_path = tmp_repo / "runs" / "events.jsonl"
    assert events_path.is_file()
    roles: set[str] = set()
    chapter_num_stamps: set[int] = set()
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        role = payload.get("role", "")
        roles.add(role)
        caller = payload.get("caller_context") or {}
        ch = caller.get("chapter_num") or caller.get("chapter")
        if ch is not None:
            chapter_num_stamps.add(int(ch))
    # All 3 Phase 4 Opus caller roles must appear.
    assert "chapter_critic" in roles, f"missing chapter_critic role; got {roles!r}"
    assert "entity_extractor" in roles, f"missing entity_extractor role; got {roles!r}"
    assert "retrospective_writer" in roles, (
        f"missing retrospective_writer role; got {roles!r}"
    )
    assert 99 in chapter_num_stamps, (
        f"expected chapter_num=99 stamps in events.jsonl; got "
        f"{chapter_num_stamps!r}"
    )

    # ---- Assertion group I: LLM calls counted ---- #
    # Chapter critic -> 1 parse(CriticResponse)
    # Entity extractor -> 1 parse(EntityExtractionResponse)
    # Retrospective writer -> 1 create(...)
    parse_types = [t for (t, _m) in mock_llm_client.messages.parse_calls]
    assert parse_types.count("CriticResponse") == 1
    assert parse_types.count("EntityExtractionResponse") == 1
    assert len(mock_llm_client.messages.create_calls) == 1


# --------------------------------------------------------------------------- #
# Parametrize variant: mid-chapter pin upgrade (voice_pin_shas size == 2)     #
# --------------------------------------------------------------------------- #


def test_end_to_end_mid_chapter_pin_upgrade(
    tmp_repo: Path,
    mock_llm_client: MockLLMClient,
    mock_retrievers_factory: Any,
    mock_embedder_and_reranker: Any,
    bundler_fingerprint_spy: BundlerSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mid-chapter pin upgrade: sc02 has a different voice_pin_sha.

    Asserts chapter frontmatter.voice_pin_shas == [sha_default, sha_alt]
    (size 2, order preserved by ConcatAssembler's dedup logic).
    """
    import book_pipeline.cli.chapter as chapter_mod

    _install_common_monkeypatches(
        monkeypatch,
        mock_llm_client,
        mock_retrievers_factory,
        mock_embedder_and_reranker,
        bundler_fingerprint_spy,
    )

    # Rewrite sc02's voice_pin_sha in the tmp_repo's drafts/ch99/.
    sc02_path = tmp_repo / "drafts" / "ch99" / "ch99_sc02.md"
    _rewrite_scene_voice_pin(sc02_path, ALT_VOICE_PIN_SHA)

    args = argparse.Namespace(
        chapter_num=99, expected_scene_count=3, no_archive=False
    )
    rc = chapter_mod._run(args)
    assert rc == 0

    canon_path = tmp_repo / "canon" / "chapter_99.md"
    canon_text = canon_path.read_text(encoding="utf-8")
    _, rest = canon_text.split("---\n", 1)
    fm_text, _body = rest.split("\n---\n", 1)
    chapter_fm = yaml.safe_load(fm_text)

    assert chapter_fm["voice_pin_shas"] == [
        DEFAULT_VOICE_PIN_SHA,
        ALT_VOICE_PIN_SHA,
    ], (
        f"expected [default, alt] ordered voice_pin_shas in mid-chapter-upgrade; "
        f"got {chapter_fm['voice_pin_shas']!r}"
    )


# --------------------------------------------------------------------------- #
# Parametrize variant: chapter critic fail → no canon commit, exit 3          #
# --------------------------------------------------------------------------- #


def test_chapter_critic_fail_no_canon_commit(
    tmp_repo: Path,
    mock_llm_client: MockLLMClient,
    mock_retrievers_factory: Any,
    mock_embedder_and_reranker: Any,
    bundler_fingerprint_spy: BundlerSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chapter critic returning overall_pass=False -> CHAPTER_FAIL, exit 3."""
    import book_pipeline.cli.chapter as chapter_mod

    mock_llm_client.messages.critic_overall_pass = False

    _install_common_monkeypatches(
        monkeypatch,
        mock_llm_client,
        mock_retrievers_factory,
        mock_embedder_and_reranker,
        bundler_fingerprint_spy,
    )

    pre_hashes = _git_log_hashes(tmp_repo)

    args = argparse.Namespace(
        chapter_num=99, expected_scene_count=3, no_archive=False
    )
    rc = chapter_mod._run(args)
    assert rc == 3, f"expected exit 3 on CHAPTER_FAIL; got {rc}"

    # No new commits.
    post_hashes = _git_log_hashes(tmp_repo)
    assert post_hashes == pre_hashes, (
        f"expected no new commits on CHAPTER_FAIL; got "
        f"{len(post_hashes) - len(pre_hashes)} new commits"
    )

    # canon/chapter_99.md must NOT exist.
    canon_path = tmp_repo / "canon" / "chapter_99.md"
    assert not canon_path.exists()

    # Chapter state record reached CHAPTER_FAIL.
    cs_path = tmp_repo / "drafts" / "chapter_buffer" / "ch99.state.json"
    if cs_path.is_file():
        cs_record = ChapterStateRecord.model_validate_json(
            cs_path.read_text(encoding="utf-8")
        )
        assert cs_record.state == ChapterState.CHAPTER_FAIL
        assert cs_record.dag_step == 0
        assert "chapter_critic_axis_fail" in cs_record.blockers

    # Silence unused-fixture warning.
    _ = shutil
