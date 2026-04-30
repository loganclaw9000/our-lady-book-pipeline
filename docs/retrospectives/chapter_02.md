---
chapter_num: 2
candidate_theses:
- id: T-ch02-001
  description: Scenes that *extend* a freshly-established metaphysics axiom regen
    faster than scenes that *introduce* one — does the introducing-vs-extending distinction
    predict regen cost across ch03+?
- id: T-ch02-002
  description: Chapter-critic gating dropped ch02_sc03 from final assembly despite
    drafter+regen cycles converging at scene level — is assembly-level rejection a
    feature or a defect, and what attempt-count policy should govern drop-vs-retry?
- id: T-ch02-003
  description: Retriever issued 200+ duplicate calls on ch02_sc01 before drafter ran
    (latencies 9-73s, output_tokens=8 each) — is this a retry-storm bug in the context_pack_bundler
    upstream loop or expected re-ranking behavior?
- id: T-ch02-004
  description: ch02_sc02 cleared on a single critic pass while ch02_sc01 needed 3
    cycles + 3 full drafter re-runs — does the per-scene critic cost gradient correlate
    with first-kill emotional load specifically, or with theological-premise introduction
    generally?
---

# Chapter 02 Retrospective

## What Worked
ch02_sc02 cleared the critic on a single pass — drafter (latency 463s, 2048 output_tokens) → critic (54s, 2550 tokens), no regenerator invoked. Voice axis landed: long cumulative clauses survived ("the second-class *Nuestra Señora del Campeón* moved in formation at his elbow, two paces back and two paces wide"), tactile-as-theology held ("the suction of it under their feet... somewhere very far away, the child humming"), and italicized interior categories (*Combat-bind.*) preserved Paul-voice signature. The arc axis landed because the scene *extends* sc01's premise — "the child had not asked him about it" — instead of introducing it; Andrés's decision to kill the knee not the heart-chamber reads as moral consequence of premise already established, not premise-and-consequence in one beat.

## What Drifted
ch02_sc01 burned 3 full drafter cycles and 3 critic cycles. First drafter attempt returned 459 output_tokens (truncated). Second drafter attempt: 352 tokens. Third: 2048 tokens. Each followed by critic → regenerator → critic loop. Metaphysics axis was the load-bearing failure: introducing the saint-silence semantics ("the saint was not answering") plus first-kill registration ("she was somebody's") in one scene exceeded what one critic pass could ratify. Additionally, ch02_sc03 was drafted (3 attempts, including a 462s/1806-token regen) but does NOT appear in `assembled_from_scenes` — chapter_critic ran 3 times against ch02_sc00 (assembly view) and the final commit drops sc03. Whether that drop was deliberate gating or a silent fail is not legible from the event log.

## Emerging Patterns
The ch01 retro thesis — *attempt count tracks metaphysics density* — holds and sharpens here into a finer claim: it tracks metaphysics-*introduction* density, not metaphysics density per se. ch02_sc02 carries equal metaphysics weight (the saint's continued silence, child-as-moral-signal) but inherits the axiom from sc01 and converges in one cycle. The pipeline's regen cost is concentrated at premise-introduction beats. Secondary pattern: a retriever/context_pack_bundler storm preceded sc01's first drafter run (200+ duplicate-shape retriever calls, many in triplets at identical latency_ms — strongly suggestive of an outer retry loop firing on the same query). Storm did not recur for sc02/sc03, so either sc01 hit a transient upstream condition or the bundler retries on something sc01-specific (large cast of new entities? Nahuatl proper-noun retrieval miss?).

## Open Questions for Next Chapter
- Scenes that *extend* a freshly-established metaphysics axiom regen faster than scenes that *introduce* one — does the introducing-vs-extending distinction predict regen cost across ch03+?
- Chapter-critic gating dropped ch02_sc03 from final assembly despite drafter+regen cycles converging at scene level — is assembly-level rejection a feature or a defect, and what attempt-count policy should govern drop-vs-retry?
- Retriever issued 200+ duplicate calls on ch02_sc01 before drafter ran (latencies 9-73s, output_tokens=8 each) — is this a retry-storm bug in the context_pack_bundler upstream loop or expected re-ranking behavior?
- ch02_sc02 cleared on a single critic pass while ch02_sc01 needed 3 cycles + 3 full drafter re-runs — does the per-scene critic cost gradient correlate with first-kill emotional load specifically, or with theological-premise introduction generally?

<!-- chapter-nav-injected -->

---

[Index](../index.md) · [Chapter 2 canon](../chapters/chapter_02.md) · [💬 Feedback on Chapter 2 retrospective](https://github.com/loganclaw9000/our-lady-book-pipeline/issues/new?template=reader_feedback.yml&chapter=Chapter+2+retrospective)
