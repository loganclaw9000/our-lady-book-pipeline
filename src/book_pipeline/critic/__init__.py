"""book_pipeline.critic — scene critic (Plan 03-05, CRIT-01 + CRIT-04).

Chapter critic lands in Phase 4. Kernel package — MUST NOT import from
project-domain packages. Import-linter contract 1 (pyproject.toml) guards
the boundary on every commit.

Task 1 ships: audit.write_audit_record + AuditRecord + SystemPromptBuilder +
SceneCriticError. Task 2 ships: SceneCritic.

The importlib+contextlib.suppress fallback for SceneCritic lets tests that
only need Task 1 artifacts (audit + templates) import cleanly even if
Task 2 has not yet landed — same B-1 pattern as voice_fidelity/__init__.py
(Plan 03-01).
"""
from __future__ import annotations

import contextlib
import importlib
from typing import Any

from book_pipeline.critic.audit import AuditRecord, write_audit_record
from book_pipeline.critic.scene import (
    AXES_ORDERED,
    SceneCriticError,
    SystemPromptBuilder,
)

# SceneCritic is landed by Task 2 of Plan 03-05; fallback keeps the package
# importable for tests that only exercise Task 1 artifacts.
SceneCritic: Any = None
with contextlib.suppress(ImportError, AttributeError):
    _scene = importlib.import_module("book_pipeline.critic.scene")
    SceneCritic = getattr(_scene, "SceneCritic", None)

__all__ = [
    "AXES_ORDERED",
    "AuditRecord",
    "SceneCritic",
    "SceneCriticError",
    "SystemPromptBuilder",
    "write_audit_record",
]
