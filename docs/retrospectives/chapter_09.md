---
chapter_num: 9
candidate_theses:
- id: t009_metaphysics_plus_historical_compounds_regens
  description: Scenes pairing new metaphysics introduction (deity-speaking, engine-as-question)
    with dense historical-canon load (causeway entry, palace of Axayacatl) require
    regen; scenes that are historical-procedural alone (Malintzin translation ritual
    at midpoint) pass first attempt
- id: t009_confessional_pov_stresses_donts_axis
  description: Cockpit/mirror confessional scenes where the deity addresses the pilot
    directly (sc03) may stress the donts axis differently than rank-formation metaphysics
    (sc01); both regen but the failure modes likely differ — needs disambiguation
    in next chapter with a comparable confessional beat
- id: t009_voice_fidelity_aggregate_missing
  description: voice_fidelity_aggregate is null in chapter frontmatter despite chapter_critic_pass=true
    — either the aggregator failed silently for ch09 or the contract changed; check
    pipeline_state.json and the chapter-assembly path
---

# Chapter 09 Retrospective

## What Worked
ch09_sc02 — the causeway-midpoint meeting between Moctezuma and Cortés — landed cleanly on first attempt (1 drafter call, 1 critic call, no regenerator). Despite carrying heavy historical canon (Malintzin + Aguilar translation chain, the *Requerimiento* set aside, formal tlatoani-greeting protocol) and an entity-recognition beat where the narrator identifies Malintzin as "the girl Xochitl was teaching," the scene held. The historical axis was procedural rather than introducing new world-rules, and the entity axis got its hinge moment ("she was, in that moment, the only person on the causeway who understood both sides") without leaning on metaphysics. Arc axis also clean: the narrator's private filing-away of Malintzin as future-useful is a setup beat, not a payoff, and the critic let the restraint stand.

## What Drifted
ch09_sc01 needed one regen cycle (drafter→critic→drafter→regenerator→critic). The scene introduces multiple new metaphysics elements simultaneously — Tezcatlipoca engines "waiting," the Great Engine's half-step hum-shift as a register of Moctezuma's choice, *Obsidian Mirror*'s "new question" that liturgy has no answer-phrase for — while also carrying the full historical-canon load of the Spanish column composition (third-class iron dolls, four named Reliquaries, *Santiago del Paso*, Tlaxcalan auxiliaries). The metaphysics axis is the likeliest regen driver: the engine-as-question framing is a genuinely new rule the chapter has to install.

ch09_sc03 also regenerated once. The cockpit-mirror confessional ("The mirror was honest in the way Tezcatlipoca was honest") introduces a second new metaphysics rule — the deity speaks back, addresses the pilot as *teōmachtiani*, "records" rather than rewards. This is a donts-axis-adjacent move: deity-direct-address risks tipping into theological exposition the chapter has so far avoided. The regen likely tightened that boundary.

## Emerging Patterns
ch15's thesis ("regen count tracks historical-canon density when the scene is canon-introducing") refines further here: in ch09 the regen pattern tracks **metaphysics-introduction compounded with historical-canon density**. sc01 and sc03 both introduce new metaphysics rules AND carry heavy historical specificity (named engines, named places, named protocols); both regen. sc02 carries equally heavy historical specificity but introduces no new metaphysics — passes first try. The compound, not either factor alone, predicts regen this chapter.

Secondary pattern: position in chapter does not predict regen here. sc01 (opening) and sc03 (closing) both regen; sc02 (middle) is clean. The signal is content-shape, not position.

## Open Questions for Next Chapter
- Scenes pairing new metaphysics introduction (deity-speaking, engine-as-question) with dense historical-canon load (causeway entry, palace of Axayacatl) require regen; scenes that are historical-procedural alone (Malintzin translation ritual at midpoint) pass first attempt
- Cockpit/mirror confessional scenes where the deity addresses the pilot directly (sc03) may stress the donts axis differently than rank-formation metaphysics (sc01); both regen but the failure modes likely differ — needs disambiguation in next chapter with a comparable confessional beat
- voice_fidelity_aggregate is null in chapter frontmatter despite chapter_critic_pass=true — either the aggregator failed silently for ch09 or the contract changed; check pipeline_state.json and the chapter-assembly path

<!-- chapter-nav-injected -->

---

[Index](../index.md) · [Chapter 9 canon](../chapters/chapter_09.md)

<form class="reader-feedback" data-page-id="Chapter 9 retrospective" onsubmit="return submitReaderFeedback(event)">
  <details>
    <summary>💬 Send anonymous feedback on this page</summary>
    <input type="hidden" name="chapter" value="Chapter 9 retrospective">
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
