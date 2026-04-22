# ADR-001: Mode dial (voice / frontier) over capability-promotion ladder

**Status:** accepted
**Date:** 2026-04-21
**Supersedes:** — (initial architectural choice)

## Context

Early exploration proposed a **promotion ladder** for the drafter: scene → chapter → block → section → book, each level unlocked after K consecutive critic-passing runs at the prior level. The idea was that the pipeline would discover its own ceiling by measurement.

## The objection

No non-frontier model 1-shots clean prose beyond ~1000 words. A fine-tuned local voice model cannot escape this ceiling by accumulating successes at scene level — the ceiling is a property of the model class, not the pipeline's track record. "Promotion" past scene-level would therefore force one of two losses:

1. Keep the voice model, produce degraded output at chapter+ length (bad).
2. Switch to frontier at chapter+ length, lose voice fidelity (also bad, just differently).

The ladder dressed up a **voice/scale tradeoff** as capability growth. That's a lie the pipeline would tell about itself.

## Decision

Replace the ladder with a **mode dial**:

- **Mode A (default): voice.** FT local drafter, scene-level generation, chapters assembled from 2-4 scenes.
- **Mode B (escape hatch): frontier.** Claude Opus with voice samples in-context, opt-in per scene or chapter, used when Mode A regen budget is exceeded or the beat is pre-flagged as structurally complex.

Every committed unit carries a `mode` tag in the run log. Mode-B rate is first-class metric in the weekly digest.

## Consequences

**Positive:**

- Architecture tells the truth about the voice/scale tradeoff instead of hiding it.
- Mode-B rate becomes a signal for Paul: rising rate means voice model is losing ground or being asked to do things it can't; falling rate means pipeline is learning which beats the voice model can actually handle.
- No fake promotion state machine to maintain.

**Negative:**

- Loses the research motivation of "can this pipeline's voice model one-shot a chapter eventually?" — this can be preserved as a **separate background benchmark** (not a gate), see note below.
- Requires discipline to keep Mode B opt-in rather than default — easy to slide toward "Mode B for everything" once a few scenes get flagged.

## Background benchmark (preserved separately)

As a non-blocking side experiment, every N chapters the pipeline can have Opus one-shot the next 3 chapters from outline. Critic scores both. This answers "is frontier-1shot approaching acceptable quality for longer units?" and informs whether voice-FT investment keeps scaling or pivots. Zero impact on canon.

## Alternatives considered

- **Pure frontier pipeline** (no local FT). Ships fastest, highest token cost, loses voice.
- **Pure local FT pipeline** (no frontier). Preserves voice, fails on structurally complex beats with no escape.
- **Ladder (original proposal).** Confuses capability with track record, forces voice loss at promotion.

## Related

- ADR-002 (scene-gen + chapter-commit unit model)
- `docs/ARCHITECTURE.md` diagram 4
