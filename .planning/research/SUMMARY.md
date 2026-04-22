# Project Research Summary

**Project:** our-lady-book-pipeline
**Domain:** Autonomous LLM-based long-form creative-writing pipeline (voice-FT drafter + frontier critic + typed RAG + experiment telemetry)
**Researched:** 2026-04-21
**Confidence:** HIGH on stack and architecture; MEDIUM-HIGH on features and pitfalls

## Executive Summary

This is an autonomous novel-drafting pipeline that operates as both a production tool (producing *Our Lady of Champion*, a 27-chapter historical-fiction novel) and a deliberate testbed for a family of writing pipelines. The dominant design tension is that it must run unattended nightly while simultaneously generating structured experimental evidence that transfers to pipelines #2-N. This dual-purpose defines everything: observability is first-class, not polish; the Mode-dial (voice-FT default, frontier escape) is an explicit measured metric, not an implementation detail; and the testbed plane (theses, ablations, retrospectives) is a core deliverable, not a nice-to-have. Commercial tools (NovelCrafter, Sudowrite, NovelAI) are categorically wrong comparators — this pipeline is closer in spirit to an MLOps harness that produces a novel as its artifact.

The recommended approach builds on entirely existing local infrastructure: vLLM (cu130, already serving Gemma-4 for wipe-haus-state), openclaw (already systemd-managed), and Anthropic SDK 0.96+ (Opus 4.7). No new services are introduced; the pipeline is a Python package (uv-managed) that talks to these services over HTTP and file-based handoff. The architecture is deliberately cron-tick/batch-style: openclaw fires a short-lived Python process every night, all state lives on disk in JSONL/JSON/Markdown, and the process exits cleanly. This design choice is load-bearing — it enables crash recovery, ablation runs, and kernel extraction without framework lock-in.

The top risks are (1) observability being deferred — ADR-003 makes this non-negotiable, and any phase structure that defers OBS-01/OBS-02 past Phase 0 will silently destroy the testbed's ability to learn from its own first chapters; (2) the voice model silently drifting into generic fiction prose on dialogue-heavy beats (no fiction training data in the thinkpiece corpus — thesis 001 tests this); and (3) the critic-drafter-RAG collusion triangle, where drafter and critic share the same RAG pack and both inherit any pack errors without independent correction. The mitigation for all three is built into the architecture, but only if the roadmap phases them correctly.

## Key Findings

### Recommended Stack

The stack is fully determined by the existing DGX Spark GB10 infrastructure. vLLM (cu130 wheel, 0.19+) serves the voice-FT checkpoint on a dedicated port (8002, separate from wipe-haus-state's port 8000). The Python package uses uv (deliberate deviation from paul-thinkpiece-pipeline's bare-venv approach — this is production-shaped, not experiment-shaped), Pydantic 2 for all structured data, LanceDB 0.30+ as the embedded vector store (no server, 5 × ≤500 row indexes, columnar files under `indexes/`), BGE-M3 for embeddings (8K clean context, strong on long retrieval queries), and stdlib `logging` + `python-json-logger` for the JSONL event log. The Anthropic SDK 0.96+ handles all frontier calls (critic, entity extractor, retrospective writer, digest, Mode-B drafter) with native structured outputs via `messages.parse()` and 1h ephemeral corpus cache.

**Core technologies:**
- **vLLM 0.19+ (cu130)**: Local OpenAI-compatible server for Mode-A voice checkpoint — already installed and serving; book pipeline adds a dedicated port, not a new install
- **Anthropic SDK 0.96+**: Opus 4.7 for critic/extractor/retrospective/digest; native structured outputs; 1h cache on repeated corpus prefix
- **LanceDB 0.30+**: Embedded vector store, 5 typed indexes, metadata `where` filters first-class (critical for date-range, POV-name, chapter-number queries at bundler)
- **BGE-M3 (BAAI/bge-m3)**: Local embeddings, 8K context, no per-query API cost, runs on iGPU at ~2GB
- **openclaw 2026.4.5**: Already systemd-managed; `openclaw.json` at repo root (not `.openclaw/`); cron via `openclaw cron add`; workspaces under `workspaces/<agent>/`
- **uv**: Lock-file-based dependency management; `[[tool.uv.index]]` handles cu130 nightly index cleanly
- **Pydantic 2 + pydantic-settings + PyYAML**: Typed config loading for all 4 YAML configs; type-checked at load; one source of truth for shapes
- **stdlib logging + python-json-logger**: Zero-dep JSONL event emission; Logfire-compatible for optional upgrade later
- **tenacity**: Retry with exponential backoff on vLLM 502 and Anthropic 529; wraps every LLM call for unattended overnight reliability

