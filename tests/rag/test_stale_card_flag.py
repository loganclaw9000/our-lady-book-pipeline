"""Tests for bundler stale-card flag (Plan 05-03 Task 3, SC6 closure).

Covers (D-11):
  - _card_to_row propagates EntityCard.source_chapter_sha into the LanceDB row.
  - scan_for_stale_cards emits ConflictReport(dimension='stale_card') on SHA
    mismatch; empty on match; graceful degrade outside a git repo.

Intentionally kept in tests/rag/ (not tests/chapter_assembler/) so the
bundler + reindex units stay the test-surface seam.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from book_pipeline.interfaces.types import (
    EntityCard,
    RetrievalHit,
    RetrievalResult,
)

# --- Helpers ---------------------------------------------------------------


class _FakeEmbedder:
    def encode(self, text: str) -> list[float]:
        # 1024-dim zeros — matches BGE-M3 shape for CHUNK_SCHEMA.
        return [0.0] * 1024


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


# --- Unit: _card_to_row extension -----------------------------------------


def test_card_to_row_includes_source_chapter_sha() -> None:
    from book_pipeline.rag.reindex import _card_to_row

    card = EntityCard(
        entity_name="Malintzin",
        last_seen_chapter=7,
        state={"current_state": "in Cholula"},
        evidence_spans=[],
        source_chapter_sha="abc123def456",
    )
    row = _card_to_row(
        card, ingestion_run_id="ing-1", embedder=_FakeEmbedder()
    )
    assert row["source_chapter_sha"] == "abc123def456", (
        "reindex._card_to_row must propagate EntityCard.source_chapter_sha "
        "into the LanceDB row for bundler stale-card scan (Plan 05-03 D-11)"
    )


# --- Unit: scan_for_stale_cards -------------------------------------------


def test_scan_for_stale_cards_no_mismatch(tmp_path: Path) -> None:
    from book_pipeline.rag.bundler import scan_for_stale_cards

    repo = _init_repo(tmp_path)
    sha = _commit(repo, "canon/chapter_99.md", "# Ch 99 v1\n", "canon(ch99): v1")

    result = RetrievalResult(
        retriever_name="entity_state",
        query_fingerprint="qf",
        bytes_used=10,
        hits=[
            RetrievalHit(
                text="card body",
                source_path="entity-state/chapter_99_entities.json",
                chunk_id="Malintzin",
                score=0.9,
                metadata={"source_chapter_sha": sha, "chapter": 99},
            )
        ],
    )
    out = scan_for_stale_cards(result, repo)
    assert out == [], f"expected no conflicts when SHA matches; got {out}"


def test_scan_for_stale_cards_mismatch_generates_conflict(tmp_path: Path) -> None:
    from book_pipeline.rag.bundler import scan_for_stale_cards

    repo = _init_repo(tmp_path)
    sha1 = _commit(repo, "canon/chapter_99.md", "# Ch 99 v1\n", "canon(ch99): v1")
    sha2 = _commit(repo, "canon/chapter_99.md", "# Ch 99 v2\n", "canon(ch99): v2")
    assert sha1 != sha2

    result = RetrievalResult(
        retriever_name="entity_state",
        query_fingerprint="qf",
        bytes_used=10,
        hits=[
            RetrievalHit(
                text="card body",
                source_path="entity-state/chapter_99_entities.json",
                chunk_id="Malintzin",
                score=0.9,
                # Card was stamped against the OLD SHA; HEAD now points at
                # the new one → stale.
                metadata={"source_chapter_sha": sha1, "chapter": 99},
            )
        ],
    )
    out = scan_for_stale_cards(result, repo)
    assert len(out) == 1, f"expected exactly 1 stale-card conflict; got {out}"
    conflict = out[0]
    assert conflict.dimension == "stale_card"
    assert conflict.entity == "Malintzin"
    assert conflict.values_by_retriever["entity_state.card_sha"] == sha1
    assert conflict.values_by_retriever["canon.head_sha"] == sha2


def test_scan_handles_non_git_repo(tmp_path: Path) -> None:
    """Pitfall 6: scanning in a tmp_path without .git must not crash; the
    scanner degrades gracefully (card treated as non-stale)."""
    from book_pipeline.rag.bundler import scan_for_stale_cards

    # No git init — tmp_path is a plain dir.
    result = RetrievalResult(
        retriever_name="entity_state",
        query_fingerprint="qf",
        bytes_used=10,
        hits=[
            RetrievalHit(
                text="card body",
                source_path="entity-state/chapter_99_entities.json",
                chunk_id="Malintzin",
                score=0.9,
                metadata={"source_chapter_sha": "abc123", "chapter": 99},
            )
        ],
    )
    out = scan_for_stale_cards(result, tmp_path)
    assert out == [], (
        f"Pitfall 6: non-git scan must return []; got {out}"
    )
