---
chapter_num: 1
candidate_theses:
- id: sc01_attempt_count_signals_metaphysics_load
  description: Scenes carrying heavy metaphysics setup (Reliquary cockpit, named-saint
    engine) need 3+ drafter attempts vs. 1 for pure-human scenes — does attempt count
    correlate with metaphysics-axis density per scene, and should we pre-budget regeneration
    cycles by axis load?
- id: sc02_clean_pass_minimal_lore
  description: ch01_sc02 (Malintzin/Citlal) passed critic in one regenerator cycle
    while sc01 and sc03 needed multiple — is voice-fidelity easier when the scene
    contains zero metaphysics/engine content, and should we sequence early-chapter
    scenes to alternate lore-heavy and lore-light to give the drafter recovery beats?
- id: sc03_dual_omen_collision
  description: ch01_sc03 stacks Venus-omen (historical/metaphysics) plus dormant-Quetzalcoatl-engine
    plus narrator's withheld dream — three signal events in one scene drove the regenerator
    output to 9177 tokens. Is there a per-scene "foreshadow budget" beyond which drafter
    coherence collapses?
- id: donts_axis_unverified
  description: Event log shows no donts-axis violations flagged this chapter, but
    corpus contains modern-anachronism and on-the-nose-prophecy traps the critic should
    be probing — is the donts retriever firing at all, or silently empty?
---

# Chapter 01 Retrospective

## What Worked
ch01_sc02 (Malintzin's morning at the compound) landed on the **voice** and **arc** axes with minimal rework: one drafter pass (`latency_ms=222459, output_tokens=1130`), one regenerator cycle (`output_tokens=1795`), critic clean on second pass. The Citlal exchange carries the slave-compound power dynamic ("A girl who asks *but* is a girl who has already decided to know") without leaning on engine-lore or historical scaffolding. The line "Carrying is heavy in this place." doubles as character voice and thematic seed. Entity introduction (Citlal, Rabbit, Malintzin's trilingual fact) deposited cleanly for later chapters.

ch01_sc03's closing image — "For one breath... I felt that the stones could be taken down" — landed the **arc** axis cleanly: narrator complicity-foreshadow without naming the conquest.

## What Drifted
ch01_sc01 (Andrés / La Niña de Córdoba) drifted hardest on the **metaphysics** axis. The drafter required three full regenerator cycles before the first chapter_critic pass and a fourth attempt after chapter-level rework (`drafter latency_ms=903002 input_tokens=6524 output_tokens=1215`, `regenerator output_tokens=8001`). The hum-as-saint-presence rule ("You don't cross yourself in the presence of a saint.") is the chapter's anchoring metaphysics claim — drafter kept under-rendering or over-rendering it across attempts (regenerator outputs swung 5418 → 8687 → 14981 tokens before convergence). Voice/historical axes co-drifted: Reliquary-class nomenclature ("knightship", "Second-class") needed reinforcement against the Cortés-fleet historical frame.

ch01_sc03 drifted on the **historical** axis specifically around the Venus-omen reading — first regenerator burst was 9177 tokens (vs. sc02's 1795), and the second drafter run still required `critic latency_ms=156308` to clear. The Quetzalcoatl-engine-dormant-at-Cholula claim collides with Tlahuizcalpantecuhtli astronomy in a way the drafter struggled to keep proportional.

## Emerging Patterns
**Attempt count tracks metaphysics density.** sc01 (engine + saint-relic + cockpit-trance): 3+ regen cycles. sc03 (dormant engines + Venus omen + dream-prophecy): 2 regen cycles, second critic taking 156s. sc02 (zero engine/metaphysics content): 1 regen cycle. The drafter is fluent on human interiority and visibly degrades when forced to integrate named-saint engine rules with historical scene-blocking simultaneously.

**Context-pack bundler latency pathology, separate from quality.** The `context_pack_bundler` ran hundreds of times for sc01 alone with latencies between 14689 ms and 160434 ms before any drafter call fired. Output_tokens cluster at 31122 / 31603 (two distinct context-pack shapes). The retry storm pre-drafter is its own cost line — worth confirming whether bundler is being re-invoked due to upstream retriever timeouts (multiple retriever calls show 30s+ latency).

**Entity-extractor cost dwarfs critic cost.** `entity_extractor latency_ms=358643 output_tokens=12552` on first chapter pass; second invocation `latency_ms=339376 output_tokens=3` (likely cache hit / no-op). Per-chapter, extractor is the most expensive single call.

## Open Questions for Next Chapter
- Scenes carrying heavy metaphysics setup (Reliquary cockpit, named-saint engine) need 3+ drafter attempts vs. 1 for pure-human scenes — does attempt count correlate with metaphysics-axis density per scene, and should we pre-budget regeneration cycles by axis load?
- ch01_sc02 (Malintzin/Citlal) passed critic in one regenerator cycle while sc01 and sc03 needed multiple — is voice-fidelity easier when the scene contains zero metaphysics/engine content, and should we sequence early-chapter scenes to alternate lore-heavy and lore-light to give the drafter recovery beats?
- ch01_sc03 stacks Venus-omen (historical/metaphysics) plus dormant-Quetzalcoatl-engine plus narrator's withheld dream — three signal events in one scene drove the regenerator output to 9177 tokens. Is there a per-scene "foreshadow budget" beyond which drafter coherence collapses?
- Event log shows no donts-axis violations flagged this chapter, but corpus contains modern-anachronism and on-the-nose-prophecy traps the critic should be probing — is the donts retriever firing at all, or silently empty?

<!-- chapter-nav-injected -->

---

[Index](../index.md) · [Chapter 1 canon](../chapters/chapter_01.md) · [💬 Feedback on Chapter 1 retrospective](https://github.com/loganclaw9000/our-lady-book-pipeline/issues/new?template=reader_feedback.yml&chapter=Chapter+1+retrospective)
