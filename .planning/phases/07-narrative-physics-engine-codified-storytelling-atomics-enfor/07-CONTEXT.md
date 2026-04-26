# Phase 7: Narrative Physics Engine - Context

**Gathered:** 2026-04-25 (seed) + 2026-04-25 (discuss-phase deep-dive)
**Status:** Ready for research
**Source:** Operator directive 2026-04-25 (post-V7C handoff session) + discuss-phase 2026-04-25

<domain>
## Phase Boundary

Phase 7 builds the **Narrative Physics Engine** — the metadata + rules + enforcement layer that codifies storytelling atomics so the pipeline can draft and validate scenes against narrative invariants the way Unreal Engine validates motion against physical invariants.

The mental model: every scene is a **rigid body** with declared properties (POV, characters, motivations, voice, treatment, beat function, scene-buffer ownership). The engine refuses to draft scenes whose properties violate continuity, refuses to commit scenes whose output drifts from declared properties, and refuses to assemble chapters whose scenes contradict each other.

**Forward-only scope (D-21 lock):** Phase 7 builds the engine to make **future generation correct** — ch15-27 + ch09 retry. ch01-14 are historical artifacts; the engine does NOT retrofit them. Re-DAG of ch05-14 is opportunistic / out-of-scope-for-acceptance. ch01-04 (proper-DAG output) remain available as a read-only regression-sanity baseline; the engine MAY validate against them as a smoke test, but produces no commits to them.

**Phase 7 is a single integrated system** — not a list of fixes — that subsumes every drift class seen in the ch01-14 ship cycle (and locks future generation against re-occurrence):

- Drafter overlap (sc01 content regenerated as sc02) — solved by **declared content ownership** + **scene-buffer dedup as critic axis (BGE-M3 cosine ≥ 0.80)**
- POV breaches (Andrés POV recycled Itzcoatl interior in ch09 sc01) — solved by **enforced perspective metadata gate at drafter pre-flight + pov_fidelity critic axis**
- Continuity drift (Andrés age 26→23, La Niña height 50→60→55→42 ft, Santiago del Paso 210ft/300ft/11 stories, Cholula date stub Oct 30 vs canon Oct 18, Cempoala double-arrival) — solved by **6th RAG axis (continuity_bible) with verbatim canonical injection**
- Stub leakage into canon (ch11 sc03 line 119 "Establish: ...") — solved by **stub_leak critic axis with hard reject + scene-kick**
- Degenerate loops (ch10 sc02 "He did not sleep...") — solved by **repetition_loop critic axis**
- Itzcoatl POV regression (1st in ch01 → 3rd from ch06) — solved by **pov_lock layer (per-character POV mode)**, activated **starting ch15** (see Open Questions for ch09 retry)
- Retrospective writer argv overflow — solved as a side-fix (pipe via stdin) — Claude's Discretion placement

</domain>

<decisions>
## Implementation Decisions

### LOCKED — Operator directive 2026-04-25

**D-01: Narrative Physics metaphor is the architectural commitment.** The engine implements narrative physics like Unreal Engine implements real physics. Every scene declares its properties up-front; gates enforce them at draft time AND at critic time AND at chapter-assembly time. Drift = constraint violation = engine refuses to advance.

**D-02: Character motivation is the load-bearing axis. Always center.** Every scene's metadata MUST declare each present character's active motivation for that scene. A scene without a centered motivation is a scene that does not exist. The drafter prompt includes motivation as a top-of-prompt anchor; the critic has a rubric axis whose sole job is "did the scene serve declared motivation, or drift?".

**D-03: Codified Scene Metadata Schema** (operator-listed, MANDATORY fields):
- **Contents** — what physically/narratively happens in the scene (beat function expanded; the "kill", the "confession", the "wake")
- **Characters present** — explicit list with on-screen vs off-screen distinction
- **Character motivation** — per-character motivation, anchor of the scene
- **Voice** — the voice configuration (which FT pin, which sampling profile)
- **Perspective** — POV: 1st person / 3rd close / 3rd omniscient / etc. STRICT enforcement (ch09 was the canary)
- **Treatment** — emotional/tonal register: dramatic / mournful / comedic / light / propulsive / contemplative / etc.

