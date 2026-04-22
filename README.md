# our-lady-book-pipeline

First-draft automation for the novel *Our Lady of Champion*. Pipeline #1 of a planned family (blog, thinkpiece, short-story, ...). Serves double duty as the testbed whose learnings shape later pipelines and feed back into `paul-thinkpiece-pipeline` voice-FT decisions.

## What this repo does

Drafts scenes and assembles chapters with:

- **Voice fidelity** via a fine-tuned local model (pinned checkpoint from `paul-thinkpiece-pipeline`).
- **Factual consistency** enforced pre-commit via a 5-axis critic + typed RAG (historical, metaphysics, entity-continuity, arc-position, thematic don'ts).
- **Minimal human involvement** — nightly autonomous runs via openclaw, weekly digest, hard-block alerts only.
- **Experiment telemetry** — every LLM call logged, retrospectives written per chapter, open theses tracked in `theses/`.

## Key dependencies

- **Corpus (read-only source-of-truth):** `~/Source/our-lady-of-champion/` — 10 markdown lore bibles (brief, engineering, pantheon, relics, outline, etc.)
- **Voice model:** pinned checkpoint produced by `~/paul-thinkpiece-pipeline/`. Upgrades are deliberate, configured in `config/voice_pin.yaml`.
- **Orchestration:** `openclaw` (already installed, systemd-managed gateway).
- **Critic / reasoning models:** Anthropic API (Opus primary, Sonnet fallback).

## Repo layout

```
.
├── README.md
├── docs/
│   ├── ARCHITECTURE.md        5 diagrams + components table
│   └── ADRs/                  accepted architectural decisions
├── config/                    per-environment pipeline config
│   ├── rubric.yaml            5-axis critic rubric
│   ├── rag_retrievers.yaml    typed retriever config
│   ├── mode_thresholds.yaml   Mode-A/B dial thresholds
│   └── voice_pin.yaml         voice-FT checkpoint pinning
├── canon/                     committed chapters (book content)
├── drafts/                    pre-commit buffer, scene-level
├── indexes/                   5 RAG vector stores
├── entity-state/              auto-generated entity cards per chapter
├── runs/                      openclaw run artifacts, events.jsonl
├── theses/                    experiment registry (open + closed)
├── retrospectives/            post-chapter notes by retrospective writer
└── digests/                   weekly human-facing summaries
```

## Status

**2026-04-21:** Architecture locked, scaffolding committed, no code yet. Next: `/gsd-new-project` to produce `PROJECT.md`, roadmap, phase-1 plan (likely: repo-layout scaffolding, corpus ingestion + indexing, first RAG retriever end-to-end).

## See also

- `docs/ARCHITECTURE.md` — current design
- `docs/ADRs/` — decisions and rationale
- `theses/open/` — active experimental questions
- `~/paul-thinkpiece-pipeline/` — sibling project producing the voice checkpoints consumed here
- `~/Source/our-lady-of-champion/` — source-of-truth corpus
