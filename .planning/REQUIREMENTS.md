# Requirements: our-lady-book-pipeline

**Defined:** 2026-04-21
**Core Value:** Autonomously produce first-draft novel chapters that are both voice-faithful (Paul's prose via FT local checkpoint) and internally consistent (5-axis critic enforced pre-commit), while capturing enough experiment telemetry that learnings transfer to every future writing pipeline.

## v1 Requirements

Requirements for the first full draft of *Our Lady of Champion* (27 chapters, ~81k words). Each maps to a roadmap phase.

### Foundation

- [ ] **FOUND-01**: Python repo is packaged with `uv` (pyproject.toml, lockfile); dev venv bootstrap documented; CI-friendly install path.
- [ ] **FOUND-02**: Four Pydantic-Settings-backed YAML configs load and validate: `config/voice_pin.yaml`, `config/rubric.yaml`, `config/rag_retrievers.yaml`, `config/mode_thresholds.yaml`.
- [ ] **FOUND-03**: `openclaw.json` at repo root defines at least one agent workspace (`workspaces/drafter/`) with AGENTS/SOUL/USER markdown; openclaw gateway reaches the workspace; `openclaw cron add` is used (not systemd timers).
- [ ] **FOUND-04**: Python package layout creates the 13 Protocol interfaces (Retriever, ContextPackBundler, Drafter, Critic, Regenerator, ChapterAssembler, EntityExtractor, RetrospectiveWriter, ThesisMatcher, DigestGenerator, SceneStateMachine, Orchestrator, EventLogger) with docstring contracts — stub implementations acceptable.
- [ ] **FOUND-05**: Module boundary lint enforces that book-specific code does not import from kernel-shaped modules (ADR-004 extraction hygiene).

### Observability (OBS)

- [ ] **OBS-01**: Every LLM call (drafter, critic, regen, entity extractor, retrospective writer, digest, thesis matcher) emits a structured JSONL event with timestamp, role, model, prompt hash, token counts (input/cached/output), latency, temperature, top_p, caller context, output hash, mode tag (A/B).
- [ ] **OBS-02**: Per-axis critic scores persist per committed scene + chapter into a SQLite metric ledger suitable for weekly aggregation; schema versioned; idempotent re-scan from events.jsonl supported.
- [ ] **OBS-03**: Voice-fidelity score (embedding cosine vs 20-30 anchor passages from paul-thinkpiece-pipeline training corpus) computed and stored per Mode-A scene; anchor set curated before first production Mode-A scene commits (cannot be retroactive).
- [ ] **OBS-04**: Mode-B escape rate, regen count distribution, and critic false-positive-rate proxies are first-class metrics in the ledger and the weekly digest.

### Corpus + Typed RAG

- [x] **CORPUS-01**: `~/Source/our-lady-of-champion/` lore bibles ingested (read-only mount/copy) into LanceDB with 5 separate tables: `historical`, `metaphysics`, `entity_state`, `arc_position`, `negative_constraint`.
- [ ] **CORPUS-02**: Entity-state auto-extraction agent runs post-commit, writes structured markdown entity cards (YAML frontmatter + body) into `entity-state/chapter_NN/<entity>.md`, and re-indexes the `entity_state` LanceDB table.
- [ ] **RAG-01**: The 5 typed retrievers each return structured findings with provenance (source file + chunk id) given a scene request keyed on `{POV, date, location, beat_function, chapter_num}`.
- [ ] **RAG-02**: Chapter outline (`our-lady-of-champion-outline.md`, 27 chapters × 3 blocks × 3 beats nominal) parsed into the arc-position retriever at beat-function-level granularity; stable beat IDs.
- [ ] **RAG-03**: Context Pack Bundler enforces a hard cap of ≤40KB total retrieved context per drafter call, with a cross-retriever reconciliation step that surfaces contradictions instead of silently concatenating.
- [ ] **RAG-04**: Golden-query CI gate: a fixed set of RAG queries produces a fixed set of expected chunks; breaks on index drift.

### Drafter

- [ ] **DRAFT-01**: Mode-A drafter speaks to a vLLM OpenAI-compatible endpoint serving a pinned voice-FT checkpoint from `paul-thinkpiece-pipeline`; checkpoint pinned by SHA in `voice_pin.yaml`; startup asserts SHA match.
- [ ] **DRAFT-02**: Mode-A drafter accepts per-scene `{temperature, top_p, repetition_penalty}` from config and overrides via scene-type tag (e.g., dialogue-heavy, action, reflection).
- [ ] **DRAFT-03**: Mode-B drafter uses Anthropic SDK (Opus 4.7) with voice samples in-context and prompt caching enabled (ephemeral `ttl="1h"`); per-scene opt-in via controller decision; scene carries `mode="B"` in event log and commit metadata.
- [ ] **DRAFT-04**: Structurally complex beats (Cholula stir, two-thirds revelation, siege climax — list derived from outline tags) are pre-flagged for Mode-B by default and can be demoted to Mode-A via config.

### Critic

- [ ] **CRIT-01**: Scene critic scores each drafted scene on 5 axes (`historical`, `metaphysics`, `entity`, `arc`, `don'ts`) producing structured JSON via `client.messages.parse()` with Pydantic schema; per-axis `{score: 0-100, severity: low|mid|high, issues: [{location, claim, evidence}]}`.
- [ ] **CRIT-02**: Chapter-level critic runs after scene assembly with arc-coherence and voice-consistency axes layered on top of the per-scene rubric.
- [ ] **CRIT-03**: Cross-family critic audit runs on ≥10% of scenes using a non-Anthropic judge (Gemini 2.5 Pro or GPT-5); disagreement > threshold flags a human review candidate in digest.
- [ ] **CRIT-04**: Critic rubric is versioned (`rubric.yaml` v1, v2, …); score histories tagged with rubric version for meaningful longitudinal comparison.

### Regeneration + Mode Dial

- [ ] **REGEN-01**: Regenerator takes critic issue list + severities and rewrites only affected passages (scene-local regeneration preferred over full regen).
- [ ] **REGEN-02**: Max-iteration budget R per scene, configurable; per-scene spend cap enforces a frontier-cost ceiling during Mode-B.
- [ ] **REGEN-03**: After R Mode-A failures on a scene, controller auto-escalates that scene to Mode B; escape event logged with triggering issue IDs.
- [ ] **REGEN-04**: Stuck-loop detector flags when a scene oscillates between two failure modes across regen iterations; triggers hard-block alert instead of continuing.

### Loop + Chapter Commit

- [ ] **LOOP-01**: Scene loop runs end-to-end autonomously: request → RAG bundle → Drafter → Critic → (PASS=buffer | FAIL=regen | EXHAUST=Mode B | BLOCK=alert); ≤1 human-touch per nominal scene.
- [ ] **LOOP-02**: Chapter assembler stitches scene-buffer scenes into a chapter markdown file; runs a chapter-level critic pass; on PASS, atomically commits to `canon/chapter_NN.md` and re-indexes.
- [ ] **LOOP-03**: Post-chapter DAG runs to completion before next chapter's scenes begin: entity extractor → LanceDB re-index → retrospective writer; subsequent drafting blocks on DAG completion.
- [ ] **LOOP-04**: Rollback on chapter-level critic FAIL: surgical scene-kick by default, full-chapter redraft on explicit severity signal.

### Testbed (Theses + Retrospective + Ablation)

- [ ] **TEST-01**: Retrospective writer (Opus) runs post-chapter-commit and produces markdown (`retrospectives/chapter_NN.md`) with sections for what-worked / what-didn't / candidate-theses, with a lint rule that rejects generic output.
- [ ] **TEST-02**: Thesis registry under `theses/open/` and `theses/closed/` stores experiments with frontmatter schema `{id, title, status, opened, closed, tags, metric, owner}`; thesis matcher closes theses when evidence threshold is met and writes resolution + transferable-artifact block.
- [ ] **TEST-03**: Ablation harness runs N scenes under variant-A vs variant-B configs with everything else held fixed (SHA-snapshot of config + corpus + checkpoint), outputs to `runs/ablations/<ts>/` with structured deltas.
- [ ] **TEST-04**: Weekly digest includes open-thesis health (age since last evidence), with linter flagging theses open > 30 days without new evidence.

### Orchestration + Alerting

- [ ] **ORCH-01**: Nightly cron (via `openclaw cron add`) at 02:00 kicks the scene-generation loop; gateway running under systemd user unit; persistent state across reboots verified.
- [ ] **ORCH-02**: Digest cron at 07:00 produces `digests/week_YYYY-WW.md` summarizing production (chapters committed, voice fidelity trend), experiments (open/closed theses, ablation results), cost spend, and blockers.
- [ ] **ALERT-01**: Hard-block conditions (stuck regen loop, rubric conflict, critic budget blown, voice-drift > threshold, checkpoint SHA mismatch, vLLM health failure, stale cron run) emit Telegram alerts via the existing channel.
- [ ] **ALERT-02**: Alert deduplication + cool-down prevents alert storms; re-alert after 1 hour of continued condition.

### First Draft

- [ ] **FIRST-01**: Pipeline autonomously produces a complete first draft of *Our Lady of Champion* (27 chapters) committed to `canon/` with ≥ 3 closed theses yielding transferable artifacts (config recommendation / architectural lesson / known failure mode / corpus-curation implication).
- [ ] **FIRST-02**: Final digest at milestone completion includes: production summary (word count, chapter pacing, mode-A/mode-B distribution, regen distribution, total cost), testbed summary (closed theses with artifacts, open theses snapshot), and transfer-ready notes for pipeline #2 (blog).

## v2 Requirements

Deferred to a later milestone.

### Kernel Extraction

- **KERNEL-01**: Extract generic modules (drafter/critic/regenerator/rag/observability/orchestration) into `~/Source/writing-pipeline-kernel/` when pipeline #2 (blog) is about to begin, per ADR-004.
- **KERNEL-02**: Blog pipeline (pipeline #2) consumes kernel as a dependency; book pipeline refactored to do the same.

### Richer Review Surface

- **REVIEW-01**: Web dashboard for digest review (beyond markdown files).
- **REVIEW-02**: Scene-level diff viewer for regen history.
- **REVIEW-03**: Timeline visualization of voice fidelity / mode distribution / thesis closure over time.

### Richer Critic

- **CRIT-v2-01**: Dynamic per-chapter rubric additions (inspired by WritingBench) that know which POV + beat-type-specific axes apply.
- **CRIT-v2-02**: Multi-judge ensemble (beyond 10% spot-check) with formal disagreement resolution.

### Publication Polish

- **POLISH-01**: Post-draft line-edit pass (optional pipeline-driven).
- **POLISH-02**: Chapter-boundary transition smoother across chapters, not just within.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Publication-ready manuscript | Pipeline outputs first drafts. Human does final editing. |
| Cover art / marketing / pitch letters | Out of scope for any writing pipeline in this family. |
| Real-time collaborative editing | Async digest review is the v1 surface. Live editor is over-engineering. |
| Model training | Responsibility of `paul-thinkpiece-pipeline`. Book pipeline consumes checkpoints only. |
| Mutating `our-lady-of-champion/` corpus | Read-only source-of-truth. Lore updates happen at the corpus repo, not through the pipeline. |
| Separate writing-pipeline-kernel repo in v1 | Deferred until pipeline #2 exists (ADR-004). Premature abstraction hazard. |
| Browser dashboard UI | Markdown digests sufficient for v1. Add only if markdown-reading friction is proven. |
| Frontier-primary architecture | Mode A (FT local) is default. If Mode-B rate climbs, that's a signal to invest in book-voice FT branch, not flip default. |
| OAuth / multi-user auth | Single-user pipeline. No auth surface. |
| Video / audio generation | Text-only pipeline. |
| LangChain / CrewAI / AutoGen / Temporal | Not a fit — architecture research explicitly rejected these. Use Protocols + openclaw + Anthropic SDK directly. |
| Postgres / pgvector | Not needed at this scale (5 indexes × ≤500 rows). LanceDB embedded. |
| Full-corpus context per drafter call | Research explicitly calls this out as anti-feature ("Lost in the Middle" + 5-10× cost). 40KB cap enforced via RAG-03. |
| Unbounded regen loops | Research flags as high-risk anti-feature. R-cap per REGEN-02. |
| Monolith critic | Research flags as anti-feature (kills regen targeting). 5-axis per CRIT-01. |

## Traceability

Populated by roadmapper during roadmap creation. Every v1 REQ-ID maps to exactly one phase in `.planning/ROADMAP.md`.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Pending |
| FOUND-02 | Phase 1 | Pending |
| FOUND-03 | Phase 1 | Pending |
| FOUND-04 | Phase 1 | Pending |
| FOUND-05 | Phase 1 | Pending |
| OBS-01 | Phase 1 | Pending |
| OBS-02 | Phase 6 | Pending |
| OBS-03 | Phase 3 | Pending |
| OBS-04 | Phase 6 | Pending |
| CORPUS-01 | Phase 2 | Complete |
| CORPUS-02 | Phase 4 | Pending |
| RAG-01 | Phase 2 | Pending |
| RAG-02 | Phase 2 | Pending |
| RAG-03 | Phase 2 | Pending |
| RAG-04 | Phase 2 | Pending |
| DRAFT-01 | Phase 3 | Pending |
| DRAFT-02 | Phase 3 | Pending |
| DRAFT-03 | Phase 5 | Pending |
| DRAFT-04 | Phase 5 | Pending |
| CRIT-01 | Phase 3 | Pending |
| CRIT-02 | Phase 4 | Pending |
| CRIT-03 | Phase 6 | Pending |
| CRIT-04 | Phase 3 | Pending |
| REGEN-01 | Phase 3 | Pending |
| REGEN-02 | Phase 5 | Pending |
| REGEN-03 | Phase 5 | Pending |
| REGEN-04 | Phase 5 | Pending |
| LOOP-01 | Phase 5 | Pending |
| LOOP-02 | Phase 4 | Pending |
| LOOP-03 | Phase 4 | Pending |
| LOOP-04 | Phase 4 | Pending |
| TEST-01 | Phase 4 | Pending |
| TEST-02 | Phase 6 | Pending |
| TEST-03 | Phase 6 | Pending |
| TEST-04 | Phase 6 | Pending |
| ORCH-01 | Phase 5 | Pending |
| ORCH-02 | Phase 6 | Pending |
| ALERT-01 | Phase 5 | Pending |
| ALERT-02 | Phase 5 | Pending |
| FIRST-01 | Phase 6 | Pending |
| FIRST-02 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 41 total
- Mapped to phases: 41
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-21*
*Last updated: 2026-04-21 after roadmap creation (traceability populated)*
