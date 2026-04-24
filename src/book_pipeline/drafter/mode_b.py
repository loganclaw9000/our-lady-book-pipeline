"""ModeBDrafter — Protocol-conformant Mode-B frontier drafter (DRAFT-03 + DRAFT-04).

Plan 05-01 Task 2. Consumes a ContextPack, renders the Jinja2 mode_b.j2 USER
prompt, calls Anthropic Opus 4.7 via ``client.messages.create`` with a
pre-rendered voice-samples SYSTEM block cached at ``ttl='1h'``, emits exactly
ONE role='drafter' OBS-01 Event per draft() call (including error paths).

Design rules (D-01..D-04 per CONTEXT.md + ADR-004):

- **Clone-not-abstract (D-01):** ModeADrafter stays untouched. Shared strings
  (VOICE_DESCRIPTION, RUBRIC_AWARENESS) are paraphrased here, NOT imported
  from mode_a.py. The two modes share the Drafter Protocol and the Event
  shape, nothing else.

- **Cache identity (D-02):** ``self._system_blocks`` is a list built ONCE in
  ``__init__`` and reused across every ``draft()`` call. Same Python list
  object → same memory → byte-identical cache prefix → Anthropic's 1h
  ephemeral cache hits on request #2+ within the TTL window (Pitfall 1).

- **Voice-samples prefix (D-03):** 3-5 curated passages (400-600 words each;
  slack 300-700 accepted per RESEARCH.md). Validated at ``__init__`` with
  loud RuntimeError if the curator hasn't run.

- **B-3 lineage:** DraftResponse.voice_pin_sha = voice_pin.checkpoint_sha. A
  Mode-B draft CLAIMS the pinned FT checkpoint for lineage even though the
  B draft came from Opus; chapter frontmatter invariants downstream rely on
  this passthrough.

- **Observability-is-load-bearing (ADR-003):** error paths emit a
  role='drafter' Event BEFORE raising ModeBDrafterBlocked, so a wedged
  nightly run still leaves a forensic trail.

Error paths route through ``_emit_error_event``:
  - ``anthropic_transient_exhausted`` — tenacity 5x retry exhausted.
  - ``empty_completion`` — Opus returned empty/whitespace prose.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2
import tenacity

from book_pipeline.config.voice_pin import VoicePinData
from book_pipeline.interfaces.drafter import Drafter  # noqa: F401 — Protocol ref
from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.types import DraftRequest, DraftResponse, Event
from book_pipeline.observability.hashing import event_id, hash_text

# Guarded import — tenacity retry_if_exception_type needs real class objects
# at module load; bare-import anthropic so a missing SDK surfaces cleanly.
try:  # pragma: no cover — import-time guard
    from anthropic import APIConnectionError, APIStatusError
except ImportError as _exc:  # pragma: no cover
    raise RuntimeError(
        "anthropic SDK is required for ModeBDrafter; install "
        "anthropic>=0.96.0 as declared in pyproject.toml"
    ) from _exc


# Paraphrase of mode_a.py constants per ADR-004 clone-not-abstract.
# DO NOT import VOICE_DESCRIPTION / RUBRIC_AWARENESS from mode_a — if the two
# ever diverge (Mode-B gets genre-specific voice nudges, Mode-A stays pure FT),
# a shared constant would encode a false "these must match" invariant.
VOICE_DESCRIPTION = (
    "You write in the voice demonstrated by the samples above: clean "
    "declarative prose with em-dash rhythm, numeric specificity in sensory "
    "description, and structural asides that sharpen rather than decorate. "
    "You resist purple prose, expository dumps, and genre-tropes-as-shorthand. "
    "Sentences tend short; paragraphs close on decisions, not gestures."
)

RUBRIC_AWARENESS = (
    "The scene will be scored on a 5-axis rubric: historical fidelity, "
    "metaphysics coherence, entity continuity, arc beat hit, and negative "
    "constraints (no romanticizing, exoticizing, or cartoonifying). Do not "
    "reference factual claims the corpus section does not support. Preserve "
    "named-entity continuity from prior chapters. Hit the stated beat "
    "function without narrating meta-structure."
)

_DEFAULT_TEMPLATE_PATH = Path(__file__).parent / "templates" / "mode_b.j2"
_MIN_VOICE_SAMPLES = 3
_VOICE_SAMPLE_WC_MIN = 300  # slack window per RESEARCH.md Pattern 1 line 759
_VOICE_SAMPLE_WC_MAX = 700
_FORGE_POSTPROCESS_PATH = Path("/home/admin/paul-thinkpiece-pipeline/eval")


def _apply_forge_postprocess_modeb(text: str) -> str:
    """Strip <think>+mojibake+em-dashes on Mode-B Opus output (Forge contract v1)."""
    try:
        import sys as _sys

        if str(_FORGE_POSTPROCESS_PATH) not in _sys.path:
            _sys.path.insert(0, str(_FORGE_POSTPROCESS_PATH))
        from postprocess import clean_output  # type: ignore[import-not-found]

        return clean_output(text)  # type: ignore[no-any-return]
    except Exception:
        return text


class ModeBDrafterBlocked(Exception):
    """Wraps Mode-B failure modes for scene-loop routing (Plan 05-02).

    Reasons:
      - anthropic_transient_exhausted — 5x tenacity retries exhausted.
      - empty_completion — Opus returned empty/whitespace prose.
    """

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = context
        ctx_keys = ", ".join(sorted(context))
        super().__init__(
            f"ModeBDrafterBlocked({reason!r}; context keys: {ctx_keys})"
        )


def _validate_voice_samples(samples: list[str]) -> None:
    """Reject bootstrap-broken voice_samples lists at drafter __init__ time.

    Per D-03: need >=3 passages; each 400-600 words (slack 300-700).
    """
    if len(samples) < _MIN_VOICE_SAMPLES:
        raise RuntimeError(
            f"ModeBDrafter requires >=3 curated voice samples (D-03), "
            f"got {len(samples)}. Run `book-pipeline curate-voice-samples` "
            f"to populate config/voice_samples.yaml."
        )
    for i, passage in enumerate(samples):
        wc = len(passage.split())
        if wc < _VOICE_SAMPLE_WC_MIN or wc > _VOICE_SAMPLE_WC_MAX:
            raise RuntimeError(
                f"ModeBDrafter voice sample {i} has word_count={wc}; "
                f"target band 400-600 (slack {_VOICE_SAMPLE_WC_MIN}-"
                f"{_VOICE_SAMPLE_WC_MAX}). Fix config/voice_samples.yaml."
            )


def _build_system_text(voice_samples: list[str]) -> str:
    """Concatenate voice samples with a separator + trailing voice/rubric brief.

    The returned string becomes the one-and-only 'text' in _system_blocks and
    serves as the cache key — so keep it deterministic across calls.
    """
    samples_text = "\n\n---\n\n".join(voice_samples)
    return (
        f"<voice_samples>\n{samples_text}\n</voice_samples>\n\n"
        f"{VOICE_DESCRIPTION}\n\n{RUBRIC_AWARENESS}"
    )


def _to_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ModeBDrafter:
    """Drafter Protocol impl — Mode-B via Anthropic Opus 4.7 (DRAFT-03)."""

    mode: str = "B"

    def __init__(
        self,
        *,
        anthropic_client: Any,
        event_logger: EventLogger | None,
        voice_pin: VoicePinData,
        voice_samples: list[str],
        model_id: str = "claude-opus-4-7",
        max_tokens: int = 3072,
        temperature: float = 0.7,
        prompt_template_path: Path | None = None,
    ) -> None:
        self.anthropic_client = anthropic_client
        self.event_logger = event_logger
        self.voice_pin = voice_pin
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature

        # D-03 validation — fail loud at wiring time, never silent.
        _validate_voice_samples(voice_samples)
        self.voice_samples = list(voice_samples)

        # Jinja2 env for the per-scene USER message.
        self._template_path = (
            prompt_template_path
            if prompt_template_path is not None
            else _DEFAULT_TEMPLATE_PATH
        )
        if not self._template_path.exists():
            raise RuntimeError(
                f"mode_b.j2 template not found at {self._template_path}"
            )
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self._template_path.parent)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = self._env.get_template(self._template_path.name)

        # D-02 — pre-render the voice-samples SYSTEM block ONCE. Same Python
        # list object reused across every draft() call so Anthropic's 1h
        # ephemeral cache hits on request #2+ within the TTL window.
        system_text = _build_system_text(self.voice_samples)
        self._system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ]

    # ------------------------------------------------------------------ #
    # Protocol method                                                    #
    # ------------------------------------------------------------------ #

    def draft(self, request: DraftRequest) -> DraftResponse:
        scene_request = request.context_pack.scene_request
        scene_id = (
            f"ch{scene_request.chapter:02d}_sc{scene_request.scene_index:02d}"
        )
        attempt_number = _to_int(
            request.generation_config.get("attempt_number"), default=1
        )
        word_target = _to_int(
            request.generation_config.get("word_target"), default=1500
        )
        preflag_reason = request.generation_config.get("preflag_reason")

        rendered_prompt = self._template.render(
            scene_request=scene_request,
            retrievals=request.context_pack.retrievals,
            prior_scenes=request.prior_scenes,
            word_target=word_target,
            preflag_reason=preflag_reason,
        )
        messages = [{"role": "user", "content": rendered_prompt}]

        t0_ns = time.monotonic_ns()
        try:
            response = self._call_opus(messages=messages)
        except (APIConnectionError, APIStatusError) as exc:
            self._emit_error_event(
                reason="anthropic_transient_exhausted",
                scene_id=scene_id,
                attempt_number=attempt_number,
                cause=str(exc),
            )
            raise ModeBDrafterBlocked(
                "anthropic_transient_exhausted",
                scene_id=scene_id,
                attempt_number=attempt_number,
                cause=str(exc),
            ) from exc

        scene_text = _extract_text(response)
        if not scene_text or not scene_text.strip():
            self._emit_error_event(
                reason="empty_completion",
                scene_id=scene_id,
                attempt_number=attempt_number,
            )
            raise ModeBDrafterBlocked(
                "empty_completion",
                scene_id=scene_id,
                attempt_number=attempt_number,
            )

        # Forge postprocess contract v1.0.0 — strip <think>+mojibake+em-dashes
        # on Mode-B Opus output too (mirrors Mode-A wiring 2026-04-24).
        scene_text = _apply_forge_postprocess_modeb(scene_text)

        latency_ms = max(1, (time.monotonic_ns() - t0_ns) // 1_000_000)
        output_sha = hash_text(scene_text)
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        cached_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        draft_response = DraftResponse(
            scene_text=scene_text,
            mode="B",
            model_id=self.model_id,
            voice_pin_sha=self.voice_pin.checkpoint_sha,  # B-3 lineage
            tokens_in=input_tokens + cached_tokens,
            tokens_out=output_tokens,
            latency_ms=int(latency_ms),
            output_sha=output_sha,
            attempt_number=attempt_number,
        )

        self._emit_success_event(
            scene_id=scene_id,
            scene_request=scene_request,
            attempt_number=attempt_number,
            rendered_prompt=rendered_prompt,
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            latency_ms=int(latency_ms),
            output_sha=output_sha,
            context_pack_fingerprint=request.context_pack.fingerprint,
        )
        return draft_response

    # ------------------------------------------------------------------ #
    # Tenacity-wrapped Anthropic call                                    #
    # ------------------------------------------------------------------ #

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
        retry=tenacity.retry_if_exception_type(
            (APIConnectionError, APIStatusError)
        ),
        reraise=True,
    )
    def _call_opus_inner(self, *, messages: list[dict[str, Any]]) -> Any:
        """Raw Anthropic messages.create with tenacity retry.

        Tests monkeypatch ``ModeBDrafter._call_opus_inner.retry.wait`` to
        ``wait_fixed(0)`` to keep test wall-time <1s (Plan 03-06 pattern).
        """
        return self.anthropic_client.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=self._system_blocks,
            messages=messages,
        )

    def _call_opus(self, *, messages: list[dict[str, Any]]) -> Any:
        return self._call_opus_inner(messages=messages)

    # ------------------------------------------------------------------ #
    # Event emission                                                     #
    # ------------------------------------------------------------------ #

    def _emit_success_event(
        self,
        *,
        scene_id: str,
        scene_request: Any,
        attempt_number: int,
        rendered_prompt: str,
        input_tokens: int,
        cached_tokens: int,
        output_tokens: int,
        latency_ms: int,
        output_sha: str,
        context_pack_fingerprint: str,
    ) -> None:
        if self.event_logger is None:
            return
        ts_iso = _now_iso()
        prompt_h = hash_text(rendered_prompt)
        eid = event_id(
            ts_iso, "drafter", f"drafter.mode_b.draft:{scene_id}", prompt_h
        )
        caller_context: dict[str, Any] = {
            "module": "drafter.mode_b",
            "function": "draft",
            "scene_id": scene_id,
            "chapter": scene_request.chapter,
            "pov": scene_request.pov,
            "beat_function": scene_request.beat_function,
            "voice_pin_sha": self.voice_pin.checkpoint_sha,
            "attempt_number": attempt_number,
            "context_pack_fingerprint": context_pack_fingerprint,
        }
        extra: dict[str, Any] = {"cache_ttl": "1h"}
        event = Event(
            event_id=eid,
            ts_iso=ts_iso,
            role="drafter",
            model=self.model_id,
            prompt_hash=prompt_h,
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            temperature=self.temperature,
            top_p=None,
            caller_context=caller_context,
            output_hash=output_sha,
            mode="B",
            rubric_version=None,
            checkpoint_sha=self.voice_pin.checkpoint_sha,
            extra=extra,
        )
        self.event_logger.emit(event)

    def _emit_error_event(self, reason: str, **ctx: Any) -> None:
        """Emit one role='drafter' error Event BEFORE raising (ADR-003)."""
        if self.event_logger is None:
            return
        ts_iso = _now_iso()
        scene_id = str(ctx.get("scene_id", "unknown"))
        prompt_h = hash_text(f"error:{reason}:{scene_id}")
        eid = event_id(
            ts_iso, "drafter", f"drafter.mode_b.draft:{scene_id}", prompt_h
        )
        caller_context: dict[str, Any] = {
            "module": "drafter.mode_b",
            "function": "draft",
            "scene_id": scene_id,
            "voice_pin_sha": self.voice_pin.checkpoint_sha,
            "attempt_number": int(ctx.get("attempt_number", 1)),
        }
        extra: dict[str, Any] = {"status": "error", "error_reason": reason}
        for k, v in ctx.items():
            if k in ("scene_id", "attempt_number"):
                continue
            extra[k] = v
        event = Event(
            event_id=eid,
            ts_iso=ts_iso,
            role="drafter",
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
            mode="B",
            rubric_version=None,
            checkpoint_sha=self.voice_pin.checkpoint_sha,
            extra=extra,
        )
        self.event_logger.emit(event)


# ---------------------------------------------------------------------- #
# Helpers                                                                #
# ---------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _extract_text(response: Any) -> str:
    """Pull prose text from an Anthropic messages.create response.

    Handles SDK ContentBlock objects AND test fakes exposing dict-shaped
    content.
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
    "RUBRIC_AWARENESS",
    "VOICE_DESCRIPTION",
    "ModeBDrafter",
    "ModeBDrafterBlocked",
]
