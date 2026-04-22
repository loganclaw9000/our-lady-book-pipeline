"""File-path + corpus-name constants for the Our Lady of Champion lore bibles.

These constants are used by Phase 2 ingestion + Phase 4 entity extraction.
They are book-specific by construction — no other writing pipeline needs them.
"""

from pathlib import Path

CORPUS_ROOT = Path("~/Source/our-lady-of-champion").expanduser()
BRIEF = CORPUS_ROOT / "brief.md"
ENGINEERING = CORPUS_ROOT / "engineering.md"
PANTHEON = CORPUS_ROOT / "pantheon.md"
SECONDARY_CHARACTERS = CORPUS_ROOT / "secondary-characters.md"
OUTLINE = CORPUS_ROOT / "outline.md"
KNOWN_LIBERTIES = CORPUS_ROOT / "known-liberties.md"
