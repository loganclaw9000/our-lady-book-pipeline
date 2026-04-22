# Feature Research — Autonomous Long-Form Creative-Writing Pipeline (Testbed-Framed)

**Domain:** autonomous long-form fiction pipeline with fine-tuned local drafter + frontier critic + typed RAG + experiment telemetry
**Researched:** 2026-04-21
**Confidence:** MEDIUM-HIGH (architecture findings verified against multiple sources; testbed-specific features are MEDIUM — this axis is under-represented in commercial tools and therefore under-documented)

---

## Framing — Why "differentiator" means something different here

This is pipeline #1 of a family (book / blog / thinkpiece / short-story). The canonical commercial competitors (NovelCrafter, Sudowrite, NovelAI, HoloAI, AI Dungeon) optimize for **polish of creative output** so a human can click "generate" and get a usable paragraph. This pipeline optimizes for **autonomy + measured learning transfer to pipelines #2-N**, with a single human reader reviewing weekly digests. Therefore:

- **Table stakes** here = the minimum set without which the pipeline either can't run unattended for a night, can't produce output that passes a human eye, or can't learn from what it produced.
- **Differentiators** here = things that make this testbed better at **generating transferable experimental evidence** than a commercial tool. Observability + experiment tracking are first-class competitive advantages, not polish.
- **Anti-features** = things commercial tools ship because they have human-in-the-loop to clean up, but which would silently degrade output or generate false confidence in an autonomous pipeline.

This reframe is load-bearing. The rest of the doc assumes it.

---

## Table Stakes (without which the pipeline is useless)

