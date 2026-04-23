"""OpusRetrospectiveWriter — TEST-01 post-chapter retrospective generator.

Mirrors OpusEntityExtractor structure (pre-rendered cached system prompt,
tenacity 3x retry, ONE role='retrospective_writer' Event per invocation) but
differs in three ways:

  1. FREE-TEXT output (messages.create, NOT messages.parse). Retrospective is
     a markdown document with YAML frontmatter; the writer parses the four H2
     sections + frontmatter locally into a Retrospective Pydantic instance.

  2. LINT-ON-OUTPUT: ``lint_retrospective`` runs on the parsed Retrospective;
     on fail the writer re-invokes Opus ONCE with a nudge prompt. On second
     fail, the writer emits a WARNING log + commits anyway (ungated path per
     CONTEXT.md: "failure -> log + skip; next chapter unblocks").

  3. UNGATED FAILURE: unlike OpusEntityExtractor which raises
     EntityExtractorBlocked on tenacity exhaustion, this writer RETURNS a stub
     Retrospective(what_worked="(generation failed)", what_didnt=<exc head>,
     ...). Failures here block NOTHING — retrospectives are a soft signal
     consumed by the Phase 6 thesis matcher. CONTEXT.md explicitly marks this
     path "ungated".

Kernel discipline: no book-domain imports. Import-linter contract 1 enforces.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tenacity
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from book_pipeline.interfaces.types import Event, Retrospective
from book_pipeline.observability.hashing import event_id as compute_event_id
from book_pipeline.observability.hashing import hash_text
from book_pipeline.retrospective.lint import lint_retrospective

logger = logging.getLogger(__name__)


DEFAULT_RETROSPECTIVE_TEMPLATE_PATH = Path(
    "src/book_pipeline/retrospective/templates/retrospective_system.j2"
)

_TENACITY_MAX_ATTEMPTS = 3

_LINT_NUDGE = (
    "The prior draft did not cite specific scene IDs or critic-issue "
    "artifacts. Please revise: cite at least one scene_id (format "
    "chNN_scNN) and at least one of: axis name (historical / metaphysics "
    "/ entity / arc / donts), a chunk_id (format chunk_XXXXXXX), or an "
    "evidence quote of >=20 characters in double quotes."
)


class RetrospectiveWriterBlocked(Exception):
    """Raised internally on parse failure. NOT surfaced to caller — the
    writer's public contract is 'always return a Retrospective'; this
    exception is caught in write() and folded into the stub-retro path."""

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = context
        super().__init__(f"RetrospectiveWriter: {reason} | {context}")


class _RetrospectiveSystemPromptBuilder:
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


class OpusRetrospectiveWriter:
    """Concrete RetrospectiveWriter Protocol impl: Opus 4.7 + lint + nudge retry.

    Post-conditions:
      - Always returns a Retrospective (never raises). Ungated failure paths
        produce a stub retro with what_worked="(generation failed)" +
        what_didnt carrying the exception summary.
      - Exactly one Event emitted per write() call (success XOR error).
      - caller_context carries lint_retries (0 or 1) + lint_pass.
    """

    def __init__(
        self,
        *,
        anthropic_client: Any,
        event_logger: Any | None,
        model_id: str = "claude-opus-4-7",
        max_tokens: int = 6000,
        temperature: float = 0.4,
        template_path: Path = DEFAULT_RETROSPECTIVE_TEMPLATE_PATH,
    ) -> None:
        self.anthropic_client = anthropic_client
        self.event_logger = event_logger
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature

        self._builder = _RetrospectiveSystemPromptBuilder(Path(template_path))
        self._system_prompt, self._system_prompt_sha = self._builder.render()
        self._system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._system_prompt,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ]

    # ------------------------------------------------------------------ #
    # RetrospectiveWriter Protocol                                       #
    # ------------------------------------------------------------------ #

    def write(
        self,
        chapter_text: str,
        chapter_events: list[Event],
        prior_retros: list[Retrospective],
    ) -> Retrospective:
        ts_iso = _now_iso()
        chapter_num = _infer_chapter_num(chapter_events, prior_retros)

        # Attempt 1.
        start = time.monotonic()
        try:
            retro_1 = self._attempt_write(
                chapter_text=chapter_text,
                chapter_events=chapter_events,
                prior_retros=prior_retros,
                chapter_num_hint=chapter_num,
                nudge=None,
            )
        except Exception as exc:
            # Tenacity exhaustion OR parse failure — ungated path.
            stub = self._stub_retrospective(
                chapter_num=chapter_num, exc=exc
            )
            self._emit_error_event(
                exc=exc,
                chapter_num=chapter_num,
                chapter_events=chapter_events,
                prior_retros_count=len(prior_retros),
                ts_iso=ts_iso,
                start_time=start,
            )
            logger.warning(
                "retrospective generation failed for chapter %d: %s",
                chapter_num,
                exc,
            )
            return stub

        passed_1, reasons_1 = lint_retrospective(retro_1)
        if passed_1:
            self._emit_success_event(
                retro=retro_1,
                chapter_num=chapter_num,
                chapter_events=chapter_events,
                prior_retros_count=len(prior_retros),
                lint_retries=0,
                lint_pass=True,
                first_fail_reasons=None,
                lint_reasons_if_failed=None,
                ts_iso=ts_iso,
                start_time=start,
            )
            return retro_1

        # Attempt 2 (with nudge).
        try:
            retro_2 = self._attempt_write(
                chapter_text=chapter_text,
                chapter_events=chapter_events,
                prior_retros=prior_retros,
                chapter_num_hint=chapter_num,
                nudge=_LINT_NUDGE,
            )
        except Exception as exc:
            # Retry failed — ungated path. Return stub.
            stub = self._stub_retrospective(
                chapter_num=chapter_num, exc=exc
            )
            self._emit_error_event(
                exc=exc,
                chapter_num=chapter_num,
                chapter_events=chapter_events,
                prior_retros_count=len(prior_retros),
                ts_iso=ts_iso,
                start_time=start,
            )
            logger.warning(
                "retrospective retry-generation failed for chapter %d: %s",
                chapter_num,
                exc,
            )
            return stub

        passed_2, reasons_2 = lint_retrospective(retro_2)
        if passed_2:
            self._emit_success_event(
                retro=retro_2,
                chapter_num=chapter_num,
                chapter_events=chapter_events,
                prior_retros_count=len(prior_retros),
                lint_retries=1,
                lint_pass=True,
                first_fail_reasons=reasons_1,
                lint_reasons_if_failed=None,
                ts_iso=ts_iso,
                start_time=start,
            )
            return retro_2

        # Second fail — WARNING log, emit event, RETURN retro anyway.
        logger.warning(
            "retrospective lint failed twice for chapter %d: %r; "
            "committing anyway (ungated)",
            chapter_num,
            reasons_2,
        )
        self._emit_success_event(
            retro=retro_2,
            chapter_num=chapter_num,
            chapter_events=chapter_events,
            prior_retros_count=len(prior_retros),
            lint_retries=1,
            lint_pass=False,
            first_fail_reasons=reasons_1,
            lint_reasons_if_failed=reasons_2,
            ts_iso=ts_iso,
            start_time=start,
        )
        return retro_2

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _attempt_write(
        self,
        *,
        chapter_text: str,
        chapter_events: list[Event],
        prior_retros: list[Retrospective],
        chapter_num_hint: int,
        nudge: str | None,
    ) -> Retrospective:
        user_prompt = self._build_user_prompt(
            chapter_text=chapter_text,
            chapter_events=chapter_events,
            prior_retros=prior_retros,
            chapter_num=chapter_num_hint,
            nudge=nudge,
        )
        messages = [{"role": "user", "content": user_prompt}]
        response = self._call_opus(messages=messages)
        markdown = _extract_text(response)
        return _parse_retrospective_markdown(
            markdown, chapter_num_hint=chapter_num_hint
        )

    def _build_user_prompt(
        self,
        *,
        chapter_text: str,
        chapter_events: list[Event],
        prior_retros: list[Retrospective],
        chapter_num: int,
        nudge: str | None,
    ) -> str:
        parts: list[str] = []
        parts.append(f"chapter_num={chapter_num}")
        parts.append("")
        parts.append("Chapter text:")
        parts.append(chapter_text)
        parts.append("")
        parts.append("Event-log slice (this chapter's drafting cycle):")
        if chapter_events:
            for ev in chapter_events:
                caller = ev.caller_context or {}
                scene_id = caller.get("scene_id", "?")
                parts.append(
                    f"- [{ev.role}] scene={scene_id} "
                    f"latency_ms={ev.latency_ms} "
                    f"input_tokens={ev.input_tokens} "
                    f"output_tokens={ev.output_tokens}"
                )
        else:
            parts.append("(no events for this chapter)")
        parts.append("")
        parts.append("Prior retrospectives summary:")
        if prior_retros:
            for r in prior_retros:
                parts.append(f"- ch{r.chapter_num}: {r.pattern[:200]}")
        else:
            parts.append("(none)")
        parts.append("")
        if nudge:
            parts.append(nudge)
        return "\n".join(parts)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(_TENACITY_MAX_ATTEMPTS),
        wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _call_opus_inner(self, *, messages: list[dict[str, Any]]) -> Any:
        from anthropic import APIConnectionError, APIStatusError

        try:
            return self.anthropic_client.messages.create(
                model=self.model_id,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self._system_blocks,
                messages=messages,
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
        except Exception:  # pragma: no cover
            logger.exception(
                "failed to emit Event(role=%r)", event.role
            )

    def _stub_retrospective(
        self, *, chapter_num: int, exc: Exception
    ) -> Retrospective:
        return Retrospective(
            chapter_num=chapter_num,
            what_worked="(generation failed)",
            what_didnt=str(exc)[:500],
            pattern="",
            candidate_theses=[],
        )

    def _emit_success_event(
        self,
        *,
        retro: Retrospective,
        chapter_num: int,
        chapter_events: list[Event],
        prior_retros_count: int,
        lint_retries: int,
        lint_pass: bool,
        first_fail_reasons: list[str] | None,
        lint_reasons_if_failed: list[str] | None,
        ts_iso: str,
        start_time: float,
    ) -> None:
        latency_ms = int((time.monotonic() - start_time) * 1000)
        event_id_value = compute_event_id(
            ts_iso,
            "retrospective_writer",
            f"retrospective.opus.write:chapter_{chapter_num:02d}",
            self._system_prompt_sha,
        )
        output_hash = hash_text(retro.model_dump_json())
        caller_context: dict[str, Any] = {
            "module": "retrospective.opus",
            "function": "write",
            "chapter_num": chapter_num,
            "events_consumed": len(chapter_events),
            "prior_retros_count": prior_retros_count,
            "sections_generated": 4,
            "lint_pass": lint_pass,
            "lint_retries": lint_retries,
        }
        extra: dict[str, Any] = {}
        if first_fail_reasons is not None:
            extra["first_fail_reasons"] = list(first_fail_reasons)
        if lint_reasons_if_failed is not None:
            extra["lint_reasons_if_failed"] = list(lint_reasons_if_failed)
        event = Event(
            event_id=event_id_value,
            ts_iso=ts_iso,
            role="retrospective_writer",
            model=self.model_id,
            prompt_hash=self._system_prompt_sha,
            input_tokens=0,
            cached_tokens=0,
            output_tokens=0,
            latency_ms=latency_ms,
            temperature=self.temperature,
            top_p=None,
            caller_context=caller_context,
            output_hash=output_hash,
            mode=None,
            rubric_version=None,
            checkpoint_sha=None,
            extra=extra,
        )
        self._emit(event)

    def _emit_error_event(
        self,
        *,
        exc: Exception,
        chapter_num: int,
        chapter_events: list[Event],
        prior_retros_count: int,
        ts_iso: str,
        start_time: float,
    ) -> None:
        latency_ms = int((time.monotonic() - start_time) * 1000)
        event_id_value = compute_event_id(
            ts_iso,
            "retrospective_writer",
            f"retrospective.opus.write:chapter_{chapter_num:02d}",
            self._system_prompt_sha,
        )
        caller_context: dict[str, Any] = {
            "module": "retrospective.opus",
            "function": "write",
            "chapter_num": chapter_num,
            "events_consumed": len(chapter_events),
            "prior_retros_count": prior_retros_count,
            "sections_generated": 0,
            "lint_pass": False,
            "lint_retries": 0,
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
            role="retrospective_writer",
            model=self.model_id,
            prompt_hash=self._system_prompt_sha,
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


def _infer_chapter_num(
    chapter_events: list[Event],
    prior_retros: list[Retrospective],
) -> int:
    """Best-effort chapter number inference. Falls back to prior_retros + 1
    if no events carry chapter_num, else 1."""
    for ev in chapter_events:
        raw = (ev.caller_context or {}).get("chapter_num")
        if isinstance(raw, int):
            return raw
    if prior_retros:
        return max((r.chapter_num for r in prior_retros), default=0) + 1
    return 1


def _extract_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if content and isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts)
    return ""


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z",
    re.DOTALL,
)
_SECTION_RE = re.compile(
    r"^##\s+(What Worked|What Drifted|Emerging Patterns|Open Questions for Next Chapter)\s*\n(.*?)(?=\n##\s+|\Z)",
    re.DOTALL | re.MULTILINE,
)


def _parse_retrospective_markdown(
    markdown: str, *, chapter_num_hint: int
) -> Retrospective:
    """Parse markdown with YAML frontmatter + 4 H2 sections into a
    Retrospective. On malformed input, raise RetrospectiveWriterBlocked —
    caught by write() and converted to the stub-retro path."""
    if not markdown.strip():
        raise RetrospectiveWriterBlocked(
            "empty_output", chapter_num=chapter_num_hint
        )
    m = _FRONTMATTER_RE.match(markdown)
    frontmatter: dict[str, Any] = {}
    body = markdown
    if m is not None:
        fm_text, body = m.group(1), m.group(2)
        try:
            loaded = yaml.safe_load(fm_text)
            if isinstance(loaded, dict):
                frontmatter = loaded
        except yaml.YAMLError:
            # Malformed frontmatter — keep empty; body still parseable.
            frontmatter = {}

    sections: dict[str, str] = {}
    for header, text in _SECTION_RE.findall(body):
        sections[header] = text.strip()

    chapter_num_raw = frontmatter.get("chapter_num", chapter_num_hint)
    try:
        chapter_num = int(chapter_num_raw)
    except (TypeError, ValueError):
        chapter_num = chapter_num_hint

    what_worked = sections.get("What Worked", "")
    what_didnt = sections.get("What Drifted", "")
    pattern = sections.get("Emerging Patterns", "")
    open_questions = sections.get("Open Questions for Next Chapter", "")

    # candidate_theses: prefer the frontmatter list; fall back to splitting
    # the Open Questions section into {id: qN, description: <line>}.
    fm_theses_raw = frontmatter.get("candidate_theses")
    candidate_theses: list[dict[str, object]] = []
    if isinstance(fm_theses_raw, list):
        for idx, entry in enumerate(fm_theses_raw, start=1):
            if isinstance(entry, dict):
                cid = str(entry.get("id", f"q{idx}"))
                desc = str(entry.get("description", ""))
                candidate_theses.append({"id": cid, "description": desc})
    if not candidate_theses and open_questions:
        for idx, line in enumerate(
            (line.strip() for line in open_questions.splitlines() if line.strip()),
            start=1,
        ):
            candidate_theses.append({"id": f"q{idx}", "description": line})

    return Retrospective(
        chapter_num=chapter_num,
        what_worked=what_worked,
        what_didnt=what_didnt,
        pattern=pattern,
        candidate_theses=candidate_theses,
    )


__all__ = [
    "OpusRetrospectiveWriter",
    "RetrospectiveWriterBlocked",
]
