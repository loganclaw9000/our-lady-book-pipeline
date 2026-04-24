---
chapter_num: 1
candidate_theses:
- id: th_ch01_001
  description: Historical-detail-dense Spanish-world scenes (ch01_sc01) require more
    drafter iterations than indigenous-POV scenes; historical-axis grounding (fleet
    size, viaticum mechanics, Marian iconography) is the primary regen driver for
    conquistador POVs.
- id: th_ch01_002
  description: Metaphysics-axis scenes with dense Nahuatl cosmology (ch01_sc03) pass
    regeneration on the first cycle but generate the largest critic payloads, suggesting
    critic needs a denser rule-card retrieval bundle up-front rather than a second
    pass.
- id: th_ch01_003
  description: Two-language compound-dialogue scenes (ch01_sc02, Mayan/Nahuatl code-switch
    via Citlal) land cleanest under the current rubric — entity-axis fidelity is easier
    to enforce when the named-entity set is small and locally scoped.
- id: th_ch01_004
  description: Chapter-level entity_extractor required a second pass (output tokens
    11700 → 12552) and chapter_critic ran four times; cross-scene cohesion (Andrés
    / Malintzin / Itzcoatl as foreshadowed thread) is not yet converging in one pass.
- id: th_ch01_005
  description: Retriever warmup storms (hundreds of duplicated context_pack_bundler
    calls at 30–160s latency before the first real drafter call) suggest a cold-index
    or cache-miss pathology worth measuring as a separate thesis before ch02 drafts.
---

# Chapter 01 Retrospective

## What Worked
Scene ch01_sc02 (Malintzin at the waterhole / kitchen with Citlal) was the cleanest pass in the chapter: one regenerator cycle, critic output_tokens=1670 on the second pass (smallest of the three scenes), and a compact named-entity footprint (Malintzin, Citlal, "the boy they call Rabbit"). The entity axis held without a second chapter-critic pass flagging it — the scene's two-woman, two-language interior ("You are a beautiful girl," the woman said in Mayan) gave the drafter a narrow surface to defend. The arc axis landed: Citlal's ask ("If anything happens to me… the boy will need a friend in this compound") planted a concrete future obligation inside a scene that otherwise is mostly atmosphere, and the critic accepted it on the first regen.

Scene ch01_sc03's metaphysics axis also worked on first regen despite the heaviest critic report in the chapter (output_tokens=5632). The rule-card retrievals evidently landed: Tezcatlipoca-as-smoking-mirror, Tlahuizcalpantecuhtli as Venus-morning-star, and the Feathered Serpent distinction from Huitzilopochtli's sun all appear in-voice, without the critic flagging a rule-violation on the second pass.

## What Drifted
Scene ch01_sc01 (Andrés in Havana) was the problem scene: three drafter iterations (latencies 501s → 544s → 302s), each followed by a regenerator cycle, with the final regenerator emitting 14,981 output tokens — by far the heaviest rewrite in the chapter. The drift axis was almost certainly **historical**: the scene has to carry "eleven hulls Cortés had gathered for the crossing to Yucatán," "Our Lady of Antigua… the cathedral at Seville," the viaticum-plus-lifted-excommunication sequence, and a chapel/plaza/galley geography of Havana-c.1519 — every one of which is a citable claim the historical retriever has to underwrite. The chapter_critic running four separate times (and entity_extractor re-running with 12,552 output tokens on the second pass) reinforces that the sc01 drift propagated up: entity state for Andrés, the Genoese cook, and the implied Córdoba household needed extraction more than once to stabilize.

The donts axis is also suspect in sc01: the closing paragraph ("He did not cry. A soldier does not cry…") is the kind of epigrammatic interiority that the voice pin tolerates but that can tip into cliché if the critic's donts-list flags the "soldier does not cry" beat. No confirmation in the log, but the large regenerator token count (14,981) on a 2816-word chapter suggests the final rewrite restructured more than a paragraph.

## Emerging Patterns
Regen cost scales with **density of external citeable detail**, not with scene length or emotional difficulty. sc01 (Spanish historical surface) was ~1000 drafter output tokens and needed 3 iterations; sc03 (Nahuatl metaphysical surface) was ~1365 tokens and needed 1 iteration despite a deeper critic report. The difference is that the metaphysics rule-cards appear to retrieve cleanly from the corpus as self-contained units, whereas the historical scene needs the retriever to assemble multiple small facts (fleet count, Marian copy-vs-original, excommunication remission mechanics) into a single coherent context pack — and the bundler's output_tokens=31,603 (sc01) vs. 3,280 (sc00 chapter-critic pass) suggests the sc01 bundle was stuffed but still missed targets.

Second pattern: the event log opens with hundreds of retriever + context_pack_bundler calls for ch01_sc01 at 30–160s latency each, many triplicated with identical latency values. This looks like warmup / cache-miss / retry noise rather than productive retrieval, and it precedes the first real drafter call. Worth instrumenting separately — if the warmup storm is producing the stuffed-but-imprecise context packs, it's the root cause of the sc01 regen count, not the drafter.

Third pattern: single-POV-interior scenes (all three here) let the critic operate on a narrow voice surface. The voice pin held on first drafter pass for all three scenes (no voice-fidelity regen triggers visible in the slice) — drift was content-axis, not voice-axis. This is a useful invariant to preserve heading into ch02's multi-POV scenes.

## Open Questions for Next Chapter
- Historical-detail-dense Spanish-world scenes (ch01_sc01) require more drafter iterations than indigenous-POV scenes; historical-axis grounding (fleet size, viaticum mechanics, Marian iconography) is the primary regen driver for conquistador POVs.
- Metaphysics-axis scenes with dense Nahuatl cosmology (ch01_sc03) pass regeneration on the first cycle but generate the largest critic payloads, suggesting critic needs a denser rule-card retrieval bundle up-front rather than a second pass.
- Two-language compound-dialogue scenes (ch01_sc02, Mayan/Nahuatl code-switch via Citlal) land cleanest under the current rubric — entity-axis fidelity is easier to enforce when the named-entity set is small and locally scoped.
- Chapter-level entity_extractor required a second pass (output tokens 11700 → 12552) and chapter_critic ran four times; cross-scene cohesion (Andrés / Malintzin / Itzcoatl as foreshadowed thread) is not yet converging in one pass.
- Retriever warmup storms (hundreds of duplicated context_pack_bundler calls at 30–160s latency before the first real drafter call) suggest a cold-index or cache-miss pathology worth measuring as a separate thesis before ch02 drafts.
