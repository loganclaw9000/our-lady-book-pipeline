"""Tests for book_pipeline.drafter.memorization_gate (Plan 03-04 Task 1).

V-2 PITFALLS mitigation: 12-gram overlap scan against paul-thinkpiece-pipeline
training corpus. Any hit → ModeADrafterBlocked("training_bleed") in drafter.
"""
from __future__ import annotations

import json
from pathlib import Path

from book_pipeline.drafter.memorization_gate import (
    MemorizationHit,
    TrainingBleedGate,
)


def _write_corpus(path: Path, gpt_texts: list[str]) -> None:
    """Write a synthetic paul-thinkpiece-style jsonl; each row has a gpt turn."""
    with path.open("w", encoding="utf-8") as fh:
        for t in gpt_texts:
            row = {
                "conversations": [
                    {"from": "system", "value": "you are paul"},
                    {"from": "human", "value": "prompt"},
                    {"from": "gpt", "value": t},
                ],
                "task_type": "fixture",
            }
            fh.write(json.dumps(row) + "\n")


# --- Test 4: 12-gram hit in scene_text raises a MemorizationHit --------------

def test_training_bleed_gate_detects_12gram_hit(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    _write_corpus(
        corpus,
        [
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi",
        ],
    )
    gate = TrainingBleedGate(corpus, ngram=12)
    # Scene text that overlaps first 12 tokens of the corpus row.
    scene = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    hits = gate.scan(scene)
    assert len(hits) == 1
    assert isinstance(hits[0], MemorizationHit)
    # Position 0 — the hit starts at index 0 of the scene.
    assert hits[0].position == 0


# --- Test 5: no overlap returns [] ------------------------------------------

def test_training_bleed_gate_no_hit_on_unrelated_text(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    _write_corpus(
        corpus,
        [
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi",
        ],
    )
    gate = TrainingBleedGate(corpus, ngram=12)
    scene = (
        "entirely unrelated prose across fourteen words here now really "
        "without any overlap at all"
    )
    hits = gate.scan(scene)
    assert hits == []


# --- Test 6: scene with fewer than ngram tokens returns [] -------------------

def test_training_bleed_gate_returns_empty_when_too_short(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    _write_corpus(corpus, ["one two three four five six seven eight nine ten eleven twelve"])
    gate = TrainingBleedGate(corpus, ngram=12)
    # 11 tokens — below ngram threshold.
    scene = "one two three four five six seven eight nine ten eleven"
    hits = gate.scan(scene)
    assert hits == []


def test_training_bleed_gate_ignores_non_gpt_turns(tmp_path: Path) -> None:
    """Only conversations[-1]["from"]=="gpt" rows are indexed."""
    corpus = tmp_path / "corpus.jsonl"
    # Row has gpt value "X" but there's a preceding row whose last turn is "human".
    with corpus.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "conversations": [
                        {"from": "system", "value": "s"},
                        {"from": "gpt", "value": "ignored because last turn is human"},
                        {"from": "human", "value": "hopeful paul response that exceeds twelve tokens should not appear in hash set"},
                    ],
                    "task_type": "test",
                }
            )
            + "\n"
        )
    gate = TrainingBleedGate(corpus, ngram=12)
    scene = (
        "hopeful paul response that exceeds twelve tokens should not appear in hash set"
    )
    # The human turn isn't indexed — so no hit.
    hits = gate.scan(scene)
    assert hits == []


def test_training_bleed_gate_exposes_counts(tmp_path: Path) -> None:
    """Gate records row_count + ngram_count on construction for Plan 03-06 UX."""
    corpus = tmp_path / "corpus.jsonl"
    _write_corpus(
        corpus,
        [
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi",
            "second row alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
        ],
    )
    gate = TrainingBleedGate(corpus, ngram=12)
    # Both rows have >=12 tokens; gate exposes the count for Plan 03-06 UX.
    assert gate.row_count == 2
    assert gate.ngram_count >= 2  # at least one 12-gram per row
