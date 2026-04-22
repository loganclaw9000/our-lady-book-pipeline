"""book_pipeline.observability — concrete OBS-01 implementation.

Phase 1 plan 05 ships the one concrete EventLogger impl in the pipeline.
Phases 2+ callers import from here:

    from book_pipeline.observability import JsonlEventLogger, hash_text, event_id
"""

from book_pipeline.observability.event_logger import JsonlEventLogger
from book_pipeline.observability.hashing import event_id, hash_text

__all__ = ["JsonlEventLogger", "event_id", "hash_text"]