| # | Feature | Why Required | Complexity | Notes / Dependencies |
|---|---------|--------------|------------|----------------------|
| 1 | **Scene-level drafter with temperature / top_p dialable per scene type** | Voice-FT local models are proven to degrade past ~1000w; varied scene types (action vs exposition vs dialogue) demand different sampling regimes or the model picks one mode and hurts the others. Industry standard (NovelCrafter, Sudowrite Muse, RecurrentGPT all expose sampling controls). | LOW | Config lives in `config/drafter.yaml`. Recommend starting with 3 scene-type profiles (narrative, dialogue, action) rather than per-scene hand-tuning. |
| 2 | **Frontier escape hatch ("Mode B")** | No non-frontier model 1-shots structurally complex beats (ADR-001). Without escape, pipeline hard-blocks on 20-30% of scenes for this book (Cholula stir, two-thirds reveal, Tenochtitlan siege). Every commercial tool has this (Sudowrite lets you pick model per call; NovelCrafter routes via BYO-API). | LOW | Just an Anthropic API call with voice samples in-context + mode tag in run event. |
| 3 | **Structured outline / beat-function awareness** | DOC (Yang et al. 2022) demonstrated +22.5% plot coherence from passing detailed outline hierarchy into each draft call vs end-to-end generation. The outline.md is already decomposed to 27 chapters × beat function — not using it is arson. | LOW-MEDIUM | Arc-position retriever in typed RAG covers this (RAG-02 in PROJECT.md). |
| 4 | **Lore-bible / codex retrieval** | NovelCrafter's Codex and Sudowrite's Story Bible are cited as the #1 differentiator in every comparison article — a fiction pipeline without one produces contradictory lore. With 10 bibles = ~250KB, this is non-negotiable. | MEDIUM | Typed RAG (5 retrievers) per ARCHITECTURE.md. |
| 5 | **Character / entity state tracking across chapters** | Every long-form AI writing tool treats this as critical and every one fails at implicit state (emotional shifts, belief changes) — Novarrium advertises "auto-extracts facts after every chapter" as a premium feature specifically because Sudowrite/NovelAI/NovelCrafter all require manual maintenance. Automating extraction is table stakes for an **autonomous** pipeline because no human will manually update entity cards nightly. | MEDIUM-HIGH | CORPUS-02 + entity-state retriever. Post-commit Opus extractor writing markdown cards is the pattern. |
| 6 | **Critic pass with structured output (per-axis or otherwise)** | Without a critic, drafts commit raw and errors compound across chapters (classic AI-novel failure mode — "got shorter, flatter, and more disconnected" per Amy Ma's medium post forcing GPT to write a novel). WritingBench and LLM-RUBRIC both demonstrate that structured multi-dimensional critique outperforms holistic pass/fail. | MEDIUM | CRITIC-01. JSON output is the only part that's load-bearing here; number of axes is a differentiator not a table stake. |
| 7 | **Issue-conditioned regeneration** | Regenerating a whole scene on any failure burns tokens and rarely targets the actual defect; targeted regen (Self-Refine pattern) is what makes the critic useful. Without it, you have a pass/fail gate with no repair mechanism. | MEDIUM | REGEN-01. Must take structured issue list as input; must have max-iteration cap (see anti-feature #1). |
| 8 | **Resume-from-crash / durable workspace state** | A 27-chapter autonomous run across weeks will crash. If state isn't durable, every crash is a silent corpus-state corruption risk (partial chapters in canon, half-indexed RAG). openclaw systemd workspaces already give this. | LOW | ORCH-01. Persistent workspace + atomic chapter commits. |
| 9 | **Scheduled / cron-driven execution** | "Autonomous" means the pipeline runs without Paul being at the keyboard. Nightly cron driving scene-generation is the whole point. | LOW | openclaw gateway handles this. |
| 10 | **Per-call structured event logging** | You cannot debug an autonomous pipeline that ran for 8 hours last night without a structured trace. This is table stakes for any LLM system in 2026 (OpenLLMetry, Arize, Braintrust all normalized this). | LOW | OBS-01. JSONL events with prompt hash, model, tokens, latency, caller context. |
| 11 | **Per-call token / cost accounting** | Without per-call cost, "budget blown" is a question you answer after the fact. Anthropic API spend needs weekly aggregation at minimum. | LOW | OBS-02 subsumes. |
| 12 | **Hard-block alerting (out-of-band to human)** | When the pipeline wedges (stuck regen loop, every scene failing critic, budget exhausted), Paul needs to know without reading the digest. Telegram channel already exists. | LOW | ALERT-01. |
| 13 | **Atomic commit unit (chapter, not scene)** | ADR-002. Partial chapters in canon confuse downstream readers (human + RAG retrievers) and cause re-indexing thrash. Every serious tool commits at chapter grain or similar. | LOW | Assembler + chapter-level critic gate the commit. |
| 14 | **RAG context cap / budget per draft call** | Feeding full corpus (~250KB) per call degrades drafter quality (thesis-005 will test; empirically well-established — "lost in the middle" literature). Every production RAG system caps retrieved context. | LOW | Bundler enforces ~30-40KB ceiling. |

**Table-stakes complexity total:** 14 features, dominated by LOW + MEDIUM. The pipeline architecture already accounts for all of these. Confidence that this list is complete: HIGH.

---

## Differentiators (this pipeline's competitive advantage as a testbed)

**Important re-emphasis:** for a testbed, differentiation is about **generating transferable experimental evidence** for pipelines #2-N and for the sibling `paul-thinkpiece-pipeline` FT training. It is NOT about polish, creative flair, or UX. Most of these differentiators would be dead weight in a commercial product.

| # | Feature | Value Proposition (testbed) | Complexity | Notes |
|---|---------|----------------------------|------------|-------|
| 1 | **Typed RAG (5 retrievers, not monolith)** | Gives critic axis-specific structured evidence to grade against ("entity retriever returned X; draft contradicts on Y") — this is what lets the critic produce actionable issue lists, not vague feedback. Thesis 005 tests it; if refuted, simplify later. Differentiates from Sudowrite/NovelCrafter (both use single retrieval). | MEDIUM-HIGH | 5 indexes: historical, metaphysics, entity-state, arc-position, negative-constraint. Hybrid BM25+vector is a proven pattern for this class of keyword-heavy corpus (per 2025 RAG production articles — BM25 explicitly called out as strong for "scripture-like" text). |
| 2 | **5-axis critic rubric with per-axis scores + issue lists persisted** | Collapsing to pass/fail discards 90% of the information the critic produced. WritingBench uses 14 dimensions; LLM-RUBRIC uses calibrated multi-dimensional scoring. Persisting per-axis enables thesis 004 (does decomposition drive better regens?). | MEDIUM | Rubric in `config/rubric.yaml`. 5 axes: historical / metaphysics / entity / arc / don'ts. Must include severity per issue, not just binary. |
| 3 | **Entity-state auto-extraction post-commit (structured cards)** | Unstructured RAG misses state-change signals; structured entity cards ("Andrés at Cempoala, possesses copper disc, has killed N, emotional state=...") give critic something to pattern-match. Thesis 003 tests catch rate on adversarial probes. Differentiates from every commercial tool (all require manual entity entry). | MEDIUM-HIGH | Opus subagent post-chapter-commit. Markdown cards in `entity-state/chapter_NN/*.md`. Keep schema stable — if it changes, old cards become incompatible. |
| 4 | **Thesis registry (open/closed) + thesis matcher** | This is the artifact that transfers learnings to pipelines #2-N and back to FT training. Without it, the testbed framing is just slogan. A thesis closed here ("5-axis rubric beats monolith by 20%+") becomes a pre-baked assumption for pipeline #2. | MEDIUM | `theses/open/` + `theses/closed/`. Frontmatter: hypothesis, test design, success metric, transferable artifact. Matcher is Opus reading retrospectives + events and proposing closures. |
| 5 | **Paired ablation harness** | Without A/B ablation on held-fixed corpus state, all claims about what works are testimonials. Harness must be able to run N scenes under variant-A vs variant-B with everything else pinned. All 5 open theses assume this harness exists. | MEDIUM | `runs/ablations/`. Tag events with ablation_id so traces don't pollute production metrics. |
| 6 | **Retrospective auto-writer (Opus, post-chapter)** | Metrics see "critic axis-3 failed 4 times" — retrospectives see "the voice model keeps flattening Itzcoatl's dialogue when the beat is political". Qualitative LLM-written observations catch patterns metrics can't see. | LOW-MEDIUM | Opus reads chapter + its run events + prior retrospectives. `retrospectives/chapter_NN.md`. |
| 7 | **Voice fidelity scoring via embedding cosine against reference set** | Drift detection is standard in ML observability (Arize, Evidently). For a voice-FT pipeline, voice drift is the silent killer — the critic could pass all 5 axes and the prose still wanders off-voice. Embedding cosine against 20-30 curated anchor passages is a cheap scalar check. | LOW-MEDIUM | Reference passages from the FT training corpus. Track per-scene; aggregate per-chapter in ledger. Flag drift > threshold. |
| 8 | **Mode-B rate as first-class metric in weekly digest** | Rate rising = voice model losing ground or being asked too much; falling = pipeline learning which beats it can handle. The rate is the signal; without surfacing it, the mode-dial architecture is invisible. | LOW | Already in OBS-02. Digest generator surfaces it weekly. |
| 9 | **Scene-aware / recency-weighted retrieval** | Prior scenes in the same chapter should weight higher than chapters 20 chapters ago. "Lost in the middle" compounds if retrieval doesn't respect recency. Simple pattern: weight decay by chapter distance for entity / arc retrievers, no decay for metaphysics / historical (those are timeless). | LOW-MEDIUM | Implement in bundler, not retrievers (keeps retrievers stateless). |
| 10 | **Config pinning + versioning (voice checkpoint, prompt templates, rubric)** | ADR-003. Changing a prompt template mid-run and then attributing a quality shift to anything else is self-deception. Every config that affects output must be version-pinned and logged per run. | LOW | `config/voice_pin.yaml`, `config/prompts/` hash-pinned, `config/rubric.yaml`. Emit versions with every event. |
| 11 | **Pre-flagging structurally-complex beats for Mode B from the start** | ADR key-decision. Battle staging / multi-POV convergence / dense theological argument are known to exceed voice-FT reach; burning regen cycles on them to "discover" this is waste. Pre-flag cuts Mode-B ambiguity and makes Mode-B rate a cleaner metric. | LOW | Static list in `config/mode_b_beats.yaml`, 3 flagged beats listed in ARCHITECTURE.md §4 already. Revisit after first pass. |
| 12 | **Cross-pipeline learning transfer artifacts** | When a thesis closes here, its transferable artifact (config recommendation / architectural lesson / known failure mode / corpus-curation implication) must be structured so pipeline #2 can consume it mechanically, not just as prose. | LOW-MEDIUM | Closed thesis frontmatter includes `transferable_artifact` field (already in theses/open/00*.md). Format: markdown with a specific schema. |
| 13 | **Per-call caller-context logging (who called this LLM, why)** | Without caller context, a JSONL event log is just noise. "This was a regen triggered by axis-3 failure on scene 2 of chapter 7" is the minimum context needed to reconstruct a cause-chain. | LOW | Subsumed in OBS-01 but call it out — easy to under-specify. |
| 14 | **Digest summarization (Opus) of week's events into markdown** | Raw JSONL events don't scale to human review. Weekly digest compresses: chapters committed, voice fidelity trend, Mode-B rate, closed/new theses, cost, blockers. This is the single human-facing interface. | LOW-MEDIUM | DIGEST-01. Template-driven; Opus fills in qualitative sections. |
| 15 | **Background benchmark (Mode-B-only one-shot chapter)** | Non-blocking side experiment (ADR-001). Every N chapters, have Opus one-shot the next 3 chapters from outline; critic both. Answers "is frontier-1shot approaching voice-FT quality for longer units?" — informs whether voice-FT investment keeps scaling. Zero impact on canon. | LOW-MEDIUM | Runs tagged as ablation, doesn't touch canon. |

**Differentiator complexity total:** 15 features, heavy on MEDIUM. This is where the 2-3× engineering cost (per ADR-003) gets spent. If budget pressure forces cuts, the order to cut from is: #15 (benchmark) → #9 (recency weighting) → #11 (pre-flagging) before touching #1-8.

---

## Anti-Features (deliberately NOT building — with warnings grounded in existing systems' failure modes)

| # | Anti-Feature | Why It Sounds Useful | What Actually Happens | What To Do Instead |
|---|--------------|----------------------|------------------------|--------------------|
| 1 | **Unbounded regen loops / self-refine without iteration cap** | "Just keep trying until the critic passes." | Self-Refine literature (Madaan et al. 2023) shows diminishing returns past ~3 iterations; without a cap, the pipeline gets stuck on hard scenes, burns tokens, and eventually the LLM starts "complying-hallucinating" — producing output that games the critic's rubric without actually solving the underlying issue. HN reports of AI-Dungeon / NovelAI users describe this as "it agrees with me and then writes the same mistake again." | Hard cap `R` on Mode-A regens (REGEN-02 sets this to 3-5). After R, escalate to Mode B (which can itself fail → hard-block alert). Never "one more try." |
| 2 | **Feed the full corpus (~250KB) every call "so the model has context"** | "Models have long context now, just give them everything." | Critic and drafter quality degrades past ~30-40KB of retrieved content (thesis-005 tests this; empirically well-established — "Lost in the Middle", Liu et al. 2023). Model starts latching onto irrelevant details, hallucinating connections between unrelated bible entries, ignoring the specific beat function. Also: 5-10× the token cost. | Typed RAG with bundler cap ~30-40KB. If typed RAG underperforms (thesis refuted), revisit — but don't skip the test. |
| 3 | **"One rubric to rule them all" — monolith critic with holistic score** | "Simpler, one number to track." | Monolith output is either vague ("this scene feels off") or fragmented — regenerator can't target the actual defect. WritingBench / LLM-RUBRIC both moved from monolith to multi-axis for exactly this reason. HoloAI / AI Dungeon reviews consistently cite "AI forgets things" as the #1 complaint, which is often really "the critic-equivalent had no way to tell the drafter WHAT it forgot." | 5-axis rubric (thesis 004 tests whether it beats monolith; if inconclusive, keep the decomposition for regen-targeting even if mean scores are similar). |
| 4 | **Auto-promotion ladder ("scene → chapter → book as model proves itself")** | "Discover the pipeline's ceiling by measurement." | Confuses capability with track record (ADR-001). No non-frontier model 1-shots clean prose >1000w; promotion forces either degraded output or a silent switch to frontier (losing voice). The ladder is a lie the pipeline tells itself about its own capabilities. | Mode dial — voice default, frontier escape. Mode-B rate as explicit metric, not hidden. Preserve the "is frontier-1shot getting better?" question as a separate non-blocking benchmark. |
| 5 | **Real-time / streaming / live-collaborative editing** | "Modern writing tools have this." | Pipeline is autonomous + async (weekly digest review). Building streaming UI is weeks of work that adds zero to the drafting quality, observability, or learning transfer. Sudowrite / NovelCrafter have this because they sell to writers sitting at a keyboard — wrong audience. | Markdown digests as the v1 interface (explicitly OOS per PROJECT.md). Defer dashboard until digest-reading friction is proven. |
| 6 | **Book-voice FT branch before pipeline #1 ships** | "Thinkpiece voice won't transfer; train a book-specific model first." | This is thesis 001's entire purpose — TEST whether thinkpiece voice transfers before spending weeks on a book-FT run. Training a new FT branch on speculation is expensive and the data may not even be curated (paul-thinkpiece-pipeline v6 is currently 10,751 pairs, none are fiction). Premature optimization. | Ship with thinkpiece-voice pin. Measure voice fidelity + critic voice-axis scores over Act 1 (9 chapters). If thesis refutes transfer, THEN invest in book-FT branch with measured requirements. |
| 7 | **Generic writing-pipeline kernel extracted first** | "Build the abstraction, make this book a thin config." | ADR-004. Premature abstraction tax: book-specific assumptions (chapter-commit grain, 5-axis rubric, beat-function retrieval) encoded as "universal" that won't survive contact with blog pipeline. Zero calibration against real variance. | Build book pipeline with clean internal boundaries. Extract kernel when pipeline #2 has written requirements + at least one confirmed divergence. |
| 8 | **Dashboard / web UI for digest review** | "GUIs are nicer than markdown." | Paul is single-user, minimal involvement. Weekly markdown digest is probably ~3KB and takes 5 min to read. Web UI is weeks of work supporting a use-case that may not need it. If digest-reading becomes friction, surface that as a real signal, not a speculative one. | Markdown digest in `digests/week_YYYY-WW.md`. If friction proven, revisit. |
| 9 | **Auto-committing scenes to canon (scene-grain commit)** | "Faster feedback loop, less buffering." | Partial chapters in canon break re-indexing (RAG sees incoherent state), chapter-level critic can't run (no cross-scene checks), and if a late scene fails critic after earlier ones committed, you have a half-chapter mess to unwind (ADR-002). | Scene buffer pre-commit; chapter-level critic gates the atomic commit; re-indexing fires once per chapter. |
| 10 | **"More creative" temperature dialing (temp > 1.0, top_p > 0.95)** | "Higher temp = more creative outputs, which is what fiction needs." | High temp on FT models corrupts the voice signal the FT was supposed to preserve. Long-form coherence also collapses — "drift" is a statistical property of sampling at high temp, worse the longer you generate (per Layte's narrative-drift post). Stories wander. | Start conservative (temp 0.7-0.8 narrative, 0.9 dialogue). If output feels flat, check rubric + retrieval pack first — creativity issues are usually constraint-underspecified, not temp-too-low. |
| 11 | **Auto-editing / line-polish pass in pipeline** | "Make output publication-ready." | PROJECT.md explicitly OOS. Line-edit passes are where LLMs love to blandify — removing Paul's voice idiosyncrasies in the name of "cleanup" (famous failure mode across every fiction-AI tool). Also, trying to enforce publication-ready output confuses the quality gate with editorial polish. | Pipeline produces drafts. Final line-editing is manual/human. Drafts should be recognizably voiced, not publishable. |
| 12 | **Prompt-template edits without versioning** | "Just tweaking wording, no big deal." | A prompt template edit is a silent config change. If you tweak the critic prompt on Monday and voice-fidelity score drops on Tuesday, was it the prompt or the drafter? Without hash-pinning + per-event logging, you've destroyed the ability to attribute. This is the #1 way ML observability gets silently sabotaged. | All prompts in version-controlled files, hashed, hash emitted per event. Any edit is a logged change. |
| 13 | **Silent fallback from Mode A to Mode B** | "If voice-FT fails, just retry with frontier. User won't notice." | Hides the Mode-B rate (ADR-001). Hides which beats the voice model can't handle. Hides whether voice-FT investment is paying off. You've voluntarily blinded yourself on the single most important metric for pipeline-#2 decision-making. | Mode-B is always an explicit observation: `mode=B, reason=regen_budget_exceeded|pre_flagged|critic_escalation`. Surfaced in every event and every digest. |
| 14 | **Letting the model choose its own retrieval (agent-style tool-calling)** | "Modern agentic RAG lets the model query whatever it needs." | Two problems. (1) Adds latency + token cost per query hop. (2) The model's choice is non-deterministic, making ablation impossible ("was the quality change from the rubric or because the drafter queried a different retriever this time?"). Testbed framing demands reproducibility. | Deterministic typed RAG: scene request → bundler → fixed 5 retrievers → fixed pack assembly. Agentic retrieval is a thesis, not a default. |
| 15 | **Human-in-the-loop gates per scene / per chapter** | "Let Paul approve before commit." | Negates the whole autonomous premise (PROJECT.md: "minimal hands-on involvement once running"). If the pipeline needs approval per chapter, Paul is doing 27 approvals over a draft cycle — back to Sudowrite with extra steps. | Hard-block alerts only (stuck regen, rubric conflict, budget blown, voice drift past threshold). Everything else auto-commits and shows up in weekly digest. |

**Anti-feature total:** 15. The first 3 (unbounded regen, full-corpus context, monolith critic) are the most dangerous — all three sound "simpler" and all three will silently produce bad output.

---

## Testbed-Specific Features (unique to pipeline #1 as research platform)

These warrant their own section because they don't map cleanly onto "table stakes" vs "differentiator" — they're the testbed's reason for existing. Without these, this is just a novel-drafting pipeline that happens to log things; with them, it's an experiment platform that happens to produce a novel.

| Feature | What It Captures | Dependencies | Consumer |
|---------|------------------|--------------|----------|
| **Hypothesis registry (open/closed)** | Open questions → falsifiable tests with success metrics. 5 seed theses already written (001-005). | Retrospective writer proposes candidates; ablation harness produces evidence; thesis matcher closes. | Next FT run, pipeline #2, future kernel. |
| **Retrospective auto-writing** | Qualitative LLM observation of patterns metrics miss ("voice drifts toward essay-register on dialogue-heavy scenes"). | Chapter-commit trigger; Opus call reading chapter + events + prior retros. | Thesis candidates; digest synthesis; next-FT corpus-curation guidance. |
| **Paired ablation harness** | A/B runs with everything-else-pinned, measurable deltas. | Config versioning; deterministic retrieval; tagged events. | Evidence for/against open theses. |
| **Cross-pipeline learning-transfer artifacts** | Structured output of closed theses (config recommendations / architectural lessons / known failure modes / corpus-curation implications). | Closed thesis frontmatter schema. | Pipeline #2 starts from lessons, not zero; `paul-thinkpiece-pipeline` next FT run config informed by production evidence. |
| **Voice drift detection (embedding cosine vs anchor set)** | Quantitative scalar for the one thing commercial-tool critics don't check (voice-model is off-voice even when critic passes content axes). | 20-30 curated anchor passages from FT training corpus; embedding index. | Hard-block alert threshold; digest trend line; thesis 001 evidence. |
| **Mode-B rate as headline metric** | Signal for voice-FT reach (rising = losing ground; stable-low = healthy). | Per-scene mode tag; weekly aggregation. | Thesis 002; next-FT investment decision. |
| **Per-axis critic score ledger (not just pass/fail)** | Axis-level trend lines across chapters — e.g., "entity axis has been failing 2× more since Ch 12" catches regressions invisible to pass-rate. | Critic JSON output schema. | Thesis 004; weekly digest anomaly surfacing. |
| **Thesis-aging hygiene** | Weekly digest auto-surfaces theses open >30 days with no evidence accrued (candidates for pruning or rewriting). | Thesis frontmatter `opened` dates + event log. | Keeps registry from rotting (per ADR-003). |

**Why this gets its own category:** every commercial tool compared against (Sudowrite, NovelCrafter, NovelAI, HoloAI, AI Dungeon, Novarrium) has **zero** of these. Commercial tools are optimized for human-in-the-loop writers; they have no reason to instrument themselves for cross-tool learning transfer. Academic story-generation projects (RecurrentGPT, DOC, Long-Novel-GPT) publish a single paper and move on — no multi-project lineage to transfer learnings into. This axis is a genuine gap that the testbed framing fills.

---

## Feature Dependencies

```
Cron orchestration (ORCH-01)
    └──enables──> Autonomous scene loop (LOOP-01)
                       ├──requires──> RAG Bundler (RAG-01, RAG-02)
                       │                   ├──requires──> Corpus ingest (CORPUS-01)
                       │                   └──requires──> Entity extractor (CORPUS-02)
                       │                                       └──requires──> Post-chapter commit trigger
                       ├──requires──> Voice drafter (DRAFTER-01)
                       │                   └──requires──> Voice checkpoint pin
                       ├──requires──> Critic (CRITIC-01, CRITIC-02)
                       │                   └──requires──> Structured rubric config
                       ├──requires──> Regenerator (REGEN-01, REGEN-02)
                       │                   └──requires──> Issue-list input contract
                       └──requires──> Mode-B escape (DRAFTER-02)

Event log (OBS-01) ──foundation──> Everything else
    └──enables──> Ablation harness (TESTBED-01)
                      └──enables──> Thesis evidence
    └──enables──> Digest (DIGEST-01)
    └──enables──> Voice drift detection
    └──enables──> Hard-block alerting (ALERT-01)

Thesis registry (THESIS-01)
    ├──fed by──> Retrospective writer (RETRO-01)
    ├──fed by──> Ablation runs (TESTBED-01)
    └──outputs──> Transferable artifacts → pipeline #2 / FT training

Chapter-atomic commit (implicit in LOOP-01)
    ├──required-by──> RAG re-index
    ├──required-by──> Entity extractor
    ├──required-by──> Retrospective writer
    └──required-by──> Chapter-level critic
```

### Dependency Notes

- **Typed RAG requires entity extractor output:** Chapter K+1 drafter needs entity state from chapter K's auto-generated cards. Extractor must run before re-index, which must run before Chapter K+1 first scene call. This serializes the pipeline at chapter boundaries — fine, matches ADR-002.
- **Event log is foundational:** Every differentiator (ablation, digest, drift detection, thesis evidence) reads from the event log. If event log schema changes, all downstream consumers break. Treat schema like a public API.
- **Mode-B escape requires a regen budget:** Without R (max regens), Mode-A never escalates; with R=0, every scene goes to Mode B. R is a dial, not a boolean.
- **Retrospective writer and thesis matcher are separable:** retro can run without matcher (just produces prose). Matcher without retro is possible but loses the qualitative signal. Build retro first; matcher can be semi-automated initially (Opus proposes, Paul confirms) until heuristics prove reliable.
- **Voice drift detection requires anchor corpus:** 20-30 passages curated from FT training data. This is a one-time setup cost but must happen BEFORE the first chapter commits or baseline is lost.

---

## MVP Definition — "Phase Launch" (not commercial launch)

### Launch With (v1 — first 3 chapters end-to-end autonomous)

Minimum to validate the concept: can the pipeline draft + critic + regen + commit a single chapter without human intervention, logging enough to learn from it?

- [ ] **FOUNDATION-01, CORPUS-01, CORPUS-02, RAG-01, RAG-02** — typed retrieval + entity extraction working.
- [ ] **DRAFTER-01, DRAFTER-02** — Mode A + Mode B both callable.
- [ ] **CRITIC-01** — 5-axis rubric returning structured JSON.
- [ ] **REGEN-01, REGEN-02** — issue-conditioned regen with R cap + Mode-B escalation.
- [ ] **LOOP-01** — full scene-to-commit autonomous loop.
- [ ] **OBS-01, OBS-02** — event log + metric ledger.
- [ ] **ORCH-01** — openclaw cron driving nightly runs.
- [ ] **ALERT-01** — Telegram hard-block alerts.

Rationale: this is the minimum where a single chapter can commit autonomously AND produce learnable signal. Without OBS-01+OBS-02, the pipeline could complete chapters but teach nothing.

### Add After First 3 Chapters Validate (v1.x)

Features to add once core loop is proven stable for 3 consecutive chapter commits without human intervention.

- [ ] **CRITIC-02** — chapter-level critic (can be stubbed initially as pass-through; enables thesis evidence).
- [ ] **RETRO-01** — retrospective writer (once 3 retros exist, thesis matcher becomes useful).
- [ ] **THESIS-01** — thesis registry + matcher.
- [ ] **DIGEST-01** — weekly digest generator.
- [ ] **Voice drift detection** — anchor corpus + scoring.
- [ ] **Pre-flagging** — static Mode-B beats list (ARCHITECTURE.md §4 has the 3 for Act 1 already).

Rationale: these are the features that convert the pipeline from "drafts autonomously" to "drafts autonomously AND teaches."

### Future Consideration (v2+)

- [ ] **TESTBED-01 ablation harness** — only needed once at least one thesis has enough production evidence to motivate a targeted A/B. Before then, natural-experiment evidence is probably sufficient for initial theses.
- [ ] **Background Mode-B-only benchmark** — run once 9+ chapters have committed, so there's enough signal to compare against.
- [ ] **Recency-weighted retrieval** — only if RAG misses on "prior scene state didn't surface" — natural experiment will show this.
- [ ] **Agentic / LLM-driven retrieval** — research direction, possibly a thesis, not a v1 default.
- [ ] **Book-voice FT branch** — ONLY if thesis 001 refutes thinkpiece-voice transfer.
- [ ] **Web dashboard for digest review** — ONLY if markdown digest friction is empirically demonstrated.
- [ ] **Kernel extraction** — when pipeline #2 has written requirements (ADR-004).

---

## Feature Prioritization Matrix (testbed framing)

"User value" below = **testbed value** (learning transfer, observability fidelity, autonomy), not creative-output polish.

| Feature | Testbed Value | Cost | Priority |
|---------|---------------|------|----------|
| Event log (OBS-01) | HIGH | LOW | P1 |
| Metric ledger (OBS-02) | HIGH | LOW | P1 |
| Typed RAG (5 retrievers) | HIGH | MEDIUM-HIGH | P1 |
| Scene drafter + Mode dial | HIGH | LOW-MEDIUM | P1 |
| 5-axis critic + issue lists | HIGH | MEDIUM | P1 |
| Issue-conditioned regen + cap | HIGH | MEDIUM | P1 |
| Entity extractor + state cards | HIGH | MEDIUM-HIGH | P1 |
| Chapter-atomic commit + re-index | HIGH | LOW | P1 |
| Cron orchestration | HIGH | LOW | P1 |
| Hard-block alerting | HIGH | LOW | P1 |
| Config pinning / prompt hashing | HIGH | LOW | P1 |
| Mode-B rate in digest | HIGH | LOW | P1 (just a surface of data already logged) |
| Retrospective writer | HIGH | LOW-MEDIUM | P2 |
| Voice drift detection | HIGH | LOW-MEDIUM | P2 |
| Thesis registry + matcher | HIGH | MEDIUM | P2 |
| Digest generator | HIGH | LOW-MEDIUM | P2 |
| Chapter-level critic | MEDIUM | LOW | P2 |
| Pre-flagging Mode-B beats | MEDIUM | LOW | P2 |
| Paired ablation harness | MEDIUM | MEDIUM | P3 |
| Background Mode-B-only benchmark | MEDIUM | LOW-MEDIUM | P3 |
| Recency-weighted retrieval | LOW-MEDIUM | LOW-MEDIUM | P3 |
| Agentic retrieval (thesis) | LOW | HIGH | P3 (possibly never) |

Pattern: P1 is ~12 features dominated by LOW-MEDIUM cost — the MVP loop is tractable. P2 is the learning-transfer layer. P3 is research-direction territory.

---

## Competitor Feature Analysis

| Feature | NovelCrafter | Sudowrite | NovelAI / HoloAI / AI Dungeon | This Pipeline |
|---------|--------------|-----------|-------------------------------|---------------|
| Lore/codex retrieval | Yes (Codex, manual entries) | Yes (Story Bible, manual entries) | Yes (World Info, manual) | Yes (5 typed retrievers, auto-extracted entity cards for dynamic state) |
| Character state tracking | Manual | Manual | Manual | Auto-extracted per-chapter + retrieval |
| Multi-model routing | BYO OpenAI key | Muse (FT for fiction) + Claude/GPT | Proprietary models | Local FT (voice) + Anthropic (critic/Mode-B), with explicit mode tags |
| Outline-driven drafting | Yes (with Codex) | Yes (Story Bible genre templates) | Limited | Yes (beat-function-per-chapter retriever) |
| Critic / quality gate | No (human reviews) | No (human reviews) | No | Yes (5-axis structured critic, per-axis scores persisted) |
| Auto-regeneration on critic-fail | N/A (no critic) | N/A | N/A | Yes (issue-conditioned, R-capped) |
| Autonomous scheduled runs | No (interactive) | No (interactive) | No (interactive) | Yes (openclaw cron) |
| Per-call event / cost log | Minimal | Minimal | Minimal | Full JSONL per-call |
| Ablation / experiment harness | No | No | No | Yes (P3, gated behind MVP) |
| Hypothesis / thesis registry | No | No | No | Yes |
| Retrospective auto-writing | No | No | No | Yes |
| Voice drift scoring | No | No (they use their own FT, don't expose) | No | Yes (embedding cosine vs anchor set) |
| Kernel / reuse across projects | N/A (single-product) | N/A | N/A | Yes (planned for pipeline #2 via extraction) |
| Primary audience | Writers at keyboard | Writers at keyboard | Hobbyists / roleplayers | Single researcher, async weekly review |

**Reading of the competitive landscape:** commercial tools treat fiction generation as a *human amplifier* — the writer steers, the tool executes. This pipeline treats it as an *autonomous experiment* — the writer is a digest reviewer, the pipeline is the agent + the subject of study. These are orthogonal product categories, not competitors. The right mental model: this pipeline is closer in spirit to an MLOps platform (Weights & Biases, Arize) that happens to produce a novel as its artifact.

The academic projects (RecurrentGPT, DOC, Long-Novel-GPT, DOME, Re3) are closer neighbors structurally (hierarchical outlining, memory mechanisms, multi-agent workflows), but none ship as a persistent, observability-first testbed across multiple pipelines — they're single-paper artifacts. The closest living analog is probably a research group's internal harness, and those aren't public.

---

## Sources

- [Sudowrite vs. NovelCrafter comparison (Sudowrite blog)](https://sudowrite.com/blog/sudowrite-vs-novelcrafter-the-ultimate-ai-showdown-for-novelists/) — MEDIUM confidence (vendor source, but feature parity claims consistent across independent reviews)
- [Best AI for Writing Fiction 2026 (mylifenote)](https://blog.mylifenote.ai/the-11-best-ai-tools-for-writing-fiction-in-2026/) — MEDIUM, feature-comparison aggregation
- [Kindlepreneur NovelCrafter review](https://kindlepreneur.com/novelcrafter-review/) — MEDIUM, identifies missing feature gaps
- [Nerdynav Sudowrite Review](https://nerdynav.com/sudowrite-review/) — MEDIUM, hands-on testing
- [DOC: Detailed Outline Control (arXiv 2212.10077)](https://arxiv.org/html/2212.10077) — HIGH, foundational paper for hierarchical outline → story generation (+22.5% plot coherence)
- [RecurrentGPT GitHub](https://github.com/aiwaves-cn/RecurrentGPT) — HIGH, canonical reference for recurrent long-form generation
- [Long-Novel-GPT GitHub](https://github.com/MaoXiaoYuZ/Long-Novel-GPT) — MEDIUM, hierarchical outline approach as alternative reference
- [Awesome-Story-Generation paper list](https://github.com/yingpengma/Awesome-Story-Generation) — HIGH, curated literature review
- [WritingBench (emergentmind)](https://www.emergentmind.com/topics/writingbench) — HIGH, multi-dimensional fiction evaluation framework
- [LLM-Rubric calibrated multi-dimensional eval (ACL 2024)](https://aclanthology.org/2024.acl-long.745.pdf) — HIGH, 14-dimension rubric approach
- [Self-Refine: Iterative Refinement with Self-Feedback (arXiv 2303.17651)](https://arxiv.org/abs/2303.17651) — HIGH, establishes diminishing returns in iterative refinement (~3 iterations)
- [Reflexion (Prompting Guide)](https://www.promptingguide.ai/techniques/reflexion) — MEDIUM, linguistic self-reflection pattern + caveats
- [Amy Ma — What I Learned by Forcing AI to Write a Novel (Medium)](https://medium.com/data-science-collective/what-i-learned-about-ai-by-forcing-it-to-write-a-novel-efe7e67b4fa1) — MEDIUM, practitioner failure-mode post-mortem
- [Book-Agent pipeline (Level1Techs forums)](https://forum.level1techs.com/t/my-ai-powered-novel-writing-pipeline-book-agent-generating-epistemically-controlled-long-form-fiction/243193) — MEDIUM, hobbyist autonomous pipeline writeup with real failure modes
- [Generating Narratives (Richard Layte, Medium)](https://medium.com/@rich.layte/generating-narratives-00356e4a73b4) — MEDIUM, narrative drift as a sampling property
- [OpenLLMetry (traceloop GitHub)](https://github.com/traceloop/openllmetry) — HIGH, OpenTelemetry instrumentation standard for LLM calls
- [LLM Observability Tutorial (Patronus AI)](https://www.patronus.ai/llm-testing/llm-observability) — MEDIUM, observability components enumeration
- [Evidently AI — Embedding drift detection](https://www.evidentlyai.com/blog/embedding-drift-detection) — HIGH, cosine-distance drift detection pattern
- [BM25 + hybrid search for RAG (Redis blog)](https://redis.io/blog/full-text-search-for-rag-the-precision-layer/) — MEDIUM, hybrid retrieval pattern, specifically calling out BM25 strength on scripture-like text
- [Production RAG with hybrid search + reranking (Medium)](https://machine-mind-ml.medium.com/production-rag-that-works-hybrid-search-re-ranking-colbert-splade-e5-bge-624e9703fa2b) — MEDIUM, production patterns
- [CS4 — Measuring LLM creativity via constraint specificity (arXiv 2410.04197)](https://arxiv.org/html/2410.04197v1) — HIGH, over-constraint / creativity tradeoff
- PROJECT.md, ARCHITECTURE.md, ADRs 001-004, theses/open/001-005 (in-repo source of truth) — HIGH

---

*Feature research for: autonomous long-form creative-writing pipeline (testbed for writing-pipeline family)*
*Researched: 2026-04-21*
*Confidence: MEDIUM-HIGH overall; testbed-axis MEDIUM (under-documented in commercial/academic corpus, so conclusions partly derived by composition rather than citation)*