Critical version constraints: Python 3.11 (matches `venv_cu130`); `anthropic>=0.96.0` (first version with Opus 4.7); vLLM 0.19+ requires CUDA 13 (SM_121a); `lancedb>=0.30.2`.

### Expected Features

This pipeline's feature taxonomy is non-standard. "Table stakes" means the minimum to run unattended and produce learnable signal. "Differentiators" are observability and experiment infrastructure, not creative polish. Commercial-tool features (streaming, dashboard, real-time collaboration) are explicit anti-features.

**Must have (table stakes):**
- Scene-level drafter with per-scene-type temperature configs — voice model degrades past ~1000w; varied sampling required
- Mode-B frontier escape hatch — 20-30% of scenes will exceed voice model's structural reach; blocking on them is a pipeline defect
- 5-axis typed RAG with ~35KB hard cap — monolith retrieval produces unactionable critic signal; uncapped context degrades Mode-A quality
- 5-axis structured critic with issue lists, HARD/SOFT severity split — gates regen vs commit decisions
- Issue-conditioned regeneration with max-R cap and Mode-B escalation — unbounded loops hallucinate solutions after 3 attempts
- Per-call structured JSONL event logging with checkpoint SHA, mode tag, prompt hash, tokens, latency, caller context — cannot debug an overnight pipeline without this
- Metric ledger (per-axis scores, regen counts, cost, mode tags) per committed unit
- Chapter-atomic commit with post-commit fan-out: entity extractor, RAG reindex, retrospective writer
- openclaw cron driving nightly scene-generation loop
- Telegram hard-block alerting (stuck regen, budget exceeded, voice drift past threshold)

**Should have (testbed differentiators):**
- Thesis registry with computable success metrics and structured transferable artifacts (4 ADR-003 artifact types)
- Retrospective auto-writer (templated with required fields, linted against boilerplate)
- Voice-drift detection via embedding cosine against 20-30 anchor passages — must exist from scene 1
- Mode-B rate as top-level digest metric — not buried; rising rate is the signal for voice-FT investment decisions
- Config pinning + prompt hashing with sha emitted per event
- Pre-flagged Mode-B beats in `config/mode_preflags.yaml` (Cholula stir, two-thirds reveal, siege climax)
- Chapter-level critic with independent fresh RAG pack query (not the scene pack — prevents C-4 collusion)
- Weekly digest with mode distribution, voice fidelity by mode, regen cost histogram, thesis aging panel

**Defer (v2+):**
- Paired ablation harness (TESTBED-01) — after 3+ chapters committed and first thesis has production evidence
- Background Mode-B-only benchmark — after 9+ chapters
- Book-voice FT branch — only if thesis 001 refutes thinkpiece-voice transfer
- Web dashboard, kernel extraction, agentic retrieval

### Architecture Approach

The architecture is a cron-tick batch pipeline: openclaw fires a short-lived Python process nightly that advances a file-persisted SceneStateMachine one scene at a time (PENDING → RAG_READY → DRAFTED_A → CRITIC_PASS/FAIL → REGENERATING → ESCALATED_B → COMMITTED → HARD_BLOCKED), writes every LLM call result to disk immediately, then exits. No in-memory state survives between ticks. The event log (JSONL, append-only, content-addressed blob store for prompt/output bodies) is the source of truth; SQLite metrics ledger is a derived view, rebuildable from JSONL at any time. All five component types implement Python `Protocol`s — same-Protocol instances are swappable for ablation runs without touching the orchestrator.

