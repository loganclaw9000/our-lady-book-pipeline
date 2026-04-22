---
id: 002
title: "Mode-B escape rate stabilizes below 30% across Act 1"
status: open
opened: 2026-04-21
closed: null
tags: [mode-dial, frontier, drafter, cost]
metric: "Mode-B escape rate across first 9 chapters ≤ 30% (scenes drafted via frontier as a fraction of total scenes)"
owner: autonomous
---

## Hypothesis

With aggressive pre-flagging of structurally complex beats (apex-engine scenes, multi-POV convergence, climactic dense-metaphysics scenes) as Mode B from the start, the remaining Act 1 scenes are within voice-FT model's reach. Mode-B escape rate for non-pre-flagged scenes ≤ 15%; overall escape rate ≤ 30%.

## Background

If Mode-B rate runs too high, the pipeline isn't really using the voice model — it's using frontier with extra steps. That's a signal either to pivot (accept frontier as primary and keep voice as stylization pass) or to invest in a book-specific voice FT branch.

## Test design

Natural experiment. Track Mode B vs Mode A tag in run events over first 9 committed chapters. Pre-flagged Mode-B scenes are known in advance (listed in `docs/ARCHITECTURE.md` diagram 4) and should not count against escape-rate ceiling — the test is about unplanned escapes.

## Success metric

- Overall escape rate ≤ 30% across Act 1: **supported.**
- 30-45%: **inconclusive** — revisit after Act 2.
- 45%: **refuted** — voice FT is not carrying the load for this book.

## Transferable artifact (anticipated)

- Supported: mode dial architecture validated; pipeline #2 can inherit the pattern.
- Refuted: recommend investment in book-voice FT branch before Act 2, OR pivot to frontier-primary. Either way, pipeline #2 should start with frontier-primary assumption until its own voice model is proven.
