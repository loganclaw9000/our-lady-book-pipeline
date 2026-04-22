"""Cross-Protocol Pydantic type contracts for book_pipeline.interfaces.

These BaseModels flow across the 13 Protocol boundaries defined in
book_pipeline.interfaces.*. Signatures here are DEFINITIVE — Phase 2+ plans
implement concrete components against these exact shapes.

The Event model is the OBS-01 contract. Phase 1 freezes its schema at v1.0.
Later phases may ADD OPTIONAL fields, but may NOT rename or remove existing
fields. Migration path: bump `schema_version`.

Generic payload dicts use `dict[str, object]` to satisfy mypy --strict while
preserving the "free-form JSON-shaped payload" semantics from the plan's
<interfaces> block (the plan wrote bare `dict`; we tighten only the generic
parameter, not the field name, type name, or structural behavior).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# --- RAG / Scene types ---
class SceneRequest(BaseModel):
    """Request shape presented to retrievers and the ContextPackBundler.

    One SceneRequest per scene position in the outline. Bundler uses these
    fields to route to the 5 typed retrievers (historical, metaphysics,
    entity_state, arc_position, negative_constraint).
    """

    chapter: int
    scene_index: int
    pov: str
    date_iso: str  # historical date for this scene (ISO-8601 or best-available)
    location: str
    beat_function: str  # label from outline.md (plan 2 of Phase 2 parses this)
    preceding_scene_summary: str | None = None


class RetrievalHit(BaseModel):
    """Single chunk returned by a Retriever."""

    text: str
    source_path: str
    chunk_id: str
    score: float
    metadata: dict[str, object] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Structured output of one typed retriever for one scene request."""

    retriever_name: (
        str  # "historical"|"metaphysics"|"entity_state"|"arc_position"|"negative_constraint"
    )
    hits: list[RetrievalHit]
    bytes_used: int
    query_fingerprint: str  # xxhash of SceneRequest (cache key)


class ContextPack(BaseModel):
    """Bundler output — the structured context packet handed to a Drafter."""

    scene_request: SceneRequest
    retrievals: dict[str, RetrievalResult]  # keyed by retriever name
    total_bytes: int
    assembly_strategy: str = "round_robin"
    fingerprint: str  # xxhash of the whole pack


# --- Drafter types ---
class DraftRequest(BaseModel):
    """Input to a Drafter (Mode A or B)."""

    context_pack: ContextPack
    prior_scenes: list[str] = Field(default_factory=list)
    generation_config: dict[str, object] = Field(
        default_factory=dict
    )  # temperature, top_p, repetition_penalty, max_tokens
    prompt_template_id: str = "default"


class DraftResponse(BaseModel):
    """Drafter output — one scene draft with telemetry fields for OBS-01."""

    scene_text: str
    mode: str  # "A" | "B"
    model_id: str
    voice_pin_sha: str | None = None  # required for mode="A"
    tokens_in: int
    tokens_out: int
    latency_ms: int
    output_sha: str  # xxhash of scene_text
    attempt_number: int = 1


# --- Critic types ---
class CriticIssue(BaseModel):
    """One finding from the Critic on one of the 5 rubric axes."""

    axis: str  # "historical"|"metaphysics"|"entity"|"arc"|"donts"
    severity: str  # "low"|"mid"|"high" per CRIT-01
    location: str  # char-span or paragraph id in scene_text
    claim: str
    evidence: str
    citation: str | None = None  # retriever hit chunk_id if applicable


class CriticRequest(BaseModel):
    """Input to a Critic (scene- or chapter-level)."""

    scene_text: str
    context_pack: ContextPack
    rubric_id: str  # "scene.v1" | "chapter.v1" etc, resolved against rubric.yaml
    rubric_version: str  # plan 03 config loader populates this
    chapter_context: dict[str, object] | None = None  # used by chapter-level critic in Phase 4


class CriticResponse(BaseModel):
    """Critic output — per-axis pass/score + list of issues + overall pass."""

    pass_per_axis: dict[str, bool]
    scores_per_axis: dict[str, float]  # 0..100
    issues: list[CriticIssue]
    overall_pass: bool
    model_id: str
    rubric_version: str
    output_sha: str


# --- Regen types ---
class RegenRequest(BaseModel):
    """Input to a Regenerator. attempt_number starts at 2 (1 is the original draft)."""

    prior_draft: DraftResponse
    context_pack: ContextPack
    issues: list[CriticIssue]
    attempt_number: int  # 2..R (attempt 1 is the original draft)
    max_attempts: int


