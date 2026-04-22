"""Mtime index persistence + W-4 resolved model revision persistence.

Two JSON files live under `indexes/`:

  indexes/mtime_index.json             — {abs_path: mtime_float} for idempotency.
  indexes/resolved_model_revision.json — {sha, model, resolved_at_iso} (W-4).

Both are gitignored. The mtime index drives the cron-trigger idempotency
(openclaw compares current mtimes to the stored map; full rebuild if any diff).
The resolved_model_revision.json replaces the STACK.md-rejected YAML write-back
approach: the ingester never modifies config/rag_retrievers.yaml.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# mtime index
# ---------------------------------------------------------------------------


def read_mtime_index(indexes_dir: Path) -> dict[str, float]:
    """Return {abs_path: mtime_float} from indexes/mtime_index.json, or {}."""
    p = indexes_dir / "mtime_index.json"
    if not p.exists():
        return {}
    data: dict[str, float] = json.loads(p.read_text(encoding="utf-8"))
    return data


def write_mtime_index(indexes_dir: Path, mapping: dict[str, float]) -> None:
    """Persist the mtime map. Creates indexes_dir if missing."""
    indexes_dir.mkdir(parents=True, exist_ok=True)
    (indexes_dir / "mtime_index.json").write_text(
        json.dumps(mapping, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def corpus_mtime_map(source_files: list[Path]) -> dict[str, float]:
    """Compute current {abs_path_str: mtime_float} for a list of paths.

    Paths are resolved to absolute form so the map is stable across cwd changes.
    """
    return {str(p.resolve()): p.stat().st_mtime for p in source_files}


# ---------------------------------------------------------------------------
# W-4: resolved model revision persistence (replaces YAML write-back).
# ---------------------------------------------------------------------------


def read_resolved_model_revision(indexes_dir: Path) -> dict[str, str] | None:
    """Return the persisted resolved-model-revision payload, or None if missing.

    Shape: {"sha": str, "model": str, "resolved_at": iso_timestamp_str}.
    """
    p = indexes_dir / "resolved_model_revision.json"
    if not p.exists():
        return None
    data: dict[str, str] = json.loads(p.read_text(encoding="utf-8"))
    return data


def write_resolved_model_revision(
    indexes_dir: Path, *, sha: str, model: str
) -> None:
    """Persist {sha, model, resolved_at=<now utc iso>} to indexes_dir.

    Creates indexes_dir if missing. The file is gitignored — it's the
    reproducibility anchor for a specific ingest run, not a git-tracked config.
    """
    indexes_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "sha": sha,
        "model": model,
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    (indexes_dir / "resolved_model_revision.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


__all__ = [
    "corpus_mtime_map",
    "read_mtime_index",
    "read_resolved_model_revision",
    "write_mtime_index",
    "write_resolved_model_revision",
]
