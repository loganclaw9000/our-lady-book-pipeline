"""Kernel router: file-stem -> axis mapping.

The router handles FILE-level routing only. Per W-3, heading-level classification
for multi-axis files (brief.md) is delegated to a caller-injected classifier
(see book_pipeline.corpus_ingest.ingester.CorpusIngester.heading_classifier).

This module is kernel code and stays ignorant of the book-specifics package
(import-linter contract 1 enforces the boundary). The filename stems live here
as literal strings because changing filenames is a coordinated edit across the
kernel router and the book-specific corpus-paths module in the same PR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

AXIS_NAMES: Final[tuple[str, ...]] = (
    "historical",
    "metaphysics",
    "entity_state",
    "arc_position",
    "negative_constraint",
)

# Stem (filename without extension, stripped of the `our-lady-of-champion-`
# prefix) → list of axis names. brief is the only multi-axis entry. handoff
# maps to [] (meta-document; never ingested). Unknown stems raise ValueError.
_ROUTING: Final[dict[str, list[str]]] = {
    "brief":                ["historical", "metaphysics"],
    "engineering":          ["metaphysics"],
    "pantheon":             ["entity_state"],
    "secondary-characters": ["entity_state"],
    "outline":              ["arc_position"],
    "known-liberties":      ["negative_constraint"],
    "relics":               ["metaphysics"],
    "glossary":             ["historical"],
    "maps":                 ["historical"],
    "handoff":              [],
}

_PREFIX: Final[str] = "our-lady-of-champion-"


def route_file_to_axis(path: Path) -> list[str]:
    """Return the axis list for a corpus file by its filename stem.

    Args:
      path: a corpus file path. Only the filename is inspected — parent
        directory is ignored so tests and ingester paths both resolve.

    Returns:
      The list of axis names (strings) this file feeds, in order. For
      multi-axis files the ingester applies a heading-level classifier to
      decide the per-chunk axis. For `handoff.md` returns [].

    Raises:
      ValueError: if the filename doesn't match a known stem. Prevents the
        chunker from being called on unknown inputs (T-02-02-03 mitigation).
    """
    name = path.name
    # Strip our-lady-of-champion- prefix if present; we want the bare stem.
    stem_with_ext = name[len(_PREFIX):] if name.startswith(_PREFIX) else name
    # Strip the extension (.md).
    stem = stem_with_ext[:-3] if stem_with_ext.endswith(".md") else stem_with_ext
    if stem not in _ROUTING:
        raise ValueError(
            f"Unknown corpus file: {name!r} (stem {stem!r}); "
            f"expected one of {sorted(_ROUTING.keys())}"
        )
    return list(_ROUTING[stem])


__all__ = ["AXIS_NAMES", "route_file_to_axis"]
