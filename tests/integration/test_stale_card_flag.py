"""E2E regression test for Phase 4 SC6 deferral closure (Plan 05-03 Task 3).

Narrative spec (CONTEXT.md D-11):
  Mutate canon chapter by one byte → entity_state retriever hit carries the
  OLD source_chapter_sha (stamped at extraction time) → bundler's
  scan_for_stale_cards shells out to `git rev-list -1 HEAD -- canon/...` and
  observes mismatch → ConflictReport(dimension='stale_card') surfaces in
  ContextPack.conflicts.

Uses a real git repo in tmp_path + in-process RetrievalResult (bundler's
entity_state retriever is stubbed via a FakeRetriever returning our hand-
built hit). No LanceDB involved at this layer — _card_to_row has a dedicated
unit test; this test exercises the bundler's post-retrieval scan seam only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from book_pipeline.interfaces.types import (
    RetrievalHit,
    RetrievalResult,
    SceneRequest,
)


class _FakeRetriever:
    """Minimal Retriever returning a pre-built RetrievalResult."""

    def __init__(self, name: str, result: RetrievalResult) -> None:
        self.name = name
        self._result = result

    def retrieve(self, request: SceneRequest) -> RetrievalResult:
        return self._result

    def reindex(self) -> None:
        pass

    def index_fingerprint(self) -> str:
        return "fake-idx"


def _init_repo(tmp: Path) -> Path:
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=main", str(tmp)], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp), "config", "user.email", "t@x.com"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp), "config", "user.name", "T"], check=True
    )
    return tmp


def _commit(repo: Path, rel: str, content: str, msg: str) -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", msg], check=True
    )
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _empty_retriever(name: str) -> _FakeRetriever:
    return _FakeRetriever(
        name,
        RetrievalResult(
            retriever_name=name,
            hits=[],
            bytes_used=0,
            query_fingerprint=f"qf-{name}",
        ),
    )


def test_mutate_canon_by_one_byte_surfaces_stale_flag(tmp_path: Path) -> None:
    from book_pipeline.rag.bundler import ContextPackBundlerImpl

    # 1. Init repo + commit canon/chapter_99.md V1.
    repo = _init_repo(tmp_path)
    sha1 = _commit(
        repo, "canon/chapter_99.md", "# Chapter 99 v1 text\n", "canon(ch99): v1"
    )

    # 2. Build an entity_state hit stamped against sha1 (simulates reindex
    #    output at chapter-99 extraction time — Plan 04-03 defense-in-depth
    #    override guarantees this SHA matches canon HEAD at that moment).
    entity_hit = RetrievalHit(
        text="Malintzin entity card body",
        source_path="entity-state/chapter_99_entities.json",
        chunk_id="Malintzin",
        score=0.9,
        metadata={"source_chapter_sha": sha1, "chapter": 99},
    )
    entity_state_result = RetrievalResult(
        retriever_name="entity_state",
        hits=[entity_hit],
        bytes_used=len(entity_hit.text.encode("utf-8")),
        query_fingerprint="qf-es",
    )

    # 3. Mutate canon by ONE byte (v1 → v2) + commit → new HEAD sha.
    sha2 = _commit(
        repo, "canon/chapter_99.md", "# Chapter 99 v2 text\n", "canon(ch99): v2"
    )
    assert sha1 != sha2

    # 4. Build a bundler anchored at the tmp repo; exercise bundle().
    bundler = ContextPackBundlerImpl(
        event_logger=None,
        conflicts_dir=tmp_path / "retrieval_conflicts",
        repo_root=repo,
    )
    request = SceneRequest(
        chapter=99,
        scene_index=1,
        pov="Malintzin",
        date_iso="1519-10-20",
        location="Cholula",
        beat_function="translation",
    )
    retrievers = [
        _FakeRetriever("entity_state", entity_state_result),
        _empty_retriever("historical"),
        _empty_retriever("metaphysics"),
        _empty_retriever("arc_position"),
        _empty_retriever("negative_constraint"),
    ]
    pack = bundler.bundle(request, retrievers)

    # 5. Assert: ContextPack.conflicts contains a stale_card ConflictReport
    #    with both SHAs traceable.
    assert pack.conflicts, (
        "SC6: expected ContextPack.conflicts to contain the stale-card "
        f"ConflictReport; got {pack.conflicts}"
    )
    stale = [c for c in pack.conflicts if c.dimension == "stale_card"]
    assert len(stale) == 1, (
        f"expected exactly 1 dimension='stale_card' conflict; got {stale}"
    )
    conflict = stale[0]
    assert conflict.values_by_retriever["entity_state.card_sha"] == sha1
    assert conflict.values_by_retriever["canon.head_sha"] == sha2
    assert conflict.entity == "Malintzin"
