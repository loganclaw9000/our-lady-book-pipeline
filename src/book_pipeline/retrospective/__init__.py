"""book_pipeline.retrospective — per-chapter RetrospectiveWriter kernel.

Phase 4 Plan 04-03 lands OpusRetrospectiveWriter (TEST-01 retrospective
side): Claude Code CLI backed writer producing
`retrospectives/chapter_{NN:02d}.md` with scene-ID + axis citations
enforced by a lint rule.

Plan 04-01 ships only this empty package anchor so pyproject.toml's
import-linter contracts 1 + 2 can reference the dotted name before the
concrete impl lands.
"""

from __future__ import annotations

__all__: list[str] = []
