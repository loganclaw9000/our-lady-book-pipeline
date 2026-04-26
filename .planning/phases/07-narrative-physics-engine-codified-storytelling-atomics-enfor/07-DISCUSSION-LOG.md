# Phase 7: Narrative Physics Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 07-narrative-physics-engine-codified-storytelling-atomics-enfor
**Areas discussed:** Forward scope (re-scope), Continuity-Bible (CB-01) home + injection, Gate placement + package, Post-draft semantics + stub-leak severity + dedup method

---

## Forward Scope (re-scope)

| Option | Description | Selected |
|--------|-------------|----------|
| Build engine + retrofit ch01-14 | Engine fixes future generation AND re-DAGs historical artifacts (per seed D-08 + D-12) | |
| Forward-only — engine for ch15-27 + ch09 retry | Engine fixes future. ch01-14 = historical artifacts. Re-DAG of ch05-14 opportunistic / out-of-scope-for-acceptance | ✓ |

**User's choice:** Forward-only. Operator quote: *"We are not building to fix what's been done but to make sure the future is correct."*
**Notes:** Supersedes seed D-08 + D-12. New decision D-21. ch01-04 remain available as read-only regression-sanity baseline (engine MAY validate, no commits).

---

## Continuity-Bible (CB-01) — Home

| Option | Description | Selected |
|--------|-------------|----------|
| New 6th RAG axis | `rag/retrievers/continuity_bible.py`, new `lance_schema` rule_type, conflict_detector new dimension. Pure architectural extension | ✓ |
| Extend entity_state with canonical_quantities field | No new retriever, additive schema. Risk: kitchen-sink dilutes axis purity | |
| Deterministic non-RAG dict | `canon-bible/quantities.yaml` + `ContinuityBible` class. Faster + cheaper but no fuzzy lookup | |
| Hybrid dict + 6th axis fallback | Deterministic primary, 6th-axis fallback for new entities | |

**User's choice:** New 6th RAG axis (Recommended).
**Notes:** D-22. Keeps axis purity for critic-rubric mapping. Fits ADR-002 5-axis paradigm extension.

---

## Continuity-Bible — Injection on regen

| Option | Description | Selected |
|--------|-------------|----------|
| Inject canonical values verbatim into prompt header | Top-of-prompt anchor: `CANONICAL: Andrés age=23, La Niña height=55ft. Reproduce exact.` | ✓ |
| Inject only the violated quantities | Smaller prompt; risk of next-attempt drift to different quantity | |
| Inject all relevant + log mismatch axis to critic | Verbose; biggest signal but biggest cost | |

**User's choice:** Verbatim canonical values in prompt header (Recommended).
**Notes:** D-23. Matches D-13 ownership-anchor pattern (top-of-prompt anchors are load-bearing).

---

## Gate Placement (defense-in-depth scope)

| Option | Description | Selected |
|--------|-------------|----------|
| Stub-write time | Validate stub frontmatter at author time | |
| Drafter pre-flight | Validate metadata + CB-01 + pov_lock + ownership before vLLM call (Recommended) | ✓ |
| Critic time | Add rubric axes (pov_fidelity, motivation_fidelity, content_ownership, etc.) (Recommended) | |
| Commit time | Black-box pre-commit hook: stub-leak regex + degenerate-loop n-gram + similarity ≥80% (Recommended) | |

**User's choice:** Drafter pre-flight only (single-pick from multiSelect).
**Notes:** D-24. Implication: post-draft checks (stub-leak, loop, similarity, ownership, pov, motivation, treatment, quantity) MUST fold into critic-time rubric axes. No separate commit hook. Two enforcement points total: pre-flight (cheap, before model) + critic (after expensive draft).

---

## Gate Package Location

