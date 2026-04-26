"""SceneCritic — CRIT-01 + CRIT-04.

The scene critic scores a drafted scene against the 5-axis rubric via
Anthropic Opus 4.7's ``client.messages.parse()`` structured-output API,
persists a CRIT-04 audit record on every invocation (success OR
tenacity-exhaustion failure, W-7), and emits one OBS-01 Event per call.

Kernel discipline: this module MUST NOT carry project-specific logic —
the few-shot YAML is a config asset under templates/, the rubric is a
project-agnostic 5-axis schema. Import-linter contract 1 (pyproject.toml)
guards the kernel/book-domain boundary on every commit.
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

from book_pipeline.config.rubric import REQUIRED_AXES, RubricConfig
from book_pipeline.critic.audit import write_audit_record
from book_pipeline.interfaces.types import (
    CriticRequest,
    CriticResponse,
    Event,
)
from book_pipeline.observability.hashing import event_id as compute_event_id
from book_pipeline.observability.hashing import hash_text

logger = logging.getLogger(__name__)


# Canonical 13-axis ordering for the system prompt template. Matches
# REQUIRED_AXES in book_pipeline.config.rubric. Order is load-bearing per
# Pitfall 9: schema field order = prompt rubric order.
AXES_ORDERED: tuple[str, ...] = (
    # Original 5 (CRIT-01).
    "historical",
    "metaphysics",
    "entity",
    "arc",
    "donts",
    # Phase 7 LLM-judged physics axes (Plan 07-04 PHYSICS-07 / D-26).
    "pov_fidelity",
    "motivation_fidelity",
    "treatment_fidelity",
    "content_ownership",
    "named_quantity_drift",
    "scene_buffer_similarity",
    # Phase 7 pre-LLM deterministic short-circuits (Plan 07-04 PHYSICS-08/09).
    # Filled by physics scans BEFORE the Anthropic call; intentionally absent
    # from the LLM rubric block in templates/system.j2.
    "stub_leak",
    "repetition_loop",
)

# Phase 7 Plan 04: axes that the Anthropic LLM may NOT score (deterministic
# pre-LLM short-circuits owned by physics/stub_leak.py and
# physics/repetition_loop.py). Plan 07-05 wires the call sites that fill
# these from physics scans before the Anthropic request.
PHYSICS_DETERMINISTIC_AXES: frozenset[str] = frozenset({"stub_leak", "repetition_loop"})

# Phase 7 Plan 04: LLM-judged physics axes; filled by Anthropic response.
PHYSICS_LLM_JUDGED_AXES: tuple[str, ...] = (
    "pov_fidelity",
    "motivation_fidelity",
    "treatment_fidelity",
    "content_ownership",
    "named_quantity_drift",
    "scene_buffer_similarity",
)

# Default audit dir — overridable via SceneCritic(audit_dir=...).
DEFAULT_AUDIT_DIR = Path("runs/critic_audit")

# Default template asset paths (relative to repo root under uv).
DEFAULT_FEWSHOT_PATH = Path("src/book_pipeline/critic/templates/scene_fewshot.yaml")
DEFAULT_TEMPLATE_PATH = Path("src/book_pipeline/critic/templates/system.j2")

# Filled-axis defaults (C-1): when Opus's response omits an axis, the critic
# injects a neutral pass=True, score=75.0 (warning-logged) so the scene loop
# doesn't break on partial responses.
_FILLED_AXIS_SCORE = 75.0


class SceneCriticError(Exception):
    """Raised by SceneCritic on Anthropic failure / shape-violation / invariant break.

    Carries ``reason`` (short tag) + ``context`` (dict of scene_id, attempt,
    underlying cause) so Plan 03-06 scene-loop orchestrator can persist
    HARD_BLOCKED with enough detail for post-mortem.
    """

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = context
        super().__init__(f"SceneCritic: {reason} | {context}")


class SystemPromptBuilder:
    """Renders the critic system prompt from templates/system.j2 + fewshot yaml.

    Pre-rendering the prompt once at SceneCritic.__init__ time means every
    review() call reuses the identical string — Anthropic's prompt cache hits
    on request #2 onward within the 1h TTL window.
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
        """Return (rendered_system_prompt, system_prompt_sha).

        SHA is ``hash_text(rendered)`` — used as the audit-log
        ``system_prompt_sha`` field and as part of the Event ``prompt_hash``.
        """
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
            axes_ordered=list(AXES_ORDERED),
            few_shot_bad=fewshot["bad"],
            few_shot_good=fewshot["good"],
        )
        sha = hash_text(rendered)
        return rendered, sha


