---
id: 001
title: "Thinkpiece-voice FT model transfers acceptably to historical-fiction prose"
status: open
opened: 2026-04-21
closed: null
tags: [voice, drafter, ft-transfer]
metric: "Across first 9 committed chapters, voice-fidelity-score (embedding cosine against voice reference set) ≥ 0.72 on ≥ 70% of Mode-A scenes, AND critic 'voice' axis PASS rate ≥ 80% on Mode-A scenes"
owner: paul
---

## Hypothesis

The voice checkpoint produced by `paul-thinkpiece-pipeline` (trained on Paul's essay/blog corpus) produces historical-fiction prose that reads recognizably as Paul's voice, for at least Mode-A scenes that don't demand heavy dialogue staging or apex-scale action.

## Background

Paul's thinkpiece voice is analytical, numbers-dense, specific, long-form — characteristics that arguably transfer well to dense historical-fiction prose with theological and metaphysical register. However, the training corpus contains no dialogue, limited sensory scene staging, and no sustained narrative arcs. Transfer may succeed on diction and register while failing on fiction-specific mechanics.

## Test design

**Natural experiment from production** (no dedicated ablation needed for v1):

1. First 9 chapters drafted as normal (Act 1). Most scenes go through Mode A.
2. Record critic axis scores per scene, with particular attention to the (to-be-added) "voice" axis.
3. Compute voice-fidelity-score via embedding cosine between drafted scene and a curated reference set of Paul's prose (20-30 anchor passages from training corpus).
4. Count Mode-B escapes — escape rate signals voice model's reach.

## Success metric

- **Supported:** voice fidelity ≥ 0.72 on ≥ 70% of Mode-A scenes AND critic "voice" axis PASS rate ≥ 80% on Mode-A scenes.
- **Refuted:** either threshold missed by ≥ 15 percentage points.
- **Inconclusive:** borderline, or Act 1 didn't produce enough Mode-A scenes to judge (e.g., Mode-B escape rate > 40%).

## Transferable artifact (anticipated)

- **Supported:** thinkpiece-voice FT can seed book pipeline without a book-specific FT branch. Blog pipeline can assume same checkpoint is viable.
- **Refuted:** need a book-voice FT branch. Either mix fiction exemplars into training corpus, or train a separate adapter. Paul's thinkpiece voice alone insufficient for fiction.
- **Inconclusive:** either run a more targeted ablation (2-3 scenes drafted with thinkpiece-voice vs with exemplar-only baseline) or accept uncertainty and track for more chapters.