| Option | Description | Selected |
|--------|-------------|----------|
| New `book_pipeline.physics` kernel package | New top-level pkg: schema.py + gates/*.py + canon_bible.py. ADR-004 kernel-clean. Each gate testable + mockable | ✓ |
| Extend existing packages in place | Gates as methods on drafter/critic/chapter_assembler. Less boilerplate, violates ADR-004 | |
| Mixed: schema+canon_bible in new pkg, gate logic in callers | Compromise. Risk: gate semantics fragment | |

**User's choice:** New `book_pipeline.physics` kernel package (Recommended).
**Notes:** D-25. 7th kernel pkg (joins drafter/critic/regenerator/chapter_assembler/rag/observability/alerts). Import-linter contract extension follows Plan 05-03 alerts precedent.

---

## Post-draft Check Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Fold into critic as new rubric axes | Critic gets stub_leak / repetition_loop / content_ownership_breach / scene_buffer_similarity axes. Single source of truth. Existing scene-kick handles routing | ✓ |
| Run as black-box pre-critic linter (autonomous) | Fast linter before critic; saves Anthropic tokens on obvious violations. Two enforcement systems | |
| Run BOTH — linter pre-critic + axes in critic | Defense-in-depth. Two systems harder to reason about | |

**User's choice:** Fold into critic as new rubric axes (Recommended).
**Notes:** D-26. Critic 5→13 axes. Existing CRITIC-01 5-axis (historical, metaphysics, entity_state, arc, don'ts) extends with 8 physics axes. Existing scene-kick recovery loop (Plan 05-02) routes on FAIL.

---

## Stub-leak Severity (D-17)

| Option | Description | Selected |
|--------|-------------|----------|
| Hard reject + scene-kick | Stub vocabulary in canon = unambiguous bug. Refuse + route to scene-kick + sharper directive. Black-and-white pattern | ✓ |
| Auto-strip + log warning | Detect leading `Establish:` / `Resolve:` patterns + strip + commit clean | |
| Hard reject if leading; soft warn if mid-prose | Hybrid sensitivity | |

**User's choice:** Hard reject + scene-kick (Recommended).
**Notes:** D-27. Root cause is drafter prompt issue, not output cleanup.

---

## Similarity-Dedup Method (D-14, D-28)

| Option | Description | Selected |
|--------|-------------|----------|
| BGE-M3 cosine ≥ 0.80 | Reuse existing embedder. Catches paraphrased recaps. Tunable in config/mode_thresholds.yaml | ✓ |
| Rolling-shingle Jaccard ≥ 0.80 | k=5 word shingles. Catches verbatim only; misses paraphrase. Cheap | |
| Both — fail if either exceeds threshold | Belt + suspenders. Best signal. Dual computation | |

**User's choice:** BGE-M3 cosine ≥ 0.80 (Recommended).
**Notes:** D-28. Reuses `book_pipeline.rag.embedding.BgeM3Embedder` (Phase 2). One extra embedder call per scene critic-time.

---

## Wrap-up

| Option | Description | Selected |
|--------|-------------|----------|
| Lock 3 more (POV-lock storage + treatment vocab + motivation-axis weight) | Tighter plan, fewer planner decisions | |
| Ready for context — leave rest to research/planner | Lock what we have. POV-lock + treatment + motivation = Claude's Discretion | |
| Final coherence check + write context | (User free-text) | ✓ |

**User's choice:** "Just do a final check and make sure we are addressed."
**Notes:** Triggered coherence audit (D-21 supersedes D-08+D-12; D-24 pre-flight + D-26 critic = no overlap; D-25 physics pkg + D-22 6th axis = clean separation; OQ-01 ch09 POV mode flagged; OQ-02/03 V7C-window ordering flagged; OQ-04 NARRATIVE_PHYSICS docs/ residency flagged).

---

## Claude's Discretion

Captured in CONTEXT.md `<decisions>` Claude's Discretion subsection. Areas where planner picks:
- Schema container shape (YAML frontmatter vs JSON sidecar)
- POV-lock storage location (config vs entity-state vs new artifact)
- Treatment vocabulary (closed enum vs open string vs hybrid)
- Beat-function overlap semantics (strict partition vs declared shares)
- Motivation-axis critic weight (equal vs hard-stop)
- Stub-leak regex pattern set
- Degenerate-loop detection method (n-gram vs sentence-embedding self-sim)
- Quote-extraction robustness placement (D-18 fold vs side-fix)
- NARRATIVE_PHYSICS.md depth (treatise vs brief vs two-tier)
- Plan rollout order (schema-first vs gate-first vs CB-01-first)
- Engine validation against ch01-04 frozen baseline (gate test vs defer)

## Deferred Ideas

Captured in CONTEXT.md `<deferred>`:
- Web/GUI dashboard for canon-bible inspection
- Auto-generated story-bible PDFs
- Cross-book physics (multi-novel canon)
- ML-learned atomics
- Real-time visualization of physics state
- Re-DAG of ch05-14 (deferred per D-21)

## Open Questions Surfaced

Captured in CONTEXT.md `<open_questions>`:
- OQ-01: Ch09 retry POV mode (1st per D-16 vs 3rd to match historical block)
- OQ-02: Ch09 retry timing (pre-engine vs post-engine)
- OQ-03: Ch15 sc02 resume (existing pipeline vs wait for engine)
- OQ-04: NARRATIVE_PHYSICS.md residency (phase-local vs docs/)
