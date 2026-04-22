"""ModeADrafter — Protocol-conformant Mode-A drafter (DRAFT-01 + DRAFT-02 + OBS-03).

Plan 03-04 Task 2. Consumes a ContextPack, renders the Jinja2 mode_a.j2 prompt
with a per-scene-type sampling profile (DRAFT-02), calls vLLM paul-voice via
the Plan 03-03 VllmClient, runs the V-2 TrainingBleedGate (HARD BLOCK), scores
voice fidelity vs the AnchorSetProvider centroid (OBS-03), and emits exactly
ONE role='drafter' OBS-01 Event per draft call — including on every failure
path.

Design rules (from Plan 03-04 CONTEXT):
- V-2 memorization gate is a HARD BLOCK. Any 12-gram hit fails the draft.
- V-3 SHA drift is Plan 03-03's responsibility — this drafter assumes the
  Plan 03-03 VllmClient already boot_handshook. AnchorSetDrift (V-3 extension
  for anchor drift) is caught at __init__ time via anchor_provider.load().
- Kernel discipline: imports only voice_fidelity/, drafter/vllm_client,
  interfaces/, observability/, config/. Never crosses the kernel/book-domain
  boundary — CLI composition layer injects corpus path + vllm endpoint
  constants. Import-linter contract 1 guards this.
- Every error path routes through _emit_error_event BEFORE raising
  ModeADrafterBlocked so observability captures the failure (T-03-04-03).

scene_type resolution order (see <sampling_profile_resolution>):
  1. request.generation_config["scene_type"] if set + VALID.
  2. Heuristic — concatenate prior_scenes, count paired `"..."` substrings;
     >=3 → "dialogue_heavy".
  3. Default "prose".

voice_fidelity classification (Plan 03-02 thresholds):
  score < fail_threshold       → "fail"
  score < pass_threshold       → "flag_low"
  score >= memorization_flag_threshold → "flag_memorization"
  else                         → "pass"
"""
from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2

from book_pipeline.config.voice_pin import VoicePinData
from book_pipeline.drafter.memorization_gate import (
    MemorizationHit,
    TrainingBleedGate,
)
from book_pipeline.drafter.sampling_profiles import (
    VALID_SCENE_TYPES,
    SamplingProfiles,
    resolve_profile,
)
from book_pipeline.drafter.vllm_client import VllmClient, VllmUnavailable
from book_pipeline.interfaces.event_logger import EventLogger
from book_pipeline.interfaces.types import DraftRequest, DraftResponse, Event
from book_pipeline.observability.hashing import event_id, hash_text
from book_pipeline.voice_fidelity.scorer import score_voice_fidelity

VOICE_DESCRIPTION = (
    "You write in clean declarative prose with em-dash rhythm, numeric "
    "specificity in sensory description, and structural asides that sharpen "
    "rather than decorate. You resist purple prose, expository dumps, and "
    "genre-tropes-as-shorthand. Your sentences tend short; your paragraphs "
    "close on decisions, not gestures."
)

RUBRIC_AWARENESS = (
    "Do not reference factual claims the corpus section does not support. "
    "Preserve named-entity continuity from prior chapters. Do not romanticize, "
    "exoticize, or cartoonify violence, sexuality, or faith. Hit the stated "
    "beat function without narrating meta-structure."
)

_DEFAULT_TEMPLATE_PATH = Path(__file__).parent / "templates" / "mode_a.j2"

_PAIRED_QUOTE_RE = re.compile(r'"[^"]+"')


