# Phase 7: Narrative Physics Engine — Implementation Research

**Researched:** 2026-04-25
**Domain:** Pydantic schema engineering · LanceDB additive-column extension · pre-flight gate composition · 13-axis critic prompt extension · BGE-M3 embedding cache · regex safety · physics kernel package
**Confidence:** HIGH on infrastructure (existing kernel + library versions in repo); MEDIUM-HIGH on schema container choice; MEDIUM on critic split-vs-single tradeoff; HIGH on threat model (precedent in Plan 02-05).
**Companion:** `07-NARRATIVE_PHYSICS.md` — narratology synthesis (Tier 1 + Tier 2). Read alongside.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

(Verbatim from `07-CONTEXT.md` D-01 through D-28; the planner is bound by every one of these.)

- **D-01: Narrative Physics metaphor is the architectural commitment.** Every scene declares its properties up-front; gates enforce them at draft time AND at critic time AND at chapter-assembly time. Drift = constraint violation = engine refuses to advance.
- **D-02: Character motivation is the load-bearing axis. Always center.** Every scene's metadata MUST declare each present character's active motivation. The drafter prompt includes motivation as a top-of-prompt anchor; the critic has a rubric axis whose sole job is "did the scene serve declared motivation".
- **D-03: Codified Scene Metadata Schema** — mandatory fields: contents, characters_present, motivation, voice, perspective, treatment.
- **D-04: Theater of the mind.** Metadata schema = playbook for the constructed mental theater.
- **D-05: Full autonomous.** No new human-in-the-loop steps.
- **D-06: Heavy research is required before plan.** Storytelling atomics sourced from craft canon → mapped to Pydantic models.
- **D-07: Existing primitives are the substrate.** Phase 7 EXTENDS drafter/critic/DAG/regenerator/bundler with metadata-aware gates; does NOT rewrite.
- **D-08 / D-08a: SUPERSEDED by D-21.** ch01-04 frozen baseline (read-only); manual_concat retired.
- **D-09: Canon-bible continuity layer** composing CB-01 + entity_state + retrospectives into queryable `CanonBibleView`.
- **D-10: Scene-buffer dedup.** Surface declared metadata (not full text) for prior scenes; full prior-scene text only on explicit callback.
- **D-11: Drafter/critic gates as first-class artifacts** living in `book_pipeline.physics.gates.*`. Each gate emits `role='physics_gate'` Events on every check (pass + fail) per OBS-01.
- **D-12: SUPERSEDED by D-21.**
- **D-13: Tighter beat boundaries per scene.** Schema fields `owns:` and `do_not_renarrate:`. Critic axis `content_ownership_breach`.
- **D-14: Scene-buffer dedup with similarity threshold.** ≥80% similar (BGE-M3 cosine) → reject + scene-kick. Threshold tunable in `config/mode_thresholds.yaml`.
- **D-15: Continuity-bible retriever (CB-01).** Named-quantity continuity. Critic axis `named_quantity_drift`.
- **D-16: Per-character-per-chapter POV mode in metadata.** `pov_lock` per-character; `<character> = <pov_mode>` for the lifetime of the book unless explicitly overridden in stub frontmatter with rationale.
- **D-17: Stub-leak-into-canon detection.** Black-and-white pattern check (regex on `Establish:`, `Resolve:`, `Set up:`, `[character intro]:`).
- **D-18: Quote-extraction robustness.** Defensive normalizer for `., ` corruption.
- **D-19: Degenerate-loop detector** before commit (n-gram repetition or sentence-embedding self-similarity).
- **D-20: Research output is `NARRATIVE_PHYSICS.md`** in addition to standard `07-RESEARCH.md`.
- **D-21: Forward-only scope.** ch15-27 + ch09 retry are the target. ch01-14 are historical artifacts; ch01-04 read-only smoke baseline. Phase 7 acceptance = engine ships clean + ch15+ generation passes all gates clean.
- **D-22: CB-01 as 6th RAG axis.** New retriever `src/book_pipeline/rag/retrievers/continuity_bible.py`; new lance_schema rule_type `'canonical_quantity'` (additive nullable per D-11 contract from Plan 05-03). Existing 5 retrievers untouched. Conflict_detector gains `named_quantity_drift` dimension.
- **D-23: Canonical quantities inject verbatim into drafter prompt header.** Top-of-prompt block stamps canonical values: `CANONICAL: Andrés age=23, La Niña=55ft, Cholula=Oct 18 1519`.
- **D-24: Physics gates fire at drafter pre-flight ONLY** (no separate commit-time hook). Two enforcement points total: pre-flight (cheap, before any model call) + critic-time rubric axes (after expensive draft).
- **D-25: New `book_pipeline.physics` kernel package** (joins drafter / critic / regenerator / chapter_assembler / rag / observability / alerts as 7th kernel pkg per ADR-004). Layout: `physics/schema.py`, `physics/canon_bible.py`, `physics/gates/__init__.py`, `physics/gates/{pov_lock,motivation,ownership,treatment,quantity}.py`, `physics/locks.py`. import-linter contract extension.
- **D-26: Critic absorbs all post-draft physics checks as new rubric axes.** 5 → 13 axes: `pov_fidelity`, `motivation_fidelity`, `treatment_fidelity`, `content_ownership`, `named_quantity_drift`, `stub_leak`, `repetition_loop`, `scene_buffer_similarity`.
- **D-27: Stub-leak severity = hard reject + scene-kick.** Black-and-white regex; not a soft warn, not auto-strip.
- **D-28: Similarity-dedup method = BGE-M3 cosine ≥ 0.80.** Reuse existing `book_pipeline.rag.embedding.BgeM3Embedder`. Cosine between candidate scene embedding and each prior committed scene embedding. ≥ 0.80 = recap → critic axis FAIL → scene-kick.

### Claude's Discretion

- **Schema container shape** — YAML frontmatter (existing pattern) vs JSON sidecar vs both. (RESEARCH §1 recommends extend YAML frontmatter.)
- **POV-lock storage location** — `config/pov_locks.yaml` vs `entity-state/` vs `physics/locks.yaml`. (RESEARCH §8 recommends `config/pov_locks.yaml`.)
- **Treatment vocabulary** — closed enum vs open string vs hybrid. (NARRATIVE_PHYSICS.md §4 recommends closed enum, 10 values.)
- **Beat-function overlap semantics** — strict partition vs declared `shares_with`. (RESEARCH §5 + NARRATIVE_PHYSICS.md §5 recommend strict partition with `do_not_renarrate` + `callback_allowed` exception list.)
- **Motivation-axis critic weight** — equal weight vs hard-stop. (NARRATIVE_PHYSICS.md §2.4 recommends hard-stop per D-02 "load-bearing".)
- **Stub-leak regex pattern set** — exact list. (RESEARCH §6 supplies the canonical set.)
- **Degenerate-loop detection method** — n-gram vs BGE self-sim vs both. (RESEARCH §7 recommends n-gram first; BGE self-sim deferred to v1.1.)
- **Quote-extraction robustness placement (D-18)** — separate axis vs assembler normalizer vs both. (RESEARCH §9 recommends both — pre-commit normalizer + lightweight critic axis.)
- **NARRATIVE_PHYSICS.md depth** — comprehensive vs targeted brief vs two-tier. (Researcher chose two-tier per CONTEXT default.)
- **Plan rollout order** — schema-first vs gate-first vs CB-01-first. (RESEARCH §11 recommends schema → CB-01 → pre-flight gates → critic axes → integration test.)
- **Engine validation against ch01-04 frozen baseline** — Phase 7 gate vs deferred. (RESEARCH §10 recommends Phase 7 gate; cheap because no commits.)

### Deferred Ideas (OUT OF SCOPE)

- Web/GUI dashboard for canon-bible inspection (V2, REVIEW-01).
- Auto-generated story-bible PDFs.
- Cross-book physics (multi-novel canon).
- ML-learned atomics (v1 uses craft-derived only; learned variants are v2 thesis).
- Real-time visualization of physics state (telemetry only via events.jsonl).

</user_constraints>

<phase_requirements>
## Phase Requirements (proposed 07-NN scoped REQ-IDs)

Phase 7 has no pre-assigned REQ-IDs in `REQUIREMENTS.md`. The following IDs are proposed for the planner to formalize during plan-phase. They map 1:1 to the engine's enforcement surfaces.

| Proposed ID | Description | Research support |
|---|---|---|
| **PHYSICS-01** | Pydantic `SceneMetadata` model implements all D-03 mandatory fields + D-13 ownership fields + D-04 staging fields. Strict validation (`extra="forbid"`); enforced via `pydantic.ValidationError` at stub load time. | RESEARCH §1, §3 |
| **PHYSICS-02** | `pov_lock` artifact (file location TBD planner; recommended `config/pov_locks.yaml`) loads + validates against scene `perspective` at drafter pre-flight. Override path: stub frontmatter `pov_lock_override: <rationale>`. | RESEARCH §8; NARRATIVE_PHYSICS.md §1 |
| **PHYSICS-03** | `book_pipeline.physics` kernel package landed: `schema.py`, `canon_bible.py`, `gates/__init__.py`, `gates/{pov_lock,motivation,ownership,treatment,quantity}.py`, `locks.py`. import-linter contract extended in BOTH source_modules and forbidden_modules. | RESEARCH §3, §11 |
| **PHYSICS-04** | CB-01 retriever (`book_pipeline.rag.retrievers.continuity_bible.ContinuityBibleRetriever`) lands as 6th retriever. Lance schema rule_type `'canonical_quantity'`. Bundler emits 7 events per call (was 6). Conflict_detector gains `named_quantity_drift` dimension. Existing 5 retrievers untouched. | RESEARCH §2 |
| **PHYSICS-05** | Drafter pre-flight composition: pov_lock + motivation + ownership + treatment + quantity gates run BEFORE any vLLM call. Each gate emits one `role='physics_gate'` Event (pass+fail). Pattern matches existing `drafter.memorization_gate` + `drafter.preflag`. | RESEARCH §3 |
| **PHYSICS-06** | Drafter prompt template extended: D-23 verbatim canonical-quantity stamp at top-of-prompt; D-13 ownership anchor block fenced (e.g., `<beat>...</beat>`) so directive can't smear into prose. | RESEARCH §1, §6 |
| **PHYSICS-07** | Critic prompt + structured-output schema extends from 5 → 13 axes (D-26). Token cost analyzed and within Anthropic 1h prompt-cache budget. | RESEARCH §4 |
| **PHYSICS-08** | `stub_leak` axis is regex pre-check that short-circuits to FAIL before LLM critic call. Pattern set in `physics/stub_leak.py`. | RESEARCH §6 |
| **PHYSICS-09** | `repetition_loop` axis: n-gram repetition + line-level dup detection runs pre-critic. Threshold tunable in `config/mode_thresholds.yaml`. | RESEARCH §7 |
| **PHYSICS-10** | `scene_buffer_similarity` axis: BGE-M3 cosine ≥0.80 vs prior committed scenes' embeddings. Embedding cache lives at `.planning/intel/scene_embeddings.sqlite` (or planner-chosen alt). | RESEARCH §5 |
| **PHYSICS-11** | Quote-corruption `., ` defensive normalizer in `chapter_assembler/concat.py` PLUS lightweight critic axis (deferred from §13 list as v1.1 — covered by content_ownership at v1). | RESEARCH §9 |
| **PHYSICS-12** | ch15+ first-flight smoke: ch15 sc02 resume passes all 13 axes (or scene-kicks recover deterministically). ch01-04 read-only smoke: engine flags zero false positives on the 4 frozen-baseline chapters. | RESEARCH §10 |
| **PHYSICS-13** | `motivation_fidelity` FAIL is hard-stop (overall_pass=False unconditionally) per D-02 load-bearing semantics. | NARRATIVE_PHYSICS.md §2.4 |