# --- Scene state ---
# Note: plan 01-02 <interfaces> block specifies `class SceneState(str, Enum)`
# verbatim as the frozen contract. StrEnum would be semantically equivalent but
# would change the class's MRO visible to downstream code; preserve plan shape.
class SceneState(str, Enum):  # noqa: UP042
    """States a scene can occupy in the pipeline. Persisted as JSON values.

    Transitions managed by the orchestrator (Phase 3); see
    scene_state_machine.transition().
    """

    PENDING = "pending"
    RAG_READY = "rag_ready"
    DRAFTED_A = "drafted_a"
    CRITIC_PASS = "critic_pass"
    CRITIC_FAIL = "critic_fail"
    REGENERATING = "regenerating"
    ESCALATED_B = "escalated_b"
    COMMITTED = "committed"
    HARD_BLOCKED = "hard_blocked"


class SceneStateRecord(BaseModel):
    """Persisted scene state — one file per scene under drafts/scene_buffer/<chapter>/."""

    scene_id: str  # "ch03_sc02"
    state: SceneState
    attempts: dict[str, int] = Field(
        default_factory=dict
    )  # {"mode_a_regens": int, "mode_b_attempts": int}
    mode_tag: str | None = None  # "A" | "B"
    history: list[dict[str, object]] = Field(default_factory=list)  # ordered transitions
    blockers: list[str] = Field(default_factory=list)


# --- Entity & retrospective types ---
class EntityCard(BaseModel):
    """Per-chapter entity state produced by EntityExtractor (CORPUS-02)."""

    entity_name: str
    last_seen_chapter: int
    state: dict[str, object] = Field(default_factory=dict)
    evidence_spans: list[str] = Field(default_factory=list)
    source_chapter_sha: str  # per CORPUS-02 — stale-card detection


class Retrospective(BaseModel):
    """RetrospectiveWriter output per chapter (RETRO-01)."""

    chapter_num: int
    what_worked: str
    what_didnt: str
    pattern: str
    candidate_theses: list[dict[str, object]] = Field(default_factory=list)


class ThesisEvidence(BaseModel):
    """ThesisMatcher output — one action per open thesis per retrospective."""

    thesis_id: str
    action: str  # "open" | "update" | "close"
    evidence: str
    transferable_artifact: str | None = None


# --- OBS-01 Event model — FROZEN at end of Phase 1 per CONTEXT.md D-06 ---
class Event(BaseModel):
    """Structured event for OBS-01. Emitted by EventLogger to runs/events.jsonl.

    Phase 1 freezes this schema at v1.0. Later phases may add OPTIONAL fields,
    never rename or remove. Migration path: bump schema_version.

    All 18 fields are enumerated in .planning/phases/01-foundation-observability-baseline/
    01-CONTEXT.md D-06 and 01-02-PLAN.md.
    """

    schema_version: str = "1.0"
    event_id: str  # xxhash(ts + role + caller + prompt_sha)
    ts_iso: str  # RFC3339
    role: str  # "drafter"|"critic"|"regenerator"|"entity_extractor"|"retrospective_writer"|"thesis_matcher"|"digest_generator"
    model: str  # concrete model id (vllm/paul-voice-v6-qwen3-32b, claude-opus-4-7, ...)
    prompt_hash: str  # xxhash of prompt text
    input_tokens: int
    cached_tokens: int = 0
    output_tokens: int
    latency_ms: int
    temperature: float | None = None
    top_p: float | None = None
    caller_context: dict[str, object] = Field(
        default_factory=dict
    )  # {module, function, scene_id?, chapter_num?}
    output_hash: str  # xxhash of output text
    mode: str | None = None  # "A"|"B"|None (None for non-drafter events)
    rubric_version: str | None = None  # populated for critic events
    checkpoint_sha: str | None = None  # populated for Mode-A drafter events (V-3 pitfall)
    extra: dict[str, object] = Field(default_factory=dict)  # escape hatch for role-specific extras


__all__ = [
    "ContextPack",
    "CriticIssue",
    "CriticRequest",
    "CriticResponse",
    "DraftRequest",
    "DraftResponse",
    "EntityCard",
    "Event",
    "RegenRequest",
    "RetrievalHit",
    "RetrievalResult",
    "Retrospective",
    "SceneRequest",
    "SceneState",
    "SceneStateRecord",
    "ThesisEvidence",
]
