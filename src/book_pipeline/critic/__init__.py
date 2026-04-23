"""book_pipeline.critic — scene critic (Plan 03-05) + chapter critic (Plan 04-02).

Kernel package — MUST NOT import from the book-domain layer. Import-linter
contract 1 (pyproject.toml) guards the boundary on every commit.

Plan 03-05 ships: audit.write_audit_record + AuditRecord + SystemPromptBuilder +
SceneCriticError + SceneCritic (CRIT-01 + CRIT-04).
Plan 04-02 ships: ChapterCritic + ChapterSystemPromptBuilder + ChapterCriticError +
CHAPTER_AXES_ORDERED (CRIT-02).

The importlib+contextlib.suppress fallback pattern (B-1 from Plan 03-01) keeps
the package importable for tests that only exercise a subset of artifacts.
"""
from __future__ import annotations

import contextlib
import importlib
from typing import Any

from book_pipeline.critic.audit import AuditRecord, write_audit_record
from book_pipeline.critic.chapter import (
    CHAPTER_AXES_ORDERED,
    ChapterCritic,
    ChapterCriticError,
    ChapterSystemPromptBuilder,
)
from book_pipeline.critic.scene import (
    AXES_ORDERED,
    SceneCriticError,
    SystemPromptBuilder,
)

# Scene critic import fallback (preserved from Plan 03-05 precedent).
SceneCritic: Any = None
with contextlib.suppress(ImportError, AttributeError):
    _scene = importlib.import_module("book_pipeline.critic.scene")
    SceneCritic = getattr(_scene, "SceneCritic", None)

__all__ = [
    "AXES_ORDERED",
    "CHAPTER_AXES_ORDERED",
    "AuditRecord",
    "ChapterCritic",
    "ChapterCriticError",
    "ChapterSystemPromptBuilder",
    "SceneCritic",
    "SceneCriticError",
    "SystemPromptBuilder",
    "write_audit_record",
]
