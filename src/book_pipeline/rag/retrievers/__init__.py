"""book_pipeline.rag.retrievers — 5 typed Retriever implementations + shared base.

Each concrete retriever structurally satisfies
`book_pipeline.interfaces.retriever.Retriever` (runtime_checkable). Observability
event emission is orchestrated by the ContextPackBundler in Plan 02-05; these
classes NEVER log events directly (Retriever Protocol docstring contract).

Plan 02-03 owns this file exclusively (B-1 revision of the phase's file-ownership
ledger): all 5 retriever imports are pre-declared here. Plan 02-04 creates the
two additional retriever source files (`entity_state.py`, `arc_position.py`)
but does NOT modify this `__init__.py`. The import-guarded block below lets
Plan 02-03's 3-retriever surface work even before Plan 02-04 lands; once
Plan 02-04's files exist, both imports resolve to real classes at package
import time.

B-2 compliance: every concrete retriever here and in Plan 02-04 inherits
`reindex(self) -> None` from `LanceDBRetrieverBase`; the frozen Protocol
signature is not re-opened with extra arguments. Plan 02-04's
ArcPositionRetriever may override the method body but MUST keep the zero-arg
signature.
"""

import contextlib as _contextlib
import importlib as _importlib
from typing import Any as _Any

from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase
from book_pipeline.rag.retrievers.historical import HistoricalRetriever
from book_pipeline.rag.retrievers.metaphysics import MetaphysicsRetriever
from book_pipeline.rag.retrievers.negative_constraint import NegativeConstraintRetriever

# B-1: Plan 02-04 source files — import-guarded so this package's 3-retriever
# surface works even before Plan 02-04 executes. After Plan 02-04 lands, both
# imports succeed cleanly and the sentinel-None fallbacks are bypassed. Dynamic
# importlib is used so mypy does not statically complain about modules that may
# or may not exist depending on execution order; the runtime behavior is:
#   - pre-Plan-02-04: attribute is None (graceful absence).
#   - post-Plan-02-04: attribute is the real class from the sub-module.
EntityStateRetriever: _Any = None
ArcPositionRetriever: _Any = None
with _contextlib.suppress(ImportError):  # Plan 02-04 not yet executed
    EntityStateRetriever = _importlib.import_module(
        "book_pipeline.rag.retrievers.entity_state"
    ).EntityStateRetriever
with _contextlib.suppress(ImportError):  # Plan 02-04 not yet executed
    ArcPositionRetriever = _importlib.import_module(
        "book_pipeline.rag.retrievers.arc_position"
    ).ArcPositionRetriever

__all__ = [
    "ArcPositionRetriever",
    "EntityStateRetriever",
    "HistoricalRetriever",
    "LanceDBRetrieverBase",
    "MetaphysicsRetriever",
    "NegativeConstraintRetriever",
]
