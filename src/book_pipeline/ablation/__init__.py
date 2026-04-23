"""book_pipeline.ablation — A/B variant ablation harness kernel.

Phase 4 Plan 04-04 lands the AblationRun harness (TEST-01 ablation side):
Pydantic dataclass + `runs/ablations/` layout + `book-pipeline ablate` CLI
stub that validates two variant configs and prints "Phase 6 will drive
execution." Actual A/B loop execution lands in Phase 6 (TEST-03).

Plan 04-01 ships only this empty package anchor so pyproject.toml's
import-linter contracts 1 + 2 can reference the dotted name before the
concrete impl lands.
"""

from __future__ import annotations

__all__: list[str] = []