Each field is **machine-validatable** — the schema is enforceable, not aspirational.

**D-04: Theater of the mind.** Scenes are staged in a constructed mental theater whose rules are explicit. The metadata schema is the playbook for that theater. The drafter receives the playbook; the critic checks the performance against the playbook.

**D-05: Full autonomous.** No new human-in-the-loop steps. The engine catches its own violations and routes recovery via the existing scene-kick + Mode-B escape flows.

**D-06: Heavy research is required before plan.** Storytelling atomics — the discrete, re-combinable units that craft texts have used for centuries — must be sourced from craft theory (Story Grid, Save the Cat, Robert McKee, John Truby, Sol Stein, Ursula Le Guin, Brandon Sanderson essays, Aristotle's Poetics structural primitives, theatrical beat theory, screenplay scene-card systems) and codified into our schema. This is not "what does Claude know about writing"; this is "what does the craft literature canonize, and how do we map it to enforceable Pydantic models?"

### LOCKED — Pipeline learnings carried forward

**D-07: Existing primitives are the substrate.** Phase 7 does NOT rewrite drafter / critic / DAG / regenerator. It extends the existing kernel packages with metadata-aware gates:
- `book_pipeline.drafter.mode_a` — gains pre-flight check that scene metadata is complete + consistent before any vLLM call
- `book_pipeline.critic.scene_critic` — gains rubric axes derived from declared scene metadata (POV-fidelity axis, motivation-fidelity axis, treatment-fidelity axis, content-ownership axis)
- `book_pipeline.chapter_assembler.dag` — gains canon-bible reconciliation step that cross-checks scene metadata against the running canon-bible
- `book_pipeline.regenerator.scene_local` — gains awareness of which metadata axis was violated so regen prompts target the breach
- `book_pipeline.rag.bundler` — extended with scene-buffer dedup that hashes prior-scene content and refuses to surface it as inspiration for the next scene

**D-08: Re-DAG migration scope = ch05-14.** Operator read the manuscript. ch01-04 (proper DAG) ship as-is — voice locked, characters distinct, period dense, Cortés-as-lawyer thematic line lands. ch05-14 (manual_concat) = ~50% duplicate junk and re-DAG under V7C LoRA. ch01-04 are the **frozen baseline** the engine validates against (read-only canary).

**D-08a: Stop shipping manual_concat.** The `scripts/ship_chapter.sh` bypass produced the duplication disaster. Phase 7 retires manual_concat entirely; deadline pressure does not justify it.

**D-09: Canon-bible continuity layer.** The 5-axis RAG already has entity-state. Phase 7 adds a higher-order **canon-bible** view that compiles entity-state + retrospectives + committed scene metadata into a queryable book-state object. Drafter consults canon-bible at scene preflight; chapter critic consults canon-bible at chapter-critic time; regenerator consults canon-bible when a continuity axis fires.

**D-10: Scene-buffer dedup.** The prior-scenes context (currently raw concatenation) is replaced with a **scene-buffer** that:
- Hashes each prior scene's content
- Surfaces only the **declared metadata** of immediately-prior scenes to the current draft (not their full text), eliminating model temptation to re-narrate
- Surfaces full prior-scene text only when the current scene's metadata explicitly requires continuity reference (e.g., callback)
- Prevents the sc01-content-as-sc02 bug class

**D-11: Drafter/critic gates as first-class artifacts.** Each gate is a named, testable, mockable component. Gates live in `book_pipeline.physics.gates.*` (new kernel package). Gates emit `role='physics_gate'` Events on every check (pass + fail) per OBS-01.

**D-12: Re-DAG migration is part of Phase 7 acceptance.** Phase 7 is not "complete" until ch05-14 are re-DAG'd clean OR have explicit logged exceptions. ch01-04 are validated read-only. The engine's first job is to report on the existing book.

### LOCKED — Operator manuscript-read assessment 2026-04-25

**D-13: Tighter beat boundaries per scene.** Stub `beat_function` must explicitly declare ownership: e.g. "sc01 OWNS arrival; sc02 OWNS decision; sc03 OWNS consequence — DO NOT re-narrate sc01 events." This becomes a metadata-schema field (`owns:` and `do_not_renarrate:`), not a string-prefix hack. The drafter prompt template injects ownership at top-of-prompt; the critic has a dedicated rubric axis "content_ownership_breach" that fires if scene N reproduces beats declared as scene M's ownership.

**D-14: Scene-buffer dedup with similarity threshold.** Concrete spec: at scene-buffer assembly, hash each prior scene's prose; if the candidate next-scene draft is ≥80% similar to any prior scene by content fingerprint (BGE-M3 cosine OR rolling shingle similarity — researcher picks), reject the draft and route to scene-kick + re-stub with sharper ownership directive. Threshold tunable in `config/mode_thresholds.yaml`; 80% is the v1 default per operator.

**D-15: Continuity-bible retriever (CB-01).** A new RAG axis dedicated to **named-quantity continuity** — character age, ship/structure dimensions, location dates, named-entity sizes. Not the same as `entity_state` (which is broader). The retriever returns canonical values for any named quantity referenced in the scene stub, and the drafter prompt MUST reproduce them verbatim. Critic has a `named_quantity_drift` axis. Canary cases this gate must catch:
- Andrés age regression (ch02:26 → ch04:23 → ch08:23 — non-monotonic)
- La Niña height drift (50ft → 60ft → 55ft → 42ft)
- Santiago del Paso scale (210ft / 300ft / 11 stories — three values for one apex deterrent)
- Cempoala double-arrival (ch03 sc02 + ch04 sc02)
- Cholula date drift (stub Oct 30 vs canon Oct 18)

**D-16: Per-character-per-chapter POV mode in metadata.** Itzcoatl was 1st person ("I was sixteen") in ch01 sc03 and 3rd person from ch06 onward — a regression. The schema's `perspective` field is per-scene, but a higher-order **pov_lock** layer pins `<character> = <pov_mode>` for the lifetime of the book unless explicitly overridden in stub frontmatter with rationale. Without operator-acknowledged override, drafter must respect the lock. The 1st-person Itzcoatl voice is the locked target; ch06+ Itzcoatl regression is a bug to fix on re-DAG.

**D-17: Stub-leak-into-canon detection.** ch11 sc03 line 119 contains literal stub prose: `Establish: the friendship that will become Bernardo's death-witness in Ch 26.` — beat_function regurgitated as narration. Engine MUST refuse to commit a scene whose body contains stub vocabulary (pattern: leading `Establish:`, `Resolve:`, `Set up:`, `[character intro]:`, etc., or substring match against the originating stub's beat_function string itself). This is a drafter-output linter, not a critic-rubric judgment call — black-and-white pattern check.

**D-18: Quote-extraction robustness.** ch13 sc02/sc03 dialogue mangled with `., ` corruption sequences — quote-extraction parser broke on input. Engine ships a defensive quote-extraction normalizer that flags + repairs these patterns OR refuses to commit. This may be a Plan 07-NN side fix or rolled into the canon-bible commit gate.

**D-19: Degenerate-loop detector.** ch10 sc02 went full repetition: "He did not sleep. He did not sleep the next night. He did not sleep the next night either. He was tired. He was not tired. He was tired and not tired." The engine MUST detect repetition-loop output (n-gram repetition above threshold, or sentence-embedding self-similarity above threshold within a single scene) BEFORE committing. This is a runtime safety check distinct from voice-fidelity (OBS-03).

**D-20: Research output is `NARRATIVE_PHYSICS.md`** (in addition to standard `07-RESEARCH.md`). The narratology synthesis — Genette/Bal focalization, Swain scene/sequel structure, McKee scene-bones, Booth showing-vs-telling, theater-of-mind from radio-drama craft, Save-the-Cat beat enforcement — is a first-class deliverable researcher writes. This is the canon the engine implements; planner reads it directly when designing schema enums and gate semantics.

### LOCKED — discuss-phase 2026-04-25

**D-21: Forward-only scope. SUPERSEDES D-08 + D-12.** Phase 7 builds the engine to make **future generation correct** (ch15-27 + ch09 retry). ch01-14 are historical artifacts; the engine does NOT retrofit them. Re-DAG of ch05-14 is opportunistic / out-of-scope-for-acceptance. Phase 7 acceptance = engine ships clean + ch15+ generation passes all gates clean (NOT gated on ch05-14 re-DAG). ch01-04 remain available as a read-only regression-sanity baseline. Operator quote: *"We are not building to fix what's been done but to make sure the future is correct."*

**D-22: Continuity-Bible (CB-01) lives as a new 6th RAG axis.** New retriever `src/book_pipeline/rag/retrievers/continuity_bible.py`. New `lance_schema` rule_type `'canonical_quantity'` (additive nullable per D-11 contract from Plan 05-03). Existing 5 retrievers (historical / metaphysics / entity_state / arc_position / negative_constraint) untouched. Bundler extension surfaces continuity_bible hits to the drafter prompt. Conflict_detector gains `named_quantity_drift` dimension. Reasons: pure architectural extension (not a kitchen-sink dilution of entity_state), keeps axis purity for critic-rubric mapping clean, fits ADR-002 5-axis paradigm.

**D-23: Canonical quantities inject verbatim into drafter prompt header.** Top-of-prompt block stamps the canonical values for every named quantity referenced in the scene stub: `CANONICAL: Andrés age=23 (this chapter), La Niña height=55ft, Cholula date=Oct 18 1519. Reproduce exact values.` Drafter cannot drift if the values are stamped in the prompt. Aligns with D-13 ownership-anchor pattern (top-of-prompt anchors are load-bearing).

**D-24: Physics gates fire at drafter pre-flight ONLY (no separate commit-time hook).** Pre-flight = metadata schema validation (Pydantic-strict on stub frontmatter) + pov_lock consistency + CB-01 canonical-value retrieval + ownership/do_not_renarrate declaration sanity. Refuses to draft if invalid. Same pattern as existing `drafter.memorization_gate` + `drafter.preflag`. Two enforcement points total: pre-flight (cheap, before any model call) + critic-time rubric axes (after expensive draft).

**D-25: New `book_pipeline.physics` kernel package** (joins drafter / critic / regenerator / chapter_assembler / rag / observability / alerts as 7th kernel pkg per ADR-004). Layout:
- `physics/schema.py` — Pydantic models for scene metadata (contents, characters_present, motivation, voice, perspective, treatment, owns, do_not_renarrate)
- `physics/canon_bible.py` — higher-level reader composing CB-01 retriever + entity_state + retrospectives into a queryable `CanonBibleView` object
- `physics/gates/__init__.py` — gate registry
- `physics/gates/{pov_lock,motivation,ownership,treatment,quantity}.py` — pre-flight gates (one file per gate, named/testable/mockable per D-11)
- `physics/locks.py` — pov_lock storage (location TBD by planner — see Claude's Discretion)
- import-linter contract extension: `book_pipeline.physics` added to source_modules + book-domain forbidden_modules (precedent: Plan 05-03 alerts pattern). `lint_imports.sh` mypy scope extended.
- Each gate emits `role='physics_gate'` Events on every check (pass + fail) per OBS-01.

**D-26: Critic absorbs all post-draft physics checks as new rubric axes.** Existing 5-axis critic (historical, metaphysics, entity_state, arc, don'ts per CRITIC-01) extends to 13 axes. New axes:
- `pov_fidelity` — declared perspective vs produced
- `motivation_fidelity` — declared per-character motivation vs delivered (load-bearing per D-02)
- `treatment_fidelity` — declared tonal register vs delivered
- `content_ownership` — scene N's prose against scenes M's `owns`/`do_not_renarrate` (D-13)
- `named_quantity_drift` — values produced vs CB-01 canonical (D-15)
- `stub_leak` — regex pattern check (D-17, hard reject)
- `repetition_loop` — runtime safety check (D-19)
- `scene_buffer_similarity` — BGE-M3 cosine ≥ 0.80 vs prior scenes (D-14, D-28)

Critic prompt cost grows; `templates/scene_critic.j2` and structured-output schema both extend. Existing scene-kick recovery loop (Plan 05-02) handles routing on FAIL via `extract_implicated_scene_ids` regex which already supports `\bch(\d+)_sc(\d+)\b` — the new axes' issues conform.

**D-27: Stub-leak severity = hard reject + scene-kick.** Stub vocabulary in canon = unambiguous bug (ch11 sc03 line 119 canary). Black-and-white pattern check (regex on leading `Establish:` / `Resolve:` / `Set up:` / `[character intro]:` / substring match against beat_function string). On detect: critic emits high-severity issue → existing scene-kick → re-stub with sharper directive. Not a soft warn, not auto-strip — root cause is drafter prompt issue, not output cleanup.

**D-28: Similarity-dedup method = BGE-M3 cosine ≥ 0.80.** Reuse existing `book_pipeline.rag.embedding.BgeM3Embedder` (Phase 2). Cosine similarity between candidate scene embedding and each prior committed scene embedding. ≥ 0.80 = recap → critic axis FAIL → scene-kick. Threshold tunable in `config/mode_thresholds.yaml`. Semantic similarity catches paraphrased recaps (lexical-only would miss). Cost: one extra embedder call per scene critic-time (already part of OBS-03 pipeline footprint).

### Claude's Discretion

- **Schema container shape** — YAML frontmatter in `drafts/chNN/chNN_scNN.md` (extends current pattern) vs separate JSON sidecar vs both. Planner picks based on tooling friction.
- **POV-lock storage location** — `config/pov_locks.yaml` (static hand-edit) vs `entity-state/` cards (dynamic, derivable) vs new `physics/locks.yaml` artifact. Planner picks; precedent suggests `config/` for invariant locks.
- **Treatment vocabulary** — closed enum (codified, easy to enforce) vs open string with regex constraint vs hybrid starter-enum-plus-extra. Planner picks based on NARRATIVE_PHYSICS.md craft research.
- **Beat-function overlap semantics** — strict partition (each beat element = exactly one scene) vs declared `shares_with: [scN]` (reference allowed; recap not). Planner picks; D-13 ownership pattern leans strict.
- **Motivation-axis critic weight** — equal weight with other 12 axes, OR motivation FAIL = scene FAIL regardless of other axes (per D-02 "load-bearing"). Recommend operator-strong default = motivation FAIL is hard-stop.
- **Stub-leak regex pattern set** — exact list of `Establish:` / `Resolve:` / `Set up:` / `[character intro]:` / etc. Planner extracts from existing stub authoring conventions in `drafts/chNN/`.
- **Degenerate-loop detection method** — n-gram repetition threshold (k? threshold?) OR sentence-embedding self-similarity within scene (threshold?) OR both. Planner picks; recommend cheap n-gram first, BGE self-sim as v1.1 if signal weak.
- **Quote-extraction robustness placement (D-18)** — fold into critic as `quote_corruption` axis, OR side-fix in chapter_assembler pre-commit normalizer, OR both. Planner picks.
- **NARRATIVE_PHYSICS.md depth** — comprehensive scholar treatise (Genette/Bal full focalization theory + Swain scene/sequel + Booth + McKee + Save-the-Cat + Aristotle Poetics) vs implementation-targeted brief vs two-tier (brief + appendix). Researcher picks; default = two-tier.
- **Plan rollout order** — schema-first vs gate-first vs CB-01-first. Planner picks via dependency graph (likely: schema → CB-01 retriever → pre-flight gates → critic axes → integration test against ch15 sc02).
- **Engine validation against ch01-04 frozen baseline** — read-only smoke test that engine flags zero false positives on known-good chapters. Planner decides whether to make this a Phase 7 gate test or defer.

</decisions>

<open_questions>
## Open Questions for Operator

These have material plan/code consequences but were not resolved in discuss-phase. Surfacing for explicit answer before plan-phase or during planner's first pass.

**OQ-01: Ch09 retry POV mode.** D-16 locks Itzcoatl = 1st person. ch01 sc03 was 1st ("I was sixteen"). ch06-14 went 3rd (the regression). Per D-21 forward-only, ch06-14 are historical artifacts. Ch09 retry sits **inside** the ch06-14 historical block.

Two reasonable resolutions:
- **(a)** Ch09 retry follows surrounding historical style (3rd person Itzcoatl) — preserves intra-block continuity, even though that block is acknowledged drift. POV-lock activates **starting ch15**.
- **(b)** Ch09 retry goes 1st person per D-16 lock — restores correct POV but creates discontinuity (ch08 = 3rd → ch09 = 1st → ch10-14 = 3rd → ch15+ = 1st).

**Claude's recommendation: (a)** — discontinuity inside a known-bad block (operator's own assessment: "~50% duplicate junk") is acceptable; ch15+ is the forward-correctness target. POV-lock for Itzcoatl activates at ch15 per D-21.

**OQ-02: Ch09 retry post-V7C.** Per HANDOFF_2026-04-25.md, ch09 hard-blocked because all 4 sc01 attempts critic-failed (POV breach). Stub now has `STRICT POV: ITZCOATL ONLY` prefix. Should ch09 retry happen **before** Phase 7 engine ships (under existing critic + new stub guard) or **as the first ch15+ flight** under the new engine? Recommendation: retry under existing pipeline (V7C arrives before Phase 7 ships); if retry succeeds, bank the chapter; engine doesn't need it as a canary.

**OQ-03: ch15 sc02 resume.** ch15 sc01 committed; sc02 drafted-but-killed at V7C boundary, pre-critic. Per D-21, ch15 is the **first chapter under the engine**. Should sc02 resume use the existing pipeline (immediate, V7C-ready) or wait for engine to ship (slower, fully gated)? Recommendation: resume under existing pipeline immediately on V7C land — Phase 7 takes weeks, we don't block ch15-27 production on engine shipping. Engine ships, then ch16+ gets full gating.

**OQ-04: NARRATIVE_PHYSICS.md as a permanent docs/ artifact?** Currently locked as a phase-research deliverable (D-20). Should the final synthesis live permanently in `docs/NARRATIVE_PHYSICS.md` (consulted by future plan + retrospective writers) or stay in `.planning/phases/07-.../07-NARRATIVE_PHYSICS.md` (phase-local)? Recommendation: copy to `docs/` on phase completion as the canonical narratology reference for future thesis registry.

**OQ-05: Canonical-quantity seed source.** Surfaced by gsd-phase-researcher 2026-04-25. CB-01 retriever (D-22) needs initial canonical values for the 5 manuscript canaries (Andrés age, La Niña height, Santiago del Paso scale, Cholula date, Cempoala arrival). Three options:
- **(a)** Operator hand-seeds `config/canonical_quantities_seed.yaml` with the 5 canaries before Plan 07-02 lands. Extraction agent fills the long tail post-ship.
- **(b)** Pure extraction-agent: scan ch01-04 prose + lore-bible corpus, propose canonical values, operator approves a generated seed file.
- **(c)** Hybrid (researcher recommendation): operator confirms the 5 canaries directly (low-effort, high-confidence); extraction agent generates the rest with operator-review gating before write to LanceDB.

**Claude's recommendation: (c).** The 5 canaries are the failure-evidence anchors and need operator-truth; the long tail (every named entity / quantity in ~250KB lore corpus) is too much for hand-seed but tractable for an extraction agent with review.

</open_questions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Pipeline state
- `runs/HANDOFF_2026-04-25.md` — V7C handoff state, known issues 1-4 list, ch05-14 manual-concat status, ch09 hard-block detail
- `.planning/STATE.md` — full execution history through Plan 05-03 + Phase 4 retrospective
- `.planning/ROADMAP.md` — phase entry at line 272

### Existing kernel packages (extend, don't rewrite)
- `src/book_pipeline/drafter/mode_a.py` — Mode-A drafter, sampling profiles, V-2 gate
- `src/book_pipeline/critic/scene_critic.py` — 5-axis scene critic
- `src/book_pipeline/chapter_assembler/dag.py` — chapter DAG orchestrator
- `src/book_pipeline/chapter_assembler/scene_kick.py` — scene-kick recovery
- `src/book_pipeline/regenerator/scene_local.py` — Mode-A regenerator
- `src/book_pipeline/rag/bundler.py` — context-pack bundler
- `src/book_pipeline/rag/types.py` — Chunk, RetrievalHit, ContextPack
- `src/book_pipeline/observability/event_logger.py` — OBS-01 event schema

### Locked architecture
- `docs/ADRs/001-004` — voice-pin, RAG axes, observability, kernel-extraction policy
- `.planning/REQUIREMENTS.md` — 41 v1 REQ-IDs (Phase 7 may emit new REQ-IDs scoped 07-NN)

### Scene examples (failure cases)
- `drafts/ch09/` — POV breach failures (4 attempts, all critic-failed)
- `drafts/ch15/` — partial state pre-V7C (sc01 only)

</canonical_refs>

<specifics>
## Specific Ideas

### Mandatory metadata schema fields (operator-stated)

```yaml
# Conceptual — researcher proposes Pydantic model
contents: <what happens — beat function expanded>
characters_present:
  - name: <canonical>
    on_screen: true|false
    motivation: <load-bearing per D-02>
voice: <which FT pin / sampling profile>
perspective: 1st | 3rd_close | 3rd_omniscient | ...
treatment: dramatic | mournful | comedic | light | propulsive | contemplative | ...
```

### Atomics seed list (craft canon — researcher expands)
- Aristotelian beats: incident → rising action → climax → falling action → resolution
- Story Grid 5 Commandments per scene: inciting incident, turning point, crisis, climax, resolution
- Save the Cat beat sheet primitives
- Sol Stein's "show don't tell" enforceable as non-narration density metric
- McKee's value-charge polarity per scene (positive ↔ negative on a named value axis)
- Truby's moral argument axis
- Theatrical beat: every scene = a unit of action with a goal-conflict-outcome triplet

### Theater of mind — staging schema
- Spatial: where are characters physically positioned
- Temporal: scene clock + relation to prior scene's clock
- Sensory weight: which senses dominate (Stein's 5-sense rule)
- Witness: who in the scene sees vs participates

### Failure-mode-driven gate seed list
- POV consistency gate (ch09 canary)
- Motivation centrality gate (D-02)
- Content ownership gate (sc01 bleed canary)
- Treatment fidelity gate (mournful scene drafted as comedic = drift)
- Beat-function fidelity gate
- Continuity gate against canon-bible
- Voice fidelity gate (already exists as OBS-03 — extend, don't rewrite)

</specifics>

<deferred>
## Deferred Ideas

- Web/GUI dashboard for canon-bible inspection — V2, REVIEW-01 per ROADMAP UI hint
- Auto-generated story-bible PDFs for human readers — out of scope
- Cross-book physics (multi-novel canon) — single-book only for v1
- ML-learned atomics (use only craft-literature-derived rules in v1; learned variants are a v2 thesis)
- Real-time visualization of physics state during generation — telemetry only via events.jsonl
</deferred>

---

*Phase: 07-narrative-physics-engine-codified-storytelling-atomics-enfor*
*Context locked: 2026-04-25 from operator directive*
