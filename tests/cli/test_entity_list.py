"""Tests for book_pipeline.cli._entity_list (W-1 helper).

The helper flattens NAHUATL_CANONICAL_NAMES (canonical keys + variant lists)
into a single set for injection into ContextPackBundlerImpl(entity_list=...).
Plan 02-05 established the DI seam; Plan 02-06 materializes the CLI-side
composition. Kernel does not import book_specifics; CLI does (composition
seam per pyproject.toml ignore_imports).
"""
from __future__ import annotations


def test_build_nahuatl_entity_set_returns_set_of_str() -> None:
    from book_pipeline.cli._entity_list import build_nahuatl_entity_set

    s = build_nahuatl_entity_set()
    assert isinstance(s, set)
    assert len(s) > 0
    for item in s:
        assert isinstance(item, str)


def test_build_nahuatl_entity_set_contains_canonical_keys() -> None:
    """All 6 canonical names from NAHUATL_CANONICAL_NAMES must be in the set."""
    from book_pipeline.cli._entity_list import build_nahuatl_entity_set

    s = build_nahuatl_entity_set()
    for canonical in (
        "Motecuhzoma",
        "Tenochtitlan",
        "Malintzin",
        "Cempoala",
        "Quetzalcoatl",
        "Tlaxcalteca",
    ):
        assert canonical in s, f"canonical name {canonical!r} missing from entity set"


def test_build_nahuatl_entity_set_contains_variants() -> None:
    """Variants (Moctezuma, Montezuma, Malinche, etc.) must also be present."""
    from book_pipeline.cli._entity_list import build_nahuatl_entity_set

    s = build_nahuatl_entity_set()
    for variant in (
        "Moctezuma",       # variant of Motecuhzoma
        "Montezuma",       # variant of Motecuhzoma
        "Malinche",        # variant of Malintzin
        "Doña Marina",     # variant of Malintzin
        "Tenochtitlán",    # variant of Tenochtitlan (accented)
        "Quetzalcóatl",    # variant of Quetzalcoatl (accented)
        "Tlaxcallan",      # variant of Tlaxcalteca
    ):
        assert variant in s, f"variant {variant!r} missing from entity set"


def test_build_nahuatl_entity_set_is_deterministic() -> None:
    """Same call twice -> identical set (the DI payload is a pure function)."""
    from book_pipeline.cli._entity_list import build_nahuatl_entity_set

    assert build_nahuatl_entity_set() == build_nahuatl_entity_set()
