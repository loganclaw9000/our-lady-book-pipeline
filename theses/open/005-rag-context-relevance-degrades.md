---
id: 005
title: "RAG context relevance degrades past ~30-40KB of retrieved context"
status: open
opened: 2026-04-21
closed: null
tags: [rag, context, retrieval]
metric: "Critic score on drafts generated with truncated RAG (top-K retrieval capped at 30KB) ≥ score on drafts with full corpus context (all 10 bibles = ~250KB)"
owner: autonomous
---

## Hypothesis

Feeding all 10 lore bibles (~250KB) as context per scene drafting call produces worse or equal drafts compared to targeted retrieval capped at ~30-40KB. Models lose signal in very long contexts even when information is present.

## Background

The corpus is ~250KB total. Easy temptation: "just give the model everything." But modern models (Claude Opus, certainly voice-FT local) degrade on long context needle-in-haystack tasks. Typed RAG (5 retrievers) is the alternative — each retriever returns a small focused chunk, bundler assembles ~20-40KB.

## Test design

**Paired ablation run:**

1. Select 10 scenes from Act 1 outline (varied POV, beat type, complexity).
2. Draft each scene twice:
   - Condition A: full corpus in context (~250KB).
   - Condition B: typed RAG top-K retrieval, capped at ~35KB.
3. Critic scores both drafts per scene.
4. Compare mean critic score, axis-by-axis.

## Success metric

- Condition B ≥ Condition A on ≥ 7/10 scenes AND mean score difference ≥ 0.3 points: **supported** (targeted retrieval wins).
- Condition B ≥ Condition A on 4-7/10 scenes: **inconclusive.**
- Condition B < Condition A on ≥ 7/10 scenes: **refuted** (just feed everything, or revisit retriever design).

## Transferable artifact (anticipated)

- Supported: typed RAG pattern transfers to pipeline #2. Blog corpus will be smaller but same principle applies (relevance > volume).
- Refuted: simplify architecture — drop typed retrievers, feed corpus directly. Saves significant engineering.
