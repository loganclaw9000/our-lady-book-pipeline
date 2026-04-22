# Architecture Research — Our Lady of Champion Book Pipeline

**Domain:** autonomous LLM-based long-form creative-writing pipeline (scene → chapter → canon, voice-FT + frontier-critic, testbed for pipeline family)
**Researched:** 2026-04-21
**Confidence:** HIGH on component boundaries and data flow (grounded in locked ADRs + docs/ARCHITECTURE.md); MEDIUM on specific library picks (will be re-validated in Phase 1 research); MEDIUM on framework comparisons (WebSearch-sourced, verified against general knowledge of LangGraph/DSPy/LlamaIndex).

**Scope note:** This file is a *stress-test extension* of `docs/ARCHITECTURE.md` and ADRs 001-004. It does NOT re-derive the 5 existing diagrams. It adds:
1. Component-level interface contracts (Python Protocols).
2. Canonical per-scene and per-chapter data flows with cache/retry boundaries called out.
3. State persistence model (what lives in files, what lives in SQLite, what's ephemeral).
4. Orchestration pattern (openclaw cron + Anthropic sync calls, file-based handoff).
5. Build order with phase implications.
6. Voice-pin contract with `paul-thinkpiece-pipeline`.
7. Framework survey (LangGraph / DSPy / CrewAI / LlamaIndex Workflows / Haystack / LCEL) — what's overkill, what's worth cribbing.

---

## 1. Framework survey — what fits, what's overkill

We are NOT adopting any of these frameworks as the pipeline substrate. openclaw + plain Python + Anthropic SDK is the substrate (per locked architecture). But several frameworks embody patterns worth stealing.

| Framework | Core abstraction | Verdict for this pipeline | What to steal |
|---|---|---|---|
| **LangGraph** | State graph (nodes + edges + shared state + checkpointing) | **Overkill as framework, right conceptual model.** We already have a state graph (scene request → RAG → draft → critic → regen/escape → commit). | The **checkpointer pattern**: every node writes a durable snapshot so crash recovery restarts from last good state. We will implement this as JSON-on-disk per scene in `drafts/scene_buffer/<chapter>/<scene>.json`, not pull in LangGraph's checkpointer. |
| **DSPy** | `Signature` (input/output types) + `Module` (composed stages) + optimizers | **Overkill for now, right *component* contract.** DSPy's optimizer is premature here — we want to see what fails before teaching a system to auto-tune it. But the `Signature` pattern (declarative I/O for each LLM call) maps cleanly to our Drafter, Critic, Regenerator, Entity Extractor, Retrospective Writer. | The **declarative signature pattern**: every LLM-calling component declares input fields + output fields as a Pydantic / dataclass contract. Makes the components swappable (Protocol-friendly) and the ablation harness cheap (swap model, same signature). |
| **CrewAI** | Role-based agents with goals + collaboration | **Wrong mental model.** We do NOT have collaborating personas; we have a pipeline with specialized roles. Fighting "agent crew" abstractions would add noise without buying durability. | Nothing worth pulling in. The role metaphor is cute but doesn't survive contact with our critic being a structured-JSON function, not a "QA agent." |
| **LlamaIndex Workflows** | Event-driven async steps, tight integration with LlamaIndex RAG primitives | **Attractive for the RAG layer specifically.** Their typed retriever abstractions + query engines are close to what we need for 5 typed retrievers. | Evaluate in Phase 1 RAG research: LlamaIndex's `BaseRetriever` + query engine composition for the 5 retrievers, OR use it just for ingestion and chunking, then hand off to our own `Retriever` Protocol. Don't adopt the workflow engine. |
| **Haystack 2.x** | Pipeline DAG of typed components with formal schemas | **Wrong fit — too infra-heavy.** Haystack targets production RAG at team scale. We have one user. | The **typed-component schema** idea (each component declares its in/out dict shape). We implement this as Pydantic models + Protocols, not Haystack components. |
| **LCEL (LangChain Expression Language)** | Pipe-compose Runnables (`prompt | model | parser`) | **Not needed — our call graph isn't linear**. We have branching (pass/fail → commit vs regen), state (buffer accumulates scenes), and file I/O between every stage. LCEL is for linear transform chains. | Nothing. |
| **AutoGen** | Conversational agents in group chat | **Wrong fit.** We don't want conversation; we want structured JSON and deterministic file handoff. Conversational routing is a liability when the whole point is reproducibility. | Nothing. |
| **Temporal / Prefect / Dagster** | Durable workflow engines with retries, timers, signals | **Overkill — openclaw is the orchestrator.** A Temporal worker would conflict with the cron-driven openclaw-gateway architecture already in place for wipe-haus-state, and Paul's not running a Temporal cluster on the DGX Spark. | The **idempotent-step pattern** (every step keyed by a deterministic ID so re-runs are safe) and **retry-with-exponential-backoff wrapping** around Anthropic API calls (use `tenacity` instead). |

**Net recommendation:** Build components with (a) a **Protocol-based interface** per role, (b) a **dataclass or Pydantic signature** for each LLM call's inputs/outputs, (c) **file-on-disk state** per pipeline node, (d) **`tenacity` for retries**. This gets us LangGraph's durability, DSPy's component contracts, and LlamaIndex's retriever composability without any of their framework lock-in — and keeps kernel extraction (ADR-004) clean because Protocols travel with the code they describe.

---

## 2. Component interface contracts (Python Protocols)

The existing `docs/ARCHITECTURE.md` component table names 13 components. Here are their **proposed interfaces** — Python `Protocol` signatures designed for (a) swappability, (b) future kernel extraction, (c) ablation-harness compatibility.

Naming convention: every LLM-calling component's `__call__` takes a **typed request** (Pydantic model) and returns a **typed response** (Pydantic model). Every component is instantiable via a `from_config(config: dict) -> Component` classmethod so the orchestrator can load any variant from YAML.

### 2.1 Retriever (one Protocol, 5 implementations)

```python
from typing import Protocol
from pydantic import BaseModel

class SceneRequest(BaseModel):
    chapter: int
    scene_index: int
    pov: str
    date_iso: str
    location: str
    beat_function: str
    preceding_scene_summary: str | None

class RetrievalResult(BaseModel):
    retriever_name: str            # "historical" | "metaphysics" | "entity_state" | "arc_position" | "negative_constraint"
    hits: list[dict]               # each hit: {text, source_path, score, metadata}
    bytes_used: int                # for context-pack budget enforcement
    query_fingerprint: str         # sha256 of query — cache key

class Retriever(Protocol):
    name: str
    def retrieve(self, request: SceneRequest) -> RetrievalResult: ...
    def reindex(self) -> None: ...       # rebuild index (called post-commit for entity-state)
    def index_fingerprint(self) -> str:  # sha256 of index contents — for observability
        ...
```

**Swap points:** pgvector vs lancedb vs BM25 vs hybrid — all satisfy the same Protocol. The critic and drafter both consume `RetrievalResult`, neither cares how hits came to exist.

### 2.2 ContextPackBundler

```python
class ContextPack(BaseModel):
    scene_request: SceneRequest
    retrievals: dict[str, RetrievalResult]   # keyed by retriever name
    total_bytes: int                         # must be <= cap (default 40KB)
    assembly_strategy: str                   # "round_robin" | "weighted" | ...
    fingerprint: str                         # sha256 of the whole pack — cache key for drafter + critic

class ContextPackBundler(Protocol):
    def bundle(self, request: SceneRequest, retrievers: list[Retriever]) -> ContextPack: ...
```

**Critical:** the *same* `ContextPack` goes to both drafter AND critic. Caching by `fingerprint` means repeat critic calls (during regen) don't re-query retrievers. See §3 for cache boundaries.

### 2.3 Drafter (Mode A and Mode B share the Protocol)

```python
class DraftRequest(BaseModel):
    context_pack: ContextPack
    prior_scenes: list[str]          # scenes already committed to buffer this chapter
    generation_config: dict          # temp, top_p, max_tokens
    prompt_template_id: str          # which prompt in config/prompts/

class DraftResponse(BaseModel):
    scene_text: str
    mode: str                        # "A" | "B"
    model_id: str                    # e.g. "paul-merged:v6-qwen3-32b" or "claude-opus-4-7"
    voice_pin_sha: str | None        # for Mode A, which checkpoint
    tokens_in: int
    tokens_out: int
    latency_ms: int
    output_sha: str                  # content hash for observability

class Drafter(Protocol):
    mode: str
    def draft(self, request: DraftRequest) -> DraftResponse: ...
```

**Swap points:** vLLM-local (Mode A) vs Anthropic API (Mode B) — same Protocol. Future: a DPO variant, a different base model, a 70B voice-FT — all drop in. Ablation harness can A/B two Drafter instances with identical DraftRequests.

### 2.4 Critic

```python
class CriticRequest(BaseModel):
    scene_text: str
    context_pack: ContextPack        # same pack the drafter saw
    rubric_id: str                   # which rubric in config/rubric.yaml
    chapter_context: dict | None     # for chapter-level critic

class CriticIssue(BaseModel):
    axis: str                        # "historical" | "metaphysics" | "entity" | "arc" | "donts"
    severity: str                    # "block" | "major" | "minor"
    description: str
    evidence: str                    # quote from scene_text
    citation: str | None             # which retrieval hit contradicts

class CriticResponse(BaseModel):
    pass_per_axis: dict[str, bool]
    scores_per_axis: dict[str, float]   # 0..1 per rubric
    issues: list[CriticIssue]
    overall_pass: bool
    model_id: str
    output_sha: str

class Critic(Protocol):
    level: str                       # "scene" | "chapter"
    def review(self, request: CriticRequest) -> CriticResponse: ...
```

**Note:** Scene critic and chapter critic are **two instances of the same Protocol** with different `level` and `rubric_id`. This avoids a parallel class hierarchy and makes it trivial to add, say, a voice-drift critic later.

### 2.5 Regenerator

```python
class RegenRequest(BaseModel):
    prior_draft: DraftResponse
    context_pack: ContextPack
    issues: list[CriticIssue]        # from Critic
    attempt_number: int              # 1..R
    max_attempts: int

class Regenerator(Protocol):
    def regenerate(self, request: RegenRequest) -> DraftResponse: ...
```

**Implementation note:** Regenerator implementations will typically compose a Drafter + an issue-conditioning prompt transform. Keeping it as its own Protocol (rather than "Drafter with flag") makes the escape-to-Mode-B transition cleaner: `RegenController` checks `attempt_number >= max_attempts` and switches from Mode-A-Regenerator to a Mode-B-Drafter.

### 2.6 ChapterAssembler, EntityExtractor, RetrospectiveWriter, ThesisMatcher, DigestGenerator

```python
class ChapterAssembler(Protocol):
    def assemble(self, scene_drafts: list[DraftResponse], chapter_num: int) -> str: ...

class EntityCard(BaseModel):
    entity_name: str
    last_seen_chapter: int
    state: dict                      # open-schema: location, possessions, beliefs, relationships
    evidence_spans: list[str]        # quotes from canon supporting each field

class EntityExtractor(Protocol):
    def extract(self, chapter_text: str, chapter_num: int, prior_cards: list[EntityCard]) -> list[EntityCard]: ...

class Retrospective(BaseModel):
    chapter_num: int
    what_worked: str
    what_didnt: str
    pattern: str
    candidate_theses: list[dict]     # hypothesis + test + metric

class RetrospectiveWriter(Protocol):
    def write(self, chapter_text: str, chapter_events: list[dict], prior_retros: list[Retrospective]) -> Retrospective: ...

class ThesisMatcher(Protocol):
    def match(self, retrospective: Retrospective, open_theses: list[dict]) -> list[dict]:
        """Returns thesis updates: close, update, create."""

class DigestGenerator(Protocol):
    def generate(self, week_start_iso: str, events: list[dict], metrics: dict, theses: list[dict]) -> str: ...
```

### 2.7 PromotionController (state machine)

Not an LLM-calling component — a pure Python state machine that owns the per-scene state transitions:

```python
class SceneState(str, Enum):
    PENDING = "pending"
    RAG_READY = "rag_ready"
    DRAFTED_A = "drafted_a"
    CRITIC_PASS = "critic_pass"
    CRITIC_FAIL = "critic_fail"
    REGENERATING = "regenerating"
    ESCALATED_B = "escalated_b"
    COMMITTED = "committed"
    HARD_BLOCKED = "hard_blocked"

class SceneStateMachine(BaseModel):
    scene_id: str                    # "ch03_sc02"
    state: SceneState
    attempts: dict                   # {"mode_a_regens": 2, "mode_b_attempts": 0}
    mode_tag: str | None             # "A" | "B"
    history: list[dict]              # ordered transitions
    blockers: list[str]
```

**Persisted as JSON** in `drafts/scene_buffer/<chapter>/<scene>.state.json`. See §4.

### 2.8 Orchestrator (openclaw-driven, thin)

```python
class Orchestrator(Protocol):
    """Not a conventional 'orchestrator class' — this is a convention for the openclaw-spawned entry point."""
    def run_cycle(self, budget: dict) -> None:
        """
        Called by openclaw cron. Does:
          1. Pick next PENDING scene from scene buffer.
          2. Advance it through state machine (RAG → draft → critic → ...).
          3. Persist state after every LLM call.
          4. Stop when budget exhausted OR scene committed OR hard-blocked.
        """
```

The key insight: **the orchestrator is NOT a long-running daemon**. It's a batch job that openclaw fires on a cron. State is always on disk between invocations. This is the single biggest architecture decision — see §4.

### 2.9 ObservabilityEventLogger

```python
class Event(BaseModel):
    ts_iso: str
    role: str                        # "drafter" | "critic" | "regenerator" | ...
    scene_id: str | None
    chapter_num: int | None
    model_id: str
    prompt_sha: str
    output_sha: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    temperature: float | None
    caller: str                      # e.g. "run_cycle:ch03_sc02"
    extra: dict

class EventLogger(Protocol):
    def emit(self, event: Event) -> None: ...
```

Append-only JSONL at `runs/events.jsonl`. Secondary ingester (separate cron job, can be daily) loads into `runs/metrics.sqlite` for weekly digest queries. This is the *event-sourced* pattern: JSONL is the source of truth, SQLite is a derived view, rebuildable from the JSONL at any time.

---

## 3. Data flow — canonical path per scene and per chapter

### 3.1 Per-scene path (extends diagram 2 with cache boundaries marked)

```
scene_request (from outline parser)
        │
        │  [CACHE BOUNDARY: SceneRequest sha256 is deterministic;
        │   cached ContextPack valid for this (chapter, scene_index, voice_pin, index_fingerprint) tuple]
        ▼
[bundle_context_pack]
        │
        │  parallel fan-out to 5 retrievers, fan-in to bundler
        │  → ContextPack persisted to drafts/context_packs/<scene_id>.json
        │
        │  [RETRY BOUNDARY 1: individual retriever failures retried 3x with backoff.
        │   Retriever that keeps failing marks scene HARD_BLOCKED → alert.]
        ▼
[draft_mode_a]  ← reads voice_pin.yaml, calls local vLLM
        │
        │  DraftResponse persisted to drafts/scene_buffer/<chapter>/<scene>.draft.json
        │
        │  [RETRY BOUNDARY 2: vLLM transient error → 3x retry; persistent vLLM down →
        │   HARD_BLOCKED with "mode_a_unavailable". Does NOT auto-escalate to Mode B
        │   on infra failure — escalation is for *critic-fail*, not *drafter-broken*.]
        ▼
[critic_scene]  ← calls Anthropic Opus
        │
        │  CriticResponse persisted to drafts/scene_buffer/<chapter>/<scene>.critic_N.json
        │  (N = attempt_number, keeps all attempts for ablation/post-mortem)
        │
        │  [RETRY BOUNDARY 3: Anthropic API 5xx / rate-limit → tenacity retry up to 5x
        │   with exponential backoff. Budget exceeded → HARD_BLOCKED "budget_exhausted".]
        ▼
  pass? ──yes──► [commit to scene buffer, state = COMMITTED_TO_BUFFER]
        │
        no
        ▼
  attempt_number < R?
        │
        │ yes                                     │ no (regen budget exceeded)
        ▼                                         ▼
[regenerate_mode_a]                     [draft_mode_b]  ← Anthropic API
        │                                         │
        │ back to [critic_scene] as               │ back to [critic_scene] with mode=B
        │ attempt_number += 1                     │ (may itself be regen'd, but only ONCE;
        │                                         │  if Mode-B critic fails → HARD_BLOCKED)
        └─────────────────────────────────────────┘

Final state on success: COMMITTED_TO_BUFFER with:
  - scene_buffer/<chapter>/<scene>.final.md
  - scene_buffer/<chapter>/<scene>.meta.json (mode, model, voice_pin, attempts, tokens, cost)
  - events in runs/events.jsonl for every call
```

### 3.2 Per-chapter path (from all scenes present → canon)

```
all scenes for chapter K committed to buffer
        │
        │  [CACHE BOUNDARY: scene set hashed; chapter-assembly output cached by scene-set sha]
        ▼
[chapter_assembler]  ← deterministic Python, maybe optional Opus smoother
        │
        │  output: drafts/chapter_buffer/chapter_NN.md
        ▼
[critic_chapter]  ← Anthropic Opus, different rubric (arc coherence + voice consistency)
        │
        │  [RETRY BOUNDARY 4: chapter-critic fail → controller decides:
        │    - if issues localized to 1-2 scenes → kick those scenes back to scene-level regen
        │    - if issues span the whole chapter → roll back, escalate all scenes to Mode B,
        │      OR (if budget blown) HARD_BLOCKED for Paul review]
        ▼
  pass? ──no──► re-entry into per-scene flow OR hard block
        │
        yes
        ▼
[commit_to_canon]  ← atomic move from drafts/chapter_buffer to canon/chapter_NN.md
                     + git commit (via openclaw workspace)
        │
        ▼  POST-COMMIT FAN-OUT (parallel, non-blocking):
        │
        ├──[reindex_rag]       (rebuild affected RAG indexes; entity-state always, others rarely)
        ├──[entity_extractor]  (Anthropic Opus reads canon/chapter_NN.md, writes entity-state/chapter_NN/*.md)
        ├──[retrospective_writer] (Anthropic Opus reads chapter + runs/events.jsonl filtered to this chapter, writes retrospectives/chapter_NN.md)
        └──[thesis_matcher]    (Python + Opus checks retrospective against theses/open/, updates or closes)

Weekly (separate cron):
        [digest_generator] reads last week of runs/metrics.sqlite + theses/ + retrospectives/ → digests/week_YYYY-WW.md → telegram link
```

### 3.3 Cache boundaries summary

| Cache | Key | Invalidation | Purpose |
|---|---|---|---|
| ContextPack | sha256(SceneRequest + retriever_index_fingerprints + voice_pin) | Any retriever reindex; voice pin change | Don't re-query retrievers across regen attempts |
| DraftResponse (Mode A) | sha256(ContextPack + prior_scenes + generation_config + prompt_template) | Any ContextPack change; voice pin change; prompt change | Ablation harness re-runs — if nothing changed, return cached |
| CriticResponse | sha256(scene_text + ContextPack + rubric_id) | Rubric change; context change | Same scene text critiqued twice → cached |
| Entity cards | sha256(canon/chapter_NN.md) | Chapter re-commit (rare) | Re-extraction only on canon changes |
| RAG retrievals | (query, index_fingerprint) | Index rebuild | Downstream of retriever, handled inside retriever |

**Design rule:** every cache is keyed by a *content hash*, never a wall-clock timestamp. This makes caches fully deterministic, safe to delete, and debuggable.

### 3.4 Retry boundaries summary

| Boundary | Who retries | Strategy | Escalation |
|---|---|---|---|
| Retriever call | Retriever impl | 3x exponential backoff | Mark scene HARD_BLOCKED if persistent |
| Drafter (Mode A local vLLM) | Drafter impl wrapped in `tenacity` | 3x, 1s/2s/4s | HARD_BLOCKED with "mode_a_unavailable" — no auto-Mode-B on infra failure |
| Drafter (Mode B Anthropic) | Drafter impl wrapped in `tenacity` | 5x on 5xx/rate-limit, exponential | HARD_BLOCKED with "budget_exhausted" on 4xx billing errors |
| Critic (Anthropic) | Critic impl wrapped in `tenacity` | 5x, exponential | HARD_BLOCKED on persistent 4xx |
| Regen loop (logical, not transport) | Orchestrator state machine | Up to R attempts (configured per chapter), default 3 | Escalate to Mode B |
| Mode B regen (at critic-fail) | Orchestrator | 1 attempt only | HARD_BLOCKED on fail |
| Chapter-critic fail | Orchestrator | Controller decides: surgical vs full rollback | HARD_BLOCKED if budget/time blown |

---

## 4. State persistence model — what lives where

This is the most important section because **openclaw is cron-driven**. Process state does not survive between cron ticks. Everything mutable MUST be on disk.

### 4.1 Storage taxonomy

| State kind | Storage | Format | Rationale |
|---|---|---|---|
| Committed canon | `canon/chapter_NN.md` | Markdown, git-tracked | Human-readable, version-controlled, the book itself |
| In-flight scene drafts | `drafts/scene_buffer/chapter_NN/scene_NN.*.json` | JSON (draft, critic, regen history) | Structured, inspectable, append-only per attempt |
| In-flight chapter assembly | `drafts/chapter_buffer/chapter_NN.md` | Markdown | Transient; removed when chapter commits |
| Context pack cache | `drafts/context_packs/<hash>.json` | JSON | Content-addressed; cheap to regenerate, worth caching within a run |
| Scene state machine | `drafts/scene_buffer/chapter_NN/scene_NN.state.json` | JSON | The single source of truth for "what's next" per scene |
| RAG indexes | `indexes/<retriever_name>/` | lancedb dir OR pgvector schema | Durable, rebuildable from corpus + canon |
| Entity cards | `entity-state/chapter_NN/<entity>.md` | Markdown with YAML frontmatter | Human-readable AND machine-parseable; diffable in git |
| Event log | `runs/events.jsonl` | JSONL | Append-only, never rewritten; source of truth for observability |
| Metric ledger | `runs/metrics.sqlite` | SQLite | Derived view from events.jsonl, rebuildable |
| Thesis registry | `theses/open/*.md` and `theses/closed/*.md` | Markdown w/ YAML frontmatter | Human-readable, git-tracked, narrative-first |
| Retrospectives | `retrospectives/chapter_NN.md` | Markdown | Same; narrative |
| Weekly digests | `digests/week_YYYY-WW.md` | Markdown | Human surface |
| Configuration | `config/*.yaml` | YAML | Declarative, version-controlled, diff-friendly |
| Voice pin | `config/voice_pin.yaml` | YAML (model path, sha, FT run id, date) | One file; pin upgrades are PR-reviewable |
| Run state (global) | `runs/run_state.json` | JSON | Last-completed scene, last-committed chapter, current budget posture |

### 4.2 Why the split between JSONL, JSON, and SQLite

- **JSONL (`runs/events.jsonl`)** is the append-only immutable truth. Every LLM call emits a line. Never rewritten. Survives any derived-view corruption.
- **JSON per scene/chapter** is mutable-but-append-friendly. Each regen attempt adds a new file with a suffix (`scene_01.critic_1.json`, `scene_01.critic_2.json`), never overwrites. State machine file *is* overwritten, but its history is reconstructable from event log.
- **SQLite (`runs/metrics.sqlite`)** is the queryable derived view — what the weekly digest needs (aggregate Mode-B rates, per-axis score trends, cost-per-chapter). Rebuilt nightly from events.jsonl by a separate ingester job. If it corrupts or schema-drifts, delete and rebuild.
- **Markdown + YAML frontmatter** for entity cards, retrospectives, theses, digests. These are narrative artifacts; humans must be able to read them; git diffs must be meaningful; LLMs should parse the frontmatter for structure. Pure JSON would sabotage the "readable" half.

### 4.3 Durability across crashes

**Crash scenarios and recovery:**

| Scenario | Recovery |
|---|---|
| openclaw gateway restart mid-scene | Next cron tick reads scene state JSON, resumes from last state (e.g., if `state: DRAFTED_A, critic_pending`, re-invokes critic with cached draft) |
| Machine reboot | Same as above — all state is on disk. Nothing lost except an in-flight LLM call (which will be retried on next tick by virtue of the state machine). |
| Corrupted state JSON | Fall back to event log replay: reconstruct state from events.jsonl filtered to that scene_id. Slow but never-lose-canon. |
| Corrupted SQLite metrics ledger | Delete, rebuild from events.jsonl. Only affects digest generation. |
| Corrupted RAG index | Rebuild from `our-lady-of-champion/` (corpus) + `canon/` (entity-state). Deterministic. |
| Corrupted canon | Git-revert. Canon is always in git. |
| Corrupted event log | **This is the unrecoverable case.** Protect with: (a) append-only filesystem semantics, (b) periodic rsync backup to `runs/events.archive/YYYY-MM.jsonl.gz`, (c) weekly checksum file committed to git. |

**Design rule:** Never store state in memory across an openclaw cron tick. Every function at the "orchestrator" layer must be able to be called from scratch with only (a) its input args, (b) disk state.

---

## 5. Orchestration pattern — openclaw cron + Anthropic sync

### 5.1 The architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  DGX Spark — systemd user timer fires openclaw gateway every 15 min │
│     (nightly 02:00 window is the primary production cycle;          │
│      daytime ticks are for hard-block alert delivery + digest gen)  │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  openclaw gateway spawns book-pipeline workspace                    │
│    → invokes `python -m book_pipeline.orchestrator run_cycle`       │
│    → passes budget config (max LLM calls, max wall-time, max spend) │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  run_cycle (single python process, short-lived, batch-style)        │
│    1. Read runs/run_state.json → find next PENDING scene            │
│    2. Read scene state JSON → determine next transition             │
│    3. Execute ONE transition (RAG / draft / critic / regen / commit)│
│       - SYNC call to vLLM (Mode A) or Anthropic (Mode B, critic)    │
│       - Emit event to runs/events.jsonl                             │
│       - Update scene state JSON atomically (tmp + rename)           │
│    4. Loop back to step 2 until: budget exhausted OR scene committed│
│       OR hard-blocked.                                              │
│    5. Update runs/run_state.json with cursor + budget remaining     │
│    6. Exit.                                                         │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Why batch / short-lived, not daemon / long-running

| Daemon-style | Batch-style (chosen) |
|---|---|
| Long-running Python process with async loops | Short Python process per tick, exits cleanly |
| Memory state persists across scenes | All state is on disk, any invocation can resume |
| Complex error handling for partial in-memory state | State-machine-on-disk is the error handler |
| Needs process supervision (systemd service for the pipeline) | openclaw gateway IS the supervisor; we just need cron |
| Hard to reason about crash consequences | Crash = lose at most one in-flight LLM call; state survives |
| Harder to ablation-harness (can't swap configs mid-run) | Trivial to ablation-harness — each invocation reads config fresh |

### 5.3 Anthropic sync calls inside a short-lived process

The critic and Mode-B drafter make synchronous HTTP calls to Anthropic. At ~20-60s per call, with regen loops, a single scene may consume 2-5 minutes of wall-clock. That's fine for a batch process. Key design points:

- **No async / no concurrency inside run_cycle.** One scene at a time, one LLM call at a time. Reproducibility over throughput. If wall-clock becomes a problem, parallelize across scenes (openclaw can spawn multiple workspaces for different chapters), NOT across LLM calls within a scene.
- **Timeout handling:** every Anthropic call wrapped in a hard timeout (e.g., 180s). Timeout = treat as transient failure = retry via `tenacity`.
- **Budget accounting:** track tokens used per run in `runs/run_state.json`. If projected spend exceeds weekly cap, HARD_BLOCK with budget_exhausted and stop spawning new work.

### 5.4 File-based handoff contract

When openclaw spawns a subprocess (e.g., entity extractor as a separate agent), handoff is file-based:

- Input file: `drafts/entity_extractor_queue/<chapter_num>.json` (written by orchestrator after canon commit)
- Working dir: `drafts/entity_extractor_work/<chapter_num>/`
- Output: `entity-state/chapter_NN/*.md` + `drafts/entity_extractor_queue/<chapter_num>.done`
- Failure: `drafts/entity_extractor_queue/<chapter_num>.err` with traceback

Orchestrator on next tick reads `.done` or `.err` to advance state. This pattern is the same for retrospective writer and digest generator.

---

## 6. Build order — smallest viable first version

### 6.1 Dependency DAG of components

```
Configuration loader (config/*.yaml)
     │
     ├──► VoicePinLoader (reads config/voice_pin.yaml, verifies checkpoint exists)
     │
     ├──► EventLogger (append-only JSONL sink)
     │       │
     │       └─► all other components depend on this
     │
     ├──► Retriever implementations (per-retriever, independent)
     │       │
     │       └─► ContextPackBundler (depends on Retriever Protocol)
     │               │
     │               └─► Drafter (Mode A + Mode B)
     │                       │
     │                       └─► Critic (scene + chapter)
     │                               │
     │                               └─► Regenerator (depends on Drafter + Critic)
     │                                       │
     │                                       └─► SceneStateMachine
     │                                               │
     │                                               └─► ChapterAssembler
     │                                                       │
     │                                                       └─► Orchestrator
     │                                                               │
     │                                                               └─► Post-commit fan-out:
     │                                                                      ├─► EntityExtractor
     │                                                                      ├─► RetrospectiveWriter
     │                                                                      ├─► ThesisMatcher
     │                                                                      └─► DigestGenerator
     │
     └──► ObservabilityIngester (events.jsonl → metrics.sqlite, daily cron)
```

### 6.2 Proposed phase structure

**Phase 0 — Foundation (infra + trivial end-to-end smoke)**
- Repo scaffolding, pyproject, venv, config loading
- EventLogger (the one component everything else uses)
- Corpus ingestion (read `our-lady-of-champion/` into memory; just sanity-check parsing)
- Voice pin resolver (resolves `config/voice_pin.yaml` to a concrete FT checkpoint path; *does not yet serve it*)
- openclaw workspace wired: `run_cycle` exists but only prints "hello, next scene would be ch01_sc01"

**Phase 1 — RAG plane (5 retrievers + bundler)**
- Pick pgvector vs lancedb (research + decision in this phase)
- Implement 5 Retriever instances against corpus
- Implement ContextPackBundler
- Ablation: structured retrieval vs monolith retrieval on held-out scene queries — closes thesis 005
- **Smoke end-to-end:** orchestrator can print a ContextPack for ch01_sc01

**Phase 2 — Mode A drafter + scene critic (the core loop)**
- Serve voice-FT checkpoint via vLLM (reuse patterns from paul-thinkpiece-pipeline)
- Implement Drafter Mode A
- Implement scene Critic (Anthropic Opus)
- Implement SceneStateMachine
- Implement Regenerator with max_attempts=1 (regen budget of 1 is the smallest non-trivial value; R=3 comes later)
- **End-to-end:** ch01_sc01 → ContextPack → draft → critic → pass-OR-regen-once → final draft on disk
- Drafts are NOT yet assembled into chapters. This phase ends when one scene completes the per-scene flow.

**Phase 3 — Chapter assembly + commit + post-commit fan-out**
- ChapterAssembler (deterministic first, add Opus smoother only if needed)
- Chapter Critic
- Atomic commit to canon/
- EntityExtractor (basic — cards per named entity)
- RetrospectiveWriter
- RAG reindex trigger
- **End-to-end:** ch01_sc01 through ch01_sc03 (whatever the chapter has) commit to canon/chapter_01.md + entity-state/chapter_01/ + retrospectives/chapter_01.md

**Phase 4 — Mode B escape hatch + regen budget + hard-block alerting**
- Mode B Drafter (Anthropic frontier)
- Regen budget R configurable per chapter, escalation to Mode B
- HARD_BLOCKED state paths
- Telegram alert integration (reuse existing channel)
- **End-to-end:** force a scene to fail critic repeatedly, observe escalation to Mode B commit with mode=B tag. Force Mode B to fail, observe HARD_BLOCK + Telegram alert.

**Phase 5 — Testbed plane (theses, ablations, digest)**
- Thesis registry format + matcher
- Ablation harness (run N scenes under variant A vs variant B, diff the results)
- Observability ingester (events.jsonl → metrics.sqlite)
- DigestGenerator (weekly)
- **End-to-end:** produce a first weekly digest with real data.

**Phase 6 — Production hardening + first full draft**
- Whatever pitfalls from PITFALLS.md surface
- Multi-chapter runs
- Drive toward FIRST-DRAFT requirement (27 chapters in canon)

### 6.3 Smallest viable first version (Phase 2 end state)

The minimum useful "vertical slice" — Phase 0 + 1 + 2 — produces:
- One scene (ch01_sc01) drafted by voice-FT model with 5-typed-RAG context
- Critiqued by Opus against the 5-axis rubric
- One regen attempt if it fails
- Final scene text + critic report + all events logged to disk

**What's missing** from the slice: chapter assembly, canon commit, Mode B, testbed plane. **What's present**: every component interface from §2, fully exercised. That's the point — if the interfaces are wrong, we find out at Phase 2, not Phase 6.

**Stub strategy** for Phase 2: components not yet implemented (ChapterAssembler, EntityExtractor, etc.) are **stubbed Protocols** that log a "would run here" event and return a trivial value. This lets the orchestrator state machine exercise the full flow without errors, and we add real implementations in later phases without touching the orchestrator.

---

## 7. Kernel-extraction-friendliness (ADR-004 hygiene)

Every design decision above is made with the understanding that **pipeline #2 (blog)** will arrive and force extraction of a generic writing-pipeline kernel. We don't build the kernel now, but we design so that extracting it is mechanical, not archaeological.

### 7.1 What extracts cleanly (kernel candidates)

| Component | Book-specific assumption embedded? | Extraction notes |
|---|---|---|
| Retriever Protocol | None | Pure interface; different retrievers per pipeline. Kernel takes the Protocol, pipelines supply concrete retrievers. |
| ContextPackBundler | Byte cap and assembly strategies are config — no book-specific logic | Clean extract. |
| Drafter Protocol | None — Mode A/B is a controller concern, drafter just drafts | Clean extract. |
| Critic Protocol | Rubric is per-pipeline YAML — structure is generic | Clean extract. Rubric config travels with the instance, not the kernel. |
| Regenerator Protocol | None | Clean extract. |
| SceneStateMachine | **Book-specific terminology** ("scene", "chapter") | Rename at extraction to `UnitStateMachine` with configurable `generation_unit` and `commit_unit` labels. Low effort. |
| ChapterAssembler | **Book-specific name** | Rename to `CommitUnitAssembler`. Blog pipeline might have a 1:1 scene:post mapping with a trivial assembler. |
| EntityExtractor | **Book-specific** (entities make less sense in blog) | Keep in `book_ext/`, not in kernel. Blog pipeline won't import this. |
| RetrospectiveWriter | Generic (every pipeline wants retrospectives) | Clean extract. |
| ThesisMatcher | Generic | Clean extract. |
| EventLogger | Generic | Clean extract. |
| Orchestrator `run_cycle` pattern | Generic (cron tick → advance state machine → exit) | Clean extract. |
| DigestGenerator | Generic structure, per-pipeline content | Kernel provides skeleton; pipelines customize content templates. |

### 7.2 What stays book-specific (lives in `book_ext/` at extraction time)

- `EntityExtractor` + `EntityCard` schema (entity-state is a novel concept — blog pipeline has no "cast of characters")
- 5-axis rubric content (kernel defines N-axis rubric *structure*, book defines the 5)
- The 5 typed retrievers' names and query shapes (kernel defines retriever Protocol, book defines the 5)
- `config/voice_pin.yaml` schema (generic — voice pinning is universal for "uses an FT model")
- Chapter-based outline parser (blog uses different outline format)
- Hard-block taxonomy (book-specific hard-block types; blog will have its own)

### 7.3 Extraction readiness checklist (to run at end of each phase per ADR-004)

At each phase boundary:
- [ ] Every LLM-calling component has a declared Protocol in `book_pipeline/interfaces/`
- [ ] Every Protocol's dependencies are themselves Protocols or stdlib types (no concrete class leakage)
- [ ] No component imports from another component's concrete module — imports Protocols only
- [ ] Config separates generic (byte caps, retry counts) from book-specific (rubric axes, retriever names)
- [ ] Book-specific helpers live in `book_pipeline/book_specific/` (would move to `book_ext/` at extraction)

---

## 8. Voice-pin contract — interface with paul-thinkpiece-pipeline

The book pipeline **consumes** FT checkpoints produced by `paul-thinkpiece-pipeline`. This is a one-way dependency. Voice-pinning is the formal contract.

### 8.1 The pin file

`config/voice_pin.yaml`:

```yaml
voice_pin:
  source_repo: paul-thinkpiece-pipeline
  source_commit_sha: <40-char sha from that repo>
  ft_run_id: "v6_qwen3_32b"                   # matches paul-thinkpiece-pipeline/train_v6_qwen3_32b.sh
  checkpoint_path: "~/paul-thinkpiece-pipeline/v6_data/output/paul-merged-v6-qwen3-32b"
  checkpoint_sha: <sha256 of merged weights directory tree>
  base_model: "Qwen/Qwen3-32B"
  trained_on_date: "2026-04-14"
  pinned_on_date: "2026-04-21"
  pinned_reason: "Best voice fidelity on eval/blog_comparison as of 2026-04-20; strong register transfer."
  vllm_serve_config:
    port: 8001
    max_model_len: 4096
    dtype: bfloat16
    tensor_parallel_size: 1
```

### 8.2 Pin invariants enforced at load time

- `checkpoint_path` exists and is readable
- `checkpoint_sha` matches computed sha of files (fails fast if the underlying checkpoint has been modified — upgrades must be deliberate)
- vLLM can serve it (smoke test on first load per run_cycle, short timeout)
- `source_commit_sha` is resolvable in paul-thinkpiece-pipeline git history (for reproducibility)

### 8.3 Pin upgrade protocol

Upgrading a pin is a **deliberate, PR-reviewable event**:

1. New FT run completes in paul-thinkpiece-pipeline with eval scores.
2. Paul (or a benchmark script) compares new checkpoint against current pin on held-out scenes.
3. If new checkpoint wins: edit `config/voice_pin.yaml`, commit to book-pipeline repo with a message citing eval scores + rationale.
4. Next openclaw cron tick picks up new pin, invalidates ContextPack / Draft caches, resumes.

**Anti-pattern:** silently pointing `checkpoint_path` at `latest/` symlink. The pin SHA is load-bearing for reproducibility of events.jsonl across the draft run.

### 8.4 Telemetry back to paul-thinkpiece-pipeline

Per ADR-003, thesis closures become inputs to the next FT run. Mechanism:

- Every committed scene's `meta.json` records `voice_pin_sha` + Mode A/B tag + per-axis critic score
- Retrospectives surface voice-specific failure modes ("model can't stage apex-scale action")
- Digest aggregates Mode-B rate over time — rising rate = voice model losing ground
- When a thesis closes with a voice-relevant lesson (e.g., "voice model consistently fails on dialogue-heavy scenes"), a structured note lands in `theses/closed/<id>.md` with tag `feeds:paul-thinkpiece-pipeline`
- Weekly digest surfaces closed theses with that tag, prompting Paul to fold the lesson into the next FT dataset curation cycle

No reverse API dependency. paul-thinkpiece-pipeline doesn't "read" anything from book-pipeline — Paul does.

### 8.5 Future pipelines (blog, thinkpiece, short-story)

When pipeline #2 (blog) arrives, it uses the **same voice-pin schema**. The kernel's `VoicePinLoader` is pipeline-agnostic. Blog pipeline may pin a different checkpoint (e.g., thinkpiece-optimized) or the same one as book pipeline. The pin file is a per-instance config, not a per-kernel concern.

---

## 9. Anti-patterns to avoid (pipeline-specific)

### 9.1 Mixing orchestrator state with LLM calls
**What people do:** Orchestrator "just holds" some context in memory between calls.
**Why wrong:** In a cron-tick architecture, in-memory state is lost every 15 minutes. Inevitably causes silent state loss and "why did regen #2 not know about regen #1's feedback?" debugging.
**Do instead:** Every LLM call result written to disk IMMEDIATELY. Orchestrator reads from disk on every tick.

### 9.2 Coupling the drafter to the critic
**What people do:** Drafter returns a struct that includes critic-readable metadata mixed in with draft text.
**Why wrong:** Critic becomes hard to swap. Regenerator becomes hard to test in isolation.
**Do instead:** Drafter produces `DraftResponse`; Critic takes `scene_text` + `ContextPack` and re-reads the *same* context pack. Keeps them orthogonal.

### 9.3 Framework lock-in (LangGraph, CrewAI, etc.)
**What people do:** "Let's build on LangGraph so we get checkpointing for free."
**Why wrong:** LangGraph's checkpointing model assumes a persistent graph runtime; our model assumes cron-tick short-lived processes. Impedance mismatch creates bugs at the seams. More importantly, kernel-extraction plans (ADR-004) become hostage to LangGraph API stability.
**Do instead:** Steal the *ideas* (state graph, checkpointer), implement with plain Python + JSON-on-disk. ~200 lines for state machine + persistence; that's cheaper than the integration cost.

### 9.4 Over-abstracting before pipeline #2 exists
**What people do:** "Since we know blog pipeline is coming, let's build the kernel now with book-pipeline as the first instance."
**Why wrong:** ADR-004 explicitly rejects this. Abstractions designed against one caller encode that caller's assumptions as universal.
**Do instead:** Clean Protocols + clean module layout. Extract when pipeline #2 arrives.

### 9.5 Silent Mode-B fallback
**What people do:** On Mode A failure, silently retry in Mode B without logging the escalation.
**Why wrong:** Mode-B rate is first-class metric (ADR-001). Silent escalation destroys that signal.
**Do instead:** Every Mode-B escape emits a structured event with rationale ("regen_budget_exceeded" vs "preflagged_beat" vs "mode_a_unavailable"). Digest aggregates.

### 9.6 RAG index as stateful singleton
**What people do:** RAG service is a long-running process, indexes are in memory.
**Why wrong:** In cron-tick world, loading pgvector/lancedb per invocation is fine for 5 small indexes; the "long-running RAG service" is a complication without a benefit.
**Do instead:** Retrievers load their indexes on construction (cheap for lancedb; trivial for pgvector — just a connection). Per-tick orchestrator instantiates Retrievers freshly. Zero state between ticks.

### 9.7 Entity extraction before commit
**What people do:** Run entity extractor during the drafting loop.
**Why wrong:** Entity state should reflect *committed* canon, not drafts. Otherwise a rejected scene's entity changes pollute the state for the next regen.
**Do instead:** Entity extraction is strictly post-commit. Drafts use the most recent committed chapter's entity cards.

### 9.8 Async/concurrent everywhere
**What people do:** Make every LLM call async for "throughput."
**Why wrong:** This pipeline's bottleneck is NOT LLM call concurrency within a scene. Each scene is linearly dependent (draft → critic → regen). Concurrency across scenes is possible but adds state-management complexity.
**Do instead:** Sync calls inside a cron tick. If throughput matters, parallelize at the openclaw-workspace level (spawn two workspaces, one per active chapter). Almost certainly not needed for v1.

---

## 10. Integration points summary

### 10.1 External services

| Service | Integration pattern | Notes |
|---|---|---|
| Anthropic API | Anthropic Python SDK + `tenacity` retry + sync HTTP | All critic/frontier-drafter/extractor/retrospective calls. Rate limits: batch across scenes, not within. |
| vLLM (local) | OpenAI-compatible HTTP, model on port 8001 | Follows paul-thinkpiece-pipeline pattern. Check health on orchestrator start. |
| openclaw gateway | systemd --user, cron config in `.openclaw/workspace.yaml` | Already running; matches wipe-haus-state pattern. |
| Telegram | Existing alert channel; simple HTTPS POST | For HARD_BLOCK alerts only. Digest notifications: link to digest file path. |
| git | Standard CLI invocation from Python on canon commit | Commit message includes chapter_num, mode_tag, per-axis critic pass summary. |

### 10.2 Internal boundaries

| Boundary | Communication | Durability |
|---|---|---|
| Orchestrator ↔ Retrievers | Direct call, in-process | Indexes on disk, retriever is stateless facade |
| Orchestrator ↔ Drafter | Direct call, in-process | Draft result immediately persisted to JSON |
| Orchestrator ↔ Critic | Direct call → Anthropic API | Critic result immediately persisted to JSON |
| Orchestrator ↔ State machine | Read/write JSON on disk | JSON is the state machine |
| Orchestrator ↔ EntityExtractor | File-queue pattern (§5.4) | Queued work is resumable across ticks |
| Orchestrator ↔ RetrospectiveWriter | File-queue pattern | Same |
| EventLogger ↔ everything | Direct call (synchronous append) | fsync on emit — durability over throughput |
| metrics.sqlite ← events.jsonl | Separate nightly ingest job | SQLite is disposable; JSONL is truth |
| book-pipeline → paul-thinkpiece-pipeline | Checkpoint file read via `config/voice_pin.yaml` | One-way; pipeline #2 of family has reverse telemetry via theses |

---

## 11. Summary for roadmap consumer

**Key takeaways for phase structure:**

1. **Phase 0** is foundation (repo, config loader, event logger, voice pin loader, openclaw wiring). Trivially small, enables everything else.
2. **Phase 1** is the RAG plane — 5 retrievers + bundler. Independent of drafter/critic. Good first real deliverable.
3. **Phase 2** is the core drafting loop minus escape hatch — Mode A drafter + scene critic + single regen. This is the "smallest viable first version" that exercises every component interface.
4. **Phase 3** adds chapter-level assembly + commit + post-commit fan-out (entity extractor, retrospective writer). Now the pipeline produces canon.
5. **Phase 4** adds Mode B escape hatch + hard-block alerting. Makes the pipeline autonomous (can handle failures without waking Paul up).
6. **Phase 5** adds the testbed plane (theses, ablations, digest, metrics ledger). Makes the pipeline self-documenting.
7. **Phase 6** is production hardening + driving toward first full draft (27 chapters).

**Phase ordering rationale:** RAG before drafter (drafter needs context), drafter before critic (critic needs drafts), critic before regen (regen consumes critic issues), scene flow before chapter flow (chapter is built from scenes), scene flow before Mode B (Mode B is an escape from Mode A, not a primary path), core loop before testbed (testbed observes the loop).

**Research flags for phases:**
- **Phase 1**: Needs deeper research on pgvector vs lancedb; also whether to adopt LlamaIndex ingestion utilities.
- **Phase 2**: Needs decision on critic rubric format (per-axis prompt templates vs single prompt with JSON-schema output).
- **Phase 4**: Needs Anthropic budget-modeling (projected token spend per Mode-B escape at Q1 2026 Opus pricing).
- **Phase 5**: Ablation harness design is nontrivial — may need its own mini research.

**Most important single design decision:** All mutable state lives on disk. Orchestrator is a short-lived batch process. This is load-bearing for every other design choice (no long-running RAG service, no in-memory pipeline state, no async orchestration, no framework lock-in).

---

## Sources

**Primary (authoritative — project context):**
- `/home/admin/Source/our-lady-book-pipeline/docs/ARCHITECTURE.md` — existing 5 diagrams and components table
- `/home/admin/Source/our-lady-book-pipeline/docs/ADRs/001-mode-dial-over-promotion-ladder.md`
- `/home/admin/Source/our-lady-book-pipeline/docs/ADRs/002-scene-gen-chapter-commit.md`
- `/home/admin/Source/our-lady-book-pipeline/docs/ADRs/003-testbed-framing.md`
- `/home/admin/Source/our-lady-book-pipeline/docs/ADRs/004-book-first-extract-kernel-later.md`
- `/home/admin/Source/our-lady-book-pipeline/.planning/PROJECT.md`
- `/home/admin/paul-thinkpiece-pipeline/README.md` — sibling pipeline structure and FT model failure modes

**Secondary (framework / pattern research, MEDIUM confidence — WebSearch-sourced, not independently verified in Context7):**
- [Best AI Agent Frameworks 2025: LangGraph / DSPy / CrewAI / Agno](https://langwatch.ai/blog/best-ai-agent-frameworks-in-2025-comparing-langgraph-dspy-crewai-agno-and-more)
- [CrewAI vs LangGraph vs AutoGen vs OpenAgents (2026)](https://openagents.org/blog/posts/2026-02-23-open-source-ai-agent-frameworks-compared)
- [Best Multi-Agent Frameworks in 2026](https://gurusup.com/blog/best-multi-agent-frameworks-2026)
- [LangGraph: Agent Orchestration Framework for Reliable AI Agents](https://www.langchain.com/langgraph)
- [LangGraph workflows and agents docs](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [Mastering LangGraph State Management in 2025](https://sparkco.ai/blog/mastering-langgraph-state-management-in-2025)
- [DSPy Use Cases: Build Optimized LLM Pipelines (DigitalOcean)](https://www.digitalocean.com/community/conceptual-articles/dspy-use-cases-optimized-llm-pipelines)
- [Haystack vs LlamaIndex (ZenML)](https://www.zenml.io/blog/haystack-vs-llamaindex)
- [RAG Frameworks: LangChain vs LangGraph vs LlamaIndex](https://aimultiple.com/rag-frameworks)
- [Best LLM Frameworks 2026](https://pecollective.com/tools/best-llm-frameworks/)
- [9 Best LLM Orchestration Frameworks (ZenML)](https://www.zenml.io/blog/best-llm-orchestration-frameworks)
- [Durable Workflow Platforms for AI Agents (Render)](https://render.com/articles/durable-workflow-platforms-ai-agents-llm-workloads)
- [Orchestrating Multi-Step Agents: Temporal/Dagster/LangGraph Patterns (Kinde)](https://www.kinde.com/learn/ai-for-software-engineering/ai-devops/orchestrating-multi-step-agents-temporal-dagster-langgraph-patterns-for-long-running-work/)
- [pgvector vs LanceDB (Zilliz)](https://zilliz.com/comparison/pgvector-vs-lancedb)
- [Vector Database Comparison 2026 (4xxi)](https://4xxi.com/articles/vector-database-comparison/)

**Secondary (Python interface patterns, HIGH confidence — official docs):**
- [PEP 544 — Protocols: Structural subtyping](https://peps.python.org/pep-0544/)
- [Protocols and structural subtyping (typing docs)](https://typing.python.org/en/latest/reference/protocols.html)
- [Python Protocols: Leveraging Structural Subtyping (Real Python)](https://realpython.com/python-protocol/)

**Secondary (event sourcing + SQLite patterns, MEDIUM confidence):**
- [eventsourcing Python library](https://eventsourcing.readthedocs.io/)
- [eventsourcing on PyPI](https://pypi.org/project/eventsourcing/)

**Related pattern references:**
- [Self-Improving LLM Architectures — Reflexion pattern (Rohan Paul)](https://www.rohan-paul.com/p/self-improving-llm-architectures)
- [Karpathy's LLM Knowledge Base architecture (VentureBeat)](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an)

---
*Architecture research for: autonomous LLM-based long-form creative-writing pipeline*
*Researched: 2026-04-21*
