"""OpusEntityExtractor — CORPUS-02 post-commit entity-card extractor.

Mirrors SceneCritic / ChapterCritic structure (pre-rendered cached system
prompt, tenacity-retried messages.parse, ONE OBS-01 Event per invocation,
_handle_failure W-7 error-event preservation BEFORE raise) but differs:

  1. Tenacity max_attempts = 3 (NOT 5 used in critic/regen). Per
     04-CONTEXT.md "tenacity 3x retry on transient". Total wall-time
     ceiling ~32s per chapter; extraction is 1x per committed chapter so
     the tighter budget is fine.

  2. Structured output schema is EntityExtractionResponse (this module's
     schema.py), not CriticResponse. ``messages.parse(output_format=...)``
     call shape is otherwise identical.

  3. Incremental-update diff: the caller passes prior cards, Opus returns
     a full view, and ``extract()`` returns only NEW or UPDATED cards
     (unchanged prior entities are filtered out — idempotency guarantee
     per CORPUS-02 success criterion). NEW = entity_name not in prior.
     UPDATED = entity_name in prior AND state dict differs.

  4. source_chapter_sha is OVERRIDDEN on every returned card (defense in
     depth: the prompt also instructs Opus to pass it through, but we
     don't trust the LLM for a V-3 stale-card invariant).

Kernel discipline: no book-domain imports. This module is listed in
import-linter contract 1 (pyproject.toml) — the import-linter gate catches
any accidental book-domain import at commit time.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tenacity
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from book_pipeline.entity_extractor.schema import EntityExtractionResponse
from book_pipeline.interfaces.types import EntityCard, Event
from book_pipeline.observability.hashing import event_id as compute_event_id
from book_pipeline.observability.hashing import hash_text

logger = logging.getLogger(__name__)


# Default template asset path (relative to repo root under uv).
DEFAULT_EXTRACTOR_TEMPLATE_PATH = Path(
    "src/book_pipeline/entity_extractor/templates/extractor_system.j2"
)

# Tenacity max_attempts per CONTEXT.md: 3 (tighter than critic's 5).
_TENACITY_MAX_ATTEMPTS = 3


class EntityExtractorBlocked(Exception):
    """Raised by OpusEntityExtractor on unrecoverable extraction failure.

    Carries ``reason`` + ``context`` (dict of chapter_num, underlying cause).
    Plan 04-04 DAG orchestrator catches this and transitions
    ChapterState.POST_COMMIT_DAG -> DAG_BLOCKED.

    Reasons:
      - "empty_chapter": chapter_text was empty/whitespace.
      - "entity_extraction_failed": 3 tenacity attempts exhausted.
      - "parsed_output_missing": Opus returned None parsed_output.
    """

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = context
        super().__init__(f"EntityExtractor: {reason} | {context}")


class _ExtractorSystemPromptBuilder:
    """Renders the extractor system prompt from templates/extractor_system.j2.

    Pre-rendering once at __init__ means every extract() call reuses the same
    string — Anthropic's prompt cache hits on call #2+ within the 1h TTL.
    """

    def __init__(self, template_path: Path) -> None:
        self.template_path = Path(template_path)

    def render(self) -> tuple[str, str]:
        env = Environment(
            loader=FileSystemLoader(str(self.template_path.parent)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
        template = env.get_template(self.template_path.name)
        rendered = template.render()
        sha = hash_text(rendered)
        return rendered, sha


class OpusEntityExtractor:
    """Concrete EntityExtractor Protocol impl: Opus 4.7 + incremental diff.

    Post-conditions:
      - Every returned EntityCard.source_chapter_sha == chapter_sha.
      - Returned list contains ONLY new or updated cards (unchanged prior
        entities filtered out).
      - Exactly one Event emitted per call (role='entity_extractor').
      - Returns list[EntityCard] on success; raises EntityExtractorBlocked on
        unrecoverable failure.
    """

    def __init__(
        self,
        *,
        anthropic_client: Any,
        event_logger: Any | None,
        model_id: str = "claude-opus-4-7",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        template_path: Path = DEFAULT_EXTRACTOR_TEMPLATE_PATH,
    ) -> None:
        self.anthropic_client = anthropic_client
        self.event_logger = event_logger
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Pre-render once — identical text across extract() calls.
        self._builder = _ExtractorSystemPromptBuilder(Path(template_path))
        self._system_prompt, self._system_prompt_sha = self._builder.render()
        self._system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._system_prompt,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ]

    # ------------------------------------------------------------------ #
    # EntityExtractor Protocol                                           #
    # ------------------------------------------------------------------ #

    def extract(
        self,
        chapter_text: str,
        chapter_num: int,
        chapter_sha: str,
        prior_cards: list[EntityCard],
    ) -> list[EntityCard]:
        if not chapter_text.strip():
            raise EntityExtractorBlocked(
                "empty_chapter", chapter_num=chapter_num
            )

        ts_iso = _now_iso()
        user_prompt = self._build_user_prompt(
            chapter_text=chapter_text,
            chapter_num=chapter_num,
            chapter_sha=chapter_sha,
            prior_cards=prior_cards,
            extraction_timestamp=ts_iso,
        )
        user_prompt_sha = hash_text(user_prompt)
        messages = [{"role": "user", "content": user_prompt}]

        start = time.monotonic()
        try:
            response = self._call_opus(messages=messages)
        except Exception as exc:  # tenacity exhausted OR unexpected
            self._handle_failure(
                exc=exc,
                chapter_num=chapter_num,
                chapter_sha=chapter_sha,
                ts_iso=ts_iso,
                user_prompt_sha=user_prompt_sha,
                prior_cards_count=len(prior_cards),
                start_time=start,
            )
            raise EntityExtractorBlocked(
                "entity_extraction_failed",
                chapter_num=chapter_num,
                underlying_cause=str(exc),
            ) from exc

        latency_ms = int((time.monotonic() - start) * 1000)

        parsed_raw = response.parsed_output
        if parsed_raw is None:
            raise EntityExtractorBlocked(
                "parsed_output_missing", chapter_num=chapter_num
            )
        parsed: EntityExtractionResponse = parsed_raw

        # Defense-in-depth: stamp source_chapter_sha on every card.
        for card in parsed.entities:
            card.source_chapter_sha = chapter_sha

        # Incremental diff: filter unchanged prior entities.
        prior_name_to_card = {c.entity_name: c for c in prior_cards}
        filtered: list[EntityCard] = []
        new_cards = 0
        updated_cards = 0
        for card in parsed.entities:
            prior = prior_name_to_card.get(card.entity_name)
            if prior is None:
                filtered.append(card)
                new_cards += 1
            elif card.state != prior.state:
                filtered.append(card)
                updated_cards += 1
            # else unchanged — drop (idempotency).

        # Emit success Event.
        usage = getattr(response, "usage", None)
        cached_input_tokens = int(
            getattr(usage, "cache_read_input_tokens", 0) or 0
        )
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        prompt_hash = hash_text(
            self._system_prompt + "\n---\n" + user_prompt
        )
        event_id_value = compute_event_id(
            ts_iso,
            "entity_extractor",
            f"entity_extractor.opus.extract:chapter_{chapter_num:02d}",
            user_prompt_sha,
        )
        output_hash = hash_text(
            json.dumps(
                [c.model_dump(mode="json") for c in filtered],
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        caller_context: dict[str, Any] = {
            "module": "entity_extractor.opus",
            "function": "extract",
            "chapter_num": chapter_num,
            "chapter_sha": chapter_sha,
            "entity_count": len(filtered),
            "new_cards": new_cards,
            "updated_cards": updated_cards,
            "prior_cards_count": len(prior_cards),
        }
        event = Event(
            event_id=event_id_value,
            ts_iso=ts_iso,
            role="entity_extractor",
            model=self.model_id,
            prompt_hash=prompt_hash,
            input_tokens=input_tokens,
            cached_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            temperature=self.temperature,
            top_p=None,
            caller_context=caller_context,
            output_hash=output_hash,
            mode=None,
            rubric_version=None,
            checkpoint_sha=None,
            extra={},
        )
        self._emit(event)
        return filtered

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _build_user_prompt(
        self,
        *,
        chapter_text: str,
        chapter_num: int,
        chapter_sha: str,
        prior_cards: list[EntityCard],
        extraction_timestamp: str,
    ) -> str:
        parts: list[str] = []
        parts.append(f"chapter_num={chapter_num}")
        parts.append(f'source_chapter_sha="{chapter_sha}"')
        parts.append(f"extraction_timestamp={extraction_timestamp}")
        parts.append("")
        if prior_cards:
            parts.append("Prior entity cards (compact view):")
            compact = [
                {
                    "entity_name": c.entity_name,
                    "last_seen_chapter": c.last_seen_chapter,
                    "current_state_summary": str(
                        c.state.get("current_state", "")
                    ),
                }
                for c in prior_cards
            ]
            parts.append(json.dumps(compact, ensure_ascii=False))
            parts.append("")
        else:
            parts.append("Prior entity cards (compact view): none")
            parts.append("")
        parts.append("Chapter text:")
        parts.append(chapter_text)
        parts.append("")
        parts.append(
            "Return JSON matching the EntityExtractionResponse schema. "
            "Emit ONLY NEW or UPDATED entity cards relative to the prior view."
        )
        return "\n".join(parts)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(_TENACITY_MAX_ATTEMPTS),
        wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _call_opus_inner(self, *, messages: list[dict[str, Any]]) -> Any:
        """Raw messages.parse with tenacity retry on transient errors."""
        from anthropic import APIConnectionError, APIStatusError

        try:
            return self.anthropic_client.messages.parse(
                model=self.model_id,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self._system_blocks,
                messages=messages,
                output_format=EntityExtractionResponse,
            )
        except (APIConnectionError, APIStatusError):
            raise

    def _call_opus(self, *, messages: list[dict[str, Any]]) -> Any:
        return self._call_opus_inner(messages=messages)

    def _emit(self, event: Event) -> None:
        if self.event_logger is None:
            return
        try:
            self.event_logger.emit(event)
        except Exception:  # pragma: no cover — best effort
            logger.exception(
                "failed to emit Event(role=%r)", event.role
            )

    def _handle_failure(
        self,
        *,
        exc: Exception,
        chapter_num: int,
        chapter_sha: str,
        ts_iso: str,
        user_prompt_sha: str,
        prior_cards_count: int,
        start_time: float,
    ) -> None:
        """W-7: error Event emitted BEFORE EntityExtractorBlocked is raised."""
        latency_ms = int((time.monotonic() - start_time) * 1000)
        event_id_value = compute_event_id(
            ts_iso,
            "entity_extractor",
            f"entity_extractor.opus.extract:chapter_{chapter_num:02d}",
            user_prompt_sha,
        )
        prompt_hash = hash_text(
            self._system_prompt + "\n---\n" + user_prompt_sha
        )
        caller_context: dict[str, Any] = {
            "module": "entity_extractor.opus",
            "function": "extract",
            "chapter_num": chapter_num,
            "chapter_sha": chapter_sha,
            "entity_count": 0,
            "new_cards": 0,
            "updated_cards": 0,
            "prior_cards_count": prior_cards_count,
        }
        extra: dict[str, Any] = {
            "status": "error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "attempts_made": _TENACITY_MAX_ATTEMPTS,
        }
        error_event = Event(
            event_id=event_id_value,
            ts_iso=ts_iso,
            role="entity_extractor",
            model=self.model_id,
            prompt_hash=prompt_hash,
            input_tokens=0,
            cached_tokens=0,
            output_tokens=0,
            latency_ms=latency_ms,
            temperature=self.temperature,
            top_p=None,
            caller_context=caller_context,
            output_hash="",
            mode=None,
            rubric_version=None,
            checkpoint_sha=None,
            extra=extra,
        )
        self._emit(error_event)


# ---------------------------------------------------------------------- #
# Helpers                                                                #
# ---------------------------------------------------------------------- #


def _now_iso() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


__all__ = [
    "EntityExtractorBlocked",
    "OpusEntityExtractor",
]
