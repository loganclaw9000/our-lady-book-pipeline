"""book_pipeline.retrospective — per-chapter retrospective writer kernel.

Phase 4 Plan 04-03 lands OpusRetrospectiveWriter (TEST-01 retrospective
side): Opus 4.7 backed writer producing a Retrospective Pydantic model
from a markdown-with-frontmatter output. Lint-on-output enforces scene_id
+ critic-artifact citation per TEST-01 success criterion 5; lint fail
triggers a single nudge retry, and a second fail logs a WARNING but
commits the retrospective anyway (ungated signal per CONTEXT.md).

Kernel discipline: no book-domain imports. Import-linter contracts 1+2
in pyproject.toml enforce the kernel/book-domain boundary on every commit.
"""

from __future__ import annotations

from book_pipeline.retrospective.lint import lint_retrospective
from book_pipeline.retrospective.opus import (
    OpusRetrospectiveWriter,
    RetrospectiveWriterBlocked,
)

__all__ = [
    "OpusRetrospectiveWriter",
    "RetrospectiveWriterBlocked",
    "lint_retrospective",
]
