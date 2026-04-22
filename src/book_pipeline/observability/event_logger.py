"""JsonlEventLogger — concrete EventLogger Protocol impl writing append-only JSONL.

Satisfies OBS-01 (CONTEXT.md D-06). Every LLM call in Phases 2+ emits via this
logger. Schema frozen at end of Phase 1 — optional fields may be added later
(never renamed or removed; migration path bumps Event.schema_version).

Design:
  - Stdlib logging + python-json-logger formatter (STACK.md — no structlog/loguru).
  - Append-only: FileHandler opened with mode='a'; no rewrites, no truncation.
  - Durability: handler.flush() + os.fsync() after every emit (ADR-003).
  - Idempotent handler attachment: multiple JsonlEventLogger(path=X) share ONE
    FileHandler per resolved path, so reconstructing a logger for the same file
    does NOT duplicate lines per emit.

Security note (T-05-02): callers MUST NOT place secrets (API keys, tokens)
into Event.caller_context or Event.extra. Event payloads land in
runs/events.jsonl on disk and are source-of-truth per ADR-003. Plan 03's
SecretsConfig is the sanctioned mechanism for secret values; it never surfaces
raw values via repr/str and the only way to extract one is a deliberate
.get_secret_value() call. Phase 3 drafter/critic/regen code will be audited
against this rule.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

from pythonjsonlogger.json import JsonFormatter

from book_pipeline.interfaces.types import Event

DEFAULT_PATH = Path("runs/events.jsonl")

_HANDLER_LOCK = Lock()
_HANDLERS_BY_PATH: dict[str, logging.FileHandler] = {}


class _EventJsonFormatter(JsonFormatter):
    """Emit exactly Event.model_dump(mode='json') as the JSON line body.

    Rather than the python-json-logger default (message + levelname + ...), we
    replace the record entirely with the pre-dumped Event dict the caller
    attaches via LogRecord.extra={"event_dict": ...}. That keeps runs/events.jsonl
    free of stdlib logging clutter and matches the Event schema byte-for-byte.
    """

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        payload = getattr(record, "event_dict", None)
        if payload is not None:
            log_record.clear()
            log_record.update(payload)
        else:
            super().add_fields(log_record, record, message_dict)


def _get_or_create_handler(path: Path) -> logging.FileHandler:
    """Return the FileHandler for `path`, creating it once and reusing thereafter.

    Handler identity is keyed by the resolved absolute path so that two
    JsonlEventLogger instances pointing at the same file share one underlying
    stream. Protected by a module-level Lock against races during first
    construction.
    """
    key = str(path.resolve())
    with _HANDLER_LOCK:
        if key in _HANDLERS_BY_PATH:
            return _HANDLERS_BY_PATH[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(path), mode="a", encoding="utf-8")
        handler.setFormatter(_EventJsonFormatter())
        handler.setLevel(logging.INFO)
        _HANDLERS_BY_PATH[key] = handler
        return handler


class JsonlEventLogger:
    """Append-only JSONL EventLogger. Implements book_pipeline.interfaces.EventLogger.

    Usage (Phase 2+ callers):
        from book_pipeline.observability import JsonlEventLogger
        logger = JsonlEventLogger()                      # writes runs/events.jsonl
        logger.emit(Event(...))                          # one JSON line per emit

    Pre-conditions:
        - event is a fully-populated Event Pydantic model (required fields set).

    Post-conditions:
        - A single UTF-8 JSON line is appended to self.path.
        - stream is flushed + fsync'd before emit returns (durability).
    """

    def __init__(
        self,
        path: Path | str | None = None,
        logger_name: str = "book_pipeline.events",
    ) -> None:
        self._path = Path(path) if path is not None else DEFAULT_PATH
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # don't echo events to the root logger
        handler = _get_or_create_handler(self._path)
        if handler not in self._logger.handlers:
            self._logger.addHandler(handler)
        self._handler = handler

    @property
    def path(self) -> Path:
        """Target JSONL path. Read-only after construction."""
        return self._path

    def emit(self, event: Event) -> None:
        """Append one JSONL line to self.path. flush + fsync before returning."""
        payload = event.model_dump(mode="json")
        # Fail fast on non-serializable values (NaN floats etc) before logging.
        json.dumps(payload)
        self._logger.info("event", extra={"event_dict": payload})
        if self._handler.stream is not None:
            self._handler.stream.flush()
            # pipes / non-fsyncable FS raise OSError — flush is best-effort.
            with contextlib.suppress(OSError):
                os.fsync(self._handler.stream.fileno())
