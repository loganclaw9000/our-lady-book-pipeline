---
id: 003
title: "Entity-state auto-extraction catches continuity errors before commit"
status: open
opened: 2026-04-21
closed: null
tags: [rag, entity-state, critic, consistency]
metric: "Across first 9 chapters, seeded continuity errors (injected via adversarial probe) are caught by critic ≥ 85% of the time, without triggering false-positive rate > 10% on clean scenes"
owner: autonomous
---

## Hypothesis

The entity-state index, auto-generated from committed chapters by a post-commit extractor agent, gives the critic enough structured continuity information that most continuity errors are caught pre-commit.

## Background

Continuity errors are famously hard to catch in long-form fiction. Human editors often miss them. RAG retrieval over unstructured prose tends to miss state-change signals (e.g., character's emotional shift mid-chapter). Structured entity cards ("Andrés: location=Cempoala, possessions=[copper disc], relationships={...}, emotional state=...") give the critic something to pattern-match against.

## Test design

**Adversarial probe:**

After Chapter 3 is committed (enough state to have real continuity to violate), before any further commits:

1. Take a clean drafted Chapter 4 scene. Run through critic. Record verdict.
2. Produce 10 perturbed variants of the same scene, each injecting a different continuity error (wrong location, wrong possession, impossible time, contradicted belief, etc.). Some errors explicit, some implicit.
3. Run each variant through critic. Record verdict per variant.
4. Also run 10 clean "neighbor" scenes through critic. Record false-positive rate.

## Success metric

- Catch rate ≥ 85% on injected errors AND false-positive rate ≤ 10% on clean scenes: **supported.**
- Catch rate 60-85%: **inconclusive.** Identify which error class leaks.
- Catch rate < 60% OR false-positive rate > 20%: **refuted.** Revisit entity extractor schema or critic rubric axis for entity-continuity.

## Transferable artifact (anticipated)

- Supported: entity-state auto-extraction is a reusable pattern; pipeline #2 (blog) can use a simplified variant for multi-post continuity (e.g., a blog series).
- Refuted: may need heavier infrastructure (symbolic entity graph vs markdown cards, or more aggressive multi-hop retrieval).
