---
chapter_num: 20
candidate_theses:
- id: synthesis-density-exceeds-introduction-density
  description: When a scene's job is to collide two previously-introduced metaphysics
    revelations rather than introduce new ones, regen cost can exceed both setup scenes
    combined — synthesis load-bearing is more expensive than introduction.
- id: chapter-spine-scene-pays-tax
  description: The scene carrying a chapter's thematic punchline (the line readers
    will quote) reliably overruns regen budget regardless of metaphysics-introduction
    density, because critic enforces precision on the load-bearing utterance itself.
- id: full-redraft-as-signal
  description: A drafter re-invocation mid-cycle (after multiple regenerator passes
    already failed) is a distinct failure mode from regen-cycling and likely indicates
    the regenerator cannot reach the target from the current draft's frame.
---

# Chapter 20 Retrospective

## What Worked
sc01 (Bernardo's confession) landed in 1 regen despite introducing the entire Inquisition-feeds-saints metaphysics — `[critic] scene=ch20_sc01` ran twice with one `[regenerator]` between them. The introduction was anchored on a single tight image-pair: the guttering candle and Bernardo's eyes "the eyes of a man who had just confessed a murder he had not known he was committing." Voice axis stayed clean — the "she did not change her face. She did not change the angle of her hands" beat is recognizably Malintzin's interiority register from prior chapters. sc02 paid 2 regens but landed cleanly on the metaphysics axis: the dying priest's "the bone is the bowl the god drinks from" gives the Mexica-side terminology in a form structurally parallel to Bernardo's "*el hueso es la vasija*" — that parallelism is what sc03 will need.

## What Drifted
sc03 (cockpit synthesis) blew through budget — 5+ regenerator calls plus a mid-cycle full `[drafter]` re-invocation (`latency_ms=176958, output_tokens=11420`), then another full retriever→bundler→drafter cycle on top. Total critic invocations on sc03: 5. Drift was on the **arc** and **metaphysics** axes simultaneously: the scene has to make Malintzin deliver "They are the same account. The Reliquary is the *teōmecahuītlī*. The *teōmecahuītlī* is the Reliquary" without it reading as authorial thesis-statement, AND has to land Andrés's break ("he bent forward and put his face in his hands") without melodrama. The regenerator clearly couldn't reach both targets from any single draft frame — hence the redraft.

## Emerging Patterns
sc03 introduces zero new metaphysics — every term (`os sanctum`, `reddere`, `ixiptla`, willing-death, bone-as-housing) was already on the page from sc01 and sc02. Yet sc03 cost more regens than sc01 and sc02 combined. This inverts the ch15/ch22 thesis ("regen tracks canon-introduction density"): introduction is cheap when anchored; **synthesis is expensive even when nothing new is introduced**, because the synthesis line itself is what the critic is grading. The image-amortization thesis (ch26) doesn't save sc03 either — the cockpit scene inherits sc01's candle and sc02's brigantine ribs and still overruns. The load-bearing utterance is the cost driver, not the imagery around it.

Secondary observation: sc01's `[retriever]` and `[context_pack_bundler]` log shows a massive retry storm (~20+ duplicate context-pack assemblies before the first drafter call) that didn't translate to drafter/critic cost. Infrastructure churn is decoupled from generation cost — worth flagging but not a voice-quality signal.

## Open Questions for Next Chapter
- When a scene's job is to collide two previously-introduced metaphysics revelations rather than introduce new ones, regen cost can exceed both setup scenes combined — synthesis load-bearing is more expensive than introduction.
- The scene carrying a chapter's thematic punchline (the line readers will quote) reliably overruns regen budget regardless of metaphysics-introduction density, because critic enforces precision on the load-bearing utterance itself.
- A drafter re-invocation mid-cycle (after multiple regenerator passes already failed) is a distinct failure mode from regen-cycling and likely indicates the regenerator cannot reach the target from the current draft's frame.

<!-- chapter-nav-injected -->

---

[Index](../index.md) · [Chapter 20 canon](../chapters/chapter_20.md)

<form class="reader-feedback" data-page-id="Chapter 20 retrospective" onsubmit="return submitReaderFeedback(event)">
  <details>
    <summary>💬 Send anonymous feedback on this page</summary>
    <input type="hidden" name="chapter" value="Chapter 20 retrospective">
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
