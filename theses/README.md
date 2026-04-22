# Thesis Registry

This directory holds **open** and **closed** experimental theses about the pipeline.

A thesis is a falsifiable claim about pipeline behavior, paired with a test design and a success metric. Theses are the unit of transferable learning — they inform future writing pipelines and feed back into `paul-thinkpiece-pipeline` FT decisions.

## Layout

```
theses/
├── README.md             (this file)
├── open/                 (active, not yet resolved)
│   └── NNN-slug.md
└── closed/               (resolved: ✓ supported / ✗ refuted / ? inconclusive)
    └── NNN-slug.md
```

## Thesis frontmatter format

Every thesis file has:

```yaml
---
id: 001
title: "Short hypothesis statement"
status: open | supported | refuted | inconclusive
opened: 2026-04-21
closed: null | 2026-05-15
tags: [voice, critic, rag, ...]
metric: "What quantitative signal closes this"
owner: "paul | autonomous | name"
---
```

Body sections (use all that apply):

- **Hypothesis.** One-sentence falsifiable claim.
- **Background.** Why we think this is worth testing.
- **Test design.** How we'd gather evidence (ablation run, natural-experiment from production telemetry, targeted critic probe, etc).
- **Success metric.** Quantitative threshold for ✓ / ✗ / ?.
- **Evidence** (appended as accrued): dated observations, links to `runs/ablations/` or retrospectives.
- **Resolution** (final): verdict + synthesis + transferable artifact (config recommendation, architectural lesson, known failure mode, corpus-curation implication).

## Lifecycle

1. **Candidate** — retrospective writer spots a pattern, suggests a thesis. Goes to `open/` with `status: open`.
2. **Active** — evidence accrues naturally from production or via intentional ablation runs.
3. **Resolution** — thesis matcher (Python + Opus) closes the thesis when metric threshold is hit, writing a resolution block. Moved to `closed/`.
4. **Feedback** — resolution's transferable artifact is written into digest and, where applicable, opened as a config change or a new FT corpus request in `paul-thinkpiece-pipeline`.

## Hygiene rules

- Open theses >30 days without evidence are flagged for pruning or rewriting in the weekly digest.
- A closed thesis can be re-opened if new evidence contradicts the resolution. History is preserved; the file is not deleted.
- Theses must be about the pipeline, not about the book content. Questions like "is Andrés's arc working dramatically" belong in retrospectives, not here.