def _to_int(value: Any, *, default: int) -> int:
    """Safe int() that accepts object-typed generation_config values."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ModeADrafterBlocked(Exception):
    """Wraps every ModeADrafter failure mode for Plan 03-06 scene_state routing.

    Reasons (see draft() docstring):
      - training_bleed
      - mode_a_unavailable
      - empty_completion
      - invalid_scene_type
    """

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = context
        ctx_keys = ", ".join(sorted(context))
        super().__init__(f"ModeADrafterBlocked({reason!r}; context keys: {ctx_keys})")


def _split_on_sentinels(rendered: str) -> tuple[str, str]:
    """Split a rendered mode_a.j2 output on ===SYSTEM=== / ===USER===.

    Returns (system_text, user_text). RuntimeError if either sentinel missing.
    """
    sys_marker = "===SYSTEM==="
    user_marker = "===USER==="
    si = rendered.find(sys_marker)
    ui = rendered.find(user_marker)
    if si < 0 or ui < 0 or ui <= si:
        raise RuntimeError(
            "mode_a.j2 missing expected sentinels ===SYSTEM=== / ===USER==="
        )
    system_text = rendered[si + len(sys_marker) : ui].strip()
    user_text = rendered[ui + len(user_marker) :].strip()
    return system_text, user_text


def _resolve_scene_type(request: DraftRequest) -> str:
    """scene_type resolution — see module docstring.

    Raises ValueError if generation_config.scene_type is set but unknown.
    """
    candidate = request.generation_config.get("scene_type")
    if candidate is not None:
        if not isinstance(candidate, str) or candidate not in VALID_SCENE_TYPES:
            raise ValueError(f"unknown scene_type {candidate!r}")
        return candidate
    # Heuristic: if prior_scenes concat carries >=3 paired quotes, dialogue_heavy.
    if request.prior_scenes:
        joined = "\n".join(request.prior_scenes)
        if len(_PAIRED_QUOTE_RE.findall(joined)) >= 3:
            return "dialogue_heavy"
    return "prose"


def _classify_voice_fidelity(
    score: float,
    *,
    pass_threshold: float,
    fail_threshold: float,
    memorization_flag_threshold: float,
) -> str:
    if score >= memorization_flag_threshold:
        return "flag_memorization"
    if score < fail_threshold:
        return "fail"
    if score < pass_threshold:
        return "flag_low"
    return "pass"


class ModeADrafter:
    """Mode-A drafter — Drafter Protocol impl (DRAFT-01 + DRAFT-02 + OBS-03)."""

    mode: str = "A"

    def __init__(
        self,
        *,
        vllm_client: VllmClient | Any,
        event_logger: EventLogger | None,
        voice_pin: VoicePinData,
        anchor_provider: Any,
        memorization_gate: TrainingBleedGate | None,
        sampling_profiles: SamplingProfiles,
        embedder_for_fidelity: Any | None = None,
        prompt_template_path: Path | None = None,
    ) -> None:
        self.vllm_client = vllm_client
        self.event_logger = event_logger
        self.voice_pin = voice_pin
        self.anchor_provider = anchor_provider
        self.memorization_gate = memorization_gate
        self.sampling_profiles = sampling_profiles
        self.embedder_for_fidelity = embedder_for_fidelity
        self.prompt_template_path = (
            prompt_template_path if prompt_template_path is not None else _DEFAULT_TEMPLATE_PATH
        )

        # Jinja2 env cached on self.
        if not self.prompt_template_path.exists():
            raise RuntimeError(
                f"mode_a.j2 template not found at {self.prompt_template_path}"
            )
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.prompt_template_path.parent)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = self._env.get_template(self.prompt_template_path.name)

        # Prime the anchor-provider cache + raise early on AnchorSetDrift (V-3 ext).
        centroid, anchor_set_sha, vf_config = self.anchor_provider.load()
        self._centroid = centroid
        self._anchor_set_sha = anchor_set_sha
        self._vf_config = vf_config

    # ------------------------------------------------------------------- #
    # Protocol method
    # ------------------------------------------------------------------- #
    def draft(self, request: DraftRequest) -> DraftResponse:
        scene_request = request.context_pack.scene_request
        scene_id = (
            f"ch{scene_request.chapter:02d}_sc{scene_request.scene_index:02d}"
        )
        attempt_number = _to_int(request.generation_config.get("attempt_number"), default=1)

        # 1-2: scene_type resolution + profile lookup.
        try:
            scene_type = _resolve_scene_type(request)
        except ValueError as exc:
            self._emit_error_event(
                reason="invalid_scene_type",
                scene_id=scene_id,
                chapter=scene_request.chapter,
                pov=scene_request.pov,
                beat_function=scene_request.beat_function,
                scene_type_attempted=request.generation_config.get("scene_type"),
                attempt_number=attempt_number,
            )
            raise ModeADrafterBlocked(
                "invalid_scene_type",
                scene_id=scene_id,
                scene_type=request.generation_config.get("scene_type"),
                cause=str(exc),
            ) from exc
        profile = resolve_profile(self.sampling_profiles, scene_type)

        # 3-5: render Jinja2, split on sentinels, assemble messages.
        word_target = _to_int(request.generation_config.get("word_target"), default=1000)
        rendered = self._template.render(
            voice_description=VOICE_DESCRIPTION,
            rubric_awareness=RUBRIC_AWARENESS,
            retrievals=request.context_pack.retrievals,
            scene_request=scene_request,
            prior_scenes=request.prior_scenes,
            word_target=word_target,
            scene_type=scene_type,
        )
        system_text, user_text = _split_on_sentinels(rendered)
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
        max_tokens = _to_int(
            request.generation_config.get("max_tokens"), default=profile.max_tokens
        )

        # 6-7: call vLLM. On VllmUnavailable → error Event + ModeADrafterBlocked.
        t0_ns = time.monotonic_ns()
        try:
            completion = self.vllm_client.chat_completion(
                messages=messages,
                model="paul-voice",
                temperature=profile.temperature,
                top_p=profile.top_p,
                max_tokens=max_tokens,
                repetition_penalty=profile.repetition_penalty,
            )
        except VllmUnavailable as exc:
            self._emit_error_event(
                reason="mode_a_unavailable",
                scene_id=scene_id,
                chapter=scene_request.chapter,
                pov=scene_request.pov,
                beat_function=scene_request.beat_function,
                scene_type=scene_type,
                attempt_number=attempt_number,
                cause=str(exc),
            )
            raise ModeADrafterBlocked(
                "mode_a_unavailable",
                scene_id=scene_id,
                cause=str(exc),
                attempt_number=attempt_number,
            ) from exc

        scene_text = completion["choices"][0]["message"]["content"]
        if not isinstance(scene_text, str) or not scene_text.strip():
            self._emit_error_event(
                reason="empty_completion",
                scene_id=scene_id,
                chapter=scene_request.chapter,
                pov=scene_request.pov,
                beat_function=scene_request.beat_function,
                scene_type=scene_type,
                attempt_number=attempt_number,
            )
            raise ModeADrafterBlocked(
                "empty_completion",
                scene_id=scene_id,
                attempt_number=attempt_number,
            )

        # 9: memorization gate (V-2 HARD BLOCK).
        if self.memorization_gate is not None:
            hits: list[MemorizationHit] = self.memorization_gate.scan(scene_text)
            if hits:
                hit_grams = [h.ngram for h in hits[:5]]
                self._emit_error_event(
                    reason="training_bleed",
                    scene_id=scene_id,
                    chapter=scene_request.chapter,
                    pov=scene_request.pov,
                    beat_function=scene_request.beat_function,
                    scene_type=scene_type,
                    attempt_number=attempt_number,
                    hits=hit_grams,
                )
                raise ModeADrafterBlocked(
                    "training_bleed",
                    scene_id=scene_id,
                    hits=hit_grams,
                    attempt_number=attempt_number,
                )

        # 10: voice-fidelity score (OBS-03).
        voice_fidelity_score: float | None = None
        voice_fidelity_status: str = "not_scored"
        if self.embedder_for_fidelity is not None:
            voice_fidelity_score = float(
                score_voice_fidelity(scene_text, self._centroid, self.embedder_for_fidelity)
            )
            voice_fidelity_status = _classify_voice_fidelity(
                voice_fidelity_score,
                pass_threshold=self._vf_config.pass_threshold,
                fail_threshold=self._vf_config.fail_threshold,
                memorization_flag_threshold=self._vf_config.memorization_flag_threshold,
            )

        # 11: latency + 12: hashes.
        latency_ms = max(1, (time.monotonic_ns() - t0_ns) // 1_000_000)
        output_sha = hash_text(scene_text)
        usage = completion.get("usage") or {}
        tokens_in = int(usage.get("prompt_tokens") or 0)
        tokens_out = int(usage.get("completion_tokens") or 0)

        response = DraftResponse(
            scene_text=scene_text,
            mode="A",
            model_id="paul-voice",
            voice_pin_sha=self.voice_pin.checkpoint_sha,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=int(latency_ms),
            output_sha=output_sha,
            attempt_number=attempt_number,
        )

        # 14: emit one role='drafter' success Event.
        self._emit_success_event(
            scene_id=scene_id,
            scene_request=scene_request,
            scene_type=scene_type,
            attempt_number=attempt_number,
            profile=profile,
            rendered_prompt=rendered,
            response=response,
            completion=completion,
            voice_fidelity_score=voice_fidelity_score,
            voice_fidelity_status=voice_fidelity_status,
            context_pack_fingerprint=request.context_pack.fingerprint,
        )
        return response

    # ------------------------------------------------------------------- #
    # Event emission helpers
    # ------------------------------------------------------------------- #
    def _emit_success_event(
        self,
        *,
        scene_id: str,
        scene_request: Any,
        scene_type: str,
        attempt_number: int,
        profile: Any,
        rendered_prompt: str,
        response: DraftResponse,
        completion: dict[str, Any],
        voice_fidelity_score: float | None,
        voice_fidelity_status: str,
        context_pack_fingerprint: str,
    ) -> None:
        if self.event_logger is None:
            return
        ts_iso = datetime.now(UTC).isoformat(timespec="milliseconds")
        prompt_h = hash_text(rendered_prompt)
        eid = event_id(
            ts_iso, "drafter", f"drafter.mode_a.draft:{scene_id}", prompt_h
        )
        caller_context: dict[str, Any] = {
            "module": "drafter.mode_a",
            "function": "draft",
            "scene_id": scene_id,
            "chapter": scene_request.chapter,
            "pov": scene_request.pov,
            "beat_function": scene_request.beat_function,
            "scene_type": scene_type,
            "voice_pin_sha": self.voice_pin.checkpoint_sha,
            "anchor_set_sha": self._anchor_set_sha,
            "voice_fidelity_score": voice_fidelity_score,
            "voice_fidelity_status": voice_fidelity_status,
            "attempt_number": attempt_number,
            "repetition_penalty": profile.repetition_penalty,
        }
        extra = {
            "word_count": len(response.scene_text.split()),
            "context_pack_fingerprint": context_pack_fingerprint,
        }
        event = Event(
            event_id=eid,
            ts_iso=ts_iso,
            role="drafter",
            model="paul-voice",
            prompt_hash=prompt_h,
            input_tokens=response.tokens_in,
            cached_tokens=0,
            output_tokens=response.tokens_out,
            latency_ms=response.latency_ms,
            temperature=profile.temperature,
            top_p=profile.top_p,
            caller_context=caller_context,
            output_hash=response.output_sha,
            mode="A",
            rubric_version=None,
            checkpoint_sha=self.voice_pin.checkpoint_sha,
            extra=extra,
        )
        self.event_logger.emit(event)

    def _emit_error_event(self, reason: str, **ctx: Any) -> None:
        """Emit one role='drafter' error Event (status='error', error=reason).

        T-03-04-03 mitigation: observability trail load-bearing even on failure.
        """
        if self.event_logger is None:
            return
        ts_iso = datetime.now(UTC).isoformat(timespec="milliseconds")
        scene_id = str(ctx.get("scene_id", "unknown"))
        prompt_h = hash_text(f"error:{reason}:{scene_id}")
        eid = event_id(
            ts_iso, "drafter", f"drafter.mode_a.draft:{scene_id}", prompt_h
        )
        caller_context: dict[str, Any] = {
            "module": "drafter.mode_a",
            "function": "draft",
            "scene_id": scene_id,
            "voice_pin_sha": self.voice_pin.checkpoint_sha,
            "anchor_set_sha": self._anchor_set_sha,
            "attempt_number": int(ctx.get("attempt_number", 1)),
        }
        for key in ("chapter", "pov", "beat_function", "scene_type"):
            if key in ctx:
                caller_context[key] = ctx[key]
        extra: dict[str, Any] = {"status": "error", "error": reason}
        for k, v in ctx.items():
            if k in caller_context:
                continue
            extra[k] = v
        event = Event(
            event_id=eid,
            ts_iso=ts_iso,
            role="drafter",
            model="paul-voice",
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
            checkpoint_sha=self.voice_pin.checkpoint_sha,
            extra=extra,
        )
        self.event_logger.emit(event)


__all__ = [
    "RUBRIC_AWARENESS",
    "VOICE_DESCRIPTION",
    "ModeADrafter",
    "ModeADrafterBlocked",
]
