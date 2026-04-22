"""Book-domain pointer to the paul-thinkpiece-pipeline training corpus.

Plan 03-04 Task 1. The V-2 TrainingBleedGate in
book_pipeline.drafter.memorization_gate is corpus-agnostic; this module
declares WHERE the corpus lives on disk. The kernel never imports this —
the CLI composition seam at src/book_pipeline/cli/ (Plan 03-06) is the ONE
sanctioned bridge (pyproject.toml ignore_imports).

Row shape (declared in TRAINING_CORPUS_SOURCE_KEY):
    row["conversations"][-1]["from"] == "gpt"
    row["conversations"][-1]["value"] → the assistant-turn text to hash
"""
from __future__ import annotations

from pathlib import Path

TRAINING_CORPUS_DEFAULT: Path = Path(
    "~/paul-thinkpiece-pipeline/v3_data/train_filtered.jsonl"
).expanduser()

# Documents where the assistant-turn text lives inside each jsonl row. The
# gate's _preload() follows this shape literally.
TRAINING_CORPUS_SOURCE_KEY: str = "conversations.gpt"

__all__ = ["TRAINING_CORPUS_DEFAULT", "TRAINING_CORPUS_SOURCE_KEY"]
