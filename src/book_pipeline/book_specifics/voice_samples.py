"""Book-authored voice-samples source pointers (Plan 05-01 D-03).

Mode-B drafting (D-03) needs 3-5 curated 400-600-word passages from Paul's
thinkpiece training corpus. Selection rule (per D-03, mirroring Plan 03-02
anchor_sources.py): same ANALYTIC + ESSAY + NARRATIVE balance as the anchor
curator, but LONGER passages (anchors are 150-250 words for cosine-scoring;
samples are 400-600 words for in-context voice priming — different job).

Kernel never imports this — the CLI composition seam at
src/book_pipeline/cli/curate_voice_samples.py is the ONE sanctioned bridge
(pyproject.toml ignore_imports).

Sub-genre classification is filename-based: files named `narrative_*.txt`,
`essay_*.txt`, `analytic_*.txt` in any source dir are recognized. Operator
can hand-curate a directory of .txt files with that naming convention, or
seed from the thinkpiece jsonl corpus via an auxiliary script.
"""
from __future__ import annotations

from pathlib import Path

# Default source directories for voice-sample candidates (book-domain).
# Production path: paul-thinkpiece-pipeline training corpus on DGX Spark.
# Operator can override via --source-dir on the curate-voice-samples CLI.
DEFAULT_SOURCE_DIRS: tuple[Path, ...] = (
    Path("/home/admin/paul-thinkpiece-pipeline/voice_samples/narrative"),
    Path("/home/admin/paul-thinkpiece-pipeline/voice_samples/essay"),
    Path("/home/admin/paul-thinkpiece-pipeline/voice_samples/analytic"),
)

# Curation heuristic (paraphrase of Plan 03-02 anchor_sources.py selection
# rule, adjusted for longer passages).
TARGET_WORD_MIN: int = 400
TARGET_WORD_MAX: int = 600
# Drafter validator accepts slack 300-700; curator targets the tighter 400-600
# band for headroom. Files outside slack are always rejected; files inside
# slack but outside target are accepted as "acceptable" candidates when the
# tight-band pool is too small.
SLACK_WORD_MIN: int = 300
SLACK_WORD_MAX: int = 700

TARGET_COUNT: int = 5  # ship 5; ModeBDrafter validates >=3.
GENRE_BALANCE: dict[str, int] = {
    "narrative": 2,
    "essay": 2,
    "analytic": 1,
}


def classify_filename(filename: str) -> str | None:
    """Return sub-genre tag for a candidate filename, or None if unclassified.

    Convention: file basenames starting with `narrative_`, `essay_`, or
    `analytic_` map to those sub-genres. Unclassified files are ignored.
    """
    stem = Path(filename).stem.lower()
    for genre in ("narrative", "essay", "analytic"):
        if stem.startswith(f"{genre}_") or stem == genre:
            return genre
    return None


__all__ = [
    "DEFAULT_SOURCE_DIRS",
    "GENRE_BALANCE",
    "SLACK_WORD_MAX",
    "SLACK_WORD_MIN",
    "TARGET_COUNT",
    "TARGET_WORD_MAX",
    "TARGET_WORD_MIN",
    "classify_filename",
]
