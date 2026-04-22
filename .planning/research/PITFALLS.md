# Pitfalls Research — our-lady-book-pipeline

**Domain:** autonomous LLM-based long-form creative-writing pipeline (FT local drafter + frontier critic + typed RAG + experiment telemetry), dual-purpose as testbed + real novel producer.
**Researched:** 2026-04-21
**Confidence:** MEDIUM-HIGH (grounded in project architecture + ADRs + open theses, cross-checked against 2025 RAG/LLM-judge failure-mode literature; some pitfalls are project-specific and cannot be verified externally)

---

## Orientation

This pitfall inventory is organized by the 10 failure-mode dimensions specified in the research prompt, plus cross-cutting sections (technical debt, "looks done but isn't", recovery, and a phase-mapping table). Each pitfall has:

- **What goes wrong** — concrete failure
- **Why it happens** — root cause
- **Warning signs** — 3+ specific signals (telemetry / test / retrospective / digest)
- **Prevention** — actionable architectural or operational guardrail
- **Phase to address** — which roadmap phase owns preventing it

Phase labels used throughout correspond to the planned pipeline phases: `foundation` (scaffold, config, obs baseline), `corpus+rag` (typed indexes, retrievers, bundler), `drafter` (Mode-A vLLM + Mode-B Anthropic), `critic` (5-axis rubric + structured JSON), `regen` (issue-conditioned rewrite + escalation), `orchestration` (openclaw cron + workspace + alerts), `observability` (event log + metric ledger + thesis registry + retrospectives + digest), `ablation` (testbed harness), `final` (end-to-end book production + extraction signal).

---

## 1. Voice-fidelity failure modes (Mode-A drafter)

### V-1: Silent register collapse (thinkpiece voice → bland-fiction voice)

**What goes wrong:** Voice-FT checkpoint trained on essay/blog prose is asked to write historical fiction. Under prompt pressure (dialogue, sensory staging, dense battle choreography), the model silently falls off its training distribution and produces competent-but-generic narrator prose. Diction markers (em-dash rhythm, numeric specificity, analytic asides) disappear. Critic's "voice" axis scores PASS because the prose is readable, but the distinctive Paul-ness is gone.

**Why it happens:** Paul's thinkpiece corpus contains approximately zero dialogue staging, limited sensory description, and no sustained narrative arc. The model has no trained priors for these contexts, so it defaults to the weakest general capability — which happens to look "fine" to a critic prompted only for voice similarity rather than voice presence.

