---
chapter_num: 15
candidate_theses:
- id: historical_canon_density_drives_regen
  description: Regen count tracks historical-event-canon density more than metaphysics-introduction
    density. Set-piece scenes against fixed historical record (Toxcatl massacre) burn
    more retriever cycles than scenes introducing novel metaphysics, because the critic
    enforces canonical sequence/geography/casualty-shape against RAG, not just internal
    consistency.
- id: chapter_critic_triggers_full_rebuild
  description: When chapter_critic fires a second pass after scene-level convergence,
    it triggers a full per-scene regenerator+critic cycle across all scenes. This
    is a new failure mode not seen in ch01-ch04 and is the dominant cost driver for
    chapters where scenes individually pass but aggregate coherence fails.
- id: ixiptla_entity_slot_gap
  description: Named ixiptla (Cuauhtli of Cuauhtitlán, Tochtli, Mazatl, Tepetl) and
    offscreen-relations (Cuauhtli Ocelotl, Tepin) appear without dedicated entity-card
    scaffolding, forcing the entity axis to validate names against general RAG. A
    first-appearance ephemeral-entity slot may reduce sc02's retriever churn on future
    massacre/battle scenes.
- id: restraint_arc_beats_resist_critic
  description: Arc beats built on inaction (Itzcoatl not approaching the stable door;
    standing in muster) require more regen passes than action beats, because the critic
    appears to flag low-event scenes for arc-stall before recognizing the restraint
    as the beat itself.
---

# Chapter 15 Retrospective

## What Worked
The metaphysics axis landed cleanly in ch15_sc01 on the first regen cycle (drafter→critic→regenerator→critic, two critic passes total). The Great Engine rendered as a felt bass-note through the soles of the sandals — "the bass under the city, the thing the people standing on stone always heard without hearing" — sustained the engine-as-physical-infrastructure framing established in earlier chapters without re-introducing rules, and the semitone-drop callback ("He had heard it change once, years ago, when a Flower War went badly") was accepted as continuity rather than flagged as new metaphysics. The entity axis held on Obsidian Mirror's offscreen presence: the deity is named, located, and made operationally inaccessible (Toxcatl forbids approach, seals are placed, adorators block the door) without the engine-compound geography being re-litigated by the critic.

The arc axis converged in ch15_sc03's stable-door beat — Itzcoatl's hand moving "a half-pace toward the door before the knowledge caught up to it," then falling back — survived two regenerator passes and the second critic call dropped from 7406 to 2625 output tokens, indicating the critic stopped raising new objections.

## What Drifted
ch15_sc02 (the massacre proper) was the chapter's regen sink. After the first drafter/critic/regenerator/critic cycle failed to converge, the pipeline burned **six full retriever→context_pack_bundler cycles** (each ~120-130s bundler latency) before the second drafter attempt — historical axis churn, almost certainly on the canonical sequence and casualty shape of the Toxcatl massacre and on the named ixiptla. The second critic still emitted 3029 output tokens of findings, suggesting partial-not-clean acceptance. The drift was not voice (the prose stayed in clipped Itzcoatl-register throughout — "He counted to forty. The killing had begun forty seconds before") but historical/entity grounding under high named-entity density.

ch15_sc03 drifted on arc: five regenerator passes against four critic passes before convergence. The scene's load-bearing move is a non-action (pilot does not break Toxcatl protocol to wake the deity), and the critic appears to have flagged this as arc-stall through multiple cycles before accepting it as the arc beat.

The chapter_critic fired twice — first pass at 3757 output tokens, then a full per-scene regen+critic cascade across ch15_sc01/sc02/sc03, then a second chapter_critic at 3146 tokens. This is the first chapter where aggregate coherence failed after scenes individually passed.

## Emerging Patterns
The ch01→ch02 thesis ("attempt count tracks metaphysics-introduction density") and its ch04 counter-evidence resolve here into a sharper claim: **regen count tracks historical-canon density when the scene is bound to a fixed historical event**. ch15_sc02 introduces no new metaphysics (the engine wound is implication of established rules) and no new POV entity, yet it is the chapter's most expensive scene by an order of magnitude in retriever cycles — because it must reproduce the canonical Templo Mayor massacre against the lore-bible's historical axis without anachronism, with named ixiptla, in the right sequence (Spanish gate-block → first stone → first sword → ixiptla deaths → general slaughter). Scenes that *invent* metaphysics regen on the metaphysics axis; scenes that *render canonical history* regen on the historical and entity axes, and the latter cost more because RAG must validate against an external corpus, not just internal consistency.

Secondary pattern: the chapter_critic full-rebuild loop is now an observable failure mode and should be modeled as a distinct cost line in the digest, not folded into per-scene attempt counts.

## Open Questions for Next Chapter
- Regen count tracks historical-event-canon density more than metaphysics-introduction density. Set-piece scenes against fixed historical record (Toxcatl massacre) burn more retriever cycles than scenes introducing novel metaphysics, because the critic enforces canonical sequence/geography/casualty-shape against RAG, not just internal consistency.
- When chapter_critic fires a second pass after scene-level convergence, it triggers a full per-scene regenerator+critic cycle across all scenes. This is a new failure mode not seen in ch01-ch04 and is the dominant cost driver for chapters where scenes individually pass but aggregate coherence fails.
- Named ixiptla (Cuauhtli of Cuauhtitlán, Tochtli, Mazatl, Tepetl) and offscreen-relations (Cuauhtli Ocelotl, Tepin) appear without dedicated entity-card scaffolding, forcing the entity axis to validate names against general RAG. A first-appearance ephemeral-entity slot may reduce sc02's retriever churn on future massacre/battle scenes.
- Arc beats built on inaction (Itzcoatl not approaching the stable door; standing in muster) require more regen passes than action beats, because the critic appears to flag low-event scenes for arc-stall before recognizing the restraint as the beat itself.

<!-- chapter-nav-injected -->

---

[Index](../index.md) · [Chapter 15 canon](../chapters/chapter_15.md)

<form class="reader-feedback" data-page-id="Chapter 15 retrospective" onsubmit="return submitReaderFeedback(event)">
  <details>
    <summary>💬 Send anonymous feedback on this page</summary>
    <input type="hidden" name="chapter" value="Chapter 15 retrospective">
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