**Major components:**
1. **ContextPackBundler** — fan-out to 5 typed Retriever instances, conflict reconciliation step, 35KB hard cap; same pack to scene-drafter and scene-critic; chapter-critic re-queries independently
2. **SceneStateMachine** — file-persisted JSON per scene; owns all mode-dial state transitions; orchestrator reads, advances one step, writes, exits
3. **Drafter (Mode A / Mode B)** — Mode A: vLLM HTTP with voice-pin SHA verified at boot; Mode B: Anthropic API with voice samples in-context; both implement same Protocol, swappable for ablation
4. **Critic (scene and chapter)** — Anthropic Opus, 5-axis checklist-style rubric, HARD/SOFT severity; all responses persisted per attempt number; chapter critic uses fresh RAG pack
5. **Regenerator** — history-aware (full prior regen issue history); oscillation detector; voice check post-regen; R-cap with cost gate; word-count constraint (±10%)
6. **Post-commit DAG** — EntityExtractor (source_chapter_sha in cards) + RetrospectiveWriter (templated + linted) + ThesisMatcher; extractor must complete before next chapter can draft (O-2 prevention)
7. **EventLogger + MetricsIngester** — fsync on emit; separate nightly ingester events.jsonl → metrics.sqlite (idempotent, reconciliation check)
8. **DigestGenerator** — weekly Opus synthesis; mode distribution top-level; voice fidelity by mode; regen cost histogram; thesis aging panel; stale-card panel; run count leading
9. **VoicePinLoader** — SHA256 + first-token-logit canary at boot; refusal on mismatch; sha in every drafter event

### Critical Pitfalls

The 40+ identified pitfalls collapse into 5 clusters the roadmap must address:

1. **Observability-plane deferral** — OBS-01 must be live from scene 1. Voice-fidelity anchor set must be curated before first scene commits. Retroactive baselines are impossible. Prevention: EventLogger is a Phase 0 artifact; anchor corpus curation is Phase 2 entry condition.

2. **Voice-model register collapse + memorization (V-1, V-2)** — Thinkpiece voice-FT has zero fiction training data; will silently default to generic prose on dialogue-heavy beats; critic's voice axis may pass this. Prevention: two-tier voice axis (similarity AND presence markers); n-gram overlap gate against training corpus; voice-fidelity band (0.60-0.88, not just a floor).

3. **Critic-drafter-RAG collusion (C-4, R-1)** — Scene drafter and critic share the same RAG pack; if pack has a wrong fact, both fail silently in the same direction. Five independent retrievers can contradict each other; bundler naively concatenating all three is content corruption. Prevention: bundler conflict reconciliation emitting `retrieval_conflicts.json`; chapter critic re-queries RAG independently; weekly cross-family spot-check.

4. **Regen failure cascades (RE-1, RE-3, RE-4)** — Without regen history threading, regen oscillates axis A → B → A. Without a per-scene cost cap, one hard beat blows the weekly budget. Without a word-count constraint, regen "fixes" by deleting content. Prevention: history-aware regen prompt; hard per-scene cost cap with mid-run Telegram alert; post-regen length constraint and beat-coverage axis on critic.

5. **Testbed plane rot (OB-3, OB-4, T-1, T-2)** — Retrospectives becoming boilerplate; theses never closing; ablation confounds from silent config changes. These manifest within 5 chapters. Prevention: retrospective template with lint check from chapter 1; thesis schema linter requiring metric + test_design + deadline; ablation harness with SHA-frozen config snapshot.

## Implications for Roadmap

Based on combined research, the phase structure is derived from three hard constraints: (1) the dependency DAG (retrievers before drafter, scene before chapter, core loop before testbed plane); (2) ADR-003's mandate that observability is not deferrable past foundation; (3) the testbed framing that makes thesis infrastructure a first-class deliverable.

### Phase 0: Foundation + Observability Baseline
**Rationale:** ADR-003 makes OBS-01 non-negotiable from scene 1. EventLogger, VoicePinLoader, and openclaw wiring must exist before any LLM calls, or the first chapters produce no usable experimental evidence. Pre-flight GPU check discipline (from sibling-project MEMORY.md) belongs here, not in a drafter phase. Module boundary lint rule (book-specific code cannot leak into generic modules) must be established before any implementation begins or T-3 becomes expensive to clean up.
**Delivers:** uv repo scaffolding; Pydantic Settings config loading; EventLogger writing JSONL (with checkpoint_sha field in schema); VoicePinLoader (SHA + canary); openclaw workspace wired (drafter workspace, `run_cycle` entry point logging "next scene: ch01_sc01"); `config/mode_preflags.yaml` schema; module boundary lint rule; Telegram alert plumbing; `config/voice_pin.yaml` with sibling-pipeline handoff protocol
**Addresses:** FOUNDATION-01, OBS-01 (partial), ALERT-01 (partial)
**Avoids:** V-3 (checkpoint pin drift), T-3 (book leakage into kernel), O-5 (GPU pre-flight), OB-1 (blob store design established from day 0)
**Research needed:** No — entirely existing-infrastructure coordination. All patterns from wipe-haus-state and paul-thinkpiece-pipeline are authoritative.

