"""Entity-state LanceDB reindex helper (Plan 04-04 step 3).

`reindex_entity_state_from_jsons(entity_state_dir, indexes_dir, embedder)`:

  1. Iterate all `entity_state_dir/chapter_*.json` (one per chapter).
  2. Parse each with EntityExtractionResponse; flatten .entities.
  3. For each EntityCard produce one LanceDB row against CHUNK_SCHEMA.
  4. Open (create if missing) the `entity_state` table; delete all rows;
     insert the fresh rows. Idempotent — CONTEXT.md grey-area d says
     "regenerate FULLY".
  5. Return the row count.

The helper is pure-kernel: no book-domain imports; no CLI dependencies.
Plan 04-04's `ChapterDagOrchestrator` calls this in DAG step 3.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from book_pipeline.entity_extractor.schema import EntityExtractionResponse
from book_pipeline.interfaces.types import EntityCard
from book_pipeline.rag.lance_schema import open_or_create_table

logger = logging.getLogger(__name__)

_CHAPTER_JSON_RE = re.compile(r"^chapter_(\d+)_entities\.json$")


def _card_to_row(
    card: EntityCard,
    *,
    ingestion_run_id: str,
    embedder: Any,
) -> dict[str, Any]:
    """Build one CHUNK_SCHEMA-compatible row from an EntityCard."""
    state = card.state or {}
    current_state = str(state.get("current_state", ""))
    text = f"{card.entity_name}: {current_state}" if current_state else card.entity_name
    heading_path = f"entity_state/{card.entity_name}"
    vector = embedder.encode(text)
    # Chunk-id is entity_name; stable across reindex so LanceDB dedup is easy.
    return {
        "chunk_id": card.entity_name,
        "text": text,
        "source_file": f"entity-state/chapter_{card.last_seen_chapter:02d}_entities.json",
        "heading_path": heading_path,
        "rule_type": "entity_card",
        "ingestion_run_id": ingestion_run_id,
        "chapter": int(card.last_seen_chapter),
        # Plan 05-03 (D-11 / SC6 closure): propagate source_chapter_sha into
        # the LanceDB row so the entity_state retriever can surface it in
        # RetrievalHit.metadata for the bundler's stale-card scan.
        "source_chapter_sha": card.source_chapter_sha,
        "embedding": list(vector),
    }


def reindex_entity_state_from_jsons(
    entity_state_dir: Path,
    indexes_dir: Path,
    embedder: Any,
    *,
    ingestion_run_id: str = "dag_reindex",
) -> int:
    """Rebuild the entity_state LanceDB table from per-chapter JSON files.

    Idempotent: deletes every row and inserts a fresh row set. Matches
    CONTEXT.md grey-area d ("regenerate FULLY from entity-state/chapter_*.json").

    Returns:
        Number of rows inserted.
    """
    entity_state_dir = Path(entity_state_dir)
    indexes_dir = Path(indexes_dir)

    all_cards: list[EntityCard] = []
    if entity_state_dir.is_dir():
        for path in sorted(entity_state_dir.iterdir()):
            if not path.is_file():
                continue
            if _CHAPTER_JSON_RE.match(path.name) is None:
                continue
            try:
                payload = path.read_text(encoding="utf-8")
                resp = EntityExtractionResponse.model_validate_json(payload)
            except Exception:
                logger.exception(
                    "reindex: skipping malformed entity-state json at %s", path
                )
                continue
            all_cards.extend(resp.entities)

    rows = [
        _card_to_row(
            c, ingestion_run_id=ingestion_run_id, embedder=embedder
        )
        for c in all_cards
    ]

    tbl = open_or_create_table(indexes_dir, "entity_state")
    # Idempotent rebuild of the per-chapter slice ONLY. Corpus-level rows
    # (pantheon.md, secondary-characters.md ingested by CorpusIngester) MUST
    # survive — they hold static lore for entities never re-extracted from
    # chapter prose. Filter on source_file pattern: rows whose source_file
    # starts with "entity-state/chapter_" and ends with "_entities.json"
    # are per-chapter extractor output and safe to wipe; everything else is
    # corpus-level and stays.
    chapter_predicate = (
        "source_file LIKE 'entity-state/chapter_%_entities.json'"
    )
    try:
        tbl.delete(chapter_predicate)
    except Exception as exc:
        logger.warning(
            "reindex: predicate delete failed (%s); "
            "falling back to row-by-row delete on per-chapter rows only",
            exc,
        )
        try:
            existing = [
                r for r in tbl.to_arrow().to_pylist()
                if str(r.get("source_file", "")).startswith("entity-state/chapter_")
                and str(r.get("source_file", "")).endswith("_entities.json")
            ]
            for r in existing:
                safe = str(r["chunk_id"]).replace("'", "''")
                tbl.delete(f"chunk_id = '{safe}'")
        except Exception:
            logger.exception("reindex: per-row fallback also failed")
            raise RuntimeError(
                "entity_state reindex could not clear prior per-chapter rows; "
                "refusing to double-insert"
            ) from exc

    # Only reached when the table is verified empty (either bulk delete
    # succeeded or per-row fallback completed).
    if rows:
        tbl.add(rows)

    return len(rows)


__all__ = ["reindex_entity_state_from_jsons"]
