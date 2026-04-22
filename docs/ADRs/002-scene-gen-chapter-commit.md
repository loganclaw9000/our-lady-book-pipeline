# ADR-002: Scene-level generation, chapter-level commit

**Status:** accepted
**Date:** 2026-04-21

## Context

Need to pick generation unit (what LLM produces per call) and commit unit (what enters canon + triggers re-indexing). The outline in `our-lady-of-champion-outline.md` is already decomposed to 27 chapters × ~3000 words each, with per-chapter POV + date + location + historical event + beat function.

## Decision

- **Generation unit = scene (~800-1500 words).** Each chapter contains 2-4 scenes.
- **Commit unit = chapter.** Scenes accumulate in a pre-commit buffer; chapter commits atomically once all scenes pass.

## Rationale

**Why scene for generation:**

- Voice-FT local model produces its best prose at this length.
- RAG retrieval is tightest: one targeted query per scene ("what's Andrés's state by April 1519, what does La Niña de Córdoba carry, which metaphysics rules apply to this beat").
- Short enough to regenerate cheaply on failure.
- Beat function in outline already implicitly defines scene boundaries.

**Why chapter for commit:**

- Matches existing outline grain — canon reads in 3k-word units, not 1k scenes.
- Chapter-level critic pass catches cross-scene arc issues (coherence, voice drift, pacing) that scene-level misses.
- One atomic commit to canon per chapter is a clean re-indexing trigger for RAG + entity extraction.
- 27 commits over a draft cycle is a tractable unit for the weekly digest and human spot-checks.

**Why not generate at chapter level:**

- Local FT voice model will not 1-shot 3000 words cleanly (see ADR-001).
- Large-unit generation blurs entity state (e.g., forgets Andrés's emotional state from earlier in the chapter), drifts voice between POVs in triptych scenes.

**Why not commit at scene level:**

- Would force re-indexing after every scene → expensive and noisy.
- Partial chapters in canon confuse downstream readers (human and RAG retrievers both).
- No natural "arc unit" smaller than chapter in outline structure.

## Consequences

- Chapter assembler needs a transition-smoothing pass (lightweight — glue between scene outputs, not rewriting).
- Chapter-level critic is separate from scene-level critic and runs different checks (arc coherence, voice consistency across scenes, pacing within chapter).
- Failed chapter-level critic can either kick one scene back to regen (surgical) or roll back all scenes and redraft (drastic) — controller decides based on issue severity.

## Related

- ADR-001 (mode dial)
- `docs/ARCHITECTURE.md` diagrams 2 and 3