**Warning signs:**
- *Telemetry:* voice-fidelity embedding cosine (thesis 001's metric) drops >0.05 between chapters that are high-dialogue vs low-dialogue; per-scene variance in voice score widens as Act 1 progresses.
- *Retrospective:* retrospective writer notes "this chapter read smoother but less distinctive" without specific examples — that is the pattern. Generic praise is the symptom.
- *Ablation:* a 5-sample Opus-with-voice-samples scene vs Mode-A scene produces outputs the critic cannot reliably distinguish on voice axis.
- *Test:* anchor set of 20-30 Paul passages gets stylistically closer to Mode-A scene embedding only on essay-like passages (thinkpiece-adjacent scenes); dialogue-dense scenes cluster separately.

**Prevention:**
- Voice-fidelity metric in `observability` from scene 1, not as a v2 polish. Thesis 001 is blocker-grade, not aspirational.
- Two-tier voice axis in critic: "voice similarity" (is it Paul-ish?) AND "voice presence" (does it have Paul-specific markers — em-dash cadence, numeric specificity, structural asides?). A bland-competent draft fails presence even if similarity passes.
- Curate a **voice reference set** with sub-genres tagged: essay / dialogue-heavy / sensory / meta-analytic. Report per-sub-genre similarity, not just global.
- Pre-flag high-dialogue-density beats (two-thirds revelation, Malintzin translation scenes) as Mode-B-eligible with low threshold rather than paying regen cost to chase voice on a distribution the model was never trained for.

**Phase to address:** `drafter` (instrument voice metric at drafter commit) + `critic` (two-tier voice axis) + `observability` (per-sub-genre voice panel in digest).

---

### V-2: Training-data memorization masquerading as voice transfer

**What goes wrong:** The voice-FT model emits thinkpiece-shaped fragments (a paragraph about datasets, a numeric aside about model capability, a blog-like opener) verbatim or near-verbatim from its training set. These fragments land inside historical-fiction scenes. They sound "exactly like Paul" because they ARE Paul — copied, not generalized. Critic's voice axis rates this very high because embedding similarity is near 1.0. It is actually catastrophic.

**Why it happens:** The thinkpiece corpus is small (~10k clean pairs per the sibling project). FT on small corpora with many epochs (v3/v3.1 iterations) produces memorization. When the model is prompted out-of-distribution (a 16th-century battle scene), it retreats to nearest memorized neighborhoods.

**Warning signs:**
- *Telemetry:* n-gram overlap with training corpus >5% (tunable) on any drafted scene. Flag any scene with a 12-gram match against the training set.
- *Telemetry:* voice-fidelity score is *too high* — >0.95 cosine is more suspicious than 0.75, because anything that close is likely retrieval, not synthesis.
- *Retrospective:* retrospective writer flags "this sentence sounds like it belongs in a different genre" — that is the memorization bleeding through.
- *Test:* random Mode-A scenes spot-checked by grep against `paul-thinkpiece-pipeline/v3_data/train_filtered.jsonl` — any 12-gram hit is a P1 bug.

**Prevention:**
- `observability` emits n-gram overlap against training corpus for every Mode-A output. `critic` has a hard-block rule: any scene with 12-gram overlap >0 against training fails commit, regardless of other scores.
- Voice-fidelity gate should be a band (0.60–0.88 target), not a floor. Too-high is a failure mode.
- Run an adversarial probe at end of `drafter` phase: prompt the model with an explicit historical-fiction scene request and search outputs for training-corpus bleed. If present, consider LoRA rank reduction or add fiction exemplars to future FT.

**Phase to address:** `drafter` (memorization gate in drafter-side pre-commit check) + `critic` (hard-block rule) + `observability` (n-gram overlap panel).

---

### V-3: Voice checkpoint pin drift / silent swap

**What goes wrong:** `paul-thinkpiece-pipeline` produces a new checkpoint (v7, v8). Paul updates `config/voice_pin.yaml` to try it. The book pipeline silently re-drafts Act 1 scenes under the new checkpoint during ongoing runs, contaminating the voice-fidelity baseline. OR: a vLLM restart loads a different checkpoint than the pin specifies because of a symlink bug, and nobody notices for a week.

**Why it happens:** Checkpoints are large files, loaded by path, without hash verification. pgvector/lancedb indexes don't care which model produced the draft. Event log records `model=voice-ft` but not `checkpoint=<sha256>`.

**Warning signs:**
- *Telemetry:* voice-fidelity score jumps >0.05 between consecutive chapters for no obvious content reason.
- *Event log:* `checkpoint_sha` field is missing or same-valued across a pin change.
- *Retrospective:* chapter K retrospective notes "voice feels shifted from chapter K-1" — that is a pin slip.

**Prevention:**
- `config/voice_pin.yaml` contains checkpoint path AND sha256 AND expected first-token logit fingerprint. Drafter boots refuse to serve if hash mismatches.
- Every event log entry records `checkpoint_sha` (not just model name). Digest flags any entry where sha differs from pin.
- Pin changes are explicit migration events: cut a new run tag, do not mix pre/post-pin scenes in the same voice-fidelity trend.

**Phase to address:** `foundation` (pin schema) + `drafter` (boot-time hash check) + `observability` (sha in every event).

---

## 2. RAG failure modes (typed retrieval over the 5 indexes)

### R-1: Typed retriever divergence (the 5 indexes disagree)

**What goes wrong:** Historical retriever says "Andrés is in Cempoala, August 1519." Entity-state retriever (auto-generated from committed Ch 3) says "Andrés is at Cerro Gordo." Arc-position retriever returns a beat function consistent with neither. The bundler concatenates all three into the context pack. The drafter picks whichever feels most narratively convenient. The scene commits with inconsistent geography. The critic does not catch it because the critic reads the same contradictory pack.

**Why it happens:** Typed retrievers are independent by design (per ADR-003). No retriever knows what the others returned. Bundler is a dumb concatenator. Entity-state is auto-generated and may be wrong (the extractor agent makes errors too). Corpus-bibles are static and may contradict what canon actually emitted last chapter.

**Warning signs:**
- *Telemetry:* retrieval events for a single scene contain contradictory facts — flaggable by a post-bundle consistency check that extracts key facts from each retriever output and diffs.
- *Critic:* entity-axis issues appear alongside historical-axis issues for the same scene (two axes complaining about the same underlying fact).
- *Retrospective:* retrospective writer flags "the scene says X in paragraph 2 and Y in paragraph 7" — internal contradiction is the fingerprint.

**Prevention:**
- Add a **bundler reconciliation step**: extract structured claims from each retriever output (location, date, possessions, named-entity states), diff them, emit a `retrieval_conflicts.json` event per scene. If conflicts exceed K, either escalate to Mode B or surface to critic as explicit "retrieval conflict present" signal.
- Entity-state is **source of truth for post-Ch-N state**. Rule: entity-state index trumps character-bible for states that have been updated by committed chapters. Make this precedence explicit in the bundler.
- Ablation runs (phase `ablation`) MUST include a "retrieval conflict rate" metric; a rising rate is a pipeline health alarm.

**Phase to address:** `corpus+rag` (reconciliation step in bundler) + `observability` (conflict events) + `ablation` (conflict rate tracked).

---

### R-2: Stale entity-state leaking K-2 assumptions into chapter K

**What goes wrong:** Chapter 5 commits. Extractor runs post-commit and writes entity cards. Chapter 6 drafts. During Ch 6 drafting, Paul retroactively edits Ch 5 to change Andrés's possession (the copper disc comes from a different Tlaxcalan pilot). The extractor is NOT re-run. Chapter 6 drafter uses stale entity-state saying "Andrés has the original disc." Continuity cleanly breaks two chapters downstream before anyone notices.

**Why it happens:** Post-commit extractor is triggered by commit event, not by content-hash change. Edits to already-committed chapters don't re-trigger. Retrospective writer doesn't catch it because retrospectives are forward-looking ("what worked in Ch 6?") not backward-looking ("did Ch 5 get edited after extraction?").

**Warning signs:**
- *Event log:* canon/ chapter file mtime > entity-state/chapter_NN/ mtime. This is a flag condition.
- *Test:* nightly integrity check hashes canon chapter files and compares to the hash recorded alongside each entity card.
- *Telemetry:* critic entity-axis FAIL on chapter K+1 cites a fact from chapter K that was actually edited in chapter K-1.

**Prevention:**
- Entity cards carry a `source_chapter_sha` field. Bundler verifies SHA matches current canon file; if not, regenerates card before using.
- Treat post-commit edits to canon as a first-class event that triggers: re-extract affected chapter, re-index RAG for affected chapter, mark downstream chapters as "pending re-validation" in a dashboard panel.
- Weekly digest includes a "stale entity card" section listing any cards whose source SHA no longer matches canon.

**Phase to address:** `corpus+rag` (SHA-linked entity cards) + `orchestration` (edit-triggered re-extract cron) + `observability` (stale-card panel).

---

### R-3: Context-pack bloat (the 30-40KB soft cap drifts to 100KB)

**What goes wrong:** Over time, retriever top-K creeps up ("just give the model a bit more, regen rate will drop"). Bundler pack grows past 40KB. Mode-A voice model starts losing coherence in-context (thesis 005's predicted degradation point). Critic scores drop. Regen rate rises. Someone "fixes" this by increasing top-K further. Spiral.

**Why it happens:** Natural impulse when regens fail is to give more context. Each individual bump feels harmless. No alarm exists on pack size itself. Mode-B has more context headroom so Mode-B scenes look cleaner, reinforcing "just go Mode B" and masking the Mode-A degradation.

**Warning signs:**
- *Telemetry:* mean context-pack size trending up week-over-week in the digest.
- *Telemetry:* critic score at a specific pack-size bucket starts dropping (needs pack-size histogram against pass rate).
- *Ablation:* thesis 005 ablation results should be baseline — if pack size in production exceeds the supported-at-N-KB threshold, that is a silent regression.

**Prevention:**
- Hard pack-size cap in bundler config (default 35KB), NOT a soft target. Going over requires explicit config change with reason in commit message.
- Digest surfaces pack-size distribution per phase. A monotonic creep is a P2 alarm.
- Thesis 005 result (once closed) becomes a config guardrail: bundler rejects requests that would exceed the measured-safe threshold.

**Phase to address:** `corpus+rag` (hard cap) + `observability` (pack-size distribution in digest) + `ablation` (close thesis 005 early, use result as guardrail).

---

### R-4: Retrieval confidently surfacing wrong facts (hallucinated-index artifacts)

**What goes wrong:** Vector retrieval on engineering.md returns a "rule card" that is actually a cross-reference to a different rule. The draft uses it as if it were authoritative. Critic reads the same wrong card in the pack and grades against it, passing the scene. The book now says Tlaloc-class engines refuel with something they don't.

**Why it happens:** Semantic retrieval can return chunks that look relevant but are actually meta-commentary, examples, or what-if sections. Chunking that fragments a rule-card at a sentence boundary loses the "this is hypothetical" framing.

**Warning signs:**
- *Test:* red-team 10 retrieval queries per index with known-correct answers; if retrieved chunk is not the canonical source-of-truth chunk, score a miss.
- *Retrospective:* "the rule the draft used doesn't appear in engineering.md this way" — reviewer note about specifically which rule was invoked vs what the bible actually says.
- *Telemetry:* for each retrieved chunk, record the source filepath and line range. Any scene that retrieved from a known-problematic section (e.g., `engineering.md` Hypotheticals appendix) gets flagged.

**Prevention:**
- Chunking pass treats rule-card boundaries as semantic units, not character counts. Each chunk carries a `rule_type` metadata field (rule / example / hypothetical / cross-reference).
- Retriever filters by `rule_type=rule` by default. Examples and hypotheticals only retrievable on explicit request.
- Maintain a `corpus+rag/golden_queries.jsonl` with ≥5 queries per index and known-correct chunk IDs; nightly job verifies retrieval accuracy, alarms on regression.

**Phase to address:** `corpus+rag` (structured chunking with type metadata, golden query set) + `observability` (retrieval accuracy panel).

---

### R-5: Negative-constraint retriever failing silently

**What goes wrong:** `known-liberties.md` has a lengthy "Things to Avoid" list (noble-savage framing, romanticizing Malintzin, aestheticizing child sacrifice, cartoon Inquisition, pat moral resolution). The negative-constraint retriever is queried per scene. For a scene involving Malintzin + Cortés, it should return "do not romanticize this relationship." If the retriever doesn't surface the right constraint for the right scene, the drafter has no awareness of the landmine. The draft lands on the landmine. Critic may or may not catch it depending on how the "don'ts" rubric axis is scoped.

**Why it happens:** Negative-constraint retrieval is tag-driven ("Malintzin", "sacrifice depiction") — if the scene request doesn't name the right tag, the constraint isn't surfaced. The outline doesn't always tag these explicitly (Ch 14 is about Malintzin's pregnancy awareness; "relationship with Cortés" may not be in the tag set).

**Warning signs:**
- *Test:* ground-truth map from chapter → relevant avoid-tags (built manually once from the brief + known-liberties). For each drafted scene, check whether the avoid-retriever returned every tag in that chapter's ground-truth set. Miss rate >10% is an alarm.
- *Critic:* don'ts-axis FAIL rate higher than entity-axis FAIL rate sustains — the content keeps violating landmines the constraint retriever should have been warning about.
- *Retrospective:* any mention of "this scene reads as [romanticized / exotified / cartoonish]" is the failure loud on the page.

**Prevention:**
- Outline-to-avoid-tags mapping becomes a first-class artifact (`indexes/negative_constraint/chapter_tag_map.yaml`). Review as part of `corpus+rag` phase, update when outline changes.
- Negative-constraint retriever ALWAYS returns top-K irrespective of tag match — bundler filters at assembly time. Prevents silent miss on tag mismatch.
- Don'ts-axis critic rubric is calibrated against the actual known-liberties document, not a generic "avoid offensive content" prompt.

**Phase to address:** `corpus+rag` (tag map + retriever design) + `critic` (don'ts-axis calibration against known-liberties.md).

---

## 3. Critic failure modes

### C-1: Same-family self-preference / preference leakage (Opus judging Opus-influenced output)

**What goes wrong:** Mode-B drafter is Opus. Critic is Opus. When the critic grades a Mode-B output (Opus-generated scene), it scores systematically higher than an equivalent-quality Mode-A output, not because Mode-B is better, but because Opus-on-Opus exhibits self-preference bias (documented effect per 2025 literature). Mode-B scenes accumulate PASS more readily. Regen rates for Mode-A scenes look artificially worse. The pipeline silently biases toward escalating more scenes to Mode B.

**Why it happens:** Self-preference bias is well-documented: LLM judges favor outputs from their own family because training signatures (perplexity shape, token-distribution markers) match judge expectations. 2025 research shows this is a pervasive, real-world, hard-to-detect contamination.

**Warning signs:**
- *Telemetry:* for matched-content scenes (e.g., same beat, same RAG pack, drafted under Mode A and Mode B for comparison), critic score delta exceeds human-judged delta by >0.5 rubric points.
- *Ablation:* thesis 004 side experiment — run critic scoring with Opus and with a non-Anthropic-family judge (Gemini 2.5 Pro or GPT-5) on the same 20-scene set. If Opus scores Mode-B +0.5+ over non-Anthropic judge, self-preference is live.
- *Telemetry:* mode-B pass rate / mode-A pass rate ratio >1.3 with no obvious quality explanation.

**Prevention:**
- **Critic family ≠ Mode-B drafter family for at least a subset of rubric runs.** Budget-permitting: run a second-judge pass with a non-Anthropic model on 10% of scenes, compare, flag drift.
- Rubric must include **concrete criteria** (not "is this good prose?") to reduce judge-stylistic influence. Each axis should have 5-6 checklist items the judge can verify against, not vibes.
- Don't use Opus for BOTH Mode-B drafter and critic on the same scene in the same run. If escalating to Mode B, the critic pass on that Mode-B scene should use a different model family or explicitly flag the same-family score.
- Ablation harness tracks a `same_family_flag` per scene; retrospective writer explicitly asks "are we seeing drift between same-family and cross-family scoring?" each chapter.

**Phase to address:** `critic` (rubric design + cross-family spot-check) + `ablation` (matched-content A/B) + `observability` (same-family flag, score-delta tracking).

---

### C-2: Critic giving identical scores regardless of content (reward hacking via rubric gaming)

**What goes wrong:** Critic returns {historical: 4, metaphysics: 4, entity: 4, arc: 4, don'ts: 4} for nearly every scene. The regenerator has no signal to improve against because nothing varies. Score variance across scenes collapses to noise. The pipeline passes everything. Quality regresses silently because the critic isn't actually criticizing.

**Why it happens:** A few mechanisms:
1. Rubric is underspecified — "rate historical accuracy 1-5" is too generic; the judge defaults to midrange.
2. Prompt-length fatigue — if rubric + scene + pack is >100KB, the judge's calibration collapses and it anchors on default.
3. Reinforcement via own prior outputs — if the critic sees prior chapter scores in context for "consistency" they cluster around that anchor.

**Warning signs:**
- *Telemetry:* score variance across scenes trending down over time; standard deviation on each axis <0.3 across 20+ scenes.
- *Telemetry:* inter-axis correlation >0.95 — axes are meant to measure different things; if they correlate perfectly, critic isn't differentiating.
- *Ablation:* deliberately inject 5 known-flawed scenes (wrong location, anachronism, etc.). Verify critic flags them. Failure = critic is pattern-blind.

**Prevention:**
- Rubric axes have **concrete checkable items** per axis (e.g., historical axis: "names 3+ verifiable historical facts; none contradict known-liberties section X; dates consistent with outline"). Critic outputs pass/fail on each item, then aggregates. Forces ground-truth attention.
- Periodic calibration check (`ablation` phase monthly task): run the 5-injected-flaws test. If critic catches <4 of 5, rubric is broken.
- Score-variance watchdog: alarm on stdev collapse across a rolling window.
- Do NOT feed prior-scene critic scores into current-scene critic prompt — breaks the anchor.

**Phase to address:** `critic` (checklist-style rubric) + `ablation` (injection test monthly) + `observability` (variance/correlation watchdog).

---

### C-3: Severity drift (what used to be a FAIL becomes a MINOR over chapters)

**What goes wrong:** Chapter 1 flagged a date error as "severity=high, must regen." By Chapter 12, a similar error is flagged "severity=minor, ok to commit." No rubric change. The critic has drifted because cumulative context shifts its calibration — it has "seen" more book and starts normalizing to what exists in canon.

**Why it happens:** If the critic prompt includes prior-chapter context for consistency checking, the shifting baseline shifts the calibration. Also: regen-loop pressure subtly rewards lower severities over time because the scheduler treats minor-severity scenes as commit-able.

**Warning signs:**
- *Test:* recalibration set — 5 frozen scenes with known issues, rerun through critic every N chapters. Severity output should be stable ±0.5. Drift >1 severity level is an alarm.
- *Telemetry:* mean severity across all issues in digest, by week. Monotonic decline is a red flag.
- *Retrospective:* retrospective writer sees "a Ch 2 issue that would have blocked commit" appearing in Ch 15 without blocking.

**Prevention:**
- Frozen recalibration set is part of `observability` infra from day one. Runs weekly, score drift logged in digest.
- Critic prompt is **stateless per scene** by default — no prior scores, no "running book context," just rubric + scene + pack. Canonical context is fed via RAG not via critic history.
- Ablation harness includes a "re-score old scenes" job — run the current critic against an N-month-old scene; compare to original score.

**Phase to address:** `critic` (stateless prompt design) + `observability` (recalibration set, drift panel).

---

### C-4: Critic-drafter collusion via shared RAG pack

**What goes wrong:** Drafter reads RAG pack, writes scene. Critic reads the **same** RAG pack, scores scene. Both condition on identical context. If the pack is wrong, both make the same error. Critic PASSES the scene because the scene agrees with the (wrong) pack. The book enshrines the error.

**Why it happens:** Per architecture (Diagram 3 footer: "Drafter + Critic receives same pack"), this sharing is intentional for efficiency. It creates an epistemic monoculture: there is no independent source of truth in the critic loop.

**Warning signs:**
- *Test:* 10-sample probe where the RAG pack is deliberately seeded with a subtle error (e.g., wrong date for an event). If critic catches it on ≥5/10, the critic has independent judgment. If <3/10, collusion is live.
- *Retrospective:* "both the scene and the critic's comments seem to agree on a fact that turns out to be wrong per corpus" — this is exactly the failure mode.
- *Telemetry:* chapter-level critic (which is downstream of scene critic) flags facts the scene critic PASSED — shows where the fresh-eyes pass catches what the shared-pack pass missed.

**Prevention:**
- Chapter-level critic gets a **re-queried** RAG pack with different retrieval seeds / independent query formulation. Not the scene's pack.
- Periodic "critic-only" retrieval check: critic re-queries RAG from scratch with a query derived from the DRAFTED scene (what is this scene claiming?), compares to what the drafter received. Inconsistencies = draft departed from pack (bad) or pack was wrong (also bad, differently).
- Weekly: 2-3 random scenes spot-checked by a cross-family judge reading ONLY the scene + source-of-truth bibles (no pack). Catches pack-mediated collusion.

**Phase to address:** `critic` (chapter-critic gets fresh pack) + `observability` (cross-family spot-check in digest).

---

### C-5: False-positive-driven unnecessary regeneration (cost explosion)

**What goes wrong:** Critic over-flags. Regen rate climbs. Each regen costs tokens (Opus inference) and time. Mode-B escalation fires more often (R regens in Mode A then escape). Weekly spend triples. Real quality is not materially different. The pipeline is burning budget to fix non-issues.

**Why it happens:** Overly strict rubric, or rubric items that penalize legitimate voice quirks (em-dashes, asides). Critic doesn't distinguish "stylistic choice Paul makes" from "rule violation."

**Warning signs:**
- *Telemetry:* regen count per committed scene trending up.
- *Telemetry:* Mode-B escape rate rising without corresponding new-complex-beat flags (per thesis 002).
- *Ablation:* a "reject-only-hard-issues" critic variant produces equivalent quality at lower regen rate.

**Prevention:**
- Rubric severities distinguish: HARD (must regen — fact errors, continuity breaks, don'ts violations), SOFT (note but commit — stylistic preference, minor clarity). Only HARD triggers regen.
- Regen budget per scene is capped AND cost-metered. Budget is both count (R regens) and tokens (X*N tokens). Either triggers escape.
- Weekly digest: regen-per-scene histogram + regen cost breakdown. Rising right-tail is a P1 alarm.

**Phase to address:** `critic` (HARD/SOFT severity split) + `regen` (cost-based budget) + `observability` (regen cost panel).

---

## 4. Regeneration loop failure modes

### RE-1: Oscillation between two failure modes

**What goes wrong:** Scene fails critic with entity-axis issue. Regen fixes entity, breaks metaphysics. Regen again fixes metaphysics, reintroduces entity issue. Loop until budget exhausted. Escalate to Mode B. Mode B also struggles because the underlying issue is that the two RAG retrievers disagree (see R-1).

**Why it happens:** Regenerator sees only the most recent critic output and fixes that, with no memory of what the PREVIOUS regen was trying to fix. It's a markov process with no history.

**Warning signs:**
- *Telemetry:* per-scene regen count ≥3 AND critic-axis-flagged history shows axis A → B → A → B pattern.
- *Event log:* issue_hash rotates between 2-3 values across regens rather than monotonically resolving.
- *Retrospective:* "scene kept fixing one thing and breaking another."

**Prevention:**
- Regenerator gets the **full issue history** across all prior regens for this scene, not just current critic output. Prompt: "Prior regens addressed X then Y; fix Z without reintroducing X or Y."
- Automatic oscillation detector: if issue axes alternate across regens with no net resolution after 2 cycles, escape to Mode B immediately (don't waste R budget).
- Retrospective writer explicitly patterns for oscillation: any chapter where a scene oscillated gets called out as a R-1 candidate (retrieval conflict root cause).

**Phase to address:** `regen` (history-aware prompt + oscillation detector) + `observability` (oscillation pattern in retrospective).

---

### RE-2: Regenerator "solving" the flagged issue while breaking voice

**What goes wrong:** Regen fixes a historical fact but, in doing so, rewrites the passage in a register that is NOT the voice model's training distribution (e.g., adds exposition-heavy clarification, reverts to explanatory prose). Entity axis PASS, voice axis DROPS silently because the chapter-level critic doesn't run per-scene regen.

**Why it happens:** Regenerator prompt is issue-conditioned — "fix entity error" — without voice preservation as an explicit constraint. Voice is a property the drafter had that the regenerator doesn't know to preserve.

**Warning signs:**
- *Telemetry:* voice-fidelity score on post-regen scene drops >0.05 from pre-regen score.
- *Test:* random sample of regen pairs (pre/post) spot-checked for voice drift; flag rate >15% is a problem.
- *Retrospective:* "after regens, the scene felt more textbook-y."

**Prevention:**
- Regenerator's prompt includes explicit voice preservation instruction + voice-reference snippets from the same chapter's earlier scenes.
- Post-regen scene runs voice axis critic as a cheap check before committing regen. If voice drops, either escalate to Mode B or restore pre-regen.
- Regen uses the voice-FT model (Mode A) for targeted rewrites — NOT Opus — so long as the issue is localized. Only escalate to frontier regen after R voice-FT attempts.

**Phase to address:** `regen` (voice-preserving prompt + post-regen voice check) + `critic` (fast voice-only check for regen gating).

---

### RE-3: Cost explosion when Mode A keeps failing on a structurally hard beat

**What goes wrong:** A beat that should have been pre-flagged Mode B from the start (e.g., the Cholula awakening, Ch 8) is not flagged. Drafter tries Mode A. Critic fails. Regen fails R times. Mode B engaged. Mode B might also need regens. Total spend for one scene: 10× the per-scene budget estimate. Weekly budget blown in one night. Paul finds out in Sunday's digest.

**Why it happens:** Pre-flag list is incomplete. Or: pre-flag list is correct but orchestrator didn't read it. Or: the outline was updated to add a new complex beat and the pre-flag list wasn't updated.

**Warning signs:**
- *Telemetry:* per-scene cost histogram has a long right tail; scenes in the top 1% cost >5× median.
- *Event log:* per-scene token spend crosses an alert threshold — Telegram fires mid-run, not at end-of-week.
- *Orchestration:* regen_loop event lasting >30 minutes triggers alert.

**Prevention:**
- **Per-scene cost budget as hard cap**, not a metric. Scheduler aborts scene after 3× median cost and escalates to Mode B or human (Telegram).
- Outline-to-mode-flag mapping is reviewed each time outline changes; CI check: every chapter has a `mode_flag` field populated.
- Pre-flag list is informed by thesis 001 and 002 results — as evidence accumulates on what the voice model can and cannot do, the list gets automated updates from the ablation harness, not manual.

**Phase to address:** `orchestration` (hard cost cap + mid-run alert) + `regen` (escape on cost crossing) + `ablation` (mode-flag suggestions from data).

---

### RE-4: Regen solving the flagged issue by deleting the problematic content

**What goes wrong:** Critic flags "this scene contains an anachronism." Regenerator "fixes" by removing the sentence containing the anachronism. Scene is now 50 words shorter, still internally consistent, passes critic. But it lost the beat it was supposed to convey. Chapter assembler notices beats missing only at chapter-critic stage, which may not re-escalate properly.

**Why it happens:** Regenerator optimizes for critic pass, not for fidelity to the scene request. Deleting content is always an easy way to reduce critic complaints.

**Warning signs:**
- *Telemetry:* scene word count after regen < 85% of original. Flag.
- *Telemetry:* beat-coverage axis (did the scene accomplish its beat function?) fails at chapter level even though scene-level critic passed.
- *Retrospective:* "this chapter moved faster than I expected" — pacing collapse.

**Prevention:**
- Word count constraint on regen: post-regen scene must be within ±10% of pre-regen (or pre-regen's target length, whichever is more specific). Shrinkage beyond threshold is a failure, not a pass.
- Add a beat-coverage axis to critic: "did this scene execute the beat function specified in the request?" with explicit checkboxes.
- Chapter-level critic explicitly checks beat-coverage across all scenes against outline beats, flags missing beats even if scenes individually passed.

**Phase to address:** `regen` (length constraint) + `critic` (beat-coverage axis + chapter-level beat check).

---

## 5. Mode-dial failure modes

### M-1: Mode-B escape rate silently creeping to near-100%

**What goes wrong:** Month 1: 15% Mode B. Month 2: 30%. Month 3: 55%. The voice model is being invoked less and less. The pipeline is in effect a frontier-drafting pipeline with voice-flavored prompt. Nobody notices because each per-chapter escalation looks justified in isolation. Thesis 002's 30% ceiling is blown but there's no alarm.

**Why it happens:** Escalation is always the safer choice in the moment (pay more tokens, get better quality). Nothing is pushing back toward Mode A. Retrospectives are about the content not about the mode distribution.

**Warning signs:**
- *Telemetry:* rolling-30-day Mode-B rate exceeds 35% (thesis 002's inconclusive threshold).
- *Digest:* mode distribution trend plot in weekly digest showing a visible upward slope.
- *Thesis 002:* if the thesis's metric computation would close it REFUTED, that's the alarm.

**Prevention:**
- Hard alarm in orchestration at 40% rolling-Mode-B rate: Telegram notifies Paul, auto-pauses new non-pre-flagged Mode-B escapes until review.
- Digest surfaces mode distribution as a **top-level metric**, not buried — alongside cost and pass rate.
- If Mode-B rate crosses 30% for two consecutive weeks, auto-open a thesis on "book-voice FT branch needed?" as a decision-forcing artifact (per thesis 002's "refuted" outcome).

**Phase to address:** `orchestration` (rate-based alarm) + `observability` (digest prominence) + `ablation` (auto-thesis spawn).

---

### M-2: Mode-B scenes committed without voice-drift accounting

**What goes wrong:** Mode-B output has lossy voice fidelity by design (Opus-with-voice-samples is "best-effort"). If Mode-B scenes commit without a voice-fidelity delta logged, the overall voice-fidelity metric is silently distorted. Thesis 001's outcome becomes meaningless because it's averaging Mode-A and Mode-B scenes without separation.

**Why it happens:** Metric reporting collapses across all modes by default. Only separating by mode requires deliberate filter.

**Warning signs:**
- *Digest:* voice-fidelity metric reported without mode breakdown.
- *Thesis evaluation:* thesis 001's metric computation doesn't exclude Mode-B scenes.
- *Retrospective:* voice trend discussion doesn't distinguish modes.

**Prevention:**
- Every voice-fidelity computation is reported three ways: all scenes, Mode A only, Mode B only. Digest and retrospective both report all three.
- Mode tag is a required field on every scene event. Missing mode tag is a schema violation, event log rejects.
- Thesis 001's metric explicitly filters Mode A only.

**Phase to address:** `observability` (mode-segmented voice reporting) + `critic` (mode required in schema).

---

### M-3: Pre-flag list rotting

**What goes wrong:** Architecture doc lists flagged Mode-B beats (Ch 10 Cholula, Ch 17-18 reveal, Ch 25-27 climax). Outline evolves; Ch 17 beat function changes. Pre-flag list doesn't update. Ch 17 drafts Mode A, fails, burns regen, escalates. Meanwhile Ch 18 is still flagged but beat is now simpler and could be done Mode A. Budget is misallocated.

**Why it happens:** Pre-flag list is in `docs/ARCHITECTURE.md` (text), not a structured config the outline can validate against.

**Warning signs:**
- *Test:* `config/mode_preflags.yaml` schema validation job compares pre-flag list to outline chapter list; any chapter with no flag (or flag missing from list) is a warning.
- *Retrospective:* "this chapter didn't need Mode B" or "this chapter absolutely needed Mode B from the start" observations.
- *Telemetry:* Mode-B escalation events on non-pre-flagged chapters at >15% rate.

**Prevention:**
- Move pre-flag list from docs to `config/mode_preflags.yaml`. Outline parser validates against it at load time.
- Quarterly review event: retrospective writer, at each 9-chapter boundary, produces a "pre-flag list update" note listing chapters that should change flag.
- Automated data-driven flag suggestions from `ablation` harness — if Mode A has failed on analogous beat types 3+ times, suggest flagging.

**Phase to address:** `foundation` (config schema) + `ablation` (data-driven flag updates) + `observability` (flag review cadence).

---

## 6. Orchestration failure modes (openclaw)

### O-1: Missed cron runs with no detection

**What goes wrong:** openclaw gateway is down, cron didn't fire, or the job failed silently. Two nights of no production. Paul discovers Sunday in the digest ("this week: 0 new chapters"). Lost wall time.

**Why it happens:** openclaw is systemd --user. If the user-session is not active at cron time (machine reboot, logout), the job doesn't fire. No heartbeat, no "i'm supposed to run" signal when it doesn't run.

**Warning signs:**
- *Test:* heartbeat file `runs/last_run.json` — if older than 30 hours, alarm.
- *Event log:* gap in event timestamps >30 hours without an explicit "paused" marker.
- *Digest:* Monday digest includes "runs this week" count.

**Prevention:**
- Dead-man switch: systemd timer (or external cron) writes heartbeat every hour. Independent process (Telegram-bot or cron on different schedule) checks heartbeat; pages if stale.
- `systemctl --user` unit uses `Restart=always` with appropriate backoff. Plus `lingering` enabled for the user so services run without active session.
- Digest's "production" section leads with run count and hours-of-activity — absence is visible.

**Phase to address:** `orchestration` (dead-man switch + lingering) + `observability` (run count in digest).

---

### O-2: Race between extractor and next-scene drafter

**What goes wrong:** Chapter 5 commits. Post-commit: extractor queued, next-scene drafter queued. Drafter runs first (cron fires), uses stale entity-state from Chapter 4. Scene commits with outdated continuity. Extractor completes afterward. Damage done.

**Why it happens:** openclaw jobs may parallelize or queue in unspecified order. Post-commit triggers are fan-out, not sequenced.

**Warning signs:**
- *Event log:* drafter event for chapter K+1 has a timestamp before extractor event for chapter K.
- *Telemetry:* continuity errors cluster on first scene after commit.
- *Test:* integration test with seeded chapters verifies ordering.

**Prevention:**
- Post-commit is a **DAG**, not a fan-out: extractor must complete before next drafter runs. Openclaw workflow expressed as dependency chain.
- Alternatively: drafter reads entity-state and checks source_chapter_sha matches canon. If mismatch, waits OR refuses to draft until extractor catches up.
- State-machine explicit: chapter states are `drafting | committed | extracted | indexed | ready_for_next`. Only `ready_for_next` permits next chapter's drafter.

**Phase to address:** `orchestration` (DAG + state machine) + `corpus+rag` (SHA check in drafter entry).

---

### O-3: Workspace state corruption on abrupt shutdown

**What goes wrong:** Machine crashes mid-drafting (power outage, systemd OOM kill). openclaw workspace state file (`.openclaw/state.json`) is mid-write; file is truncated or JSON is invalid. Next run can't parse. Pipeline refuses to start. OR: it starts "fresh" and reruns already-committed scenes, double-committing.

**Why it happens:** JSON file writes are rarely atomic across the full operation. Workspace managers often don't use write-and-rename.

**Warning signs:**
- *Test:* corrupt state.json deliberately, verify recovery. Do this as a real fault-injection test.
- *Event log:* startup event shows "recovering from N" where N doesn't match commit log.
- *Orchestration:* pipeline exit code indicates corruption, pages Paul.

**Prevention:**
- Atomic writes everywhere: write-temp-then-rename, fsync. Every single state mutation.
- Workspace state is **derivable from canon + event log** — it can be rebuilt if the state file is lost. Recovery script exists. Document it.
- WAL-style append-only log for state transitions; snapshot files are periodic compactions of the log.

**Phase to address:** `orchestration` (atomic writes + WAL) + `observability` (recovery script as first-class artifact).

---

### O-4: openclaw gateway dying without alert

**What goes wrong:** Gateway process OOMs, crashes, or hangs. systemd may not restart (if Restart policy misconfigured) or may restart-loop. No alert. Paul notices when digest is missing Monday.

**Warning signs:**
- *Test:* kill gateway manually, verify Telegram alert within 5 min.
- *Event log:* no gateway heartbeat events for >1 hour while wall time suggests activity expected.
- *systemd status:* `systemctl --user status` shows failed / restart-looping state.

**Prevention:**
- Separate watchdog process (not owned by openclaw) that pings gateway HTTP health endpoint every 5 min. Failure → Telegram.
- systemd unit: `Restart=always`, `StartLimitBurst=5`, `StartLimitIntervalSec=300` — so a restart-loop is NOT silent, it rate-limits and stays failed with an alert.
- `journalctl --user -u openclaw*` events piped to observability — fatal errors trigger alert.

**Phase to address:** `orchestration` (watchdog + systemd restart config) + `observability` (journal piping).

---

### O-5: Stuck processes (vLLM / drafter holds a lock indefinitely)

**What goes wrong:** vLLM serving the voice-FT model crashes into a zombie state holding GPU memory. Next drafter run fails to load the model. Orchestrator retries. Retries fail identically. Regen budget burns on retries. Mode-B escalations fire because "Mode A isn't responding." Budget blows. Paul gets an alert but only after midnight-batch completes.

**Why it happens:** GPU state is not part of the openclaw state machine. vLLM failures from the sibling project (Qwen 122B container story, see user's memory) have a clear pattern: process alive, GPU held, serving degraded. This will happen here.

**Warning signs:**
- *Test:* nvidia-smi health check before and after drafter run. Memory not freed post-exit = zombie.
- *Event log:* drafter latency per call rising sharply, or retry-count per call >2 consistently.
- *Orchestration:* pipeline tries to start vLLM while another instance is live.

**Prevention:**
- Pre-flight: every drafter run calls `nvidia-smi` and confirms GPU state matches expected baseline. Zombie detected → kill + restart before continuing. Mirror `reference_vllm_systemd.md` discipline.
- vLLM wrapper has a hard timeout per call (3× P99 latency). Timeout triggers zombie check, not silent retry.
- Orchestrator's mode-dial decision considers drafter health: if vLLM unhealthy, don't escalate to Mode B reflexively — pause and alarm.

**Phase to address:** `orchestration` (pre-flight GPU check + timeouts) + `drafter` (vLLM wrapper discipline).

---

## 7. Observability failure modes

### OB-1: Event log becoming huge and unqueryable

**What goes wrong:** Every LLM call emits an event with prompt, output, metadata. After 2 months: events.jsonl is 20GB. Queries take minutes. Digest generation gets slow. Retrospective writer runs out of context trying to read events. Disk fills.

**Why it happens:** No rotation. No indexing. Prompts and outputs stored inline rather than by hash with external blob store.

**Warning signs:**
- *Telemetry:* events.jsonl size >1GB and growing.
- *Telemetry:* digest generation latency rising.
- *Disk:* `/home/admin` usage increasing faster than drafts commit rate would suggest.

**Prevention:**
- **Hash-based blob store for prompts/outputs** (content-addressed storage). Event log contains hashes, not bodies. Bodies on disk once.
- Monthly log rotation (already specified in ADR-003 "Hygiene"). Compressed archive. Operational procedure + verified.
- Metric ledger is the queryable layer — events.jsonl is cold storage. Don't run hot queries against JSONL.

**Phase to address:** `observability` (blob store + ledger design) + `orchestration` (rotation job).

---

### OB-2: Metric ledger drift from reality

**What goes wrong:** Metric ledger summarizes scene outcomes (pass rate, regen count, cost) by chapter. Digest reads ledger. But a bug in the aggregator silently double-counts or misses scenes. Ledger says "chapter 7: 95% pass rate, 2 regens." Truth is "chapter 7: 60% pass rate, 11 regens." Paul makes decisions on wrong data.

**Why it happens:** Aggregator is code, code has bugs, aggregator runs async so drift accumulates silently.

**Warning signs:**
- *Test:* periodic reconciliation script recomputes ledger from event log and diffs. Any diff is a bug.
- *Retrospective:* retrospective writer notices "numbers in the digest don't match what the events describe."
- *Digest:* add a "ledger vs events diff" integrity field. Non-zero is a flag.

**Prevention:**
- Aggregator is **idempotent and reproducible** — running it twice produces same ledger. Unit-tested.
- Every digest includes a "ledger integrity" line: pass iff reconciliation script saw zero diffs.
- Ledger is **derived** state; source of truth is events. In doubt, rebuild from events.

**Phase to address:** `observability` (idempotent aggregator + reconciliation script) + `ablation` (monthly audit of ledger integrity).

---

### OB-3: Retrospective writer producing vague boilerplate

**What goes wrong:** After chapter commit, retrospective writer runs. Output: "This chapter went well. Voice was consistent. The pacing felt appropriate. Some regens occurred but were resolved." Repeat, ad infinitum. Retrospectives are useless. Thesis matching (which consumes retrospectives) never closes theses.

**Why it happens:** The retrospective prompt is under-constrained ("summarize what happened"). Opus defaults to generic literary feedback when not given specific tasks. Also: if the retrospective doesn't have access to concrete events/metrics, it has nothing specific to observe on.

**Warning signs:**
- *Test:* word-overlap between consecutive retrospectives >40% — boilerplate detector.
- *Test:* retrospective contains zero metric references and zero event-specific references.
- *Thesis registry:* zero theses closed on the back of retrospectives after 5+ chapters.

**Prevention:**
- Retrospective prompt is a **structured template** with required fields: quantitative observation (metric reference), qualitative observation (specific passage reference), candidate thesis (new question raised), thesis check (evidence for/against open theses).
- Retrospective has direct access to events/metrics for the chapter, not just the text. Reads structured data, not just the markdown.
- Lint check on retrospective output: required fields populated, passage references resolve to real line numbers, metric references resolve to actual ledger values. Fail = rerun with feedback.

**Phase to address:** `observability` (templated retrospective + lint check) + `critic` (structured-output discipline applied here too).

---

### OB-4: Thesis registry ossifying (nothing ever closes)

**What goes wrong:** 5 seed theses are open. 9 chapters later, 5 theses are still open. New candidate theses get added. Now 12 open theses. Nothing ever accumulates enough evidence to close. Thesis registry becomes decorative.

**Why it happens:** Thesis closure criteria are aspirational ("once we have enough data"). No mechanism forces evaluation. The thesis matcher runs but isn't confident enough to close any.

**Warning signs:**
- *Digest:* "open theses: 12, closed: 0."
- *Test:* a thesis with a specific metric (e.g., 002's "escape rate ≤ 30% across first 9 chapters") should auto-close at chapter 9 when evidence is available. If it doesn't, closure logic is broken.
- *Retrospective:* retrospective writer never references closing a thesis.

**Prevention:**
- Every thesis has a **computable success metric** (already the case in the 5 seeds — good). Thesis matcher runs a computation each chapter to evaluate.
- **Scheduled closure evaluation** at chapter milestones (ch 3, 9, 18, 27). At each milestone, every thesis is explicitly evaluated as supported/refuted/inconclusive. Closure is not optional — if inconclusive, the thesis must be rewritten with sharper criteria OR archived as "closed inconclusive."
- ADR-003 hygiene rule (open >30 days with no evidence = prune candidate) is enforced by script, not goodwill.

**Phase to address:** `observability` (auto-evaluation at milestones) + `ablation` (thesis matcher compute discipline).

---

## 8. Testbed-specific failure modes

### T-1: Ablation runs with confounding variables

**What goes wrong:** Variant A vs Variant B run, but between the A runs and B runs Paul upgraded the voice checkpoint, or the corpus got a new paragraph, or the critic prompt was tweaked. Comparison is meaningless. Conclusion is reported anyway. Wrong lesson gets transferred to pipeline #2.

**Why it happens:** "Held fixed" is asserted but not mechanically verified. It is very easy to "just make a small improvement" mid-ablation.

**Warning signs:**
- *Test:* ablation run metadata includes every relevant config hash (voice checkpoint sha, corpus sha, critic prompt sha, RAG index sha). If any differs between A and B runs, the ablation is invalid.
- *Retrospective:* "comparing these runs we should note that X changed between them" — this is admitting the confound.

**Prevention:**
- Ablation harness snapshots the full config+corpus state before run start. Run tag = `ablation_YYYYMMDD_<hash>`. Any variant under the same tag must share the same snapshot.
- Ablation runs are gated: cannot start if pending config changes exist. Run-start event records the git SHA, checkpoint SHA, corpus SHA, prompt SHAs.
- Ablation validity check: at result time, rerun 1 scene from A under B's config to confirm delta matches — sanity check.

**Phase to address:** `ablation` (snapshot + SHA discipline) + `observability` (ablation metadata schema).

---

### T-2: Theses opened but never forced to resolution

**What goes wrong:** During production, a surprise observation gets written up as an open thesis. No test design, no metric, just "interesting — should test eventually." It sits. Three months later it's forgotten. Eventual learning lost.

**Why it happens:** Low-friction opening, high-friction closing. Asymmetric.

**Warning signs:**
- *Digest:* theses without a metric listed.
- *Test:* linter on `theses/open/*.md` — required fields include metric + test_design + deadline (e.g., "by chapter N"). Theses missing fields flagged.
- *Retrospective:* never mentions evaluating a specific open thesis.

**Prevention:**
- Thesis schema linter: every open thesis must have metric, test_design, and expected_closure_condition. If not, it's a "draft thesis" not an open one, and it accumulates pressure to be completed.
- **Closure target dates**: each thesis has a "evaluate by chapter K" deadline. At chapter K, thesis is force-evaluated; inconclusive is allowed but must be written.
- Digest calls out open theses >30 days with no evidence accrued (per ADR-003 hygiene).

**Phase to address:** `observability` (thesis schema linter) + `ablation` (scheduled force-evaluation at milestones).

---

### T-3: Book-specific assumptions leaking into "kernel-shaped" code

**What goes wrong:** Per ADR-004, pipeline is book-first, extract-kernel-later. During build, code in `critic/`, `rag/`, `regen/` quietly assumes "a scene has 800-1500 words" or "there are exactly 5 axes" or "chapters commit at 3000 words." Pipeline #2 (blog, single post, no chapters, different rubric) requires rewriting the "kernel" modules because the assumptions are baked.

**Why it happens:** Writing the abstraction for one caller naturally hardcodes that caller. ADR-004 anticipates this; the risk is the discipline slips during implementation.

**Warning signs:**
- *Test:* code review flag: any module under `drafter/`, `critic/`, `regen/`, `rag/`, `observability/` that imports from a book-specific module (`book/`, `outline/`, `entity/`) is a boundary violation.
- *Test:* grep for magic numbers in those modules — `3000`, `5`, `27` — each is a suspect hardcode.
- *Phase transition:* at each phase boundary, review module APIs against a hypothetical blog-pipeline caller.

**Prevention:**
- Strict module boundaries from day 1 — book-specific stuff lives in a `book/` subpackage. Generic modules cannot import from `book/`. Enforced by lint rule.
- Configuration over hardcoding: "axes count," "chapter grain," "beat function schema" are all config-driven, even if only one caller uses them.
- Quarterly "pretend we're building pipeline #2" exercise: spend 1 hour sketching blog pipeline, note every place the current code would break. Track as tech debt.

**Phase to address:** `foundation` (module boundaries + lint) + across all phases (config discipline) + `final` (pre-extraction review).

---

### T-4: Learnings not transferring because the artifact is vague

**What goes wrong:** Thesis closes "supported: typed RAG beats monolith." That's the artifact. Pipeline #2 starts. The blog pipeline author (future-Paul) reads the closed thesis and has to re-derive: what chunking? what retriever count? what bundler behavior? The artifact is a conclusion, not a blueprint. Re-derivation loses wall time.

**Why it happens:** Conclusions are cheap to write. Operational artifacts (config recipes, rubric templates, retriever design notes) are expensive.

**Warning signs:**
- *Test:* closed thesis markdown contains conclusion section but not "transferable artifact" section with specific config snippets.
- *Thesis registry:* ADR-003 lists 4 artifact types (config rec, architectural lesson, known failure, corpus implication) — closed theses missing one of these types is an incomplete closure.
- *Pipeline #2 first week:* author says "I had to figure this out from scratch" — symptom.

**Prevention:**
- Thesis closure template includes the four ADR-003 artifact types as required fields. Missing artifact = thesis not yet closed, only "evaluated."
- Every closed thesis spawns at least one config snippet, rubric template, or architectural note that is IMMEDIATELY usable. Store in `theses/closed/artifacts/`.
- At pipeline #2 kickoff, explicit review of all closed-thesis artifacts. Count of "useful on day 1" vs "needed re-derivation" is a quality measure.

**Phase to address:** `observability` (closure template) + `final` (artifact audit).

---

## 9. Novel-quality failure modes (specific to *Our Lady of Champion*)

### N-1: Technically consistent but DEAD prose (thesis 001 edge case)

**What goes wrong:** Critic passes every axis. Historical facts correct. Entity continuity clean. Arc beats hit. Voice axis shows good cosine. But the prose is lifeless — no rhythm, no weight, no reason to read the next sentence. The book is correct and unreadable.

**Why it happens:** Rubric grades what is checkable. Aliveness is not checkable by a checklist. Optimizing for rubric pass is orthogonal to optimizing for reader pull. Especially true under regen pressure: any passage that gets regenerated twice will regress toward safe, checkable prose and away from risk-taking prose.

**Warning signs:**
- *Retrospective:* retrospective writer's "what worked" section is empty or vague while "what didn't" is specific.
- *Test:* Paul spot-checks 1 random scene per chapter. Subjective score below 6/10 on engagement for >30% of spot-checks = alarm.
- *Telemetry:* scene-to-scene reader-compulsion proxy (e.g., passage-ending-sentence richness, or embedding-distance-from-genre-baseline — aim for nonzero distance, not zero) trending toward 0.

**Prevention:**
- Add "reader-pull" axis to critic rubric, with concrete criteria: scene-ending leaves a question, at least one specific sensory image, at least one unexpected juxtaposition. Not "is this engaging" but "does it have these building blocks."
- Reserve 10% of scenes to run WITHOUT regen — commit first-pass even if imperfect, just to preserve voice risk. Regen is a tool for fixing, not polishing toward conformity.
- Paul's weekly spot-check is protocol, not optional: 2 scenes/week, scored subjectively on engagement. Drop below threshold = alarm.

**Phase to address:** `critic` (reader-pull axis) + `regen` (no-regen tier) + `observability` (weekly spot-check protocol).

---

### N-2: Thematic spine lost under scene-level optimization

**What goes wrong:** The book's three thematic pillars (death-as-technology, translation-as-power, civil-war framing) are meant to be load-bearing across the whole novel. Per-scene critic grades against 5 axes — none of which is "does this advance a thematic pillar?" Over 27 chapters, scene-level quality is high but thematic accumulation is thin. The two-thirds revelation doesn't land because the setup was never planted.

**Why it happens:** Critic and rubric are scene-local. Thematic development is global. The axes don't add up to a theme.

**Warning signs:**
- *Retrospective:* chapter-level retrospective cannot cite concrete passages where a thematic pillar was advanced.
- *Test:* at chapter 9 (end of Act 1), a "thematic audit" query across all committed canon: how many passages reference Sanctified Death, translation power, or civil-war framing? If <N per theme, spine is thin.
- *Chapter-critic:* chapter-level critic's thematic-advance score declining or flat across Act 1.

**Prevention:**
- **Thematic-advance axis on chapter-level critic**: did this chapter concretely advance the themes? Scored with reference to specific textual moments.
- **Thematic beats are first-class outline annotations**: outline.md entries for chapters are tagged with `advances_theme=[death-as-tech, translation-as-power, civil-war]`. Beat-function retriever returns these. Scene requests include theme-tag context.
- Pre-commit check at chapter level: chapter must demonstrably touch ≥1 thematic pillar, or commit warns.

**Phase to address:** `corpus+rag` (thematic tags in arc-position retriever) + `critic` (chapter-level thematic axis) + `foundation` (outline annotation schema).

---

### N-3: Pacing collapse (too many short scenes or too few)

**What goes wrong:** Scene-level generation without a pacing-aware assembler produces chapters with uneven rhythm: 7 short staccato scenes OR 1 long sprawl of a scene. Outline grain is nominally 2-4 scenes per chapter but drift happens: Mode-B scenes tend longer, Mode-A with low regen count tend shorter, over chapters the average scene count drifts.

**Why it happens:** Nothing is evaluating pacing. Scene-length and scene-count are side effects of whatever the drafter/regen cycle produced.

**Warning signs:**
- *Telemetry:* scenes-per-chapter distribution widening across chapters (variance rising).
- *Telemetry:* word-count-per-scene distribution developing bimodality (Mode-A short + Mode-B long peaks).
- *Retrospective:* "this chapter felt rushed" or "this chapter dragged" — pacing vocabulary.

**Prevention:**
- Pacing axis on chapter-level critic: scene count in expected range (2-4), scene-length variance within chapter reasonable, transitions between scenes don't jar.
- Chapter assembler has a "pacing pass" that can request a scene be split or a transition smoothed. Not rewriting, annotating.
- Digest tracks scenes-per-chapter as a metric — visible drift is visible.

**Phase to address:** `critic` (chapter-level pacing axis) + `drafter` (assembler pacing pass) + `observability` (pacing metric in digest).

---

### N-4: Character arc not landing (critic grades beats in isolation)

**What goes wrong:** Andrés's arc: "begins certain his cause is holy, ends radically different, possibly atonement." Each chapter's Andrés scene individually passes the arc-axis (beat function matches outline). But across chapters, the interior shift is asserted not dramatized. Chapter 3 Andrés is certain. Chapter 20 Andrés is atoning. The pages between don't dramatize the breaking point as drama; they check boxes.

**Why it happens:** Arc-axis is outline-level ("did this scene hit the beat?"). It's not character-trajectory-level ("is the interior change legible and earned?"). The outline has the destination; it doesn't have the mile markers of transformation.

**Warning signs:**
- *Test:* per-POV character-state rubric — for each POV, list interior-state signals per chapter. If signals jump without intervening dramatization, the arc is asserted.
- *Retrospective:* retrospective writer flags "the scene tells us Andrés is troubled but doesn't show the texture of it."
- *Chapter-critic:* character-arc axis at chapter level includes "does this chapter advance interior change through action/image/dialogue, or merely through statement?"

**Prevention:**
- **Character-state card per POV, per chapter**, auto-generated alongside entity-state. Tracks interior-state signals, not just exterior facts. Next chapter drafter reads both.
- Chapter-level critic: "interior-change legibility" sub-axis. Asks for specific passage that dramatizes change. If absent, fails even if beats hit.
- Milestone audits (chapter 3, 9, 18, 27): reviewer (Opus or human) reads the POV arc to date, scores interior-change coherence. Below threshold triggers a "character-arc correction" thesis.

**Phase to address:** `corpus+rag` (character-state card schema) + `critic` (interior-change sub-axis) + `observability` (milestone POV audit).

---

### N-5: Sensitive-content failure (aestheticizing sacrifice, romanticizing Malintzin/Cortés, cartoon Inquisition)

**What goes wrong:** The brief and known-liberties are explicit about landmines: don't aestheticize Tlaloc child sacrifices, don't romanticize Malintzin-Cortés, don't cartoon the Inquisition. A well-meaning drafter steps on one. Critic's don'ts-axis should catch it. If don'ts-axis is loosely calibrated, it misses — because these failures are about register and framing, not factual errors.

**Why it happens:** Critics measure facts well, register poorly. "Is this romanticized?" is a judgment about tone, which requires a strong rubric anchor. Default LLM critics tend toward generic "avoid offensive content" which isn't aligned with the specific landmines.

**Warning signs:**
- *Retrospective:* retrospective writer flags tonal issues that critic missed.
- *Test:* 5 red-team scenes drafted deliberately with landmine elements. Don'ts-axis catch rate on these is the calibration metric. Below 4/5 = broken.
- *Test:* matched-content A/B — one scene written respectfully, one with landmine. Critic score delta should be clearly measurable.

**Prevention:**
- Don'ts-axis rubric is **calibrated directly from known-liberties.md** — each "Things to Avoid" item becomes a specific check in the rubric. Not "avoid offensive content" but "this scene must not: make Tlaloc sacrifice beautiful OR make it grotesque exotica; must present as civilization's serious answer to theological problem."
- Quarterly red-team probe: deliberately draft 3-5 landmine scenes, measure catch rate. Failure = rubric revision.
- Pre-commit hook at chapter level: if don'ts-axis shows any issue above "minor," block commit regardless of other scores.

**Phase to address:** `critic` (don'ts-axis calibration from known-liberties) + `ablation` (quarterly red-team) + `orchestration` (don'ts-severity hard gate).

---

### N-6: The Nahuatl ending sentence getting translated / glossed

**What goes wrong:** Chapter 27 ends with Malintzin's Nahuatl line — known-liberties is explicit that this is NOT translated. Someone along the pipeline (drafter, regen, chapter assembler, even chapter-critic suggesting a "clarification") adds a gloss, footnote, or translation. The landing of the book is compromised.

**Why it happens:** LLMs default to helpfulness. An unexplained foreign-language sentence feels like an error to a general LLM. Some component will try to "fix" it.

**Warning signs:**
- *Test:* snapshot test on Ch 27 final scene — assert no translation marker (parentheses with English, footnote markup) appears after the Nahuatl sentence.
- *Event log:* any regen on Ch 27 final scene is scrutinized for unwanted addition.

**Prevention:**
- Ch 27 final scene has an explicit **preservation directive** in its scene request: "The closing Nahuatl sentence is not to be translated, glossed, or footnoted. Any suggestion to do so is a CRITIC ERROR."
- Don'ts-axis rubric has an entry specifically for "untranslated ending preservation" that gates commit on Ch 27.
- Explicit snapshot test in `tests/` that checks the final committed Ch 27 text ends with Nahuatl.

**Phase to address:** `corpus+rag` (scene-specific preservation directives) + `critic` (Ch-27-specific rule) + `final` (snapshot test).

---

## 10. Integration failure modes

### I-1: Voice checkpoint silent corruption (paul-thinkpiece-pipeline sibling)

**What goes wrong:** The voice checkpoint file on disk gets partially corrupted (disk error, mid-copy during a sibling-project training run). vLLM still loads it but output quality drops. Mode A scenes suddenly worsen. Pipeline attributes it to "voice-FT can't do this beat," escalates, loses voice fidelity at scale.

**Why it happens:** Sibling project actively iterates on checkpoints. Disk pressure during training (documented breakthroughs at cu130 + packing 25x, plenty of ongoing activity). Checkpoint files aren't integrity-checked by most load paths.

**Warning signs:**
- *Test:* boot-time checkpoint SHA verification (see V-3). Mismatch = refuse to serve.
- *Telemetry:* first-token logit fingerprint drift on known anchor prompts. Canary prompt is "in one sentence, describe a dataset" — output logits should match pin baseline within epsilon.
- *Sibling coordination:* pipeline checks if sibling training run is active; if so, voice-pin SHA matches are extra important.

**Prevention:**
- Voice pin has SHA256 + first-token-logit canary. Both verified at drafter boot.
- Read-only binding: checkpoint directory is mounted read-only in the book pipeline's context. Sibling writes don't race with book reads.
- Explicit handoff protocol: sibling announces new checkpoint via a `ft_checkpoints/manifest.json`; book pipeline only considers checkpoints in the manifest.

**Phase to address:** `drafter` (SHA + canary verification) + `foundation` (sibling-pipeline handoff protocol).

---

### I-2: Entity-state from chapter K leaking into chapter K-2 when retroactively edited

**What goes wrong:** Paul edits chapter 5 to refine Andrés's emotional arc. The edit implies a different state by end of chapter 5 than what was originally extracted. Downstream chapter 6, 7, 8 drafted before the edit don't know. Chapter 9 about-to-draft uses the new state. Continuity break between chapter 8 (old state) and chapter 9 (new state) that is subtle because both pass axis checks individually.

**Why it happens:** Retroactive edits have ripple effects. The pipeline isn't designed for them. Canon is supposed to be write-once; in practice, human-in-the-loop editing is a real use case.

**Warning signs:**
- *Event log:* canon file modification after first commit.
- *Test:* git diff on canon/ chapter files — any chapter with multiple commits (not just initial creation) requires ripple-effect audit.
- *Retrospective:* chapter K+2 critic flags "implied state at start of scene doesn't match chapter K's end state" — may cite the wrong chapter because of the retroactive edit.

**Prevention:**
- Retroactive edit protocol: editing a committed chapter ≠ a normal commit. Spawns: re-extract entity-state, mark downstream chapters as "needs re-validation," trigger chapter-critic re-run on downstream chapters. This is a proper workflow, not a silent `git commit`.
- Weekly digest's integrity section lists any canon chapters modified after initial commit, alongside whether ripple protocol fired.
- Tooling: `gsd edit-chapter K` is a CLI that does the right thing; raw git edits are warned against in CONTRIBUTING.md.

**Phase to address:** `orchestration` (edit protocol + ripple trigger) + `observability` (integrity section in digest).

---

### I-3: Corpus updates not propagating through all 5 typed indexes

**What goes wrong:** Paul updates `our-lady-of-champion/our-lady-of-champion-engineering.md` with a new rule-card. Re-indexing fires for metaphysics retriever. But the historical retriever and arc-position retriever don't re-index (they don't consume engineering.md). Fine. But if the new rule card affects a character's possessions (e.g., Andrés's Reliquary monstrance construction), the entity-state index doesn't reflect it, because entity-state is auto-generated from chapters, not from bibles. Subtle inconsistency between bibles and entity-state.

**Why it happens:** Index ownership is per-source-doc but state flows across sources. "What does Andrés possess?" is answered by entity-state, which reads chapters, but chapters reference engineering.md rules implicitly. When engineering changes, chapters still say what they say.

**Warning signs:**
- *Test:* nightly corpus-version sanity: each index records the SHAs of source docs it was built from. Any stale SHA = re-index needed.
- *Telemetry:* retrieval events for a scene where engineering-retriever returned a rule with SHA X but character-bible-retriever returned content predating rule X.
- *Retrospective:* "this scene references a Reliquary behavior that seems inconsistent with the engineering bible I thought I updated."

**Prevention:**
- Each index records source-doc SHAs at build time. Re-index trigger compares current SHA set to recorded; mismatch forces rebuild.
- Cross-index consistency: when engineering bible updates, cross-reference against all currently-committed chapters for contradictions. Surface as retrospective observations, not silent.
- Corpus update is an atomic event: triggers all-index re-evaluation, not just the owning index.

**Phase to address:** `corpus+rag` (SHA-tracked indexes + cross-reference check) + `orchestration` (atomic re-index event).

---

### I-4: Retrospectives writing against a stale run state

**What goes wrong:** Retrospective writer runs post-commit. It reads events for the chapter. But there's a race: the chapter-critic event is still being written when retrospective fires. Retrospective writes based on incomplete event log. Missing observations.

**Why it happens:** Event-log writes are async / buffered. Post-commit triggers don't wait for all event consumers to flush.

**Warning signs:**
- *Test:* events for chapter N have timestamps after the retrospective event for chapter N. Flag.
- *Retrospective:* missing a reference to an event that clearly happened.
- *Digest:* retrospective quality downgrades on specific chapters (where race was worst).

**Prevention:**
- Chapter-commit event is a synchronization barrier: retrospective runs only after all prior-chapter events are flushed to log AND ledger aggregation completes.
- Retrospective prompt explicitly includes a "completeness check" — here are N events in your window, confirm all were considered.
- Orchestration DAG: retrospective is downstream of chapter-critic which is downstream of all scene-critics.

**Phase to address:** `orchestration` (DAG + flush barrier) + `observability` (retrospective completeness check).

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip voice-fidelity metric until digest is built | ship drafter 1 week sooner | thesis 001 can't be evaluated; 9 chapters of Mode A with no evidence on transfer | never — metric must be in from scene 1 |
| Use Opus for both Mode-B drafter AND critic | one model, one API key, simpler | self-preference bias (C-1); Mode-B pass rate inflated | acceptable only with periodic cross-family audit (10% scenes) |
| Inline prompts/outputs in event log (no blob store) | simpler schema, one file | event log hits 20GB+ in 2 months, queries slow | acceptable for first 3 chapters only; refactor before 9 |
| Single shared RAG pack for drafter + critic | one retrieval, half the cost | collusion failure (C-4); both share pack errors | acceptable at scene level; chapter-critic MUST re-query |
| Monolith critic instead of 5-axis | simpler rubric, faster prompts | thesis 004 unprovable; regen targeting weak (lower improvement per iteration) | never — testbed purpose demands axis decomposition |
| Hardcode "27 chapters" / "5 axes" / "3000 words" | config-light code, faster write | book-specific assumptions baked in; pipeline #2 can't reuse modules | acceptable in `book/` subpackage only; generic modules must be configurable |
| Retrospective as free-form prose | faster to prompt | becomes boilerplate (OB-3); thesis closure stalls | never — templated with required fields from day 1 |
| "Just run the same critic on regens" (no voice check) | simple | voice drift during regen (RE-2) undetected | never — fast voice check on regen output is cheap |
| Skip pre-flight GPU check | faster startup | zombie vLLM burns regen budget (O-5) | never; sibling project documented this exact failure |
| Manual mode pre-flag list maintenance (text file) | easy to edit | rots as outline evolves (M-3); misallocated budget | acceptable for Act 1 only; automate from ablation data by Act 2 |
| Synchronous event log writes (blocking) | never miss an event | drafter latency inflated by log writes | acceptable at low volume; switch to async-with-flush-barriers as volume grows |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| **vLLM + voice-FT checkpoint** | Load by path, trust the path | Verify SHA256 + first-token-logit canary at boot; refuse-to-serve on mismatch (V-3, I-1) |
| **Anthropic API (Opus critic)** | Use same model for drafter + critic when in Mode B | Cross-family spot-check 10%+ of scenes; flag same-family scores explicitly (C-1) |
| **pgvector / lancedb** | Assume index is current because the last ingest was today | Every index records source-doc SHAs; re-index on SHA change, not just on file mtime (I-3) |
| **openclaw systemd --user** | Assume it runs when the machine is up | Enable lingering; add dead-man heartbeat + Telegram alert (O-1, O-4) |
| **sibling paul-thinkpiece-pipeline** | Silently swap checkpoints | Checkpoint manifest + pin SHA + read-only mount (I-1) |
| **our-lady-of-champion/ corpus** | Update the doc, trust re-indexer | Atomic update event triggers ALL-index SHA check (I-3) |
| **git canon commits** | Amend / edit committed chapter silently | Retroactive edit protocol: re-extract + ripple + downstream re-validate (I-2) |
| **Telegram alerting** | One channel for everything | Tiered: hard-block (page), quality-alarm (notify), weekly-digest (email-style). Prevents alert fatigue |
| **PostgreSQL (if chosen)** | VACUUM disabled / autovacuum tuning | At 20GB events table, autovacuum lag causes bloat; set tight autovacuum_scale_factor |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Events.jsonl inline prompts | file >1GB; digest slow | Content-addressed blob store (OB-1) | 2 months of activity (~5k scenes × 5 events × 30KB avg) |
| Full corpus in context | Voice drift, critic degrades | Typed RAG with pack cap (R-3, thesis 005) | Immediately — corpus is 250KB |
| Entity-state regeneration per scene (not cached) | drafter latency adds 10+s per scene | Cache entity cards, rebuild on commit not per-query | 3 chapters in |
| Critic prompt length with all-axes + full pack + scene | Claude Opus anchor collapse (C-2) | Split critic calls per axis if prompt >60KB total | Chapter 3+ once entity state grows |
| Re-embedding entire corpus on any corpus edit | Hours of compute for minor fixes | Chunk-level incremental re-embed by SHA diff | Corpus edit frequency >1/week |
| vLLM model reload per scene | 30s startup × scenes = hours wasted | Keep vLLM warm, one process lifecycle per workday | Any volume above debugging |
| Postgres autovacuum lag on events | Queries slow down over weeks | Tight autovacuum_scale_factor; partition events by month | 6-12 months of production |
| Synchronous metric-ledger updates blocking commit | Commit latency grows | Async aggregation with reconciliation check (OB-2) | After 100+ scenes committed |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **RAG retrieval works:** Also check — does bundler reconcile conflicts between retrievers? Does each retriever return rule-type metadata? Are SHAs tracked per index? Golden-query accuracy set in place? (R-1, R-4, I-3)
- [ ] **Critic passes scenes:** Also check — variance across scenes non-trivial (not all 4/5)? Cross-family spot-check done? Don'ts-axis calibrated against known-liberties.md specifically? Severity stable across chapters? (C-1, C-2, C-3, N-5)
- [ ] **Mode-B escape implemented:** Also check — escape rate tracked and alarmed? Voice fidelity reported separately for Mode A/B? Pre-flag list in config not in prose? (M-1, M-2, M-3)
- [ ] **Retrospective writer running:** Also check — required fields populated? Passage references resolve? Metric references match ledger? Non-boilerplate content? (OB-3)
- [ ] **Thesis registry functional:** Also check — every open thesis has metric + test_design + deadline? Closure evaluations scheduled at milestones? Closed theses produce reusable artifacts, not just conclusions? (OB-4, T-2, T-4)
- [ ] **Entity-state auto-extracting:** Also check — cards carry source_chapter_sha? Stale-card detection in digest? Retroactive edits trigger re-extract? (R-2, I-2)
- [ ] **Orchestration running nightly:** Also check — dead-man heartbeat? systemd lingering enabled? Pre-flight GPU check? Restart policy tested via deliberate fault injection? (O-1, O-3, O-4, O-5)
- [ ] **Event log emitting:** Also check — checkpoint_sha on every drafter event? Mode tag required in schema? Blob store separated from metadata? (V-3, M-2, OB-1)
- [ ] **Weekly digest generating:** Also check — mode distribution top-level? Regen cost histogram? Stale-card panel? Open-thesis aging panel? Run count / hours-of-activity leading? (M-1, RE-3, R-2, OB-4, O-1)
- [ ] **Ablation harness available:** Also check — SHA snapshot before run? All configs frozen? Validity sanity-check? Results land in structured location with metadata? (T-1)
- [ ] **Pipeline produces chapters:** Also check — passed subjective Paul-read sample? Thematic-spine advance auditable? Character arcs legibly earned? Pacing reasonable? Ch 27 Nahuatl preserved? (N-1, N-2, N-3, N-4, N-6)
- [ ] **Chapter commits to canon:** Also check — retroactive edits handled? Chapter-level critic re-queries RAG independently? Beat coverage verified? (I-2, C-4, RE-4)

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| V-1 register collapse | MEDIUM | Re-run affected chapters with tighter voice-axis prompt; if persistent, add fiction exemplars to next FT iteration |
| V-2 training memorization | HIGH | Block affected scenes from canon; reduce LoRA rank in next FT; add dedup pass to training corpus |
| V-3 checkpoint drift | LOW | SHA check catches immediately; re-serve correct checkpoint, re-run affected scenes |
| R-1 retriever divergence | MEDIUM | Add reconciliation step; re-run affected chapters with new bundler; archive divergent runs |
| R-2 stale entity leak | MEDIUM | Force re-extract all post-edit chapters; chapter-critic re-run on ripple set |
| R-3 pack bloat | LOW | Revert to hard cap; regenerate affected scenes; update config guardrail |
| R-4 wrong-fact retrieval | HIGH | Chunking redo on affected source doc; golden-query validation; re-run all scenes drawing from that doc |
| R-5 missed don'ts | HIGH (editorial risk) | Manual review of affected scenes; if committed, rewrite; expand tag map + critic rubric |
| C-1 self-preference | MEDIUM | Add cross-family audit; reweight per-axis scores using delta; flag historical scores |
| C-2 collapsed variance | MEDIUM | Revise rubric to checklist form; rerun critic on 20 scenes as calibration; accept that some historical scores were inflated |
| C-3 severity drift | LOW | Apply frozen-set recalibration to identify drift magnitude; revise rubric anchors |
| C-4 critic-drafter collusion | MEDIUM | Chapter-level critic with fresh pack; cross-family spot-check; identify affected chapters for re-score |
| C-5 false-positive regens | LOW | Split rubric severities into HARD/SOFT; retroactively recompute regen need; reclaim budget |
| RE-1 oscillation | LOW | Detector fires; escalate to Mode B; investigate underlying retriever conflict |
| RE-2 voice drift in regen | LOW | Fast voice check on regen; restore pre-regen if worse |
| RE-3 cost explosion | MEDIUM | Hard cost cap catches mid-run; escalate or pause; review pre-flag list |
| RE-4 beat-deletion regen | LOW | Length constraint catches; re-run regen with beat-preservation directive |
| M-1 Mode-B creep | HIGH | Pause auto-escalation; review mode distribution; open book-voice FT thesis |
| M-2 voice metric distortion | LOW | Regenerate metric with mode filter; update digest schema |
| M-3 pre-flag list rot | LOW | Automated outline-flag-map check; update flags; re-run affected scenes |
| O-1 missed cron | MEDIUM | Heartbeat alarm triggers investigation; run manually to catch up; fix underlying systemd issue |
| O-2 extractor race | MEDIUM | DAG enforcement; for affected chapters, force re-extract + chapter-critic re-run |
| O-3 state corruption | MEDIUM | WAL replay; reconstruct state from events; re-verify canon consistency |
| O-4 gateway death | LOW | Watchdog alarm; systemd restart; review logs |
| O-5 stuck vLLM | LOW | Pre-flight check catches; kill + restart; rerun affected scenes |
| OB-1 log bloat | LOW | Migrate to blob store; rotate archives; rebuild queryable ledger |
| OB-2 ledger drift | MEDIUM | Reconciliation rebuild from events; audit past decisions made on drifted data |
| OB-3 boilerplate retrospective | MEDIUM | Template retrospective with required fields; rerun retrospectives for past chapters (optional, expensive) |
| OB-4 thesis ossification | LOW | Force-evaluate at next milestone; archive inconclusive theses; prune stale ones |
| T-1 confounded ablation | MEDIUM | Invalidate ablation; rerun with SHA-frozen snapshot; update ablation protocol |
| T-2 vague theses | LOW | Linter pass; demote non-compliant open theses to "draft" state |
| T-3 book leakage into kernel | HIGH (at extraction time) | Module-boundary audit; config-extract hardcodes; may require rewriting parts of kernel modules |
| T-4 vague transferable artifacts | MEDIUM | Closure template requires all four artifact types; retroactive fill for existing closed theses |
| N-1 dead prose | HIGH (editorial risk) | Add reader-pull axis; reserve no-regen scenes; Paul spot-check protocol; revise affected chapters |
| N-2 thematic spine loss | HIGH (editorial risk) | Chapter-level thematic audit; outline thematic tags; may require chapter rewrites in Act 2 |
| N-3 pacing collapse | MEDIUM | Pacing axis + assembler pacing pass; revise chapter structure in affected chapters |
| N-4 arc not landing | HIGH | Character-state cards + interior-change axis; milestone POV audits; may require character rewrites |
| N-5 sensitive content failure | HIGH (editorial risk) | Don'ts-axis hard gate; red-team probe; rewrite affected scenes; audit known-liberties alignment |
| N-6 Nahuatl glossed | LOW | Snapshot test; preservation directive; revert any such edit |
| I-1 voice checkpoint corrupt | LOW | SHA + canary catches; fall back to prior pinned checkpoint |
| I-2 retroactive edit ripple | MEDIUM | Edit protocol + ripple triggers; re-extract + re-validate downstream |
| I-3 stale index vs bibles | MEDIUM | SHA-tracked indexes; rebuild affected; cross-reference scan |
| I-4 retrospective race | LOW | Flush barrier + completeness check; rerun retrospective |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall ID | Name | Prevention Phase | Verification |
|------------|------|------------------|--------------|
| V-1 | Register collapse | `drafter` + `critic` + `observability` | voice-fidelity mean + per-sub-genre metric in digest |
| V-2 | Training memorization | `drafter` + `critic` + `observability` | n-gram overlap gate in place; probe test passes |
| V-3 | Checkpoint pin drift | `foundation` + `drafter` + `observability` | SHA + canary verified; `checkpoint_sha` in every event |
| R-1 | Retriever divergence | `corpus+rag` + `observability` + `ablation` | reconciliation step emits conflict events; conflict rate tracked |
| R-2 | Stale entity leak | `corpus+rag` + `orchestration` + `observability` | `source_chapter_sha` in cards; stale-card panel in digest |
| R-3 | Pack bloat | `corpus+rag` + `observability` + `ablation` | hard cap enforced; distribution in digest; thesis 005 closes |
| R-4 | Wrong-fact retrieval | `corpus+rag` + `observability` | golden-query set accuracy >95% nightly |
| R-5 | Missed don'ts | `corpus+rag` + `critic` | tag-map covers all chapters; don'ts-axis catch rate >90% on probes |
| C-1 | Same-family self-preference | `critic` + `ablation` + `observability` | cross-family 10% audit shows delta within bound |
| C-2 | Score collapse | `critic` + `ablation` + `observability` | variance/correlation watchdog; injection probe monthly |
| C-3 | Severity drift | `critic` + `observability` | frozen recalibration set drift <1 severity level |
| C-4 | Critic-drafter collusion | `critic` + `observability` | chapter-critic fresh-pack audit passes |
| C-5 | False-positive regens | `critic` + `regen` + `observability` | HARD/SOFT split; regen-per-scene in digest stable |
| RE-1 | Oscillation | `regen` + `observability` | oscillation detector fires; pattern in retrospective |
| RE-2 | Regen voice drift | `regen` + `critic` | post-regen voice delta <threshold |
| RE-3 | Cost explosion | `orchestration` + `regen` + `ablation` | hard per-scene cost cap; alert on breach |
| RE-4 | Beat-deletion regen | `regen` + `critic` | length constraint + beat-coverage axis |
| M-1 | Mode-B creep | `orchestration` + `observability` + `ablation` | rolling rate alarm at 40%; digest prominence |
| M-2 | Voice metric distortion | `observability` + `critic` | mode-segmented voice reporting in digest |
| M-3 | Pre-flag list rot | `foundation` + `ablation` + `observability` | outline/flag-map schema validation |
| O-1 | Missed cron | `orchestration` + `observability` | heartbeat alarm; run count in digest |
| O-2 | Extractor race | `orchestration` + `corpus+rag` | DAG enforced; SHA check in drafter entry |
| O-3 | State corruption | `orchestration` + `observability` | atomic writes + WAL; recovery script |
| O-4 | Gateway death | `orchestration` + `observability` | watchdog alarm |
| O-5 | Stuck vLLM | `orchestration` + `drafter` | pre-flight GPU check |
| OB-1 | Event log bloat | `observability` + `orchestration` | blob store + rotation; disk usage monitored |
| OB-2 | Ledger drift | `observability` + `ablation` | idempotent aggregator + integrity line in digest |
| OB-3 | Boilerplate retrospectives | `observability` + `critic` | template lint; non-boilerplate test |
| OB-4 | Thesis ossification | `observability` + `ablation` | milestone auto-evaluation |
| T-1 | Confounded ablation | `ablation` + `observability` | SHA-frozen snapshot protocol |
| T-2 | Vague theses | `observability` + `ablation` | thesis schema linter |
| T-3 | Book-leak into kernel | `foundation` + all phases + `final` | module boundary lint; hypothetical-blog review |
| T-4 | Vague artifacts | `observability` + `final` | closure template with four artifact types |
| N-1 | Dead prose | `critic` + `regen` + `observability` | reader-pull axis; no-regen tier; weekly spot-check |
| N-2 | Thematic spine loss | `corpus+rag` + `critic` + `foundation` | thematic tags in outline; chapter-level thematic axis |
| N-3 | Pacing collapse | `critic` + `drafter` + `observability` | pacing axis; scenes-per-chapter metric |
| N-4 | Arc not landing | `corpus+rag` + `critic` + `observability` | character-state cards; interior-change sub-axis |
| N-5 | Sensitive content | `critic` + `ablation` + `orchestration` | don'ts calibration; red-team probe |
| N-6 | Nahuatl glossed | `corpus+rag` + `critic` + `final` | scene directive; Ch 27 snapshot test |
| I-1 | Voice checkpoint corrupt | `drafter` + `foundation` | SHA + canary verification |
| I-2 | Retroactive edit ripple | `orchestration` + `observability` | edit protocol + ripple trigger |
| I-3 | Stale index vs bibles | `corpus+rag` + `orchestration` | SHA-tracked indexes |
| I-4 | Retrospective race | `orchestration` + `observability` | DAG flush barrier |

---

## Sources

- Project-internal: `.planning/PROJECT.md`, `docs/ARCHITECTURE.md`, `docs/ADRs/001-004`, `theses/open/001-005` (HIGH confidence — authoritative for this project's intent).
- Domain brief: `our-lady-of-champion-brief.md`, `our-lady-of-champion-known-liberties.md` (HIGH confidence — source of thematic-spine and content-landmine pitfalls).
- Sibling project context: `paul-thinkpiece-pipeline` memory entries on vLLM systemd ownership and GPU-zombie failures (HIGH confidence — documented user experience).
- 2025 LLM-judge bias literature (MEDIUM confidence — informs C-1, C-2): Preference Leakage (arxiv 2502.01534), Self-Preference Bias in LLM-as-a-Judge (arxiv 2410.21819), Justice or Prejudice? (llm-judge-bias.github.io), LLM-as-a-Judge reliability survey (Adaline).
- 2025 RAG failure-mode literature (MEDIUM confidence — informs R-1 through R-4): "Ten Failure Modes of RAG Nobody Talks About" (dev.to), "23 RAG Pitfalls" (nb-data.com), "RAG System in Production" (47billion.com), Snorkel RAG failure modes blog, RAGFlow 2025 year-end review, OG-RAG ontology-grounded retrieval (ACL 2025).
- 2025 catastrophic-forgetting / FT-transfer literature (MEDIUM confidence — informs V-1, V-2): "Mitigating Forgetting in LLM Fine-Tuning" (OpenReview 2025), "Mechanistic Analysis of Catastrophic Forgetting" (arxiv 2601.18699), "Mitigating Catastrophic Forgetting" (ACL EMNLP 2025).
- General software-engineering discipline (HIGH confidence): atomic writes, WAL, SHA-based integrity, dead-man heartbeats — standard practice.

---
*Pitfalls research for: autonomous LLM-based long-form creative-writing pipeline (our-lady-book-pipeline)*
*Researched: 2026-04-21*
