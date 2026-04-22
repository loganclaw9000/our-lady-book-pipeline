"""V-2 memorization gate — 12-gram overlap scan against training corpus.

PITFALLS V-2 mitigation (Plan 03-04 Task 1): any 12-gram in a drafted scene
that matches a 12-gram from the training corpus (specifically, the assistant-
role "gpt" turn of each row in paul-thinkpiece-pipeline's train_filtered.jsonl)
is treated as a HARD BLOCK. ModeADrafter catches the hit list and raises
ModeADrafterBlocked("training_bleed").

This module lives in the kernel and MUST NOT carry book-domain-specific
logic. The training corpus PATH is injected by the CLI composition layer
(Plan 03-06) from a book-domain pointer module; this gate only cares about
the jsonl row shape.

Algorithm:
    On construction:
      For each row, if row["conversations"][-1]["from"] == "gpt":
        tokens = row["conversations"][-1]["value"].split()
        for i in range(len(tokens) - ngram + 1):
          gram = " ".join(tokens[i:i+ngram])
          self._hashes.add(xxhash.xxh64_intdigest(gram.encode("utf-8")))
    On scan(scene_text):
      Tokenize scene, emit any 12-gram whose xxh64 digest is in self._hashes.

xxhash.xxh64_intdigest is stable across processes — no PYTHONHASHSEED risk
(stdlib hash() is deliberately NOT used for this reason).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import xxhash
from pydantic import BaseModel


class MemorizationHit(BaseModel):
    """One 12-gram match between a scene and the training corpus."""

    ngram: str
    position: int  # token index inside the scene where the 12-gram starts


class TrainingBleedGate:
    """Preloaded 12-gram hash set against a paul-thinkpiece-style jsonl corpus.

    Construction scans the corpus ONCE and builds an in-memory set[int] of
    xxh64 digests. Subsequent .scan(scene_text) calls are O(len(scene_text))
    hash lookups — no further I/O.

    Usage (Plan 03-06 CLI composition):

        gate = TrainingBleedGate(TRAINING_CORPUS_DEFAULT, ngram=12)
        drafter = ModeADrafter(..., memorization_gate=gate)
    """

    def __init__(self, training_corpus_path: Path, ngram: int = 12) -> None:
        self.training_corpus_path = Path(training_corpus_path).expanduser()
        self.ngram = ngram
        self._hashes: set[int] = set()
        self.row_count = 0
        self.ngram_count = 0
        self._preload()

    def _preload(self) -> None:
        path = self.training_corpus_path
        if not path.exists():
            # Empty gate — no training corpus available. Plan 03-06 decides
            # whether to tolerate this (e.g. smoke runs) or hard-fail at CLI
            # composition time. The kernel gate itself stays tolerant.
            print(
                f"[TrainingBleedGate] WARNING: corpus not found at {path}; "
                f"gate will not block any drafts",
                file=sys.stderr,
            )
            return
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                conv = row.get("conversations") or []
                if not conv:
                    continue
                last = conv[-1]
                if not isinstance(last, dict):
                    continue
                if last.get("from") != "gpt":
                    continue
                value = last.get("value")
                if not isinstance(value, str) or not value.strip():
                    continue
                tokens = value.split()
                if len(tokens) < self.ngram:
                    continue
                self.row_count += 1
                for i in range(len(tokens) - self.ngram + 1):
                    gram = " ".join(tokens[i : i + self.ngram])
                    self._hashes.add(xxhash.xxh64_intdigest(gram.encode("utf-8")))
                    self.ngram_count += 1
        print(
            f"[TrainingBleedGate] preloaded {self.row_count} rows, "
            f"{self.ngram_count} {self.ngram}-grams into {len(self._hashes)}-hash set "
            f"from {path}",
            file=sys.stderr,
        )

    def scan(self, scene_text: str) -> list[MemorizationHit]:
        """Return all positions where a 12-gram of scene_text matches the corpus.

        Empty list = pass. Any non-empty list = caller raises
        ModeADrafterBlocked("training_bleed").
        """
        if not scene_text:
            return []
        tokens = scene_text.split()
        if len(tokens) < self.ngram:
            return []
        hits: list[MemorizationHit] = []
        for i in range(len(tokens) - self.ngram + 1):
            gram = " ".join(tokens[i : i + self.ngram])
            if xxhash.xxh64_intdigest(gram.encode("utf-8")) in self._hashes:
                hits.append(MemorizationHit(ngram=gram, position=i))
        return hits


__all__ = ["MemorizationHit", "TrainingBleedGate"]
