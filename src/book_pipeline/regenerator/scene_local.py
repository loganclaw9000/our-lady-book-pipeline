"""SceneLocalRegenerator — Regenerator Protocol impl (REGEN-01, Plan 03-06).

Kernel-only scene-level regenerator. Inputs: prior DraftResponse + CriticIssue
list (from Plan 03-05 SceneCritic) + same ContextPack the drafter saw. Calls
Anthropic Opus 4.7 via ``client.messages.create`` (free-text prose, NOT
``messages.parse`` — the regen response is the full revised scene, not
structured JSON). Applies ±10% word-count guard post-response; emits ONE
role='regenerator' OBS-01 Event on success, or one error Event before
raising on any failure path.

Scope:
  - Targeted splicing of char ranges is fragile (sentence boundaries drift).
    We ask Opus for the FULL revised scene with instructions to minimize
    change outside affected ranges; word-count guard enforces the ±10% band.

Kernel discipline:
  - Imports from book_pipeline.drafter.mode_a (VOICE_DESCRIPTION) are
    kernel→kernel — allowed by import-linter contract 1.
  - No imports from the book-domain layer.

Error paths (all route through _emit_error_event BEFORE raising —
observability trail load-bearing):
  - APIConnectionError / APIStatusError after 5 tenacity retries →
    RegeneratorUnavailable('anthropic_unavailable').
  - Empty / whitespace-only response → RegeneratorUnavailable('empty_regen_response').
  - abs(new_wc - prior_wc) / max(prior_wc, 1) > 0.10 → RegenWordCountDrift.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2
import tenacity

from book_pipeline.drafter.mode_a import VOICE_DESCRIPTION
from book_pipeline.interfaces.regenerator import Regenerator  # noqa: F401 — Protocol ref
from book_pipeline.interfaces.types import DraftResponse, Event, RegenRequest
from book_pipeline.observability.hashing import event_id, hash_text

# Guarded import so unit tests can run without the anthropic SDK actually
# making calls; tenacity retry_if_exception_type still needs the real class
# objects though, so we import them at module load and surface a clear
# ImportError otherwise.
try:  # pragma: no cover — import-time guard
    from anthropic import APIConnectionError, APIStatusError
except ImportError as _exc:  # pragma: no cover
    raise RuntimeError(
        "anthropic SDK is required for SceneLocalRegenerator; install "
        "anthropic>=0.96.0 as declared in pyproject.toml"
    ) from _exc


_DEFAULT_TEMPLATE_PATH = Path(__file__).parent / "templates" / "regen.j2"
_WORD_COUNT_DRIFT_LIMIT = 0.10


class RegenWordCountDrift(Exception):
    """Raised when the regenerated scene's word count drifts >10% from the prior.

    Attributes:
      prior_word_count: word count of request.prior_draft.scene_text.
      new_word_count: word count of the Opus regen response.
      drift_pct: abs(new - prior) / max(prior, 1).

    Plan 03-07 scene loop catches this + transitions back to CRITIC_FAIL; the
    attempt counts toward R (regen budget).
    """

    def __init__(
        self,
        prior_word_count: int,
        new_word_count: int,
        drift_pct: float,
    ) -> None:
        self.prior_word_count = prior_word_count
        self.new_word_count = new_word_count
        self.drift_pct = drift_pct
        super().__init__(
            f"RegenWordCountDrift(prior={prior_word_count}, new={new_word_count}, "
            f"drift_pct={drift_pct:.3f})"
        )


class RegeneratorUnavailable(Exception):
    """Raised on regen failure modes that are NOT word-count drift.

    Reasons:
      - 'anthropic_unavailable' — tenacity 5x retries exhausted on APIConnectionError
        / APIStatusError.
      - 'empty_regen_response' — Opus returned an empty or whitespace-only scene.

    Context carries whatever kwargs the caller supplied (scene_id, attempt,
    cause, etc.); __str__ surfaces reason + sorted context keys so the
    exception is grep-able in logs.
    """

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = context
        ctx_keys = ", ".join(sorted(context))
        super().__init__(f"RegeneratorUnavailable({reason!r}; context keys: {ctx_keys})")


class SceneLocalRegenerator:
    """Regenerator Protocol impl — scene-local rewrite via Opus 4.7."""

    def __init__(
        self,
        *,
        anthropic_client: Any,
        event_logger: Any | None,
        voice_pin: Any,
        template_path: Path | None = None,
        model_id: str = "claude-opus-4-7",
        max_tokens: int = 3072,
        temperature: float = 0.7,
    ) -> None:
        self._anthropic_client = anthropic_client
        self._event_logger = event_logger
        self._voice_pin = voice_pin
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._template_path = (
            template_path if template_path is not None else _DEFAULT_TEMPLATE_PATH
        )

        if not self._template_path.exists():
            raise RuntimeError(
                f"regen.j2 template not found at {self._template_path}"
            )
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self._template_path.parent)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = self._env.get_template(self._template_path.name)

    # ------------------------------------------------------------------ #
    # Protocol method
    # ------------------------------------------------------------------ #

    def regenerate(self, request: RegenRequest) -> DraftResponse:
        scene_request = request.context_pack.scene_request
        scene_id = f"ch{scene_request.chapter:02d}_sc{scene_request.scene_index:02d}"
        attempt_number = request.attempt_number

        # 1-2: group issues by severity.
        severity_grouped_issues: dict[str, list[Any]] = {
            "high": [],
            "mid": [],
            "low": [],
        }
        for issue in request.issues:
            bucket = severity_grouped_issues.setdefault(issue.severity, [])
            bucket.append(issue)

        # 3: word-count target from prior.
        prior_wc = len(request.prior_draft.scene_text.split())
        word_count_target = prior_wc

        # 4: render Jinja2.
        rendered_prompt = self._template.render(
            prior_scene_text=request.prior_draft.scene_text,
            severity_grouped_issues=severity_grouped_issues,
            word_count_target=word_count_target,
            scene_request=scene_request,
            voice_description=VOICE_DESCRIPTION,
            retrievals=request.context_pack.retrievals,
        )

        # 5: split on sentinels.
        system_text, user_text = _split_on_sentinels(rendered_prompt)
        messages = [{"role": "user", "content": user_text}]

        # 6-7: call Opus with tenacity 5x retry.
        t0_ns = time.monotonic_ns()
        try:
            response = self._call_opus(messages=messages, system_text=system_text)
        except (APIConnectionError, APIStatusError) as exc:
            self._emit_error_event(
                reason="anthropic_unavailable",
                scene_id=scene_id,
                attempt_number=attempt_number,
                cause=str(exc),
            )
            raise RegeneratorUnavailable(
                "anthropic_unavailable",
                scene_id=scene_id,
                attempt=attempt_number,
                cause=str(exc),
            ) from exc

        # 8: extract scene text.
        new_scene_text = _extract_text(response)
        if not new_scene_text or not new_scene_text.strip():
            self._emit_error_event(
                reason="empty_regen_response",
                scene_id=scene_id,
                attempt_number=attempt_number,
            )
            raise RegeneratorUnavailable(
                "empty_regen_response",
                scene_id=scene_id,
                attempt=attempt_number,
            )

        # 10: ±10% word-count guard.
        new_wc = len(new_scene_text.split())
        drift_pct = abs(new_wc - prior_wc) / max(prior_wc, 1)
        if drift_pct > _WORD_COUNT_DRIFT_LIMIT:
            self._emit_error_event(
                reason="word_count_drift",
                scene_id=scene_id,
                attempt_number=attempt_number,
                prior_wc=prior_wc,
                new_wc=new_wc,
                drift_pct=drift_pct,
            )
            raise RegenWordCountDrift(prior_wc, new_wc, drift_pct)

        # 11-12: latency + hashes + DraftResponse.
        latency_ms = max(1, (time.monotonic_ns() - t0_ns) // 1_000_000)
        output_sha = hash_text(new_scene_text)
        usage = getattr(response, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)

        voice_pin_sha = getattr(request.prior_draft, "voice_pin_sha", None)
        draft_response = DraftResponse(
            scene_text=new_scene_text,
            mode="A",
            model_id=self.model_id,
            voice_pin_sha=voice_pin_sha,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=int(latency_ms),
            output_sha=output_sha,
            attempt_number=attempt_number,
        )

        # 13: emit success Event.
        self._emit_success_event(
            scene_id=scene_id,
            scene_request=scene_request,
            attempt_number=attempt_number,
            rendered_prompt=rendered_prompt,
            response=response,
            draft_response=draft_response,
            issues=request.issues,
            prior_wc=prior_wc,
            new_wc=new_wc,
            drift_pct=drift_pct,
            word_count_target=word_count_target,
            voice_pin_sha=voice_pin_sha,
            context_pack_fingerprint=request.context_pack.fingerprint,
            latency_ms=int(latency_ms),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return draft_response

    # ------------------------------------------------------------------ #
    # Tenacity-wrapped Anthropic call
    # ------------------------------------------------------------------ #

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
        retry=tenacity.retry_if_exception_type((APIConnectionError, APIStatusError)),
        reraise=True,
    )
    def _call_opus_inner(
        self, *, messages: list[dict[str, Any]], system_text: str
    ) -> Any:
        """Raw Anthropic messages.create call with tenacity retry."""
        return self._anthropic_client.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_text,
            messages=messages,
        )

    def _call_opus(
        self, *, messages: list[dict[str, Any]], system_text: str
    ) -> Any:
        """Stable wrapper — the decorator is applied to _call_opus_inner so
        tests can monkeypatch ``SceneLocalRegenerator._call_opus_inner.retry.wait``
        without the @tenacity.retry decoration changing the public method name."""
        return self._call_opus_inner(messages=messages, system_text=system_text)

    # ------------------------------------------------------------------ #
    # Event emission
    # ------------------------------------------------------------------ #

    def _emit_success_event(
        self,
        *,
        scene_id: str,
        scene_request: Any,
        attempt_number: int,
        rendered_prompt: str,
        response: Any,
        draft_response: DraftResponse,
        issues: list[Any],
        prior_wc: int,
        new_wc: int,
        drift_pct: float,
        word_count_target: int,
        voice_pin_sha: str | None,
        context_pack_fingerprint: str,
        latency_ms: int,
        tokens_in: int,
        tokens_out: int,
    ) -> None:
        if self._event_logger is None:
            return
        ts_iso = _now_iso()
        prompt_h = hash_text(rendered_prompt)
        eid = event_id(
            ts_iso, "regenerator", f"regenerator.scene_local.regenerate:{scene_id}", prompt_h
        )
        issue_count = len([i for i in issues if i.severity in ("mid", "high")])
        caller_context: dict[str, Any] = {
            "module": "regenerator.scene_local",
            "function": "regenerate",
            "scene_id": scene_id,
            "chapter": scene_request.chapter,
            "attempt_number": attempt_number,
            "issue_count": issue_count,
            "regen_token_count": tokens_out,
            "voice_pin_sha": voice_pin_sha,
            "word_count_drift_pct": drift_pct,
            "word_count_target": word_count_target,
            "word_count_new": new_wc,
            "context_pack_fingerprint": context_pack_fingerprint,
        }
        extra: dict[str, Any] = {
            "issues_addressed": [f"{i.axis}:{i.severity}" for i in issues],
        }
        event = Event(
            event_id=eid,
            ts_iso=ts_iso,
            role="regenerator",
            model=self.model_id,
            prompt_hash=prompt_h,
            input_tokens=tokens_in,
            cached_tokens=0,
            output_tokens=tokens_out,
            latency_ms=latency_ms,
            temperature=self.temperature,
            top_p=None,
            caller_context=caller_context,
            output_hash=draft_response.output_sha,
            mode="A",
            rubric_version=None,
            checkpoint_sha=voice_pin_sha,
            extra=extra,
        )
        self._event_logger.emit(event)

    def _emit_error_event(self, reason: str, **ctx: Any) -> None:
        """Emit one role='regenerator' error Event before raising.

        T-03-06-03 mitigation: observability trail load-bearing on failures.
        """
        if self._event_logger is None:
            return
        ts_iso = _now_iso()
        scene_id = str(ctx.get("scene_id", "unknown"))
        prompt_h = hash_text(f"error:{reason}:{scene_id}")
        eid = event_id(
            ts_iso, "regenerator", f"regenerator.scene_local.regenerate:{scene_id}", prompt_h
        )
        attempt_number = int(ctx.get("attempt_number", 1))
        voice_pin_sha = getattr(self._voice_pin, "checkpoint_sha", None)
        caller_context: dict[str, Any] = {
            "module": "regenerator.scene_local",
            "function": "regenerate",
            "scene_id": scene_id,
            "attempt_number": attempt_number,
            "voice_pin_sha": voice_pin_sha,
        }
        extra: dict[str, Any] = {"status": "error", "error": reason}
        for k, v in ctx.items():
            if k in ("scene_id", "attempt_number"):
                continue
            extra[k] = v
        event = Event(
            event_id=eid,
            ts_iso=ts_iso,
            role="regenerator",
            model=self.model_id,
            prompt_hash=prompt_h,
            input_tokens=0,
            cached_tokens=0,
            output_tokens=0,
            latency_ms=1,
            temperature=None,
            top_p=None,
            caller_context=caller_context,
            output_hash=hash_text(f"error:{reason}"),
            mode="A",
            rubric_version=None,
            checkpoint_sha=voice_pin_sha,
            extra=extra,
        )
        self._event_logger.emit(event)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _split_on_sentinels(rendered: str) -> tuple[str, str]:
    """Split rendered regen.j2 on ===SYSTEM=== / ===USER==="""
    sys_marker = "===SYSTEM==="
    user_marker = "===USER==="
    si = rendered.find(sys_marker)
    ui = rendered.find(user_marker)
    if si < 0 or ui < 0 or ui <= si:
        raise RuntimeError(
            "regen.j2 missing expected sentinels ===SYSTEM=== / ===USER==="
        )
    system_text = rendered[si + len(sys_marker) : ui].strip()
    user_text = rendered[ui + len(user_marker) :].strip()
    return system_text, user_text


def _extract_text(response: Any) -> str:
    """Pull the regen text from an Anthropic messages.create response.

    Handles both the SDK's ``ContentBlock`` objects (with ``.text`` attr) and
    test fakes that expose ``content`` as ``[{"type":"text","text":"..."}]``
    or a namespace with ``.text``.
    """
    content = getattr(response, "content", None)
    if not content:
        return ""
    first = content[0]
    text = getattr(first, "text", None)
    if text is None and isinstance(first, dict):
        text = first.get("text")
    return text if isinstance(text, str) else ""


__all__ = [
    "RegenWordCountDrift",
    "RegeneratorUnavailable",
    "SceneLocalRegenerator",
]
