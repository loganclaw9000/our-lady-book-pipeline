---
id: 004
title: "5-axis critic rubric outperforms monolith critic for driving regenerations"
status: open
opened: 2026-04-21
closed: null
tags: [critic, rubric, regenerator]
metric: "Regeneration targeting derived from axis-specific issue lists produces ≥ 20% higher critic-score improvement per regen cycle vs regeneration driven by a monolith critic's holistic feedback"
owner: autonomous
---

## Hypothesis

Decomposing critic output into 5 axes (historical / metaphysics / entity / arc / don'ts), each with its own issue list and severity, produces more useful regeneration targets than a monolith critic returning holistic feedback. Specifically: issue-conditioned regenerations improve critic score by more per iteration.

## Background

Monolith critic feedback tends to be either vague ("this scene feels off") or fragmented. Axis-decomposed feedback is actionable: "entity axis FAIL: Andrés is in Cempoala (per Ch 3 commit); draft has him in Havana" gives the regenerator a specific, localizable target.

## Test design

**Paired ablation run:**

1. Identify 20 scenes that failed initial critic pass in Mode A (natural accumulation — don't force failures).
2. Regenerate each scene twice: once driven by 5-axis issue list (condition A), once driven by a monolith critic summary (condition B).
3. Re-score both regenerations. Measure delta from pre-regen score.
4. Compare mean improvement between conditions.

## Success metric

- Condition A (5-axis) mean improvement ≥ 1.2× Condition B (monolith): **supported.**
- 1.0-1.2×: **inconclusive.** Possible effect but not decisive.
- < 1.0×: **refuted.** Monolith critic is equivalent or better for regen targeting.

## Transferable artifact (anticipated)

- Supported: 5-axis rubric is reusable. Pipeline #2 adapts axes to its domain (e.g., blog: [factual / voice / structure / hook / thesis]).
- Refuted: simpler critic is fine; invest effort elsewhere (RAG, drafter, not critic).
