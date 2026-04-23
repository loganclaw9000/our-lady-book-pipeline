"""ChapterCritic — CRIT-02 (Plan 04-02).

Second Critic Protocol impl. Mirrors SceneCritic structure-for-structure
(pre-rendered cached system prompt, tenacity-retried messages.parse,
CRIT-04 audit log written on every invocation including tenacity exhaustion
W-7, ONE OBS-01 Event per call) but differs in three critical ways:

  1. STRICTER pass threshold — each axis must score >=3/5 (equivalent to
     >=60/100 after x20 normalization) AND carry no high-severity issue.
     Scene critic used score>=70 with no-high-severity; chapter is harder.

  2. ACCEPTS a FRESH ContextPack — never reuses scene-level packs. This
     is the CORE CRIT-02 mitigation for PITFALLS C-4 (drafter + critic
     sharing the same pack silently inflates pass rates). The caller (Plan
     04-04 DAG orchestrator) runs `bundler.bundle(chapter_scene_request,
     retrievers)` where `chapter_scene_request` has `scene_index=0` + chapter
     midpoint ISO + primary POV + "chapter_overview" beat_function. The
     critic here simply TRUSTS the pack it receives; tests verify the
     audit record carries the chapter pack fingerprint (distinct from any
     scene pack fingerprint).

  3. AUDIT filename prefix is `chapter_{NN:02d}_` rather than the scene
     critic's `{scene_id}_`. Same `write_audit_record` helper — we pass
     `f"chapter_{chapter_num:02d}"` as the `scene_id` argument.

Kernel discipline: no book-domain imports. The few-shot YAML lives alongside
the Jinja2 template under templates/; the chapter rubric lives in
config/rubric.yaml (additive under the scene rubric).
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tenacity
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from book_pipeline.config.rubric import CHAPTER_REQUIRED_AXES, RubricConfig
from book_pipeline.critic.audit import write_audit_record
from book_pipeline.interfaces.types import (
    CriticRequest,
    CriticResponse,
    Event,
)
from book_pipeline.observability.hashing import event_id as compute_event_id
from book_pipeline.observability.hashing import hash_text

logger = logging.getLogger(__name__)


# Canonical 5-axis ordering for the chapter system prompt template.
CHAPTER_AXES_ORDERED: tuple[str, ...] = (
    "historical",
    "metaphysics",
    "entity",
    "arc",
    "donts",
)

# Default audit dir — overridable via ChapterCritic(audit_dir=...).
DEFAULT_CHAPTER_AUDIT_DIR = Path("runs/critic_audit")

# Default template asset paths (relative to repo root under uv).
DEFAULT_CHAPTER_FEWSHOT_PATH = Path(
    "src/book_pipeline/critic/templates/chapter_fewshot.yaml"
)
DEFAULT_CHAPTER_TEMPLATE_PATH = Path(
    "src/book_pipeline/critic/templates/chapter_system.j2"
)

# Filled-axis default score for missing axes. 60.0 == 3/5 x 20 — the chapter
# pass threshold, so a default-filled axis default-passes (warning-logged).
_CHAPTER_FILLED_AXIS_SCORE = 60.0

# Pass-threshold math: chapter rubric pass_threshold_0to5=3 maps to >=60/100.
_CHAPTER_PASS_THRESHOLD_0to100 = 60.0


class ChapterCriticError(Exception):
    """Raised by ChapterCritic on Anthropic failure / shape-violation.

    Carries ``reason`` + ``context`` (dict of chapter_num, underlying cause).
    Plan 04-04 DAG orchestrator catches this and transitions
    ChapterState.CHAPTER_CRITIQUING -> CHAPTER_FAIL or DAG_BLOCKED.
    """

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = context
        super().__init__(f"ChapterCritic: {reason} | {context}")


class ChapterSystemPromptBuilder:
    """Renders the chapter-critic system prompt from chapter_system.j2 + fewshot.

    Parallel to SceneCritic's SystemPromptBuilder. Pre-rendering once at
    ChapterCritic.__init__ time means every review() call reuses the
    identical string — Anthropic's ephemeral prompt cache hits on
    request #2 onward within the 1h TTL window.
    """

    def __init__(
        self,
        rubric: RubricConfig,
        fewshot_path: Path,
        template_path: Path,
    ) -> None:
        self.rubric = rubric
        self.fewshot_path = Path(fewshot_path)
        self.template_path = Path(template_path)

    def _load_fewshot(self) -> dict[str, Any]:
        raw = self.fewshot_path.read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(raw)
        return data

    def render(self) -> tuple[str, str]:
        """Return (rendered_system_prompt, system_prompt_sha)."""
        fewshot = self._load_fewshot()
        env = Environment(
            loader=FileSystemLoader(str(self.template_path.parent)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
        template = env.get_template(self.template_path.name)
        rendered = template.render(
            rubric=self.rubric,
            axes_ordered=list(CHAPTER_AXES_ORDERED),
            few_shot_bad=fewshot["bad"],
            few_shot_good=fewshot["good"],
        )
        sha = hash_text(rendered)
        return rendered, sha


class ChapterCritic:
    """Concrete Critic Protocol impl: Anthropic Opus 4.7 chapter-level reviewer.

    Instantiate once per book-pipeline chapter invocation so the system
    prompt (chapter rubric + chapter few-shot) is rendered once and reused
    across re-runs — Anthropic's 1h ephemeral cache hits on request #2+.

    Pre-conditions (CriticRequest):
      - `request.scene_text` carries the ASSEMBLED CHAPTER text (field name
        preserved for Protocol compatibility; plan's chapter_context dict
        carries chapter_num + assembly_commit_sha).
      - `request.context_pack` is a FRESH chapter-scoped pack (NOT a scene
        pack). Caller is responsible for freshness; we trust the fingerprint.
      - `request.chapter_context["chapter_num"]` populated; KeyError -> error.

    Post-conditions:
      - Audit record written to `audit_dir/chapter_{NN:02d}_01_{ts}.json`
        on EVERY invocation (success AND tenacity-exhaustion failure, W-7).
      - Exactly one Event emitted per call (role='chapter_critic' for
        success, role='chapter_critic' with extra['status']='error' for
        failure).
      - Returns CriticResponse on success; raises ChapterCriticError on failure.
    """

    level: str = "chapter"

    def __init__(
        self,
        *,
        anthropic_client: Any,
        event_logger: Any | None,
        rubric: RubricConfig,
        fewshot_path: Path = DEFAULT_CHAPTER_FEWSHOT_PATH,
        template_path: Path = DEFAULT_CHAPTER_TEMPLATE_PATH,
        audit_dir: Path = DEFAULT_CHAPTER_AUDIT_DIR,
        model_id: str = "claude-opus-4-7",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        self.anthropic_client = anthropic_client
        self.event_logger = event_logger
        self.rubric = rubric
        self.audit_dir = Path(audit_dir)
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Pre-render once — identical text across review() calls so
        # Anthropic's ephemeral cache hits.
        self._builder = ChapterSystemPromptBuilder(
            rubric=rubric,
            fewshot_path=Path(fewshot_path),
            template_path=Path(template_path),
        )
        self._system_prompt, self._system_prompt_sha = self._builder.render()
        # Same list object reused across review() calls (Test J).
        self._system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._system_prompt,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ]

    # ------------------------------------------------------------------ #
    # Critic Protocol                                                    #
    # ------------------------------------------------------------------ #

    def review(self, request: CriticRequest) -> CriticResponse:
        chapter_num = _derive_chapter_num(request)
        assembly_commit_sha = _derive_assembly_sha(request)
        ts_iso = _now_iso()
        context_pack_fingerprint = request.context_pack.fingerprint
        request_rubric_mismatch = (
            request.rubric_version != self.rubric.chapter_rubric.rubric_version
        )
        if request_rubric_mismatch:
            logger.warning(
                "chapter rubric-version mismatch: request=%r, critic=%r",
                request.rubric_version,
                self.rubric.chapter_rubric.rubric_version,
            )

        user_prompt = self._build_chapter_user_prompt(request)
        user_prompt_sha = hash_text(user_prompt)
        messages = [{"role": "user", "content": user_prompt}]

        start = time.monotonic()
        try:
            response = self._call_opus(messages=messages)
        except Exception as exc:  # tenacity exhausted OR unexpected
            self._handle_failure(
                exc=exc,
                chapter_num=chapter_num,
                ts_iso=ts_iso,
                user_prompt_sha=user_prompt_sha,
                context_pack_fingerprint=context_pack_fingerprint,
                assembly_commit_sha=assembly_commit_sha,
                request_rubric_mismatch=request_rubric_mismatch,
                start_time=start,
            )
            raise ChapterCriticError(
                "anthropic_unavailable",
                chapter_num=chapter_num,
                underlying_cause=str(exc),
            ) from exc

        latency_ms = int((time.monotonic() - start) * 1000)

        parsed_raw = response.parsed_output
        if parsed_raw is None:
            raise ChapterCriticError(
                "parsed_output_missing",
                chapter_num=chapter_num,
            )
        parsed: CriticResponse = parsed_raw

        # Post-process: fill missing axes, enforce threshold + high-severity
        # axis fail, enforce overall_pass invariant, stamp rubric_version,
        # recompute output_sha.
        filled_axes, invariant_fixed = self._post_process(parsed, chapter_num)

        # Compute output_sha over the parsed model excluding output_sha itself.
        parsed.output_sha = hash_text(
            parsed.model_dump_json(exclude={"output_sha"})
        )

        # Audit record (success path).
        raw_dump = _safe_model_dump(response)
        usage = getattr(response, "usage", None)
        cached_input_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        scene_id_for_audit = f"chapter_{chapter_num:02d}"
        event_id_value = compute_event_id(
            ts_iso,
            "chapter_critic",
            f"critic.chapter.review:{scene_id_for_audit}",
            user_prompt_sha,
        )

        audit_record: dict[str, Any] = {
            "event_id": event_id_value,
            "scene_id": scene_id_for_audit,
            "chapter_num": chapter_num,
            "assembly_commit_sha": assembly_commit_sha,
            "attempt_number": 1,  # chapter critic is single-attempt per review()
            "timestamp_iso": ts_iso,
            "rubric_version": self.rubric.chapter_rubric.rubric_version,
            "model_id": self.model_id,
            "opus_model_id_response": getattr(response, "model", None),
            "caching_cache_control_applied": True,
            "cached_input_tokens": cached_input_tokens,
            "system_prompt_sha": self._system_prompt_sha,
            "user_prompt_sha": user_prompt_sha,
            "context_pack_fingerprint": context_pack_fingerprint,
            "raw_anthropic_response": raw_dump,
            "parsed_critic_response": parsed.model_dump(),
        }
        audit_path = write_audit_record(
            self.audit_dir, scene_id_for_audit, 1, audit_record
        )

        # Emit success Event.
        prompt_hash = hash_text(self._system_prompt + "\n---\n" + user_prompt)
        severities = _axis_severities(parsed)
        chapter_word_count = len(request.scene_text.split())
        caller_context: dict[str, Any] = {
            "module": "critic.chapter",
            "function": "review",
            "chapter_num": chapter_num,
            "rubric_version": self.rubric.chapter_rubric.rubric_version,
            "assembly_commit_sha": assembly_commit_sha,
            "context_pack_fingerprint": context_pack_fingerprint,
            "audit_path": str(audit_path),
            "num_issues": len(parsed.issues),
            "overall_pass": parsed.overall_pass,
            "pass_per_axis": dict(parsed.pass_per_axis),
        }
        extra: dict[str, Any] = {
            "filled_axes": filled_axes,
            "invariant_fixed": invariant_fixed,
            "scores_per_axis": dict(parsed.scores_per_axis),
            "severities": severities,
            "chapter_word_count": chapter_word_count,
        }
        if request_rubric_mismatch:
            extra["request_rubric_version_mismatch"] = True

        event = Event(
            event_id=event_id_value,
            ts_iso=ts_iso,
            role="chapter_critic",
            model=self.model_id,
            prompt_hash=prompt_hash,
            input_tokens=input_tokens,
            cached_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            temperature=self.temperature,
            top_p=None,
            caller_context=caller_context,
            output_hash=parsed.output_sha,
            mode=None,
            rubric_version=self.rubric.chapter_rubric.rubric_version,
            checkpoint_sha=None,
            extra=extra,
        )
        self._emit(event)
        return parsed

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _build_chapter_user_prompt(self, request: CriticRequest) -> str:
        """Format the uncached user message: full chapter_text + retrievals
        summary + context_pack_fingerprint + surfaced conflicts if any."""
        pack = request.context_pack
        parts: list[str] = []
        parts.append(
            "Chapter text (evaluate at chapter scale, all 5 axes):\n"
            f"{request.scene_text}\n"
        )
        parts.append(f"ContextPack fingerprint: {pack.fingerprint}\n")
        parts.append(
            "Retrieval summary (source_path + chunk_id + score):\n"
        )
        for name, result in pack.retrievals.items():
            parts.append(
                f"  [{name}] {len(result.hits)} hits, {result.bytes_used} bytes:"
            )
            for hit in result.hits[:5]:
                parts.append(
                    f"    - chunk_id={hit.chunk_id} score={hit.score:.3f} "
                    f"src={hit.source_path}"
                )
        if pack.conflicts:
            parts.append("\nSurfaced cross-retriever conflicts:")
            for c in pack.conflicts:
                parts.append(
                    f"  - entity={c.entity!r} dimension={c.dimension!r} "
                    f"severity={c.severity!r} values={c.values_by_retriever}"
                )
        parts.append(
            "\nReturn structured JSON matching the CriticResponse schema "
            "with scores_per_axis values >=60.0 for axes that pass the 3/5 threshold."
        )
        return "\n".join(parts)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _call_opus_inner(self, *, messages: list[dict[str, Any]]) -> Any:
        """Raw Anthropic messages.parse with tenacity retry on transient errors."""
        from anthropic import APIConnectionError, APIStatusError

        try:
            return self.anthropic_client.messages.parse(
                model=self.model_id,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self._system_blocks,
                messages=messages,
                output_format=CriticResponse,
            )
        except (APIConnectionError, APIStatusError):
            raise

    def _call_opus(self, *, messages: list[dict[str, Any]]) -> Any:
        return self._call_opus_inner(messages=messages)

    def _post_process(
        self,
        parsed: CriticResponse,
        chapter_num: int,
    ) -> tuple[list[str], bool]:
        """Fill missing axes, enforce >=60 + no-high-severity threshold,
        enforce overall_pass invariant, override rubric_version."""
        filled_axes: list[str] = []
        for axis in sorted(CHAPTER_REQUIRED_AXES):
            if axis not in parsed.pass_per_axis:
                parsed.pass_per_axis[axis] = True
                filled_axes.append(axis)
                logger.warning(
                    "chapter-critic omitted axis=%s; filled pass=True (ch=%d)",
                    axis,
                    chapter_num,
                )
            if axis not in parsed.scores_per_axis:
                parsed.scores_per_axis[axis] = _CHAPTER_FILLED_AXIS_SCORE

        # Compute per-axis max severity from parsed.issues.
        severity_order = {"none": 0, "low": 1, "mid": 2, "high": 3}
        max_sev: dict[str, int] = {a: 0 for a in CHAPTER_REQUIRED_AXES}
        for issue in parsed.issues:
            if issue.axis in max_sev:
                s = severity_order.get(issue.severity, 0)
                if s > max_sev[issue.axis]:
                    max_sev[issue.axis] = s

        # Apply >=60 threshold AND no-high-severity rule per axis.
        for axis in CHAPTER_REQUIRED_AXES:
            score = parsed.scores_per_axis.get(axis, 0.0)
            axis_pass = (
                score >= _CHAPTER_PASS_THRESHOLD_0to100
                and max_sev[axis] < severity_order["high"]
            )
            if parsed.pass_per_axis.get(axis) != axis_pass:
                logger.warning(
                    "chapter-critic axis=%s pass flipped by post-process "
                    "(score=%.1f, max_severity=%d, ch=%d)",
                    axis,
                    score,
                    max_sev[axis],
                    chapter_num,
                )
                parsed.pass_per_axis[axis] = axis_pass

        expected_overall = all(parsed.pass_per_axis.values())
        invariant_fixed = parsed.overall_pass != expected_overall
        if invariant_fixed:
            logger.warning(
                "chapter-critic overall_pass invariant mismatch: "
                "overall_pass=%s vs all(pass_per_axis)=%s; fixing (ch=%d)",
                parsed.overall_pass,
                expected_overall,
                chapter_num,
            )
            parsed.overall_pass = expected_overall

        # Override rubric_version to critic's source-of-truth.
        chapter_version = self.rubric.chapter_rubric.rubric_version
        if parsed.rubric_version != chapter_version:
            logger.warning(
                "chapter-critic response rubric_version=%r; overriding to %r",
                parsed.rubric_version,
                chapter_version,
            )
            parsed.rubric_version = chapter_version

        return filled_axes, invariant_fixed

    def _emit(self, event: Event) -> None:
        if self.event_logger is None:
            return
        try:
            self.event_logger.emit(event)
        except Exception:  # pragma: no cover — best-effort
            logger.exception("failed to emit Event(role=%r)", event.role)

    def _handle_failure(
        self,
        *,
        exc: Exception,
        chapter_num: int,
        ts_iso: str,
        user_prompt_sha: str,
        context_pack_fingerprint: str | None,
        assembly_commit_sha: str | None,
        request_rubric_mismatch: bool,
        start_time: float,
    ) -> None:
        """W-7: audit record + error Event written BEFORE raise on tenacity
        exhaustion. Matches SceneCritic's _handle_failure shape exactly."""
        latency_ms = int((time.monotonic() - start_time) * 1000)
        scene_id_for_audit = f"chapter_{chapter_num:02d}"
        event_id_value = compute_event_id(
            ts_iso,
            "chapter_critic",
            f"critic.chapter.review:{scene_id_for_audit}",
            user_prompt_sha,
        )
        attempts_made = 5
        audit_record: dict[str, Any] = {
            "event_id": event_id_value,
            "scene_id": scene_id_for_audit,
            "chapter_num": chapter_num,
            "assembly_commit_sha": assembly_commit_sha,
            "attempt_number": 1,
            "timestamp_iso": ts_iso,
            "rubric_version": self.rubric.chapter_rubric.rubric_version,
            "model_id": self.model_id,
            "opus_model_id_response": None,
            "caching_cache_control_applied": True,
            "cached_input_tokens": 0,
            "system_prompt_sha": self._system_prompt_sha,
            "user_prompt_sha": user_prompt_sha,
            "context_pack_fingerprint": context_pack_fingerprint,
            "raw_anthropic_response": {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "attempts_made": attempts_made,
            },
            "parsed_critic_response": None,
        }
        try:
            write_audit_record(self.audit_dir, scene_id_for_audit, 1, audit_record)
        except Exception:  # pragma: no cover
            logger.exception("failed to write chapter-critic failure audit")

        prompt_hash = hash_text(self._system_prompt + "\n---\n" + user_prompt_sha)
        caller_context: dict[str, Any] = {
            "module": "critic.chapter",
            "function": "review",
            "chapter_num": chapter_num,
            "rubric_version": self.rubric.chapter_rubric.rubric_version,
            "assembly_commit_sha": assembly_commit_sha,
            "context_pack_fingerprint": context_pack_fingerprint,
        }
        extra: dict[str, Any] = {
            "status": "error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "attempts_made": attempts_made,
        }
        if request_rubric_mismatch:
            extra["request_rubric_version_mismatch"] = True
        error_event = Event(
            event_id=event_id_value,
            ts_iso=ts_iso,
            role="chapter_critic",
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
            rubric_version=self.rubric.chapter_rubric.rubric_version,
            checkpoint_sha=None,
            extra=extra,
        )
        self._emit(error_event)


