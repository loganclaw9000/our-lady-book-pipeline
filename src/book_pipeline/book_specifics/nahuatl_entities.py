"""Book-specific Nahuatl entity helpers — normalization + stopword lists.

Mesoamerican names (Quetzalcoatl, Tlaxcallan, Malintzin, Cempoalteca, etc.)
have orthography variants. Phase 4 EntityExtractor canonicalizes via these
constants. No other pipeline cares about Nahuatl orthography.
"""

NAHUATL_CANONICAL_NAMES: dict[str, list[str]] = {
    "Quetzalcoatl": ["Quetzalcóatl", "Kukulcan", "Kukulkán"],
    "Tenochtitlan": ["Tenochtitlán", "México-Tenochtitlan"],
    "Malintzin": ["Malinche", "Doña Marina", "La Malinche"],
    "Cempoala": ["Zempoala", "Cempoalteca"],
    "Tlaxcalteca": ["Tlaxcallan", "Tlaxcalan"],
    "Motecuhzoma": ["Moctezuma", "Montezuma"],
}
