---
chapter_num: 23
candidate_theses:
- id: q1
  description: Will the restart-vs-regen boundary identified in sc03 hold as a predictor
    for upcoming siege-interior scenes (chapters where Itzcoatl's POV must continue
    carrying both new cockpit-metaphysics and accumulated arc-callback simultaneously),
    and if so, should the pipeline detect compound-load *before* drafting and pre-allocate
    a second context-pack budget rather than discovering the need through regen exhaustion?
- id: q2
  description: 'Does the "half a quarter-step off the note" image — planted in sc02
    at sc02''s cost, called back in sc03 cleanly — generalize as a deliberate technique:
    introduce the chapter''s load-bearing dissonance-image in the *middle* scene rather
    than the *first* scene, so the most expensive synthesis scene (typically the closer)
    inherits a paid-for anchor?'
- id: q3
  description: Is the chapter_critic_pass=true / voice_fidelity_aggregate=null combination
    a metric-pipeline gap that lets entity-axis thinness ship under cover of voice-axis
    pass, and should chapter-critic require non-null aggregate before pass?
- id: q4
  description: '```'
---

# Chapter 23 Retrospective

## What Worked
sc02 landed cleanly on voice and arc with two regen cycles despite carrying the chapter's heaviest political-emotional freight (Itzcoatl riding beside the cousin who finished his conversion early). The scene's anchoring image — the Spanish breastplate sitting "wrong on his shoulders" with steel rim cutting "above the bone" — gives the entire causeway dialogue a physical ground that the metaphysics-axis content (Tezcatlipoca/Huitzilopochtli engine dissonance) can hang on without extra regen cost. The phrase "half a quarter-step off the note" is planted here cleanly, and its function as a load-bearing motif for sc03 is established at sc02's own cost, not deferred.

sc01's voice held through repetition: "The hum held. / It held." as terminal refrain, and the parallel construction "He had walked down the road. He had stood on the stage. He had pledged his engines" carry the defection-ceremony scene on rhythm alone. Two regen cycles for a scene that has to introduce a new POV (Itzcoatl), establish *Obsidian Mirror* as a Tezcatlipoca-caste engine, stage a Cortés/Malintzin/Ixtlilxochitl reunion, AND seal the defection — that is amortization-by-anchor working as designed.

## What Drifted
sc03 cost ~4 regen cycles **plus a full restart** (a second drafter call after re-running retrievers and re-bundling context — visible in the event log as the second `[retriever] scene=ch23_sc03` block followed by a second `[drafter]` and a second three-regen cycle). This is the most expensive single scene in the chapter by a wide margin: ~2.4M ms of total scene time vs sc01's ~895K and sc02's ~1.1M.

The drift was on the **metaphysics axis** compounded with the **arc axis**. sc03 introduces multiple new metaphysics elements simultaneously: the corner-mirror device ("he had wanted to be able to see his own back ... had spent the next twelve years declining to look at"), the doctrine that "Tezcatlipoca passed through houses, not individuals," the "catch in her hum that the older pilots described as the deity coughing in sleep," and the dawn-ritual gesture itself ("not a Spanish gesture and it was not, properly, a Texcocan one"). Each of those is a discrete new metaphysics claim. At the same time the scene must honor heavy arc-callback: Otumba ("had stopped recognizing on the field at Otumba"), Toxcatl, Noche Triste, the fifteenth year in the engine-yard, the mother's death, the pledge ceremony. New-metaphysics-introduction + named-prior-battle-callback in a single interior-monologue scene exceeded what regen could resolve. Only restart-from-retrieval recovered it.

## Emerging Patterns
The thesis chain ch19 → ch20 → ch21 → ch26 ("unit of amortization is the image") holds, but ch23 surfaces its boundary condition: **single-image amortization works for either introduction OR synthesis, not both at once.** sc02 introduces (engine-caste dissonance) anchored on one image (the breastplate) and amortizes cheaply. sc03 attempts to introduce (corner-mirror, deity-as-house, dawn ritual, deity-coughing-in-sleep) AND synthesize (Otumba, mother's death, the fifteenth year, the pledge) on the same anchor (Mirror's hum + the corner-mirror image), and the cost spikes past regen-resolvability into restart territory.

The transferable claim: when an interior-monologue scene's metaphysics-introduction load and its callback load both exceed some threshold, the failure mode is no longer drift-the-regen-loop-can-fix; it becomes drift-the-context-pack-was-wrong-shape. The pipeline's response — re-running retrievers and re-bundling context before re-drafting — confirms this diagnostically: the first context pack could not support the scene the drafter was being asked to write.

The ch20 thesis ("synthesis scenes can cost more regens than introduction scenes") and the ch04 counter-evidence to the early metaphysics-introduction thesis converge here: it is not introduction-density alone, not callback-density alone, but their **product** in a single scene that predicts restart-vs-regen.

Separately, sc01's chapter_critic_pass=true with voice_fidelity_aggregate=null is worth flagging. The aggregate is null because per-scene voice scores were not summed; the chapter passed on critic verdict alone. The "the hum held" refrain may be passing voice cheaply while masking thinner content on the entity axis (Cortés is barely characterized, Malintzin is a half-step behind a name).

## Open Questions for Next Chapter
- Will the restart-vs-regen boundary identified in sc03 hold as a predictor for upcoming siege-interior scenes (chapters where Itzcoatl's POV must continue carrying both new cockpit-metaphysics and accumulated arc-callback simultaneously), and if so, should the pipeline detect compound-load *before* drafting and pre-allocate a second context-pack budget rather than discovering the need through regen exhaustion?
- Does the "half a quarter-step off the note" image — planted in sc02 at sc02's cost, called back in sc03 cleanly — generalize as a deliberate technique: introduce the chapter's load-bearing dissonance-image in the *middle* scene rather than the *first* scene, so the most expensive synthesis scene (typically the closer) inherits a paid-for anchor?
- Is the chapter_critic_pass=true / voice_fidelity_aggregate=null combination a metric-pipeline gap that lets entity-axis thinness ship under cover of voice-axis pass, and should chapter-critic require non-null aggregate before pass?
- ```

<!-- chapter-nav-injected -->

---

[Index](../index.md) · [Chapter 23 canon](../chapters/chapter_23.md)

<form class="reader-feedback" data-page-id="Chapter 23 retrospective" onsubmit="return submitReaderFeedback(event)">
  <details>
    <summary>💬 Send anonymous feedback on this page</summary>
    <input type="hidden" name="chapter" value="Chapter 23 retrospective">
    <label>Kind:
      <select name="kind">
        <option>praise / what worked</option>
        <option>critique / what did not work</option>
        <option>factual or continuity error</option>
        <option>voice / prose suggestion</option>
        <option>bug or site issue</option>
        <option>other</option>
      </select>
    </label><br>
    <label>What you want to say:<br>
      <textarea name="body" rows="6" cols="60" required></textarea>
    </label><br>
    <label>Optional contact (leave blank to stay anonymous):
      <input type="text" name="contact" maxlength="200">
    </label><br>
    <button type="submit">Submit</button>
    <span class="reader-feedback-status" aria-live="polite"></span>
  </details>
</form>

{% include feedback-script.html %}
