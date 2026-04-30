---
chapter_num: 26
candidate_theses:
- id: q1
  description: '- Does sentence-level verbatim self-quotation across scenes consistently
    cost extra regens (donts/voice axis), or is the ch26 pattern an artifact of the
    chapter being arc-closure with grief as the dominant beat? Test on the next chapter
    that has a single emotional through-line spanning all scenes.'
- id: q2
  description: '- Does arc-closure (the resolution of a multi-chapter arc) impose
    its own regen floor of 2 independent of metaphysics/canon density? ch26 is the
    first chapter where this can be isolated; the next low-density continuation chapter
    is the cleanest test.'
- id: q3
  description: '- Is the chapter_critic first-pass-to-second-pass output ratio (here
    ~3x) a reliable convergence indicator worth promoting to a tracked metric?'
- id: q4
  description: '```'
---

# Chapter 26 Retrospective

## What Worked
ch26_sc01 carried the chapter's full metaphysics+entity+arc load in a single scene (dual-saint bracket-rite, Mozarabic sealing, Cuauhtémoc canoe-capture via Sandoval, the Templo Mayor's Great Engine going down) and held to 2 regens — the same floor as the lower-density sc02 and sc03. The arc-axis inversion lands cleanly on the line "He had killed a stranger in his first chapter. He was about to kill a friend in this one." — closing a 25-chapter callback to ch01's first-kill in two sentences without exposition. ch26_sc03's entity-axis handling of Itzcoatl is the chapter's tightest piece: his grief is rendered entirely as cockpit posture ("hatch up, hands at rest on the knees, head bowed three degrees") and an absence of motion ("the cradle did not move again that day"), no dialogue, no interiority — voice axis holds without needing a critic flag.

## What Drifted
ch26_sc02 spent the chapter's longest second-pass critic budget (8470 output tokens vs ~3300–5900 elsewhere), and the visible candidate is the donts/voice axis: the sentence "He had used up whatever inside him could weep. What was left was something colder, more useful, that he would carry for the rest of his life and never name" appears nearly verbatim in both sc01 and sc02, with a third paraphrase in sc03's "salt at the corner of his mouth, which was sweat, not weeping. He had checked." A deliberate refrain or unwanted self-quotation — the critic appears to have argued it both ways across the regen cycle. The "office for confessors. Not the office for martyrs" beat also doubles between sc02 and sc03 (donts axis: thematic restatement). chapter_critic ran twice (sc00 passes) which is consistent with the chapter-level repetition having been flagged at chapter scope, not scene scope.

## Emerging Patterns
ch19's thesis ("motif-threading amortizes density") and ch24's counter-evidence resolve further here: **the unit of amortization is the image, not the sentence.** sc01's image-level motifs (the engine-hum-in-the-jaw, the bracket-rite tooling sequence) thread into sc02 and sc03 cleanly without regen cost. But the *sentence-level* repetition ("used up whatever inside him could weep") does not amortize — sc02 still cost 2 regens despite being a low-density grief-aftermath scene that should have inherited the savings. The drafter is either over-quoting itself when the prior scene's voice is in context, or the critic is correctly flagging it as drift; either way, sentence-level repetition is structurally different from motif-image repetition for this pipeline.

A second pattern: **chapter_critic output collapsed 3x between first pass (4804 tokens) and second pass (1590 tokens)** on sc00 — a clean signal of chapter-level convergence that may be more reliable than per-scene critic output trends.

## Open Questions for Next Chapter
- - Does sentence-level verbatim self-quotation across scenes consistently cost extra regens (donts/voice axis), or is the ch26 pattern an artifact of the chapter being arc-closure with grief as the dominant beat? Test on the next chapter that has a single emotional through-line spanning all scenes.
- - Does arc-closure (the resolution of a multi-chapter arc) impose its own regen floor of 2 independent of metaphysics/canon density? ch26 is the first chapter where this can be isolated; the next low-density continuation chapter is the cleanest test.
- - Is the chapter_critic first-pass-to-second-pass output ratio (here ~3x) a reliable convergence indicator worth promoting to a tracked metric?
- ```

<!-- chapter-nav-injected -->

---

[Index](../index.md) · [Chapter 26 canon](../chapters/chapter_26.md)

<form class="reader-feedback" data-page-id="Chapter 26 retrospective" onsubmit="return submitReaderFeedback(event)">
  <details>
    <summary>💬 Send anonymous feedback on this page</summary>
    <input type="hidden" name="chapter" value="Chapter 26 retrospective">
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