### Phase 1: Corpus Ingestion + Typed RAG
**Rationale:** Every downstream component depends on retrieval quality. Testing retrieval in isolation means RAG bugs are diagnosed before they contaminate draft quality assessments. Thesis 005 (typed vs monolith) can be partially evaluated here against corpus queries — earliest possible thesis evidence. Negative-constraint tag map (`chapter_tag_map.yaml`) and thematic outline annotations (for N-2 prevention) must be built here, not retrofitted after chapters commit.
**Delivers:** 5 LanceDB indexes built from `our-lady-of-champion/` corpus; ContextPackBundler with 35KB hard cap and conflict reconciliation (emits `retrieval_conflicts.json`); golden-query accuracy set (≥5 queries/index, nightly CI job); outline parsed into arc-position retriever with beat-function + thematic-tag granularity; `indexes/negative_constraint/chapter_tag_map.yaml`; smoke test: bundler prints valid ContextPack for ch01_sc01
**Addresses:** CORPUS-01, RAG-01, RAG-02
**Avoids:** R-1 (retriever divergence — reconciliation step), R-3 (pack bloat — hard cap), R-4 (wrong-fact retrieval — chunking by rule-card boundaries), R-5 (missed don'ts — tag map), N-2 (thematic spine — tags in arc-position retriever at index time)
**Research needed:** YES — LlamaIndex ingestion utilities vs custom chunking for rule-card boundary semantics; BGE-M3 vs jina-embeddings-v3 on domain-specific corpus (Nahuatl names + metaphysics rule-cards). STACK.md explicitly flags this as an open gap.

### Phase 2: Mode-A Drafter + Scene Critic + Basic Regen (Core Loop)
**Rationale:** Smallest vertical slice that exercises every component Protocol. Voice-fidelity anchor set MUST be curated and scored before any prose commits — retroactive baseline is impossible. Interface errors discovered here cost one phase; discovered at Phase 5 they cost the testbed. Stub protocols for components not yet built (ChapterAssembler, EntityExtractor) let the orchestrator state machine run end-to-end without errors.
**Delivers:** vLLM serving pinned voice checkpoint on port 8002 (systemd --user unit); Mode-A Drafter (Protocol, boot-time SHA + canary); scene Critic (5-axis checklist rubric, HARD/SOFT severity, don'ts-axis calibrated from known-liberties.md, stateless per-scene prompt); SceneStateMachine (all states including HARD_BLOCKED, JSON-on-disk); Regenerator (max_attempts=1, history-aware prompt, oscillation detector stub, post-regen voice check, ±10% word-count constraint); voice-fidelity anchor set (20-30 curated passages scored before ch01_sc01); n-gram overlap gate; per-scene event emission (mode tag, checkpoint_sha required); end-to-end: ch01_sc01 → ContextPack → Mode-A draft → critic → 0-1 regens → state on disk
**Addresses:** DRAFTER-01, CRITIC-01, REGEN-01, OBS-01 (complete)
**Avoids:** V-1 (register collapse — voice metric live from scene 1), V-2 (memorization — n-gram gate), C-2 (score collapse — checklist rubric), C-3 (severity drift — stateless critic), RE-2 (regen voice drift — post-regen check), RE-4 (beat deletion — word-count constraint)
**Research needed:** YES — critic rubric prompt architecture (per-axis prompts vs single JSON-schema output); token budget per scene at Opus 4.7 pricing; voice-fidelity metric calibration (distance threshold for drift alarm).

### Phase 3: Chapter Assembly + Commit + Post-Commit Fan-Out
**Rationale:** Chapter-atomic commit unlocks everything in the testbed plane. Post-commit DAG ordering (extractor before next drafter) must be enforced here — the extractor-race failure (O-2) manifests at chapter boundaries, not scene boundaries. Retrospective template with lint check must be live at this phase's start; the first retrospective is when the testing machinery proves itself.
**Delivers:** ChapterAssembler (deterministic); chapter-level Critic (fresh RAG pack, independent from scene pack; pacing axis; thematic-advance axis; interior-change sub-axis); atomic git commit to `canon/`; post-commit DAG (EntityExtractor with source_chapter_sha → RAG reindex → RetrospectiveWriter with lint check); chapter-level state machine (`drafting|committed|extracted|indexed|ready_for_next`); SHA-linked entity cards with stale-card detection; retroactive-edit protocol; end-to-end: ch01 all scenes → assemble → chapter critic → commit → entity cards → retrospective
**Addresses:** CORPUS-02, CRITIC-02, LOOP-01 (partial), RETRO-01
**Avoids:** C-4 (chapter critic re-queries independently), R-2 (stale entity — SHA cards), O-2 (extractor race — DAG), OB-3 (boilerplate retrospective — template + lint from day 1), I-2 (retroactive edit ripple — protocol established), I-4 (retrospective race — flush barrier), N-3 (pacing — pacing axis on chapter critic), N-4 (arc not landing — interior-change sub-axis)
**Research needed:** No — all patterns fully specified in ARCHITECTURE.md §3 and §5. Chapter-level rubric axes need author config review, not research.

### Phase 4: Mode-B Escape + Regen Budget + Hard-Block Alerting
**Rationale:** Pipeline is not truly autonomous without a reliable failure path. Mode-A-only pipelines block silently on hard beats. Without the per-scene cost cap, one Mode-B escalation on a hard beat can blow the weekly budget overnight with no mid-run signal. This phase makes every failure path terminate in either a successful commit or a Telegram alert — never a silent wedge.
**Delivers:** Mode-B Drafter (Anthropic API, voice samples in-context, mode=B required in event schema); Regenerator updated to full R-cap (configurable, default 3) with cost gate; oscillation detector active (axis alternation → immediate Mode-B escalation without burning R budget); per-scene cost cap as hard abort (Telegram mid-run, not end-of-week); mode-B-rate rolling 30-day alarm at 40%; `config/mode_preflags.yaml` enforcement in orchestrator; complete ALERT-01 (hard-block taxonomy); end-to-end: force scene to fail R times → Mode-B commit with mode=B; force Mode-B to fail → HARD_BLOCK + Telegram
**Addresses:** DRAFTER-02, REGEN-02, ALERT-01 (complete), ORCH-01 (partial)
**Avoids:** M-1 (Mode-B creep — rate alarm), M-2 (voice metric distortion — mode-segmented reporting), M-3 (pre-flag list rot — config not prose), RE-1 (oscillation — detector), RE-3 (cost explosion — hard per-scene cap), C-1 (same-family self-preference — mode tag enables cross-family audit flag)
**Research needed:** YES — Anthropic budget modeling (Opus 4.7 pricing per Mode-B scene); Sonnet 4.6 viability as Mode-B for non-structurally-complex beats; prompt caching interaction with openclaw per-workspace session scope.

### Phase 5: Testbed Plane (Theses, Digest, Metrics Ledger)
**Rationale:** This is where the pipeline earns its testbed designation. By Phase 5 start, 3 committed chapters exist; thesis 005 (typed RAG vs monolith) and thesis 002 (Mode-B escape rate) should have enough production evidence to evaluate. Digest is the sole human-facing interface; without it, Paul has no visibility into pipeline health across chapters.
**Delivers:** Thesis registry with schema linter (metric + test_design + deadline required fields); ThesisMatcher (Opus reads retrospectives + events, proposes closures); ObservabilityIngester (events.jsonl → metrics.sqlite, idempotent + reconciliation check, integrity line in digest); DigestGenerator (weekly, mode distribution top-level, voice fidelity by mode, regen cost histogram, stale-card panel, thesis aging panel, run count leading); OBS-02 (complete); milestone force-evaluation at chapters 3/9/18/27; cross-family critic spot-check protocol (10% scenes); voice drift threshold finalized; first weekly digest with real data from ≥3 committed chapters
**Addresses:** THESIS-01, DIGEST-01, OBS-02 (complete), TESTBED-01 (partial)
**Avoids:** OB-2 (ledger drift — reconciliation), OB-4 (thesis ossification — milestone force-eval), T-1 (confounded ablation — SHA snapshot protocol), T-2 (vague theses — linter), T-4 (vague artifacts — 4-type closure template), M-1 (Mode-B creep — digest prominence)
**Research needed:** MAYBE — thesis matcher confidence threshold calibration against first 3 retrospectives; ablation harness design if more than 2 variants needed simultaneously.

### Phase 6: Production Hardening + First Full Draft
**Rationale:** Drives toward FIRST-DRAFT (27 chapters, ≥3 closed theses). Addresses pitfalls that only manifest at multi-chapter scale: event log bloat (OB-1) around 5k scenes × 5 events × 30KB bodies; thematic spine loss (N-2) invisible at chapter-grain but visible at Act-boundary audits; character arc not landing (N-4) requires cross-chapter retrospective; pacing collapse (N-3) requires scenes-per-chapter distribution monitoring.
**Delivers:** Content-addressed blob store for prompt/output bodies; monthly event log rotation; Act 1 (9 chapters) end-to-end validation; thematic audit at ch9 milestone; character-arc milestone audit (POV interior-change legibility); Paul weekly spot-check protocol (2 scenes/week, 6/10 subjective threshold); Ch 27 Nahuatl preservation snapshot test; retroactive-edit protocol CLI (`gsd edit-chapter`); sibling-pipeline checkpoint manifest + read-only mount; FIRST-DRAFT acceptance criteria (27 chapters, ≥3 closed theses with transferable artifacts)
**Addresses:** FIRST-DRAFT, TESTBED-01 (complete)
**Avoids:** N-1 (dead prose), N-2 (thematic spine), N-3 (pacing), N-4 (arc), N-6 (Nahuatl), I-1 (checkpoint corruption), I-3 (stale indexes vs bibles), OB-1 (log bloat)
**Research needed:** No — execution phase against established patterns.

### Phase Ordering Rationale

- Observability before any LLM calls: ADR-003 explicit. Voice-fidelity anchor set must precede first prose commit. Retroactive baselines are impossible.
- RAG before drafter: retrieval quality is testable in isolation; RAG bugs diagnosed before they contaminate draft quality measurements and confound thesis evidence.
- Core loop (Phase 2) before escape hatch (Phase 4): Mode-B is an escape from Mode-A failure; Mode-A must exist and be characterized before Mode-B's escalation logic is meaningful.
- Scene flow before chapter flow: ChapterAssembler consumes scene results; chapter-level critic and entity extraction are meaningful only when a full scene buffer exists.
- Core loop before testbed plane (Phase 5): theses require events; events require an operating pipeline; digest requires ≥3 committed chapters; ablation harness requires a production variant.
- Post-commit DAG ordering is non-negotiable: entity extractor must complete before next chapter's drafter runs (O-2 race condition). This drives the chapter-level state machine design in Phase 3.

### Research Flags

Phases needing deeper research during planning:
- **Phase 1 (RAG)**: LlamaIndex ingestion utilities vs custom chunking for rule-card boundary semantics; BGE-M3 vs jina-embeddings-v3 on Nahuatl + metaphysics-rule-card corpus. STACK.md identifies both as explicit gaps.
- **Phase 2 (Core Loop)**: Critic rubric prompt architecture; Opus 4.7 token budget per scene; voice-fidelity metric calibration (drift threshold, distance metric, which embedding layer).
- **Phase 4 (Mode-B)**: Anthropic budget modeling at Opus 4.7 pricing; Sonnet 4.6 viability as Mode-B fallback; prompt caching interaction with openclaw per-workspace session scope (Anthropic workspace-scoped cache changed 2026-02-05).

Phases with standard patterns (research phase not needed):
- **Phase 0 (Foundation)**: Entirely existing-infrastructure coordination. wipe-haus-state and paul-thinkpiece-pipeline patterns are authoritative. uv, Pydantic Settings, stdlib logging — all HIGH-confidence, well-documented.
- **Phase 3 (Chapter Flow)**: All patterns fully specified in ARCHITECTURE.md §3 and §5. File-queue handoff, post-commit DAG, atomic git commit — standard patterns with no research gaps.
- **Phase 6 (Production Hardening)**: Execution phase against established patterns. Content-addressed blob store, log rotation, checkpoint manifest — all standard.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | vLLM, openclaw, Anthropic SDK directly verified against installed docs and working wipe-haus-state. LanceDB version confirmed on PyPI. Only gap: domain-specific retrieval quality on Nahuatl + rule-card corpus untested. |
| Features | MEDIUM-HIGH | Table-stakes features grounded in ADRs + academic literature (DOC, Self-Refine, WritingBench). Testbed-specific features derived by composition — under-documented in commercial/academic corpus. Feature priorities HIGH confidence; exact behavior of retrospective templates MEDIUM. |
| Architecture | HIGH | Component interfaces and data flow grounded in locked ADRs 001-004 + existing ARCHITECTURE.md diagrams. State persistence and cron-tick batch pattern verified against openclaw docs and wipe-haus-state install. Framework survey (reject LangGraph/CrewAI/etc.) is MEDIUM sourcing but sound given batch-architecture constraint. |
| Pitfalls | MEDIUM-HIGH | Project-specific pitfalls (V-1, V-2, O-5, T-3) grounded in sibling-project documented failures. RAG failure modes grounded in 2025 production RAG literature. Critic failure modes grounded in LLM-judge bias research. Novel-quality pitfalls (N-1 through N-6) are editorial judgments from project brief and known-liberties.md — MEDIUM confidence. |

**Overall confidence:** HIGH on technical approach; MEDIUM-HIGH on testbed feature specifics and novel-quality assessment.

### Gaps to Address

- **BGE-M3 domain-specific retrieval quality**: Nahuatl proper nouns and metaphysics rule-card text are non-standard corpora. Compare against jina-embeddings-v3 in Phase 1 before committing to a single embedding model.
- **Voice fidelity metric calibration**: What cosine distance threshold constitutes drift? Anchor set (20-30 passages) needs curation and pilot calibration before Phase 2 begins. Detection band (0.60-0.88, per pitfall V-2) requires validation against a small pilot sample.
- **Anthropic prompt caching + openclaw workspace scope**: Corpus cache across critic calls is required by ADR-003. Whether openclaw per-agent workspace maps cleanly to Anthropic workspace-scoped cache (changed 2026-02-05) needs confirmation before Phase 2 critic implementation.
- **Regen R-cap and cost defaults**: Right value of R and per-scene cost cap depend on empirical token counts at Opus 4.7 pricing. Requires a pilot pricing run. Identify in Phase 2 research, finalize before Phase 4 config.
- **Thesis matcher confidence thresholds**: Auto-closure vs "propose and wait" calibration needs first 3 retrospectives as training data. Address at Phase 5 start.

## Sources

### Primary (HIGH confidence)
- `/home/admin/Source/our-lady-book-pipeline/docs/ARCHITECTURE.md` — component diagrams and ADR summary
- `/home/admin/Source/our-lady-book-pipeline/docs/ADRs/001-004` — locked architectural decisions (mode-dial, scene-commit, testbed, book-first)
- `/home/admin/.npm-global/lib/node_modules/openclaw/docs/` — openclaw v2026.4.5 official docs
- `/home/admin/wipe-haus-state/openclaw.json` + workspaces — working reference install
- paul-thinkpiece-pipeline memory entries — vLLM GPU zombie, systemd ownership, cu130 + packing breakthrough
- Anthropic SDK v0.96.0 GitHub releases — Opus 4.7 confirmed 2026-04-16
- `our-lady-of-champion-brief.md`, `our-lady-of-champion-known-liberties.md` — thematic-spine and content-landmine source

### Secondary (MEDIUM-HIGH confidence)
- vLLM releases — 0.19+ CUDA 13 Blackwell support
- LanceDB PyPI — 0.30.2, 2026-03-31
- BGE-M3 2026 MTEB benchmarks — cross-referenced 3+ independent sources
- DOC arXiv 2212.10077 — hierarchical outline +22.5% plot coherence
- Self-Refine arXiv 2303.17651 — diminishing returns past ~3 regen iterations
- WritingBench, LLM-RUBRIC ACL 2024 — multi-dimensional critic calibration
- LLM-judge bias: Preference Leakage arxiv 2502.01534; Self-Preference arxiv 2410.21819
- 2025 RAG failure-mode literature (Ten Failure Modes, 23 RAG Pitfalls, RAGFlow)
- 2025 catastrophic-forgetting literature (OpenReview, ACL EMNLP)

### Tertiary (MEDIUM confidence)
- Commercial tool feature comparisons (Sudowrite, NovelCrafter, NovelAI) — vendor sources, cross-checked against independent reviews
- Narrative drift as a sampling property (Layte, Medium) — single practitioner post, consistent with general sampling theory
- Pydantic Logfire LLM observability — deferred candidate; not evaluated against specific JSONL schema

---
*Research completed: 2026-04-21*
*Ready for roadmap: yes*