class SceneCritic:
    """Concrete Critic Protocol impl: Anthropic Opus 4.7 scene-level reviewer.

    Instantiate once per ``book-pipeline draft`` invocation so the system
    prompt (rubric + few-shot) is rendered once and reused across every
    scene — Anthropic's 1h ephemeral cache hits on request #2+.

    Pre-conditions (CriticRequest):
      - ``request.rubric_version`` present (may mismatch ``self.rubric``;
        logged as warning via Event.extra['request_rubric_version_mismatch']).
      - ``request.context_pack.fingerprint`` populated (for tracing).

    Post-conditions:
      - Audit record written to ``audit_dir/{scene_id}_{attempt:02d}_{ts}.json``
        on EVERY invocation (success AND tenacity-exhaustion failure, W-7).
      - Exactly one Event emitted per call (role='critic' for success,
        role='critic' with extra['status']='error' for failure).
      - Returns CriticResponse on success; raises SceneCriticError on failure.
    """

    level: str = "scene"

    def __init__(
        self,
        *,
        anthropic_client: Any,
        event_logger: Any | None,
        rubric: RubricConfig,
        fewshot_path: Path = DEFAULT_FEWSHOT_PATH,
        template_path: Path = DEFAULT_TEMPLATE_PATH,
        audit_dir: Path = DEFAULT_AUDIT_DIR,
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

        # Pre-render system prompt once — ensures identical text across
        # review() calls so Anthropic's ephemeral cache hits.
        self._builder = SystemPromptBuilder(
            rubric=rubric,
            fewshot_path=Path(fewshot_path),
            template_path=Path(template_path),
        )
        self._system_prompt, self._system_prompt_sha = self._builder.render()
        # Pre-build the system_blocks list: cache_control on the rubric block.
        # The SAME list object is reused across review() calls (Test H).
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
        scene_id = _derive_scene_id(request)
        attempt_number = _derive_attempt_number(request)
        ts_iso = _now_iso()
        context_pack_fingerprint = request.context_pack.fingerprint
        request_rubric_mismatch = (
            request.rubric_version != self.rubric.rubric_version
        )
        if request_rubric_mismatch:
            logger.warning(
                "rubric-version mismatch: request=%r, critic=%r",
                request.rubric_version,
                self.rubric.rubric_version,
            )

        user_prompt = self._build_user_prompt(request)
        user_prompt_sha = hash_text(user_prompt)
        messages = [{"role": "user", "content": user_prompt}]

        start = time.monotonic()
        try:
            response = self._call_opus(messages=messages)
        except Exception as exc:  # tenacity exhausted OR unexpected
            self._handle_failure(
                exc=exc,
                scene_id=scene_id,
                attempt_number=attempt_number,
                ts_iso=ts_iso,
                user_prompt_sha=user_prompt_sha,
                context_pack_fingerprint=context_pack_fingerprint,
                request_rubric_mismatch=request_rubric_mismatch,
                start_time=start,
            )
            raise SceneCriticError(
                "anthropic_unavailable",
                scene_id=scene_id,
                attempt=attempt_number,
                underlying_cause=str(exc),
            ) from exc

        latency_ms = int((time.monotonic() - start) * 1000)

        parsed_raw = response.parsed_output
        if parsed_raw is None:
            # SDK parse failed — treat as shape violation (rare given messages.parse).
            raise SceneCriticError(
                "parsed_output_missing",
                scene_id=scene_id,
                attempt=attempt_number,
            )
        parsed: CriticResponse = parsed_raw

        # Post-process: fill missing axes, enforce invariant, stamp rubric_version,
        # recompute output_sha.
        filled_axes, invariant_fixed = self._post_process(parsed)

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

        event_id_value = compute_event_id(
            ts_iso,
            "critic",
            f"critic.scene.review:{scene_id}",
            user_prompt_sha,
        )

        audit_record = {
            "event_id": event_id_value,
            "scene_id": scene_id,
            "attempt_number": attempt_number,
            "timestamp_iso": ts_iso,
            "rubric_version": self.rubric.rubric_version,
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
            self.audit_dir, scene_id, attempt_number, audit_record
        )

        # Emit success Event.
        prompt_hash = hash_text(self._system_prompt + "\n---\n" + user_prompt)
        severities = _axis_severities(parsed)
        caller_context: dict[str, Any] = {
            "module": "critic.scene",
            "function": "review",
            "scene_id": scene_id,
            "chapter": request.context_pack.scene_request.chapter,
            "attempt_number": attempt_number,
            "num_issues": len(parsed.issues),
            "overall_pass": parsed.overall_pass,
            "pass_per_axis": dict(parsed.pass_per_axis),
            "context_pack_fingerprint": context_pack_fingerprint,
            "audit_path": str(audit_path),
        }
        extra: dict[str, Any] = {
            "filled_axes": filled_axes,
            "invariant_fixed": invariant_fixed,
            "scores_per_axis": dict(parsed.scores_per_axis),
            "severities": severities,
        }
        if request_rubric_mismatch:
            extra["request_rubric_version_mismatch"] = True

        event = Event(
            event_id=event_id_value,
            ts_iso=ts_iso,
            role="critic",
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
            rubric_version=self.rubric.rubric_version,
            checkpoint_sha=None,
            extra=extra,
        )
        self._emit(event)
        return parsed

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _build_user_prompt(self, request: CriticRequest) -> str:
        """Format the uncached user message: scene_text + retrievals (with
        hit TEXT, not just metadata) + context_pack_fingerprint + conflicts.

        Per pipeline audit 2026-04-24: prior implementation sent only
        chunk_id + score + source_path, leaving the critic blind to corpus
        content. Now each top-5 hit per axis carries its actual text snippet
        (capped at 500 chars per hit) so the critic can verify the scene
        against concrete lore — e.g. mecha specs from engineering.md, donts
        from known-liberties.md, named-entity continuity from pantheon.md.
        """
        pack = request.context_pack
        parts: list[str] = []
        parts.append(f"Scene text (evaluate against the 5-axis rubric):\n{request.scene_text}\n")
        parts.append(f"ContextPack fingerprint: {pack.fingerprint}\n")
        parts.append(
            "Retrieval evidence (axis → top-5 hits with text). "
            "USE this evidence: cite chunk_ids in your issues; flag the scene "
            "if it omits clearly-relevant lore (e.g., a metaphysics hit names "
            "an engine class but the scene fails to surface engine context):\n"
        )
        for name, result in pack.retrievals.items():
            parts.append(
                f"\n[{name}] {len(result.hits)} hits, {result.bytes_used} bytes"
            )
            if not result.hits:
                parts.append(
                    "  (no hits — this axis has no corpus evidence; "
                    "do NOT auto-pass on absence)"
                )
                continue
            for hit in result.hits[:5]:
                snippet = " ".join(hit.text.split())  # collapse whitespace
                if len(snippet) > 500:
                    snippet = snippet[:500] + "..."
                parts.append(
                    f"  - chunk_id={hit.chunk_id} score={hit.score:.3f} src={hit.source_path}"
                )
                parts.append(f"    text: {snippet}")
        if pack.conflicts:
            parts.append("\nSurfaced cross-retriever conflicts:")
            for c in pack.conflicts:
                parts.append(
                    f"  - entity={c.entity!r} dimension={c.dimension!r} "
                    f"severity={c.severity!r} values={c.values_by_retriever}"
                )
        parts.append("\nReturn structured JSON matching the CriticResponse schema.")
        return "\n".join(parts)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _call_opus_inner(self, *, messages: list[dict[str, Any]]) -> Any:
        """Raw Anthropic messages.parse call with tenacity retry on transient errors."""
        # Retry only on transient Anthropic errors. Import here to avoid hard
        # dependency surfaces elsewhere.
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
            raise  # let tenacity retry

    def _call_opus(self, *, messages: list[dict[str, Any]]) -> Any:
        """Thin wrapper that invokes the retried call. Separate so callers see
        a stable method name even though the retry decorator is applied."""
        return self._call_opus_inner(messages=messages)

    def _post_process(self, parsed: CriticResponse) -> tuple[list[str], bool]:
        """Fill missing axes + enforce overall_pass invariant + override
        rubric_version. Returns (filled_axes, invariant_fixed).

        Per pipeline audit 2026-04-24: omitted axes now fill pass=False
        (was pass=True). A critic that fails to score a required axis is
        not licensing the scene to advance — it is a critic protocol
        violation that must be surfaced as a blocker, not papered over.
        Score fill at _FILLED_AXIS_SCORE (75) retained only as a
        placeholder for downstream telemetry; pass=False forces
        overall_pass=False and routes the scene to regen.
        """
        filled_axes: list[str] = []
        for axis in sorted(REQUIRED_AXES):
            if axis not in parsed.pass_per_axis:
                parsed.pass_per_axis[axis] = False
                filled_axes.append(axis)
                logger.warning(
                    "critic-response omitted axis=%s; filling pass=False "
                    "(scene will be routed to regen — critic protocol violation)",
                    axis,
                )
            if axis not in parsed.scores_per_axis:
                parsed.scores_per_axis[axis] = _FILLED_AXIS_SCORE

        expected_overall = all(parsed.pass_per_axis.values())
        invariant_fixed = parsed.overall_pass != expected_overall
        if invariant_fixed:
            logger.warning(
                "critic-response invariant mismatch: overall_pass=%s vs all(pass_per_axis)=%s; fixing",
                parsed.overall_pass,
                expected_overall,
            )
            parsed.overall_pass = expected_overall

        # Phase 7 Plan 04 PHYSICS-13: motivation_fidelity is the load-bearing
        # axis (D-02). A FAIL on this axis forces overall_pass=False
        # UNCONDITIONALLY, regardless of other axes. This is a hard-stop, not
        # a severity-weighted vote. The check is BELOW the existing
        # all-axes-AND invariant fix-up so that even if a future change
        # relaxes the AND, the hard-stop persists.
        if parsed.pass_per_axis.get("motivation_fidelity") is False:
            if parsed.overall_pass:
                logger.warning(
                    "motivation_fidelity FAIL forces overall_pass=False (D-02 load-bearing)"
                )
                invariant_fixed = True
            parsed.overall_pass = False

        # Always override rubric_version to the critic's source-of-truth.
        if parsed.rubric_version != self.rubric.rubric_version:
            logger.warning(
                "critic-response rubric_version=%r; overriding to %r",
                parsed.rubric_version,
                self.rubric.rubric_version,
            )
            parsed.rubric_version = self.rubric.rubric_version

        # Preserve filled_axes sorted for deterministic Event.extra comparisons.
        return filled_axes, invariant_fixed

    def _emit(self, event: Event) -> None:
        if self.event_logger is None:
            return
        try:
            self.event_logger.emit(event)
        except Exception:  # pragma: no cover — event emission is best-effort
            logger.exception("failed to emit Event(role=%r)", event.role)

    def _handle_failure(
        self,
        *,
        exc: Exception,
        scene_id: str,
        attempt_number: int,
        ts_iso: str,
        user_prompt_sha: str,
        context_pack_fingerprint: str | None,
        request_rubric_mismatch: bool,
        start_time: float,
    ) -> None:
        """W-7 failure-path: audit record STILL written + error Event emitted."""
        latency_ms = int((time.monotonic() - start_time) * 1000)
        event_id_value = compute_event_id(
            ts_iso,
            "critic",
            f"critic.scene.review:{scene_id}",
            user_prompt_sha,
        )
        # Best-effort attempts count — tenacity's reraise=True means the last
        # raised error surfaces here; we report 5 as the configured max.
        attempts_made = 5
        audit_record: dict[str, Any] = {
            "event_id": event_id_value,
            "scene_id": scene_id,
            "attempt_number": attempt_number,
            "timestamp_iso": ts_iso,
            "rubric_version": self.rubric.rubric_version,
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
            write_audit_record(
                self.audit_dir, scene_id, attempt_number, audit_record
            )
        except Exception:  # pragma: no cover — disk failure is non-recoverable here
            logger.exception("failed to write failure audit record")

        # Emit error Event.
        prompt_hash = hash_text(self._system_prompt + "\n---\n" + user_prompt_sha)
        caller_context: dict[str, Any] = {
            "module": "critic.scene",
            "function": "review",
            "scene_id": scene_id,
            "attempt_number": attempt_number,
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
            role="critic",
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
            rubric_version=self.rubric.rubric_version,
            checkpoint_sha=None,
            extra=extra,
        )
        self._emit(error_event)


# ---------------------------------------------------------------------- #
# Helpers                                                                #
# ---------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _derive_scene_id(request: CriticRequest) -> str:
    sr = request.context_pack.scene_request
    return f"ch{sr.chapter:02d}_sc{sr.scene_index:02d}"


def _derive_attempt_number(request: CriticRequest) -> int:
    if request.chapter_context is None:
        return 1
    raw: object = request.chapter_context.get("attempt_number", 1)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return 1
    return 1


def _safe_model_dump(response: Any) -> dict[str, Any]:
    """Best-effort model_dump on an arbitrary SDK response object."""
    dumper = getattr(response, "model_dump", None)
    if callable(dumper):
        try:
            result: dict[str, Any] = dumper()
            return result
        except Exception:  # pragma: no cover
            logger.exception("model_dump() failed on response; falling back")
    # Fallback: collect a few stable attrs.
    return {
        "id": getattr(response, "id", None),
        "type": getattr(response, "type", None),
        "model": getattr(response, "model", None),
        "role": getattr(response, "role", None),
    }


def _axis_severities(parsed: CriticResponse) -> dict[str, str]:
    """Return max severity per axis from parsed.issues (or 'none' if no issues)."""
    order = {"none": 0, "low": 1, "mid": 2, "high": 3}
    reverse = {v: k for k, v in order.items()}
    result = {axis: 0 for axis in REQUIRED_AXES}
    for issue in parsed.issues:
        if issue.axis in result:
            cur = result[issue.axis]
            new = order.get(issue.severity, 0)
            if new > cur:
                result[issue.axis] = new
    return {axis: reverse[v] for axis, v in result.items()}


__all__ = [
    "AXES_ORDERED",
    "SceneCritic",
    "SceneCriticError",
    "SystemPromptBuilder",
]