</phase_requirements>

## Summary

Phase 7 is a **kernel-package addition + RAG-axis extension + critic-prompt extension** that codifies storytelling atomics from the craft canon into enforceable Pydantic schemas, deterministic pre-flight gates, and Anthropic-judged critic axes. The engine implements 13 enforcement surfaces, replacing the existing 5-axis critic with a 13-axis variant and adding a 7-file `book_pipeline.physics` kernel package.

The infrastructure is well-prepared: the alerts kernel package (Plan 05-03) is a precedent for adding `book_pipeline.physics` to the import-linter contracts; the additive-nullable column policy on the LanceDB schema (D-11 contract from Plan 05-03's `source_chapter_sha` work) is the precedent for adding `rule_type='canonical_quantity'` rows; the `drafter.memorization_gate` + `drafter.preflag` modules are the in-house references for the new pre-flight gate file pattern. The critical engineering risks are (a) critic prompt-cost growth from 5 → 13 axes (mitigated by Anthropic 1h ephemeral cache + structured-output schema), (b) BGE-M3 cosine cost on every scene critic-time (one extra embedder call per scene; embedder is already loaded for OBS-03 — marginal cost), (c) regex DoS surface on the stub-leak detector (mitigated by anchored, non-nested patterns).

**Primary recommendation:** Schema-first plan rollout. Land `physics/schema.py` + Pydantic SceneMetadata + new YAML frontmatter shape under feature flag in Plan 07-01. Land CB-01 retriever in Plan 07-02 (forward-compatible — empty index until populated). Land pre-flight gates + drafter prompt extensions in Plan 07-03. Land critic 13-axis extension + stub-leak regex + repetition-loop detector in Plan 07-04. Land scene-buffer dedup + ch15 integration test in Plan 07-05. ch01-04 read-only smoke validation rolls into Plan 07-04's acceptance.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Scene metadata schema (Pydantic) | `book_pipeline.physics` (NEW) | `book_pipeline.interfaces.types` | Domain-shaped types live in physics; Protocol-flowing types stay in interfaces |
| POV lock storage | `config/` (yaml) | `book_pipeline.physics.locks` (loader) | Static invariant lock; precedent: `config/voice_pin.yaml`, `config/mode_preflags.yaml` |
| Pre-flight gate execution | `book_pipeline.physics.gates` | `book_pipeline.drafter.mode_a` (composition site) | Gates are kernel; drafter composes. Same pattern as `memorization_gate`. |
| Canonical-quantity retrieval | `book_pipeline.rag.retrievers.continuity_bible` (NEW 6th) | `book_pipeline.physics.canon_bible` (higher-order view) | Retriever is RAG-shaped; CanonBibleView is a domain composition over retriever + entity_state + retrospectives |
| Drafter prompt header (D-23 stamp) | `book_pipeline.drafter.mode_a` | `book_pipeline.physics.canon_bible` (data source) | Prompt assembly stays in drafter; physics provides the data |
| Critic 13-axis extension | `book_pipeline.critic.scene` (extend `system.j2` + `CriticResponse` schema) | `book_pipeline.physics.stub_leak` (regex pre-check), `book_pipeline.physics.repetition_loop` (n-gram check), `book_pipeline.rag.embedding` (cosine dep) | Critic owns prompt + structured output; physics provides deterministic axis pre-checks short-circuit-able before LLM |
| Scene-buffer similarity | `book_pipeline.physics` + `book_pipeline.rag.embedding` (BGE-M3 reuse) | embedding cache (sqlite under `.planning/intel/`) | New axis, reuses existing embedder. Cache is a v1 pragma. |
| Stub-leak detection | `book_pipeline.physics.stub_leak` (regex set) | `book_pipeline.critic.scene` (consumer) | Pure-function regex module |
| Quote-corruption normalizer | `book_pipeline.chapter_assembler.concat` (extend) | (no new package) | Pre-commit defensive parse; not a critic axis at v1 |
| Event emission | `book_pipeline.observability.event_logger` (existing OBS-01) | `book_pipeline.physics.gates.*` (emit role='physics_gate') | New role tag joins existing schema |
| import-linter contracts | `pyproject.toml` | (no new package) | Add `book_pipeline.physics` to BOTH source_modules + forbidden_modules per Plan 05-03 alerts precedent |

## Standard Stack

### Core (existing — unchanged)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | `>=2.10` (in repo) | All schemas (SceneMetadata, ValueCharge, Staging, CharacterPresence, GateResult) | [VERIFIED: pyproject.toml] Already the canonical contract type for the pipeline. |
| pydantic-settings | `>=2.7` (in repo) | YAML config loading for pov_locks.yaml + mode_thresholds.yaml extensions | [VERIFIED: pyproject.toml] Same loader pattern as mode_thresholds, voice_pin. |
| PyYAML | `>=6.0` (in repo) | YAML frontmatter parse + config | [VERIFIED: pyproject.toml] Existing in `concat.py::_parse_scene_md`; reuse, don't replace with python-frontmatter. |
| lancedb | `>=0.30.2` (in repo) | CB-01 retriever's table on existing schema (additive nullable per D-11) | [VERIFIED: pyproject.toml] Same engine; new rule_type, no new table |
| sentence-transformers | `>=3.3` (in repo) | BGE-M3 embedder (D-28 reuse) | [VERIFIED: pyproject.toml] Already loaded once per process; one shared instance |
| anthropic | `>=0.96.0,<0.97` (in repo) | Critic 13-axis call via `messages.parse()` + `cache_control={ttl:"1h"}` | [VERIFIED: pyproject.toml] Same client + structured-output path as Plan 04-02 chapter critic |
| tenacity | `>=9.0` (in repo) | Retry on transient Anthropic 429/529 (already in scene critic) | [VERIFIED: pyproject.toml] |
| python-json-logger | `>=3.0` (in repo) | OBS-01 JSONL events emitted by physics gates | [VERIFIED: pyproject.toml] |
| xxhash | `>=3.0` (in repo) | Hashing for prompt + output + scene-buffer fingerprints | [VERIFIED: pyproject.toml] |
| jinja2 | `>=3.1` (in repo) | Critic system prompt template (extend `system.j2`) | [VERIFIED: pyproject.toml] |
| import-linter | `>=2.0` (in repo) | Kernel/book-domain boundary on physics package | [VERIFIED: pyproject.toml] Plan 05-03 alerts precedent |

### Supporting (existing — used differently)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | (transitive via sentence-transformers) | Cosine similarity arithmetic between embedding vectors | D-28 dedup math (`cos = a @ b / (|a||b|)`) — but BGE-M3 already returns unit-normalized vectors so it's just `a @ b` |
| sqlite3 | stdlib (Python 3.12) | Scene-embedding cache at `.planning/intel/scene_embeddings.sqlite` | Recompute-on-demand strategy (RESEARCH §5) |
| `re` | stdlib | All regex (stub-leak, scene-id extraction, n-gram extraction) | Anchored patterns ONLY (no nested quantifiers) — see Threat Model §T-07-04 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| Extend YAML frontmatter (existing) | python-frontmatter library | Adds dependency for a problem the repo already solves with PyYAML. The `_parse_scene_md` helper in `chapter_assembler/concat.py` already parses `---\n<yaml>\n---\n<body>` correctly. | DON'T add python-frontmatter; reuse existing PyYAML pattern. [VERIFIED: chapter_assembler/concat.py:50-64] |
| Single 13-axis critic call | Split into two calls (5 existing + 8 physics) | Single call is cheaper (one prompt-cache hit, one round-trip) but prompt is bigger; split is smaller-but-2x calls. | RECOMMEND single call. Prompt cache amortizes cost. Cross-axis context (motivation FAIL hard-stop) is preserved. (RESEARCH §4) |
| BGE-M3 cosine for stub-leak | Open-vocab regex | Stub-leak is FAR cleaner as regex (literal `Establish:`, `Resolve:`). Don't use embeddings for what regex solves directly. | DON'T use embeddings for stub-leak (RESEARCH §6) |
| BGE-M3 cosine for repetition-loop | n-gram repetition (RES §7) | n-gram is O(n) for tokens, cheap, deterministic; embedding self-sim within scene is heavier and adds little signal for the canary case ("He did not sleep..."). | RECOMMEND n-gram first; BGE self-sim deferred (RESEARCH §7) |
| sqlite cache | LanceDB cache | LanceDB-as-cache is the right shape but adds a 7th table for one cache concern. SQLite is stdlib, atomic write is trivial, the table is two columns (scene_id PK, embedding BLOB). | RECOMMEND sqlite (RESEARCH §5) |
| pov_locks in `config/` | pov_locks in `entity-state/` (auto-derived) | Auto-derivation from chapter outputs is dynamic but adds derive-time inconsistency. ch01 is 1st-Itzcoatl — derived correctly — until ch06 regression contaminates the lock. Static config is the safer source-of-truth. | RECOMMEND `config/pov_locks.yaml` (RESEARCH §8) |

### Version Verification

- `anthropic>=0.96.0` — verified locked in `pyproject.toml` (line 11). Plan 04-02 chapter critic + Plan 03-04 scene critic both call `client.messages.parse()` against this version. No upgrade needed for Phase 7.
- `lancedb>=0.30.2` — verified locked in `pyproject.toml`. Plan 05-03 added the additive-nullable column under this same version. No upgrade.
- `sentence-transformers>=3.3` — verified locked. BGE-M3 + reranker both use this. No upgrade.
- `pydantic>=2.10` — verified. `model_config = ConfigDict(extra="forbid", frozen=True)` available since 2.0. Use `frozen=False` for SceneMetadata (it gets stamped post-load with computed values like `pack_fingerprint`).

## Architecture Patterns

### System Architecture Diagram

```
                                         drafts/chNN/chNN_scNN.md
                                              (YAML frontmatter
                                               with v2 schema)
                                                        │
                                                        ▼
                                   ┌────────────────────────────────────┐
                                   │ physics/schema.py: SceneMetadata   │  ◄── PHYSICS-01
                                   │ Pydantic strict validation         │       (Pydantic schema
                                   │ (extra="forbid")                    │        as security boundary)
                                   └────────────────┬───────────────────┘
                                                    │ valid stub
                                                    ▼
                       ┌─────────────────────────────────────────────────┐
                       │            DRAFTER PRE-FLIGHT (D-24)             │  ◄── PHYSICS-05
                       │                                                  │
                       │  ┌──────────────┐  ┌──────────────┐             │
                       │  │ pov_lock.py  │  │ motivation.py │             │
                       │  └──────┬───────┘  └──────┬───────┘             │
                       │         │                 │                      │
                       │  ┌──────▼───────┐  ┌──────▼───────┐             │
                       │  │ ownership.py │  │ treatment.py │             │
                       │  └──────┬───────┘  └──────┬───────┘             │
                       │         │                 │                      │
                       │              ┌──────▼──────┐                    │
                       │              │ quantity.py │ ◄── needs CB-01    │
                       │              └──────┬──────┘                    │
                       │                     │                           │
                       │   each gate emits role='physics_gate' Event     │
                       │   (pass + fail) per OBS-01                       │
                       └─────────────────────┬───────────────────────────┘
                                             │
                                             │ all PASS  │ ANY FAIL
                                             ▼           ▼
                                   ┌──────────────┐    REJECT — refuse to
                                   │ ContextPack  │    draft. Caller
                                   │ Bundler:     │    re-stubs / errors out.
                                   │  6 retrievers│
                                   │  (5 + CB-01) │  ◄── PHYSICS-04
                                   └──────┬───────┘
                                          │
                                          ▼
                  ┌────────────────────────────────────────────────────┐
                  │  Drafter prompt header:                             │
                  │  CANONICAL: Andrés age=23, La Niña=55ft, ...        │  ◄── PHYSICS-06 (D-23)
                  │  OWNS: sc01_arrival                                 │
                  │  DO_NOT_RENARRATE: ch04_sc02_decision_to_burn       │
                  │  PERSPECTIVE: 3rd_close (Andrés)                    │
                  │  TREATMENT: mournful                                │
                  │  MOTIVATION (Andrés): warn Xochitl about the count  │
                  │  <beat>...stub beat function fenced...</beat>        │
                  │                                                      │
                  │  [retrieval evidence — 6 axes, 40KB cap]             │
                  └──────────────────────┬─────────────────────────────┘
                                         │ vLLM
                                         ▼
                              produced scene_text
                                         │
                                         ▼
              ┌──────────────────────────────────────────────────────┐
              │  PRE-CRITIC DETERMINISTIC FILTERS (cheap, fail-fast)  │
              │                                                        │
              │  ┌─────────────────┐   ┌──────────────────┐           │
              │  │ stub_leak.py    │   │ repetition_loop  │           │
              │  │ regex check     │   │ .py n-gram check │           │
              │  └────────┬────────┘   └────────┬─────────┘           │
              │           │                     │                      │
              │           └──────────┬──────────┘                      │
              │                      │ HARD FAIL on any match          │
              │                      ▼                                 │
              │           SCENE-KICK (skip Anthropic call)              │
              │                      │ both pass                       │
              └──────────────────────┼──────────────────────────────┘
                                     │
                                     ▼
              ┌──────────────────────────────────────────────────────┐
              │  Scene critic (Anthropic Opus 4.7) — 13 axes          │  ◄── PHYSICS-07
              │                                                        │
              │  Existing 5: historical, metaphysics, entity, arc,    │
              │              donts                                     │
              │  + 6 LLM-judged: pov_fidelity, motivation_fidelity,    │
              │                   treatment_fidelity, content_owner-   │
              │                   ship, named_quantity_drift,          │
              │                   scene_buffer_similarity              │
              │  + 2 already short-circuited at pre-critic:            │
              │    stub_leak, repetition_loop (FAIL = scene-kick)      │
              │                                                        │
              │  motivation_fidelity FAIL = HARD-STOP (D-02)            │  ◄── PHYSICS-13
              │  Other axes: severity-weighted regen routing            │
              │  (existing scene-kick wiring per Plan 05-02)            │
              └──────────────────────┬───────────────────────────────┘
                                     │
                                     ▼
                            (existing flow:
                             PASS → buffer → chapter assembly → DAG
                             FAIL → regen / scene-kick / Mode-B escape)
```

### Recommended Project Structure

```
src/book_pipeline/
├── physics/                          # NEW kernel package (D-25)
│   ├── __init__.py                   # exports: SceneMetadata, GateResult, run_pre_flight, ...
│   ├── schema.py                     # Pydantic models — PHYSICS-01
│   ├── canon_bible.py                # CanonBibleView — D-09 composer
│   ├── locks.py                      # pov_lock loader + PovLock model — PHYSICS-02
│   ├── stub_leak.py                  # regex pattern set + check() — PHYSICS-08
│   ├── repetition_loop.py            # n-gram check — PHYSICS-09
│   ├── scene_buffer.py               # scene-embedding cache + cosine dedup — PHYSICS-10
│   └── gates/
│       ├── __init__.py               # registry + run_pre_flight composition
│       ├── base.py                   # GateResult, GateError, common emit-Event helper
│       ├── pov_lock.py               # check perspective vs lock
│       ├── motivation.py             # check on_screen chars have valid motivation
│       ├── ownership.py              # check owns / do_not_renarrate consistency
│       ├── treatment.py              # check treatment enum + value_charge
│       └── quantity.py               # check stub-referenced quantities resolve via CB-01
├── rag/
│   └── retrievers/
│       └── continuity_bible.py       # NEW 6th retriever — PHYSICS-04
├── drafter/
│   └── mode_a.py                     # EXTEND: integrate physics.gates.run_pre_flight()
├── critic/
│   ├── scene.py                      # EXTEND: 13-axis schema + post-process — PHYSICS-07
│   └── templates/
│       ├── system.j2                 # EXTEND: append physics-axis block
│       └── scene_fewshot.yaml        # EXTEND: bad/good examples for new axes
└── chapter_assembler/
    └── concat.py                     # EXTEND: D-18 quote-corruption normalizer — PHYSICS-11

config/
├── pov_locks.yaml                    # NEW: per-character POV mode invariants
├── mode_thresholds.yaml              # EXTEND: physics_dedup section (sim_threshold, ngram_k)
└── rubric.yaml                       # EXTEND: 13 axes (preserves rubric_version semantics; bump)

.planning/intel/
└── scene_embeddings.sqlite           # NEW: scene-buffer dedup cache (D-28)
```

### Pattern 1: New Kernel Package — alerts Precedent (Plan 05-03)

**What:** A new `book_pipeline.<package>` directory with single-responsibility files, exporting from `__init__.py`, registered in BOTH import-linter contracts.

**When to use:** Always — for every new kernel package per ADR-004.

**Example (alerts package, in-repo precedent):**
```python
# src/book_pipeline/alerts/__init__.py — pattern for physics/__init__.py
from book_pipeline.alerts.cooldown import CooldownCache
from book_pipeline.alerts.taxonomy import (
    ALLOWED_DETAIL_KEYS,
    HARD_BLOCK_CONDITIONS,
    MESSAGE_TEMPLATES,
)
from book_pipeline.alerts.telegram import TelegramAlerter, ...

__all__ = ["CooldownCache", ..., "TelegramAlerter", ...]
```

**For physics/:**
```python
# src/book_pipeline/physics/__init__.py
from book_pipeline.physics.schema import (
    SceneMetadata,
    Contents,
    Staging,
    CharacterPresence,
    Perspective,
    Treatment,
    ValueCharge,
    BeatTag,
)
from book_pipeline.physics.gates import (
    GateResult,
    GateError,
    run_pre_flight,
)
from book_pipeline.physics.canon_bible import CanonBibleView, build_canon_bible_view
from book_pipeline.physics.locks import PovLock, load_pov_locks
from book_pipeline.physics.stub_leak import scan_stub_leak, STUB_LEAK_PATTERNS
from book_pipeline.physics.repetition_loop import scan_repetition_loop
from book_pipeline.physics.scene_buffer import (
    SceneEmbeddingCache,
    cosine_similarity_to_prior,
)

__all__ = [...]  # full list above
```

**import-linter extension (pyproject.toml):**
```toml
[[tool.importlinter.contracts]]
name = "Kernel packages MUST NOT import from book_specifics"
type = "forbidden"
source_modules = [
    ...,
    "book_pipeline.alerts",
    "book_pipeline.physics",  # ADD THIS
]
forbidden_modules = ["book_pipeline.book_specifics"]

[[tool.importlinter.contracts]]
name = "Interfaces MUST NOT import from concrete kernel implementations"
type = "forbidden"
source_modules = ["book_pipeline.interfaces"]
forbidden_modules = [
    ...,
    "book_pipeline.alerts",
    "book_pipeline.physics",  # ADD THIS
]
```

### Pattern 2: Pre-Flight Gate (in-house references)

**What:** A pure-function gate that consumes a stub object + injected deps, returns a `GateResult` (success/failure + reason + emit-able Event payload). Composition is sequential; first FAIL short-circuits.

**When to use:** Every Phase 7 gate (pov_lock, motivation, ownership, treatment, quantity).

**In-house references:**
- `drafter.memorization_gate.TrainingBleedGate.scan(scene_text) -> list[MemorizationHit]`. Loaded once at construction; called per scene. Returns hit list (empty = pass).
- `drafter.preflag.is_preflagged(scene_id, set) -> bool`. Pure function. Returns boolean.

**Recommended pattern for physics gates** (cleaner than memorization_gate's exception-as-bool, simpler than preflag's bool-only):

```python
# src/book_pipeline/physics/gates/base.py
from pydantic import BaseModel
from typing import Any

class GateResult(BaseModel):
    """Pure value object emitted by every physics gate.
    
    Each gate returns one of these. Composition (run_pre_flight) iterates
    gates and short-circuits on first FAIL (severity='high'). Lower-severity
    fails accumulate and the composer decides the action.
    """
    gate_name: str
    passed: bool
    severity: Literal["pass", "low", "mid", "high"] = "pass"
    reason: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)

def emit_gate_event(
    event_logger,
    *,
    gate_name: str,
    scene_id: str,
    chapter_num: int,
    result: GateResult,
) -> None:
    """Emit one role='physics_gate' Event per gate invocation (D-11)."""
    ...  # builds Event with role='physics_gate', model='n/a', extra={gate_name, severity, reason}
```

**Pattern matches existing in-house style:**
- Returns a value object (not raises) — easier to compose, easier to test, matches `RetrievalResult` shape
- Emits exactly one Event per check (matches retriever bundler's per-retriever event invariant)
- Severity enum maps to existing `CriticIssue.severity` taxonomy (low/mid/high) — uniform reasoning

### Pattern 3: LanceDB Schema Additive Nullable (D-22 / D-11 contract)

**What:** New rule_type `'canonical_quantity'` lives in the existing CHUNK_SCHEMA without a new column. The rule_type column already exists [VERIFIED: rag/lance_schema.py:36-37].

**Implementation:**
```python
# Existing schema in rag/lance_schema.py:
pa.field("rule_type", pa.string(), nullable=False)  # already exists
```

`'canonical_quantity'` is a new VALUE for the existing column. The CHUNK_SCHEMA does NOT need a new column. The CB-01 retriever's rows write `rule_type='canonical_quantity'` along with text containing the canonical name + value.

**Storage shape (recommended):**
```
chunk_id: "canonical:andres_age:ch01"
text: "Andrés Olivares: age 26 at start of ch01 (1519-02-10). Source: brief.md L42."
source_file: "indexes/canon_bible/andres.md"   # generated, not from corpus
heading_path: "Canonical Quantity: andres_age"
rule_type: "canonical_quantity"
chapter: 1                                      # the chapter the value is canonical FOR
embedding: <BGE-M3 of the text — yes, embedded>
```

**Embedding semantics for canonical quantities (Pitfall mitigation per CONTEXT):** the BGE-M3 cosine on a "canonical value" string is NOT semantically meaningful for raw value lookup. The recommended retrieval semantics:

1. **Primary:** entity-name fuzzy semantic match. Query is the scene's entity-and-context (e.g., `"Andrés age and origin"`), retrieves canonical-quantity rows for `andres_age`, `andres_origin`, etc. Top-k=4 with rerank.
2. **Secondary:** deterministic dict-style direct lookup INSIDE a returned row (per CONTEXT pitfall guidance). Each row's `text` field is structured (parseable) so the bundler / drafter can extract the value verbatim for the prompt-header stamp (D-23). Don't ask the embedder to do exact-value retrieval; ask it to surface the right row, then read the value out.

This keeps the LanceDB shape uniform (D-22 — no new table, no new column) while sidestepping the "embed a number" anti-pattern.

### Pattern 4: Critic Prompt 13-Axis Extension

**What:** Extend `templates/system.j2` to render an additional rubric block for the 8 new physics axes; extend `CriticResponse.scores_per_axis` and `pass_per_axis` to absorb new axis names; extend post-process to enforce `motivation_fidelity` hard-stop semantics.

**Token cost analysis** (estimated):
- Existing 5-axis prompt: ~1500 tokens (rendered system + few-shot good/bad).
- 8 new axes added (per-axis description + 1-2 few-shot examples each): ~+1200 tokens.
- New total system prompt: ~2700 tokens.
- Anthropic 1h ephemeral cache: hit on request #2+, cost = 0.1× input price for cached tokens [VERIFIED: platform.claude.com/docs/en/build-with-claude/prompt-caching].
- Per-scene critic call uncached input (scene_text + retrievals): ~3000 tokens (unchanged).
- Total per call: ~5700 tokens uncached request 1; ~3270 effective tokens for cached requests 2+ (system tokens at 0.1×).

**Cost growth:** ~5% increase per critic call once cache is warm. Within budget.

**Single call vs split:** RECOMMEND single call. Reasoning:
- Single call's prompt-cache hit covers all 13 axes' rubric definition.
- Split into 5+8 means 2 round-trips, 2 prompt-cache writes (or one warm + one new), and the cross-axis hard-stop logic (`motivation_fidelity` FAIL → overall FAIL) requires post-call combination anyway.
- Anthropic structured outputs handle 13-key dicts cleanly — no schema-shape pressure.

**post_process change** (concrete code addition to `critic/scene.py:_post_process`):
```python
# After the existing 5-axis filling logic:
PHYSICS_REQUIRED_AXES = ("pov_fidelity", "motivation_fidelity", "treatment_fidelity",
                         "content_ownership", "named_quantity_drift",
                         "scene_buffer_similarity",
                         # stub_leak, repetition_loop are pre-LLM short-circuits
                         # — they appear in pass_per_axis only via the deterministic
                         # path, never set by the Anthropic response.
                         )
for axis in PHYSICS_REQUIRED_AXES:
    if axis not in parsed.pass_per_axis:
        parsed.pass_per_axis[axis] = False
        filled_axes.append(axis)
        # ... (logger warning, same pattern as 5-axis)

# D-02 hard-stop semantics:
if parsed.pass_per_axis.get("motivation_fidelity") is False:
    if parsed.overall_pass:
        logger.warning("motivation_fidelity FAIL forces overall_pass=False (D-02)")
    parsed.overall_pass = False
```

### Anti-Patterns to Avoid

- **Don't put physics gates inside chapter_assembler.dag.** D-24 locks pre-flight at drafter only. Putting gates at chapter-assemble time would (a) duplicate the work, (b) defeat the cheap-pre-LLM-rejection design, and (c) confuse OBS-01 caller_context.
- **Don't put pov_locks in `entity-state/`.** entity-state cards are derived from chapter outputs; the ch06+ Itzcoatl regression would contaminate the lock if it's auto-derived from canon. Static `config/pov_locks.yaml` is operator-edited, version-controlled, immutable until explicit edit.
- **Don't add a 6th retriever's events as side-channel to the bundler's event count.** The bundler currently emits 6 events (5 retrievers + 1 bundler). After Phase 7: 7 events. Update tests for `test_event_count_invariant`.
- **Don't make stub_leak a critic-prompt-judgment axis.** Black-and-white regex; LLM is unnecessary cost and unnecessary uncertainty. Run regex BEFORE the Anthropic call; on FAIL, short-circuit to scene-kick.
- **Don't compute scene-buffer cosine on every scene critic-time without caching.** Embedding a 2000-word scene each time is the cost driver, not the cosine math. Cache embeddings on FIRST commit.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML frontmatter parsing | Custom split-on-`---` | Existing `chapter_assembler.concat._parse_scene_md` (in-repo) | Already handles edge cases — extend, don't replicate |
| BGE-M3 cosine | Custom NumPy reduction with normalization | Reuse `BgeM3Embedder.embed_texts` (returns unit-normalized) + `np.dot` | The embedder already normalizes; just dot product |
| Tenacity-retried Anthropic call | Custom retry wrapper for the new 13-axis call | Existing `SceneCritic._call_opus_inner` decorator pattern | Identical exception types (APIConnectionError, APIStatusError); reuse decorator |
| Event emission for physics gates | New emit() helper | Existing `book_pipeline.observability.event_logger.emit` + `Event` model | Existing OBS-01 v1.0 schema; just use `role='physics_gate'`. Schema additive-only. |
| Path-traversal sanitization for scene_id | Custom regex/check | Existing `int(chapter_num)` + canonical-format pattern from `chapter_assembler/scene_kick.py:54-79` | Same precedent (T-05-02-01) — re-format, don't trust input |
| Atomic file write for cache/state | Custom tmp+rename | Existing `_persist_scene_state` pattern in `chapter_assembler/scene_kick.py:96-101` | tmp+rename idiom proven across 4 phases |

**Key insight:** Phase 7's surface area is 80% extension of existing kernel + 20% new. The existing patterns (gate-as-pure-function, retriever-with-LanceDB-base, critic-with-cached-prompt, event-emission-on-every-call, atomic tmp+rename) cover almost every new module. Phase 7 should NOT introduce a new pattern unless the existing ones cannot be made to work.

## Common Pitfalls

### Pitfall 1: Schema Container Choice Drives Implementation Complexity

**What goes wrong:** Picking JSON sidecars or python-frontmatter for the new SceneMetadata fields creates a parallel parsing path that diverges from the existing YAML frontmatter convention.

**Why it happens:** Phase 7 adds many new fields (perspective, treatment, motivation, owns, do_not_renarrate, staging, value_charge), and there's a temptation to "make a clean break" with a structured JSON sidecar.

**How to avoid:** Extend the existing YAML frontmatter. The existing `chapter_assembler.concat._parse_scene_md` already loads frontmatter into a dict; extending that dict's expected shape adds zero complexity. Use Pydantic's `SceneMetadata.model_validate(parsed_frontmatter)` for strict validation.

**Warning signs:** A draft plan that introduces `python-frontmatter` as a new dependency, or proposes `chNN_scNN.meta.json` sidecar files. Both are over-engineered.

### Pitfall 2: Critic Token Cost Scales Faster Than Estimated If Few-Shot Grows Per-Axis

**What goes wrong:** Adding 8 new axes × 2 few-shot examples each (good/bad per axis) bloats `scene_fewshot.yaml` and inflates the cached system prompt. Anthropic's 1h cache cost is 2× write-input price [VERIFIED: platform.claude.com/docs/en/build-with-claude/prompt-caching], so a 3000-token prompt that misses the cache costs 6000 tokens worth of write.

**Why it happens:** Each new axis "deserves" few-shots; nobody pushes back on which ones are skippable.

**How to avoid:** Few-shots ONLY for axes that need them — pov_fidelity (sketchy without examples), content_ownership (subjective recap-vs-reference line), treatment_fidelity (per-treatment rubric needs ground truth). The deterministic axes (stub_leak, repetition_loop) get NO few-shots — they short-circuit before the LLM. named_quantity_drift gets minimal few-shots because the rubric is "compare to canonical" — examples don't add much.

**Warning signs:** A draft plan that adds 8×2 = 16 new YAML few-shot entries. Push back to ≤8 total new few-shots.

### Pitfall 3: BGE-M3 Cosine on Non-Normalized Vectors Returns Wrong Numbers

**What goes wrong:** Coding `cos = np.dot(a, b) / (norm(a) * norm(b))` when BGE-M3's `embed_texts(...)` already returns unit-normalized vectors silently re-normalizes (no-op for unit vectors but wastes cycles AND opens drift if a future refactor changes embedder behavior).

**Why it happens:** Cosine formula reflex.

**How to avoid:** [VERIFIED: rag/embedding.py:104-107] `BgeM3Embedder.embed_texts` calls `model.encode(..., normalize_embeddings=True)`. Trust the contract. Use `np.dot(a, b)` directly. Add an assertion in `physics/scene_buffer.py` that `||a|| ≈ 1.0 ± 1e-3` on read, and on miss recompute.

**Warning signs:** Any cosine code that imports `numpy.linalg.norm` should justify why.

### Pitfall 4: Stub-Leak Regex Catastrophic Backtracking on Long Dialogue

**What goes wrong:** A naive regex like `(Establish:|Resolve:|Set up:)\s*(.*)\s*$` against multiline scene text can hit catastrophic backtracking on degenerate input [CITED: regular-expressions.info/catastrophic.html; snyk.io/blog/redos-and-catastrophic-backtracking/].

**Why it happens:** `\s*(.*)\s*$` looks innocent but `(.*)` followed by `\s*` against a string of all-spaces creates ambiguity.

**How to avoid:** Anchor patterns LINE-BY-LINE (not multi-line `.*`). Use `re.MULTILINE` and `^` anchor. The pattern set:
```python
import re
STUB_LEAK_PATTERNS = [
    re.compile(r"^\s*(?:Establish|Resolve|Set up|Setup|Beat|Function|Goal|Conflict|Outcome|Disaster|Reaction|Dilemma|Decision)\s*:", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*\[[a-z_]+\]\s*:", re.MULTILINE),  # [character intro]: style
]
```
- No nested quantifiers.
- Anchored at line-start (`^`) under MULTILINE — bounded by line length, not whole-text length.
- Word-boundary alternation, no `(.*)`.
- Tested against synthetic adversarial inputs (long lines of spaces, recursive backslashes).

**Warning signs:** A regex pattern with `(.*)`, `(\s+)+`, `(.+)+`, or any nested quantifier. Reject in code review.

### Pitfall 5: Workspace-Scoped Anthropic Cache Cross-Chapter Leak

**What goes wrong:** Anthropic cache became workspace-scoped on 2026-02-05 [CITED: platform.claude.com/docs/en/build-with-claude/prompt-caching]. The pipeline's chapter critic + scene critic share a workspace; a chapter's prompt-cache may persist into the next chapter's calls. Most of the time this is correct (rubric is the cached prefix). But if Phase 7 adds chapter-specific physics directives (e.g., "POV LOCK ITZCOATL = 1ST_PERSON for ch15+"), those must be in the UNCACHED user message, NOT the cached system block, or chapter 14's cache will refuse chapter 15's overrides.

**Why it happens:** "Add it to the system prompt for cleanliness" reflex.

**How to avoid:** All chapter-/scene-specific physics directives go in the UNCACHED user message (`_build_user_prompt`). The cached system block contains ONLY rubric definition + few-shots that are stable across calls. Match existing `SceneCritic` discipline [VERIFIED: critic/scene.py:158-176].

**Warning signs:** A draft plan that puts pov_lock values inside `templates/system.j2`. They belong in the user-prompt assembly.

### Pitfall 6: GPU Coexistence with vLLM Serving (in-house memory: vLLM occupies most GPU during build)

**What goes wrong:** Phase 7 tests that load BGE-M3 (~2GB) and run cosine-on-prior-scenes will conflict with vLLM serving the voice FT (~35-65GB). Project memory: "no vLLM serving during build". A pytest run that needs the embedder loaded competes with vLLM for GPU.

**Why it happens:** Forgetting that BGE-M3 is GPU-resident.

**How to avoid:**
- Tests for physics gates that DON'T need embeddings: pure-function tests (pov_lock, motivation, ownership, treatment, stub_leak, repetition_loop). These are most of Phase 7. Run on CPU; no GPU.
- Tests that DO need embeddings (scene_buffer cosine, CB-01 retrieval): mark `@pytest.mark.slow` (existing convention). Skip in default pre-push hook. Match Plan 02-06's pattern [VERIFIED: pyproject.toml:48-55].
- Integration test (ch15 sc02 end-to-end smoke) is `@pytest.mark.slow`. Operator runs it with vLLM stopped, deliberately.

**Warning signs:** Any new pytest fixture that loads `BgeM3Embedder` without `@pytest.mark.slow`.

### Pitfall 7: Embedding Cache Invalidation on Voice-FT Pin Bump

**What goes wrong:** Scene embeddings are computed against BGE-M3 (corpus embedder, NOT voice FT). Voice FT pin bumps (V6 → V7C) DO NOT invalidate scene embeddings — BGE-M3 is unchanged. But if BGE-M3 itself is upgraded, every cached embedding is stale.

**Why it happens:** Conflating the two model contexts.

**How to avoid:** Cache key includes BGE-M3 `revision_sha` [VERIFIED: rag/embedding.py:81-91]. Cache schema:
```sql
CREATE TABLE scene_embeddings (
    scene_id TEXT NOT NULL,
    bge_m3_revision_sha TEXT NOT NULL,
    embedding BLOB NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (scene_id, bge_m3_revision_sha)
);
```
A revision_sha change naturally invalidates by missing the composite-key cache hit; the cache-miss path computes + writes new row. Old rows remain (cheap; can be GC'd).

**Warning signs:** A cache schema with only `scene_id` as primary key.

### Pitfall 8: pov_lock Activation Boundary Off-By-One

**What goes wrong:** D-21 + OQ-01 say lock activates at ch15. If lock is checked as `chapter >= active_from_chapter` and active_from=15, then ch15 IS gated. If active_from=16 (some plan ambiguity), ch15 escapes. ch09 retry must NOT be gated (per OQ-01 recommendation a).

**Why it happens:** Operator-stated boundaries are inclusive but code defaults vary.

**How to avoid:** Explicit, documented inclusivity. PovLock model:
```python
class PovLock(BaseModel):
    character: str
    perspective: Perspective
    active_from_chapter: int  # INCLUSIVE — lock applies to this chapter and forward
    expires_at_chapter: int | None = None  # exclusive — None = never expires
    rationale: str  # operator note for the lock
    # Activation check:
    def applies_to(self, chapter: int) -> bool:
        if chapter < self.active_from_chapter:
            return False
        if self.expires_at_chapter is not None and chapter >= self.expires_at_chapter:
            return False
        return True
```
Test: `assert lock_itzcoatl_1st.applies_to(14) is False; assert lock_itzcoatl_1st.applies_to(15) is True; assert lock_itzcoatl_1st.applies_to(9) is False  # ch09 retry not gated`.

**Warning signs:** A check like `chapter > lock.active_from_chapter` (off-by-one) or hardcoded chapter constants in `pov_lock.py`.

### Pitfall 9: 13-Axis Critic Response Schema Order Sensitivity

**What goes wrong:** Anthropic structured outputs sometimes degrade quality if the schema's field order doesn't reflect the rubric prompt's order. If the prompt walks axes in order `historical, metaphysics, ..., scene_buffer_similarity` but the response schema has `motivation_fidelity` first, parse may succeed but reasoning quality may suffer.

**Why it happens:** Pydantic field order ≠ prompt rubric order.

**How to avoid:** Match `CriticResponse.scores_per_axis` ORDERED dict (Python 3.7+ dicts preserve insertion order) to the prompt's axis-walking order. Define a constant `AXIS_ORDER_v2 = (5 existing in rubric.yaml order) + (8 physics in NARRATIVE_PHYSICS.md §8 order)` and assert against it in tests.

**Warning signs:** Tests that use a `set` of axis names instead of an ordered tuple.

### Pitfall 10: Repetition-Loop Detector False Positives on Liturgical Treatment

**What goes wrong:** A scene with `treatment: LITURGICAL` (repetition is the entire point — a chant, a prayer, a ritual) will trigger n-gram repetition detection.

**Why it happens:** ch01 sc01 baseline already has "The hum. Always the hum." — intentional liturgical repetition. Naive thresholds reject it.

**How to avoid:** Repetition-loop check is **conditional on treatment**. If `treatment ∈ {LITURGICAL}`, raise the threshold significantly (or skip the check). Less radical: keep the global threshold but also apply a *line-level repetition* check that weights identical-line repetition heavily (the canary "He did not sleep. He did not sleep the next night..." is line-level identical, NOT n-gram-level — different signal). Recommended thresholds:
- Default treatment: trigram repetition rate >0.15 within scene → FLAG; identical-line count ≥3 within scene → FAIL.
- LITURGICAL: trigram threshold raised to >0.40; identical-line threshold raised to ≥6.

Tunable in `config/mode_thresholds.yaml`:
```yaml
physics_repetition:
  default:
    trigram_repetition_rate_max: 0.15
    identical_line_count_max: 2
  liturgical_treatment:
    trigram_repetition_rate_max: 0.40
    identical_line_count_max: 5
```

**Warning signs:** A test fixture that runs the canary "He did not sleep..." but doesn't also test the inverse (ch01 sc01 liturgical opening passing).

### Pitfall 11: Stale `lru_cache` on canon_bible (Plan 05-03 Pitfall 6 Echo)

**What goes wrong:** `@lru_cache` at module scope on the canon_bible build function would persist a stale view across draft cycles, missing newly-committed chapter-7 entity-state cards or retrospectives.

**Why it happens:** "Caching is good" reflex.

**How to avoid:** Per-bundle (per-scene-loop) memoization via a local dict, NOT module-scope `lru_cache`. Match Plan 05-03's `scan_for_stale_cards` precedent [VERIFIED: rag/bundler.py:104-154 docstring "NOT lru_cache — A6 RESEARCH.md: lru_cache at module scope would persist across bundles and miss new commits between runs"].

**Warning signs:** `@lru_cache` decorator on any module-level function in `physics/canon_bible.py`.

### Pitfall 12: SQLite Cache File Lock on Concurrent Test Runs

**What goes wrong:** pytest with `-n` (xdist parallel) running scene_buffer tests concurrently against `.planning/intel/scene_embeddings.sqlite` will hit SQLite's writer-exclusive lock and fail intermittently.

**Why it happens:** SQLite WAL mode helps but cross-process writes still serialize.

**How to avoid:** Tests use a temp-dir cache (`tmp_path / "scene_embeddings.sqlite"`), not the production path. Cache module accepts `db_path` constructor arg [VERIFIED: precedent: `EntityStateRetriever.__init__` keyword-only deps]. Production composition wires the production path; tests inject tmp.

**Warning signs:** Tests that don't override the cache path.

## Code Examples

### Example 1: SceneMetadata Pydantic Schema (PHYSICS-01)

```python
# src/book_pipeline/physics/schema.py
# Source: This module — synthesized from D-03 + D-13 + D-04 + NARRATIVE_PHYSICS.md §1-6
from __future__ import annotations
from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Perspective(str, Enum):
    FIRST_PERSON = "1st_person"
    THIRD_CLOSE = "3rd_close"
    THIRD_LIMITED = "3rd_limited"
    THIRD_OMNISCIENT = "3rd_omniscient"
    THIRD_EXTERNAL = "3rd_external"

class Treatment(str, Enum):
    DRAMATIC = "dramatic"
    MOURNFUL = "mournful"
    COMEDIC = "comedic"
    LIGHT = "light"
    PROPULSIVE = "propulsive"
    CONTEMPLATIVE = "contemplative"
    OMINOUS = "ominous"
    LITURGICAL = "liturgical"
    REPORTORIAL = "reportorial"
    INTIMATE = "intimate"

BeatTag = str  # documented shape: "ch{NN}_sc{II}_<beatname>"

class CharacterPresence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    on_screen: bool
    motivation: str = ""  # required if on_screen=True; gate enforces
    motivation_failure_state: str | None = None

    @field_validator("motivation")
    @classmethod
    def motivation_min_words_when_present(cls, v: str) -> str:
        if v and len(v.split()) < 3:
            raise ValueError("motivation must be empty OR ≥3 words")
        return v

class Contents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1)
    conflict: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    sequel_to_prior: str | None = None

class Staging(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_canonical: str
    spatial_position: str
    scene_clock: str
    relative_clock: str | None = None
    sensory_dominance: list[Literal["sight","sound","smell","taste","touch","kinesthetic"]] = Field(min_length=1, max_length=2)
    on_screen: list[str] = Field(default_factory=list)
    off_screen_referenced: list[str] = Field(default_factory=list)
    witness_only: list[str] = Field(default_factory=list)

class ValueCharge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    axis: str  # "loyalty/betrayal", "faith/doubt", etc. — open string
    starts_at: Literal["positive", "negative", "neutral"]
    ends_at: Literal["positive", "negative", "neutral", "compound_positive", "compound_negative"]

class SceneMetadata(BaseModel):
    """Phase 7 scene-stub schema — strict-validate from YAML frontmatter.
    
    Loaded by drafter pre-flight via SceneMetadata.model_validate(parsed_frontmatter).
    Pydantic ValidationError on shape violation — caught by gate and emitted as physics_gate Event.
    """
    model_config = ConfigDict(extra="forbid")
    
    # Identity
    chapter: int = Field(ge=1)
    scene_index: int = Field(ge=1)
    
    # D-03 mandatory fields
    contents: Contents
    characters_present: list[CharacterPresence] = Field(min_length=1)
    voice: str  # voice pin SHA or pin name
    perspective: Perspective
    treatment: Treatment
    
    # D-13 ownership
    owns: list[BeatTag] = Field(min_length=1)
    do_not_renarrate: list[str] = Field(default_factory=list)
    callback_allowed: list[str] = Field(default_factory=list)
    
    # D-04 staging + value charge
    staging: Staging
    value_charge: ValueCharge | None = None  # v1 schema present, v1 critic axis deferred
    
    # D-16 explicit override path (rare)
    pov_lock_override: str | None = None  # rationale; gate consults pov_locks.yaml
    
    @field_validator("characters_present")
    @classmethod
    def at_least_one_on_screen_with_motivation(cls, v: list[CharacterPresence]) -> list[CharacterPresence]:
        on_screen = [c for c in v if c.on_screen]
        if not on_screen:
            raise ValueError("at least one character must be on_screen=True")
        for c in on_screen:
            if not c.motivation:
                raise ValueError(f"on_screen character {c.name!r} requires motivation (D-02 load-bearing)")
        return v
```

### Example 2: pov_lock Gate (PHYSICS-02 + PHYSICS-05)

```python
# src/book_pipeline/physics/gates/pov_lock.py
# Source: synthesized from D-16, NARRATIVE_PHYSICS.md §1.3, drafter.memorization_gate pattern
from __future__ import annotations
from book_pipeline.physics.gates.base import GateResult
from book_pipeline.physics.schema import SceneMetadata
from book_pipeline.physics.locks import PovLock

GATE_NAME = "pov_lock"

def check(stub: SceneMetadata, locks: dict[str, PovLock]) -> GateResult:
    """Pre-flight: stub.perspective must match per-character pov_lock unless overridden.
    
    Returns:
        GateResult(passed=True, ...) if no breach OR explicit override present
        GateResult(passed=False, severity='high', ...) on breach
    """
    on_screen_chars = [c.name for c in stub.characters_present if c.on_screen]
    breaches: list[str] = []
    for char in on_screen_chars:
        lock = locks.get(char.lower())
        if lock is None or not lock.applies_to(stub.chapter):
            continue  # no lock or not yet active for this chapter — pass
        if lock.perspective != stub.perspective:
            if stub.pov_lock_override:
                # Explicit override is allowed but logged in the GateResult.detail
                continue
            breaches.append(
                f"{char}: declared {stub.perspective.value} but lock pins "
                f"{lock.perspective.value} (active_from_chapter={lock.active_from_chapter}, "
                f"rationale={lock.rationale!r})"
            )
    if not breaches:
        return GateResult(gate_name=GATE_NAME, passed=True, severity="pass")
    return GateResult(
        gate_name=GATE_NAME,
        passed=False,
        severity="high",
        reason="pov_lock_breach",
        detail={"breaches": breaches, "scene_id": f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"},
    )
```

### Example 3: stub_leak Pre-Critic Pattern (PHYSICS-08)

```python
# src/book_pipeline/physics/stub_leak.py
# Source: D-17 + D-27 + Pitfall 4 (this doc) + ch11 sc03 line 119 canary
from __future__ import annotations
import re
from pydantic import BaseModel

# ANCHORED line-start patterns. NO nested quantifiers. Bounded by line length.
_PATTERN_DIRECTIVE = re.compile(
    r"^\s*(?:Establish|Resolve|Set up|Setup|Beat|Function|Goal|Conflict|Outcome|"
    r"Disaster|Reaction|Dilemma|Decision|Pay off|Setup pay)\s*:",
    re.MULTILINE | re.IGNORECASE,
)
_PATTERN_BRACKETED_LABEL = re.compile(
    r"^\s*\[[a-z_ ]+\]\s*:",  # [character intro]: style
    re.MULTILINE,
)

STUB_LEAK_PATTERNS: tuple[re.Pattern[str], ...] = (_PATTERN_DIRECTIVE, _PATTERN_BRACKETED_LABEL)

class StubLeakHit(BaseModel):
    pattern_id: str  # "directive" | "bracketed_label"
    line_number: int  # 1-indexed
    matched_text: str

def scan_stub_leak(scene_text: str) -> list[StubLeakHit]:
    """Return the list of stub-leak hits. Empty list = pass.
    
    Pure function; no side effects; deterministic; no LLM call.
    """
    hits: list[StubLeakHit] = []
    for line_no, line in enumerate(scene_text.splitlines(), start=1):
        if _PATTERN_DIRECTIVE.match(line):
            hits.append(StubLeakHit(pattern_id="directive", line_number=line_no, matched_text=line[:200]))
        elif _PATTERN_BRACKETED_LABEL.match(line):
            hits.append(StubLeakHit(pattern_id="bracketed_label", line_number=line_no, matched_text=line[:200]))
    return hits
```

### Example 4: Scene-Buffer Cosine (PHYSICS-10)

```python
# src/book_pipeline/physics/scene_buffer.py
# Source: D-14 + D-28 + rag/embedding.py:104-107 (BGE-M3 returns unit-normalized)
from __future__ import annotations
import sqlite3
from pathlib import Path
import numpy as np
from book_pipeline.rag.embedding import BgeM3Embedder, EMBEDDING_DIM

class SceneEmbeddingCache:
    """SQLite-backed embedding cache keyed by (scene_id, bge_m3_revision_sha).
    
    Pitfall 7 mitigation: cache key includes embedder revision so a model
    upgrade naturally invalidates. Pitfall 12 mitigation: db_path is
    constructor arg so tests inject tmp_path.
    """
    def __init__(self, db_path: Path, embedder: BgeM3Embedder) -> None:
        self.db_path = Path(db_path)
        self.embedder = embedder
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS scene_embeddings ("
            "  scene_id TEXT NOT NULL,"
            "  bge_m3_revision_sha TEXT NOT NULL,"
            "  embedding BLOB NOT NULL,"
            "  computed_at TEXT NOT NULL,"
            "  PRIMARY KEY (scene_id, bge_m3_revision_sha)"
            ")"
        )
        self._conn.commit()

    def get_or_compute(self, scene_id: str, scene_text: str) -> np.ndarray:
        revision = self.embedder.revision_sha
        row = self._conn.execute(
            "SELECT embedding FROM scene_embeddings "
            "WHERE scene_id = ? AND bge_m3_revision_sha = ?",
            (scene_id, revision),
        ).fetchone()
        if row is not None:
            arr = np.frombuffer(row[0], dtype=np.float32)
            assert arr.shape == (EMBEDDING_DIM,)
            return arr
        # Compute, store, return.
        arr = self.embedder.embed_texts([scene_text])[0]  # unit-normalized
        from datetime import UTC, datetime
        ts = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO scene_embeddings VALUES (?, ?, ?, ?)",
            (scene_id, revision, arr.tobytes(), ts),
        )
        self._conn.commit()
        return arr

def cosine_similarity_to_prior(
    candidate_embedding: np.ndarray,
    prior_embeddings: dict[str, np.ndarray],
) -> dict[str, float]:
    """Return {scene_id: cosine_sim} for each prior. BGE-M3 vectors unit-norm → dot product is cosine.
    
    Pitfall 3 mitigation: trust embedder normalization; assert on read.
    """
    assert abs(np.linalg.norm(candidate_embedding) - 1.0) < 1e-3
    out: dict[str, float] = {}
    for sid, vec in prior_embeddings.items():
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-3, f"{sid} embedding not unit-normalized"
        out[sid] = float(np.dot(candidate_embedding, vec))
    return out
```

## Validation Architecture

> Required per Nyquist Dimension 8. The phase has substantial test surface; below is the framework + map + sampling rate + Wave 0 gaps.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8 (in repo) + pytest-asyncio (in repo) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (already configured for `slow` marker) |
| Quick run command | `pytest tests/physics/ -m "not slow" -x` |
| Full suite command | `pytest tests/ -x` (includes slow tests; ops runs with vLLM stopped) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PHYSICS-01 | SceneMetadata Pydantic schema strict validation | unit | `pytest tests/physics/test_schema.py -x` | ❌ Wave 0 |
| PHYSICS-02 | pov_lock loader + applies_to logic | unit | `pytest tests/physics/test_locks.py -x` | ❌ Wave 0 |
| PHYSICS-03 | physics package import-linter contract | static | `bash scripts/lint_imports.sh` (existing) | ✅ (scripts/ exists; contract update is in pyproject.toml) |
| PHYSICS-04 | CB-01 retriever + bundler 7-event invariant | integration (slow) | `pytest tests/rag/test_continuity_bible_retriever.py -m slow -x` | ❌ Wave 0 |
| PHYSICS-05 | Pre-flight gate composition + event emission | unit | `pytest tests/physics/test_gates.py -x` | ❌ Wave 0 |
| PHYSICS-06 | Drafter prompt header includes canonical stamp | unit | `pytest tests/drafter/test_mode_a_prompt.py -k physics_header -x` | partial (exists for mode_a; new test fixtures needed) |
| PHYSICS-07 | Critic 13-axis schema + post-process motivation hard-stop | unit | `pytest tests/critic/test_scene_13axis.py -x` | ❌ Wave 0 |
| PHYSICS-08 | stub_leak regex against synthetic + ch11 sc03 actual | unit + property | `pytest tests/physics/test_stub_leak.py -x` | ❌ Wave 0 |
| PHYSICS-09 | repetition_loop n-gram detector + treatment-conditional thresholds | unit + property | `pytest tests/physics/test_repetition_loop.py -x` | ❌ Wave 0 |
| PHYSICS-10 | scene-buffer cosine cache + dedup | integration (slow) | `pytest tests/physics/test_scene_buffer.py -m slow -x` | ❌ Wave 0 |
| PHYSICS-11 | Quote-corruption normalizer in concat + ch13 sc02 fixture | unit | `pytest tests/chapter_assembler/test_quote_normalizer.py -x` | ❌ Wave 0 |
| PHYSICS-12 | ch15 sc02 end-to-end + ch01-04 zero-FP smoke | integration (slow) | `pytest tests/integration/test_phase7_ch15.py -m slow -x` | ❌ Wave 0 |
| PHYSICS-13 | motivation_fidelity hard-stop in critic post-process | unit | (same as PHYSICS-07) `tests/critic/test_scene_13axis.py::test_motivation_fail_hard_stop` | ❌ Wave 0 |

### Property Tests (where applicable)

- **stub_leak regex DoS resistance:** Run `_PATTERN_DIRECTIVE.match` against adversarial inputs (`" " * 100_000`, `"\\" * 100_000`) with `signal.alarm(2)` timeout — must complete in <100ms.
- **D-28 cosine threshold sweep:** Property test sweeps threshold from 0.50 to 0.95, asserts the canary "manual_concat duplicate" is caught at 0.80 and a non-duplicate ch01 sc01 vs ch02 sc01 stays below 0.65.
- **PovLock activation boundary:** Property test sweeps chapter 1..30, asserts `applies_to(chapter)` is True iff `active_from_chapter <= chapter < (expires_at_chapter or ∞)`.

### Sampling Rate

- **Per task commit:** `pytest tests/physics/ -m "not slow" -x` (~2-5 sec)
- **Per wave merge:** `pytest tests/ -m "not slow" -x` (~30 sec)
- **Phase gate:** Full suite green (`pytest tests/ -x` with vLLM stopped) before `/gsd-verify-work`. Includes the integration test (PHYSICS-12) which exercises the full ch15 sc02 path against mocked vLLM and mocked Anthropic.

### Wave 0 Gaps

- [ ] `tests/physics/test_schema.py` — covers PHYSICS-01
- [ ] `tests/physics/test_locks.py` — covers PHYSICS-02
- [ ] `tests/physics/test_gates.py` — covers PHYSICS-05 (one test per gate file)
- [ ] `tests/physics/test_stub_leak.py` — covers PHYSICS-08 (synthetic + ch11 sc03 fixture)
- [ ] `tests/physics/test_repetition_loop.py` — covers PHYSICS-09 (canary "He did not sleep..." + LITURGICAL false-positive)
- [ ] `tests/physics/test_scene_buffer.py` — covers PHYSICS-10 (slow)
- [ ] `tests/physics/conftest.py` — shared fixtures (sample SceneMetadata, mock event_logger, tmp pov_locks.yaml)
- [ ] `tests/rag/test_continuity_bible_retriever.py` — covers PHYSICS-04 (slow; needs lance index)
- [ ] `tests/critic/test_scene_13axis.py` — covers PHYSICS-07 + PHYSICS-13 (mocks Anthropic; tests hard-stop post-process)
- [ ] `tests/chapter_assembler/test_quote_normalizer.py` — covers PHYSICS-11 (ch13 sc02/sc03 corruption fixture)
- [ ] `tests/integration/test_phase7_ch15.py` — covers PHYSICS-12 (slow; mock vLLM, mock Anthropic, real BGE-M3 + real LanceDB)

Framework install: not required (pytest already in dev group).

## Threat Model (security_enforcement enabled)

> Required because security_enforcement is the engine default. Threat surface for Phase 7 follows. Planner folds these into PLAN.md `<threat_model>` blocks. STRIDE categorization throughout.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-user offline pipeline; no auth surface (existing requirement |
| V3 Session Management | no | Same as V2 |
| V4 Access Control | no | Filesystem-based; existing UNIX perms |
| V5 Input Validation | yes | Pydantic strict validation on all stub frontmatter (PHYSICS-01); `extra="forbid"` rejects unknown fields |
| V6 Cryptography | partial | xxhash for fingerprints (non-crypto); SHA only for git/voice-pin verification (existing) |
| V7 Error Handling | yes | All gates emit Event on FAIL with full context — no silent failures (W-7 pattern from existing critic) |

### Known Threat Patterns for This Phase

| ID | Pattern | STRIDE | Standard Mitigation |
|---|---|---|---|
| **T-07-01** | Untrusted stub frontmatter (operator may copy-paste from external) injecting fields | Tampering | Pydantic `extra="forbid"` + per-field `field_validator` rejects unknown shapes; PHYSICS-01 |
| **T-07-02** | Path traversal via `chapter` / `scene_index` integer fields used in path assembly | Tampering / EoP | Pydantic `int` cast + canonical `f"ch{int(chapter):02d}_sc{int(scene_index):02d}"` re-format; precedent: `chapter_assembler/scene_kick.py:54-79` |
| **T-07-03** | SQLite injection via cache db_path interpolation | Tampering | sqlite3 `?` parameter binding (NEVER f-string into query); db_path is constructor arg, not from user input; precedent: `bundler.scan_for_stale_cards` parameterized SQL |
| **T-07-04** | Regex DoS in stub_leak detector via degenerate input | DoS | Anchored line-start patterns + no nested quantifiers + `re.MULTILINE` (line-bounded matching); property test enforces <100ms on 100k-byte adversarial inputs; Pitfall 4 |
| **T-07-05** | Anthropic prompt-cache leak across chapters (workspace-scoped post 2026-02-05) | InfoDisclosure / Tampering | Chapter/scene-specific physics directives go in UNCACHED user message; cached system block contains rubric only; Pitfall 5; precedent: `critic/scene.py:158-176` |
| **T-07-06** | LanceDB schema migration silent corruption when adding `'canonical_quantity'` rule_type | Tampering | rule_type is an existing column value (D-22 — additive ADDS NO COLUMNS); `open_or_create_table` raises RuntimeError on schema mismatch [VERIFIED: rag/lance_schema.py:55-86]; D-11 contract holds |
| **T-07-07** | import-linter contract bypass via runtime imports inside physics gates | EoP | All imports at module top; ruff `F401` + `F811` configured (existing); `lint_imports.sh` runs on every commit; T-04-02-01 precedent for the boundary |
| **T-07-08** | pov_lock override rationale field used to bypass legitimate locks without operator awareness | Repudiation / EoP | Override emits its own `role='physics_gate'` Event with `extra={pov_lock_override_used: True, rationale: "..."}` so weekly digest surfaces overrides; OBS-01 audit trail |
| **T-07-09** | Embedding cache poisoning via concurrent writes (Pitfall 12 echo) | Tampering | Cache db_path injected at construction; tests use tmp; production composition wires `.planning/intel/`; PRIMARY KEY (scene_id, revision_sha) prevents duplicate-row scenarios |
| **T-07-10** | Stub frontmatter YAML deserialization injection (`!!python/object` in PyYAML) | Tampering / EoP | Use `yaml.safe_load` ONLY (never `yaml.load`) [VERIFIED: chapter_assembler/concat.py:63 uses safe_load]; same convention for new pov_locks.yaml loader |
| **T-07-11** | Critic prompt template injection via stub fields rendered into prompt without escaping | Tampering | The Jinja2 `system.j2` is the cached prompt — it has NO scene-specific fields. Scene-specific data goes in `_build_user_prompt` plain-text concatenation (no template rendering). Strings are not interpreted; precedent: `critic/scene.py::_build_user_prompt` |
| **T-07-12** | Voice-FT pin SHA spoofing via stub `voice` field | Tampering | The pre-flight `motivation` gate (or a sibling `voice` gate) cross-checks `stub.voice` against the running drafter's pinned SHA; mismatch = HARD FAIL pre-flight. Precedent: `voice_pin.yaml` SHA verify |

### Per-Module Threat Notes

- **`physics/schema.py`** — input validation layer. Treat ALL stub frontmatter as untrusted. `extra="forbid"` is the wall.
- **`physics/locks.py`** — config loader. `yaml.safe_load` only; Pydantic-Settings strict. Operator-edited file, lower threat surface, but defense in depth: the loader rejects unknown PovLock fields.
- **`physics/stub_leak.py`** — regex surface. Anchored, line-bounded, no nesting. Property tests for DoS resistance.
- **`physics/scene_buffer.py`** — SQLite cache surface. Parameterized queries only; constructor-injected path; tests use tmp.
- **`rag/retrievers/continuity_bible.py`** — LanceDB writer. The CB-01 ingestion script (separate plan task) must use the existing `open_or_create_table` machinery so schema invariants are enforced on every reopen.
- **`physics/gates/*.py`** — pure functions. Each emits a `role='physics_gate'` Event regardless of pass/fail (T-07-08 mitigation: visible audit).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | runtime | ✓ | 3.12 | — |
| anthropic SDK | critic 13-axis call | ✓ | >=0.96.0 (in pyproject) | — |
| BGE-M3 model on disk | scene_buffer + CB-01 retriever | ✓ (loads on first use) | revision pinned in mode_thresholds.yaml | — |
| LanceDB | CB-01 retriever | ✓ | >=0.30.2 | — |
| import-linter | kernel boundary | ✓ | >=2.0 | — |
| GPU (BGE-M3 inference) | scene_buffer test (slow) | conditional | sm_121 (Spark) | run with vLLM stopped — operator known constraint |

**Missing dependencies with no fallback:** none (all deps already in repo).

**Missing dependencies with fallback:** GPU coexistence with vLLM is the known operational constraint (Pitfall 6). Slow tests are gated behind `@pytest.mark.slow`; fast tests run on CPU without GPU.

## Open Questions (Operator-Facing)

These echo OQ-01..OQ-04 from CONTEXT.md and add one new gap surfaced by research:

1. **OQ-01 (CONTEXT)** — Ch09 retry POV mode. Researcher recommends (a): ch09 retry follows ch06-14 historical 3rd-person; pov_lock activates at ch15. Deferred to operator/planner.
2. **OQ-02 (CONTEXT)** — Ch09 retry timing (before vs after Phase 7 ships). Researcher recommends BEFORE — V7C arrives sooner; engine takes weeks. Deferred.
3. **OQ-03 (CONTEXT)** — Ch15 sc02 resume timing. Same recommendation as OQ-02 — resume immediately on V7C land; full gating from ch16+. Deferred.
4. **OQ-04 (CONTEXT)** — `NARRATIVE_PHYSICS.md` permanent home. Researcher recommends copy to `docs/NARRATIVE_PHYSICS.md` on phase completion. Deferred to plan-phase final task.
5. **OQ-05 (NEW from research)** — Where do **canonical-quantity values themselves** come from to populate the CB-01 LanceDB index? Three candidates:
   - (a) New artifact `~/Source/our-lady-of-champion/canonical-quantities.md` ingested by an extension to `corpus_ingest`. Operator-curated; high quality; new corpus dep.
   - (b) Auto-extract from existing `brief.md` + `pantheon.md` + `engineering.md` via an Opus pass; structured-output Pydantic returns the named-quantity table. Pipeline-extracted; high coverage but extraction-error risk.
   - (c) Hybrid: operator seeds top-20 most-load-bearing quantities (Andrés age, La Niña dimensions, Cholula date, Santiago del Paso scale, Cempoala arrival date) into a hand-curated YAML; extraction agent fills the long tail.

   **Researcher recommends (c).** The 5 manuscript canaries (D-15) are the must-have; everything else is gravy. Hand-seed those 5; extraction handles the rest. Concrete artifact: `config/canonical_quantities_seed.yaml` parsed by the CB-01 ingestion task in Plan 07-02. Operator decision needed.

## Plan Rollout Order Recommendation

Per Claude's Discretion, recommend **schema-first** rollout:

| Plan | Scope | Why this order |
|---|---|---|
| **07-01** | physics/schema.py + SceneMetadata Pydantic model + stub-frontmatter migration of ch15+ stubs to v2 schema. import-linter contract addition for `book_pipeline.physics`. | Schema is the foundation; everything else consumes it. Migrating ch15+ stubs to v2 unblocks all subsequent gates. ch01-14 stubs stay v1 (forward-only per D-21). |
| **07-02** | rag/retrievers/continuity_bible.py (6th retriever) + bundler 7-event invariant + corpus_ingest for canonical_quantity rule_type + `config/canonical_quantities_seed.yaml` (5 manuscript canaries hand-seeded). | CB-01 is independent of gates; ingest runs ahead of pre-flight gates needing it. The seed YAML is mandatory for ch15+ generation to validate canonical injection (D-23). |
| **07-03** | physics/gates/{base,pov_lock,motivation,ownership,treatment,quantity}.py + physics/locks.py + `config/pov_locks.yaml` + drafter pre-flight composition (extends `mode_a.py`) + drafter prompt header (D-23 stamp + fenced beat anchor). | Gates depend on schema (07-01) + CB-01 (07-02). Drafter prompt extension is paired with gate composition. |
| **07-04** | critic/scene.py 13-axis extension + templates/system.j2 + scene_fewshot.yaml additions + physics/stub_leak.py + physics/repetition_loop.py + critic post-process motivation hard-stop. | Critic axes consume drafter output; depend on gates (07-03) being live so the test fixtures can roundtrip a real pre-flight + draft + critic flow. |
| **07-05** | physics/scene_buffer.py (SceneEmbeddingCache + cosine_similarity_to_prior) + scene_buffer_similarity critic axis wiring + chapter_assembler/concat.py quote-corruption normalizer + ch15 sc02 integration smoke test + ch01-04 zero-FP smoke validation. | Scene-buffer dedup is the heaviest test surface (slow, BGE-M3 loaded). Quote-corruption and integration smoke land alongside since they depend on the full pipeline being assembled. |

**Critical path:** 07-01 → 07-02 (parallelizable with 07-01 if extraction agent comes second) → 07-03 → 07-04. 07-05 can split: scene-buffer + integration smoke is one wave, quote-corruption normalizer is another (independent).

**Acceptance gate:** ch15 sc02 produces a clean draft on V7C LoRA via the new engine in <15 min. ch01-04 read-only smoke produces zero FAIL events across all 13 axes (zero-FP target).

## Sources

### Primary (HIGH confidence — Context7 + verified in-repo + official docs)

- Context7 `/eyeseast/python-frontmatter` — verified the library exists; researcher recommendation is to NOT add this dep (RESEARCH §1) and reuse existing PyYAML pattern in `chapter_assembler/concat.py:50-64`.
- Anthropic prompt caching docs (verified post-2026-02-05 workspace-scoping) — [platform.claude.com/docs/en/build-with-claude/prompt-caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- Anthropic SDK release notes — [github.com/anthropics/anthropic-sdk-python/releases](https://github.com/anthropics/anthropic-sdk-python/releases)
- LanceDB additive-column policy — verified in repo at `rag/lance_schema.py:55-86` (RuntimeError on schema mismatch); D-11 precedent established by Plan 05-03's `source_chapter_sha` addition
- Pydantic 2 Literal vs Enum docs — [docs.pydantic.dev/latest/concepts/pydantic_settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) and [github.com/pydantic/pydantic/issues/8708](https://github.com/pydantic/pydantic/issues/8708)
- BGE-M3 normalize_embeddings convention — verified in repo at `rag/embedding.py:104-107`
- import-linter contract pattern — verified in repo at `pyproject.toml:60-191`
- All in-house module references — verified via direct `Read` of `src/book_pipeline/{drafter,critic,rag,chapter_assembler}/*.py`
- Existing kernel-package precedent — `src/book_pipeline/alerts/__init__.py` (in-repo)

### Secondary (MEDIUM confidence — WebSearch + verified)

- Regex catastrophic backtracking + ReDoS prevention — [regular-expressions.info/catastrophic.html](https://www.regular-expressions.info/catastrophic.html) ; [snyk.io/blog/redos-and-catastrophic-backtracking](https://snyk.io/blog/redos-and-catastrophic-backtracking/) ; [johal.in/debugging-python-regex-catastrophic-backtracking-with-atomic-groups-and-testing-3](https://johal.in/debugging-python-regex-catastrophic-backtracking-with-atomic-groups-and-testing-3/)
- N-gram repetition + LLM degeneration — [arxiv.org/html/2504.12608v1](https://arxiv.org/html/2504.12608v1) ; [aclanthology.org/2025.acl-long.48.pdf](https://aclanthology.org/2025.acl-long.48.pdf) ; [Curious Case of Neural Text Degeneration arxiv:1904.09751](https://ar5iv.labs.arxiv.org/html/1904.09751)
- python-frontmatter PyPI — [pypi.org/project/python-frontmatter](https://pypi.org/project/python-frontmatter/)
- Anthropic 2026 prompt-caching guides — [aicheckerhub.com/anthropic-prompt-caching-2026-cost-latency-guide](https://aicheckerhub.com/anthropic-prompt-caching-2026-cost-latency-guide) ; [markaicode.com/anthropic-prompt-caching-reduce-api-costs](https://markaicode.com/anthropic-prompt-caching-reduce-api-costs/)
- Pydantic Literal vs Enum performance equivalence post-2.7 — [github.com/pydantic/pydantic/pull/9262](https://github.com/pydantic/pydantic/pull/9262)
- Narratology sources cited inline in `07-NARRATIVE_PHYSICS.md` Bibliography (Genette, Bal, Booth, McKee, Swain, Truby, Snyder, Stein, Le Guin, Sanderson, Aristotle, Verma).

### Tertiary (LOW confidence — single-source or training-only; flagged for validation)

- 13-axis critic prompt token-cost estimate (~5% growth post-cache-warm). Estimate based on `templates/system.j2` line count + per-axis description + few-shot YAML structure. Should be measured empirically on first Plan 07-04 dry-run before committing the full prompt.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The 5 manuscript canaries (D-15) cover 80%+ of canonical-quantity drift cases worth catching at v1. | OQ-05 recommendation | If wrong, hand-seed YAML is too narrow; extraction agent must supply more. Cost: extraction-error risk on the long tail. Mitigation: start with seed (c), grow as drift cases surface. |
| A2 | Single 13-axis critic call's prompt-cache hit rate at steady-state will be >95% in nightly runs. | RESEARCH §4 | If wrong, cache-write cost (2× input) on every miss could double critic spend. Mitigation: monitor weekly digest spend; if cache-hit-rate <90% on real runs, investigate workspace boundary or split into 5+8. |
| A3 | The closed-enum 10-value Treatment vocabulary covers the *Our Lady of Champion* manuscript register variety. | NARRATIVE_PHYSICS.md §4.3 | If a chapter needs a treatment outside the 10 (e.g., "elegiac-comedic" blend for ch26 Bernardo death-witness), the schema rejects it. Mitigation: v1.1 `treatment_secondary` field for blends. |
| A4 | n-gram repetition detection at trigram threshold 0.15 catches the ch10 sc02 canary while passing ch01 sc01 baseline. | Pitfall 10 | If thresholds need tuning, mode_thresholds.yaml has the dial. Risk: tuning never converges. Mitigation: ship with operator-tunable thresholds AND a /tests/integration/test_repetition_threshold_calibration.py that runs both canaries. |
| A5 | The CB-01 6th retriever doesn't push the 40KB context cap (RAG-03) over budget. | RESEARCH §2 | The bundler's `enforce_budget` is per-retriever-cap aware; can shrink CB-01 hits to 8KB without corrupting the canonical injection (D-23 takes the values from the row text, not from full hits). Risk: if CB-01 returns >8KB it competes with other retrievers. Mitigation: per-axis cap `continuity_bible: 8192` in `config/rag_retrievers.yaml`. |

## Metadata

**Confidence breakdown:**
- Standard stack (libraries, versions): HIGH — every library verified in pyproject.toml; no upgrades needed.
- Architecture (kernel package, gates, retriever, schema): HIGH — Plan 05-03 alerts + Plan 05-03 D-11 column extension + Plan 05-02 scene-kick + Plan 04-02 chapter critic provide concrete in-house precedents for every new piece.
- Schema container choice (YAML vs sidecar vs frontmatter library): MEDIUM-HIGH — recommendation is "extend existing YAML" because the cost of alternatives outweighs benefits at the manuscript's actual size. If operator surfaces tooling friction, pivot.
- Critic single-vs-split call: MEDIUM — recommendation depends on cache-hit rate (A2). Empirical measurement in Plan 07-04 dry-run is the validator.
- Pitfalls + threat model: HIGH — every pitfall traces to either an in-repo precedent (Plan 02-05 BL-01, Plan 05-03 stale-card scan, Plan 05-02 scene-kick path sanitization) or to an externally-cited known anti-pattern (regex DoS, Anthropic 2026-02-05 cache scope, Pydantic Literal vs Enum). 

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (30 days for stable infrastructure; revisit if Anthropic SDK ≥0.97 lands or LanceDB schema policy changes)

---

*Phase 7 Implementation Research synthesized 2026-04-25. Companion: 07-NARRATIVE_PHYSICS.md (narratology canon → enforceable atomics).*