# ---------------------------------------------------------------------- #
# Helpers                                                                #
# ---------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _derive_chapter_num(request: CriticRequest) -> int:
    ctx = request.chapter_context
    if ctx is None or "chapter_num" not in ctx:
        raise ChapterCriticError("missing_chapter_context", chapter_num=None)
    raw = ctx["chapter_num"]
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            raise ChapterCriticError(
                "chapter_num_not_int", chapter_num=None, raw=raw
            ) from None
    raise ChapterCriticError("chapter_num_wrong_type", chapter_num=None, raw=raw)


def _derive_assembly_sha(request: CriticRequest) -> str | None:
    ctx = request.chapter_context
    if ctx is None:
        return None
    raw = ctx.get("assembly_commit_sha")
    if raw is None:
        return None
    return str(raw)


def _safe_model_dump(response: Any) -> dict[str, Any]:
    dumper = getattr(response, "model_dump", None)
    if callable(dumper):
        try:
            result: dict[str, Any] = dumper()
            return result
        except Exception:  # pragma: no cover
            logger.exception("model_dump() failed on chapter-critic response; falling back")
    return {
        "id": getattr(response, "id", None),
        "type": getattr(response, "type", None),
        "model": getattr(response, "model", None),
        "role": getattr(response, "role", None),
    }


def _axis_severities(parsed: CriticResponse) -> dict[str, str]:
    order = {"none": 0, "low": 1, "mid": 2, "high": 3}
    reverse = {v: k for k, v in order.items()}
    result = {axis: 0 for axis in CHAPTER_REQUIRED_AXES}
    for issue in parsed.issues:
        if issue.axis in result:
            cur = result[issue.axis]
            new = order.get(issue.severity, 0)
            if new > cur:
                result[issue.axis] = new
    return {axis: reverse[v] for axis, v in result.items()}


__all__ = [
    "CHAPTER_AXES_ORDERED",
    "ChapterCritic",
    "ChapterCriticError",
    "ChapterSystemPromptBuilder",
]
