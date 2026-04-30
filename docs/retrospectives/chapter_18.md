---
chapter_num: 18
candidate_theses:
- id: ch18_q01
  description: Interior-monologue scenes that catalog losses without an anchoring
    image incur runaway regen — sc02's eight regens vs sc03's one, on comparable POV-density,
    suggests the ch26 image-amortization thesis extends to historical-roll-call interiority,
    not just sensory motif chains.
- id: ch18_q02
  description: When chapter_critic forces a second pass, does per-scene re-regen (the
    current behavior — three more critic+regen cycles) actually fix chapter-level
    coherence drift, or is it papering over a missing chapter-integration step? sc01
    and sc02 each took one extra regen post-chapter_critic; sc03 also took one despite
    already being clean, suggesting the second pass may be over-firing.
- id: ch18_q03
  description: sc01's retriever/bundler thrash (15+ bundler invocations before the
    drafter ran) on a scene that ultimately drafted in one pass — is the context-pack
    assembly cost decoupled from drafting difficulty, and if so, what triggered the
    retriever loop without producing a corresponding drafter retry?
---

# Chapter 18 Retrospective

## What Worked
ch18_sc03 (Itzcoatl alone with Mirror, defection-naming, the engine cough) drafted in a single pass: one drafter call (277s, 2048 output tokens), one regenerator, one critic accepting. This is the most psychologically dense scene of the chapter — the protagonist's *interior* defection turn — and it landed clean on first attempt across the **arc** axis. The scene rides one dominant image: Mirror's hum dropping "half a tone lower than at dawn" and later coughing "like a person coughing in sleep." That single recurring sensory motif anchors the entire interiority — the philosopher-mother's exercise, the cousin Ixtlilxochitl recruitment flashback, the sister Xochitl's three stained objects, the dream of his mother's table — all hang off the engine-cough image. Voice held: short declaratives, deliberate naming ("the calmecac verb"), no over-explanation of what defection means.

## What Drifted
ch18_sc02 (Mirror walks the flank, examining the lost war) thrashed catastrophically: **4 drafter calls, 8 regenerator calls, 9 critic calls** before chapter_critic. The drift was on the **historical** axis — sc02 attempts to compress the entire Conquest-loss roll-call into Itzcoatl's consciousness in a single examination beat: Otumba ground, Tlacopan causeway seven nights past, Toxcatl massacre at Templo Mayor, Cholula's dormant Quetzalcoatl, Centla Maya turning, Moctezuma's rooftop death, Tlaxcala's defection. Every one of those is a canon-introducing reference inside one paragraph. The drafter kept producing it, the critic kept rejecting historical-axis violations, the regenerator kept patching, and the loop ran four full drafter-restart cycles before settling. Compare to sc01 (action scene, comparable historical density but distributed across observable engine-actions) which drafted once and only needed one regen.

ch18_sc01 also showed a different drift signature pre-drafting: the retriever/context_pack_bundler chain ran ~15 full bundler cycles (each 35-120s) before the drafter ever fired. Drafter then succeeded in one shot. Something in the retriever loop was unstable but the drafted scene was sound.

## Emerging Patterns
The ch26 thesis ("unit of amortization is the image, not the sentence") sharpens here into a stronger claim: **interior-monologue scenes amortize on a single anchoring image; without one, historical-canon density compounds linearly into regen cost**. sc03 has Mirror's cough — one image, one motif, anchors a dozen inner references. sc02 has no anchoring image — the "kill-geometry" abstraction is conceptual, not sensory, and the corner-mirror "line of his own back" arrives too late and isn't reused. Result: sc02 thrashes on the same historical axis sc03 navigates clean, despite sc03 carrying *more* psychological weight.

Second pattern: chapter_critic forced a uniform second pass on all three scenes after they'd individually passed. sc01 and sc02 each took one additional critic+regen cycle (+~180s each). sc03, already clean, also got re-regenned. This suggests chapter_critic's "scene_kick" mechanism doesn't discriminate which scenes actually need the chapter-coherence fix — it kicks all of them. Worth measuring whether the re-regen on already-clean sc03 changed anything substantive or was wasted compute.

## Open Questions for Next Chapter
- Interior-monologue scenes that catalog losses without an anchoring image incur runaway regen — sc02's eight regens vs sc03's one, on comparable POV-density, suggests the ch26 image-amortization thesis extends to historical-roll-call interiority, not just sensory motif chains.
- When chapter_critic forces a second pass, does per-scene re-regen (the current behavior — three more critic+regen cycles) actually fix chapter-level coherence drift, or is it papering over a missing chapter-integration step? sc01 and sc02 each took one extra regen post-chapter_critic; sc03 also took one despite already being clean, suggesting the second pass may be over-firing.
- sc01's retriever/bundler thrash (15+ bundler invocations before the drafter ran) on a scene that ultimately drafted in one pass — is the context-pack assembly cost decoupled from drafting difficulty, and if so, what triggered the retriever loop without producing a corresponding drafter retry?
