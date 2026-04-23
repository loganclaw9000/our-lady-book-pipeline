"""book_pipeline.ablation — A/B variant ablation harness kernel.

Phase 4 Plan 04-04 lands the AblationRun harness (TEST-01 ablation side):
Pydantic dataclass + `runs/ablations/` layout helper. Actual A/B loop
execution lands in Phase 6 (TEST-03).

Kernel package — no book-domain imports. Import-linter contract 1
enforces the boundary.
"""

from __future__ import annotations

from book_pipeline.ablation.harness import (
    AblationRun,
    create_ablation_run_skeleton,
    utc_timestamp,
)

__all__ = [
    "AblationRun",
    "create_ablation_run_skeleton",
    "utc_timestamp",
]
