"""CLI helper — flatten NAHUATL_CANONICAL_NAMES into a set for the bundler.

W-1 DI seam. Plan 02-05's `ContextPackBundlerImpl(entity_list=...)` consumes
this set so Mesoamerican names (Motecuhzoma, Malintzin, Tenochtitlan, ...)
participate in cross-retriever conflict detection alongside the English-
capitalization regex path.

Kernel does NOT import book-domain entity tables; this CLI module does (per
pyproject.toml import-linter contract 1 ignore_imports — same composition
seam pattern established by Phase 2 Plan 02's cli/ingest.py).

Returned set includes both canonical keys and variant values:

    {"Motecuhzoma", "Moctezuma", "Montezuma",
     "Tenochtitlan", "Tenochtitlán", "México-Tenochtitlan",
     "Malintzin", "Malinche", "Doña Marina", "La Malinche",
     ...}
"""
from __future__ import annotations

from book_pipeline.book_specifics.nahuatl_entities import NAHUATL_CANONICAL_NAMES


def build_nahuatl_entity_set() -> set[str]:
    """Return the union of canonical names + all variants from the book-specific table."""
    out: set[str] = set()
    for canonical, variants in NAHUATL_CANONICAL_NAMES.items():
        out.add(canonical)
        out.update(variants)
    return out


__all__ = ["build_nahuatl_entity_set"]
