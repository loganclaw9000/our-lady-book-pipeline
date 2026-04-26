# Phase 7: Narrative Physics — Storytelling Atomics Codification

**Researched:** 2026-04-25
**Domain:** Narratology synthesis → enforceable schema/gate/critic-axis grammar
**Confidence:** HIGH on Genette/Swain/McKee/Booth/Truby/Sanderson core; MEDIUM on synthesis judgments (where canonicals differ, this doc picks).
**Consumer:** `gsd-planner` reads this directly when designing schema enums, gate semantics, and critic rubric axes for Phase 7.

---

## How To Read This

Two tiers, by operator directive (D-20 + Claude's-Discretion default = "two-tier").

- **Tier 1 — Implementation Brief.** Load-bearing atomics that map directly to schema fields, pre-flight gates, and critic axes. Planner-actionable. Every section closes with a "PLANNER HOOK" block stating the concrete artifact (Pydantic field, gate name, critic axis name) the planner emits from it.
- **Tier 2 — Deep References Appendix.** Fuller scholarly treatment of each source's contribution. Used by future thesis-registry experiments and for v1.1+ refinement of treatment vocabulary, focalization variants, and beat-charge nuance.

The engine implements Tier 1. Tier 2 is the canon Tier 1 was distilled from.

---

## Tier 0 — The One-Page Frame

**The metaphor (D-01):** A scene is a rigid body. Its declared properties — POV, motivation, treatment, ownership, named-quantity continuity — are the body's mass, charge, position, velocity. The drafter is the simulation; the critic is the integrity check. Drift = constraint violation = engine refuses to advance, just as Unreal refuses to let two rigid bodies inter-penetrate.

**The atomics (six families).** Every craft tradition this doc consulted converges on six discrete, re-combinable units that compose a scene:

| # | Atomic family | Question it answers | Lead source(s) |
|---|---|---|---|
| 1 | **Focalization** | Whose perception orients the scene? Whose voice narrates it? | Genette 1972/1980, Bal 1985 |
| 2 | **Drive** | What does the focal character want, and why now? | Truby (desire/ghost), McKee (want/need), Stanislavskian objective |
| 3 | **Action shape** | Goal → conflict → outcome (scene); reaction → dilemma → decision (sequel) | Swain 1965, McKee 1997 |
| 4 | **Value charge** | Which value-axis does this scene turn, and in which direction? | McKee polarity, Truby moral argument |
| 5 | **Beat ownership** | Which discrete plot-event does THIS scene own; which are forbidden as recap? | Save-the-Cat / Story Grid / Truby 22-step (each event = one location) |
| 6 | **Theater staging** | Where, when, through which senses, with whom on/off screen? | Aristotle (opsis), Stein (5-sense), radio-drama theater-of-mind (Verma 2012) |

**The gate-grammar.** Each atomic gets one schema field, one pre-flight gate (cheap), one critic axis (post-draft), and at least one mapped failure case from the manuscript-evidenced canon list (D-13..D-19).

```
ATOMIC          SCHEMA FIELD               PRE-FLIGHT GATE       CRITIC AXIS              CANARY (manuscript)
focalization    perspective + pov_lock     pov_lock              pov_fidelity             ch09 sc01 (Andrés re-narrating Itzcoatl interior)
drive           characters[].motivation    motivation            motivation_fidelity      "centered motivation" baseline (D-02)
action shape    contents (goal/conflict/   ownership             content_ownership        sc01 content as sc02 (drafter overlap)
                outcome triplet)
value charge    treatment + value_charge   treatment             treatment_fidelity       (mournful drafted as light)
beat ownership  owns + do_not_renarrate    ownership             content_ownership +      ch11 sc03 stub leak ("Establish: ...")
                                                                  stub_leak
theater         staging block + sensory    quantity (CB-01)       named_quantity_drift +   Andrés age 26→23, La Niña 50→60→55→42 ft,
                weight + on_screen list                            scene_buffer_similarity   Cholula Oct 30 vs Oct 18, ch10 sc02 loop
```

This is the spine of Phase 7. Tier 1 expands each row.

---

# TIER 1 — Implementation Brief

## 1. Focalization Model

### 1.1 Genette's three-way split (canonical)

Gérard Genette, *Narrative Discourse* (1972/1980), distinguishes **who sees** from **who speaks** — narratology's most-cited correction to confused "POV" usage [CITED: en.wikipedia.org/wiki/Focalisation; estetikajournal.org/articles/10.33134/eeja.364].

| Type | Definition | Genette's name | Concrete narrator stance |
|---|---|---|---|
| **Zero focalization** | Narrator knows more than any character. Free movement between minds, places, times. | non-focalised | Classical omniscient. ("Reader, she did not love him, though she did not yet know it.") |
| **Internal focalization** | Restricted to one character's perception, knowledge, sensorium at a time. Can be **fixed** (one character throughout — Henry James, *The Ambassadors*), **variable** (different characters in different sections — Flaubert, *Bovary*), or **multiple** (same event seen through different characters — Faulkner, Joyce). | focalisation interne | Free-indirect-discourse 3rd-close. 1st-person. "He saw the smoke. He had not yet thought the word fire." |
| **External focalization** | Camera-eye. Externally observable actions and speech only — no interior. | focalisation externe | Hammett. Hemingway short stories. ("She set the cup down. She did not look at him.") |

**Mieke Bal's refinement** (Narratology, 1985) distinguishes the **focalizer** (the perceiver) from the **focalized** (the object of perception) — useful when the same focal character watches and is watched in alternation, but at v1 we collapse this back into Genette's three-way for schema simplicity.

### 1.2 The engine's enum

For the manuscript at hand, three Genette categories explode into five practically-distinguishable enum values that critics can score against:

```python
class Perspective(str, Enum):
    FIRST_PERSON = "1st_person"           # Genette internal-fixed, 1st-person grammar
    THIRD_CLOSE = "3rd_close"             # Genette internal-fixed, 3rd-person grammar (free indirect)
    THIRD_LIMITED = "3rd_limited"         # Genette internal-fixed, 3rd-person, more reportorial than free-indirect
    THIRD_OMNISCIENT = "3rd_omniscient"   # Genette zero, with explicit narrator commentary
    THIRD_EXTERNAL = "3rd_external"       # Genette external, camera-eye
```

`THIRD_CLOSE` vs `THIRD_LIMITED` is a working distinction inherited from craft handbooks (Le Guin, *Steering the Craft* ch.7) [CITED: ursulakleguin.com/steering-the-craft]: close = free-indirect access to thought-rhythm; limited = third-person reporter who knows what the character knows but doesn't braid the syntax to the character's interior. The critic distinguishes by inspecting (1) presence of unmediated thought-fragments lacking attribution (close), (2) explicit narratorial frame ("he thought", "she felt") (limited).

Variable internal focalization (multi-POV chapters: ch07 Andrés/Itzcoatl alternation in *Our Lady of Champion*) is encoded as a *per-scene* `perspective` — the chapter is variable BECAUSE its scenes are each fixed-internal under different characters. The schema does not need a "variable" enum value; the chapter critic sees the alternation by inspecting scene-level metadata.

### 1.3 The Itzcoatl regression case (D-16 canary, worked example)

Manuscript evidence: ch01 sc03 "I was sixteen" → ch06+ third-person Itzcoatl. **This is a Genette internal-fixed-1st → internal-fixed-3rd shift, mid-character, mid-book.** No craft tradition tolerates this without explicit thematic marking; it is an unmarked focalization breach.

**Engine response — pov_lock layer (D-16):**
1. A `pov_lock.yaml` artifact pins `<character>: <perspective>` for the lifetime of the book.
2. Drafter pre-flight reads the lock. If the stub's `perspective` disagrees with the lock for the scene's focal character, drafter REFUSES with `PovLockBreach`.
3. Override is allowed but explicit: stub frontmatter must carry `pov_lock_override: <rationale>`. Then a `role='physics_gate'` event records the override with rationale.
4. Critic's `pov_fidelity` axis confirms produced perspective matches declared perspective post-draft.

**Implementation note for ch15+ activation (per OQ-01 recommendation (a)):** lock activates at ch15 boundary. ch01-04 are read-only baseline; ch05-14 are historical artifacts. The lock object MUST encode this: `{character: itzcoatl, mode: 1st_person, active_from_chapter: 15}`.

### 1.4 Worked example: ch09 sc01 canary

Manuscript evidence: ch09 sc01 critic-failed all four attempts because Andrés (POV) recycled Itzcoatl's interior. **This is Genette internal-fixed-violation: focalizer drift mid-scene.** Andrés cannot perceive Itzcoatl's interior under internal-fixed; that's omniscient (zero) territory, which the chapter's prior scenes do NOT use. The critic axis `pov_fidelity` enforces *no perceptual access not authorized by the declared perspective*.

The detection rule (concrete, codable):

> If `perspective ∈ {1st_person, 3rd_close, 3rd_limited, 3rd_external}`, then any prose passage rendering the interior thought, sensation, or unspoken intent of a character OTHER than the declared focal character is a breach. The critic's `pov_fidelity` axis cites the location and the breaching prose.

The drafter prompt CANNOT be relied on to enforce this — voice-FT models trained on omniscient prose drift toward it. The CRITIC is the enforcement.

### PLANNER HOOK 1
- Pydantic field: `perspective: Perspective` (enum above) on `SceneMetadata`.
- New artifact: `physics/locks.py` exposing `load_pov_locks()` returning `dict[str, PovLock]` (where `PovLock = {character, perspective, active_from_chapter, expires_at_chapter | None}`).
- Pre-flight gate file: `physics/gates/pov_lock.py`. Function: `def check(stub: SceneMetadata, locks: dict[str, PovLock]) -> GateResult`.
- Critic axis: `pov_fidelity`. Rubric prompt language: see §1.4 detection rule.

---

## 2. Drive (Motivation) — The Load-Bearing Axis (D-02)

### 2.1 Three traditions, one synthesis

Three craft traditions converge on a per-scene drive primitive:

- **John Truby** (*The Anatomy of Story*, 2007 [CITED: truby.com/the-anatomy-of-story/]): every protagonist has a **ghost** (past wound), a **desire** (conscious goal), a **need** (unconscious moral requirement), and an **opponent** (whose desire conflicts). At scene-grain, the desire is the active motivator.
- **Robert McKee** (*Story*, 1997): every scene operates on a **want vs need** tension. The "spine" is what the character wants; the "controlling idea" is what the character needs to learn.
- **Stanislavskian theatrical practice** (1900s-): every scene = a unit of action with an **objective** (what does this character want, in this scene, from another character — phrased as an active transitive verb).

The engine adopts the *Stanislavskian per-scene objective*, with Truby's ghost/desire/opponent triple available as *book-grain context* injected via the canon-bible (CB-01 cousin), NOT per-scene.

**Why Stanislavski over Truby/McKee at scene grain:** Truby and McKee are book-shaped (one ghost per protagonist, one moral argument per book). Stanislavski is scene-shaped — exactly the granularity our schema needs. The book-grain Truby data lives in `entity-state/` cards; the scene-grain Stanislavski data lives in `motivation` per-character per-scene.

### 2.2 The schema

```python
class CharacterPresence(BaseModel):
    name: str                                    # canonical
    on_screen: bool                              # bodily present in the staged scene
    motivation: str                              # active transitive verb + object: "warn Xochitl about the count"
    motivation_failure_state: str | None = None  # optional: what does failure look like for this scene's want
```

`motivation` is a **structured-but-string** field. Closed-enum is wrong here — character desires are open-vocabulary. But we enforce **shape**: must contain (a) an active verb (regex `\b(?:to\s+)?(\w+ing|\w+e?|\w+s)\b` is too loose; we recommend a soft critic-rubric check rather than a hard regex gate). Pre-flight gate enforces only: `motivation` is non-empty + ≥3 words + does not contain stub vocabulary (`Establish:`, `Set up:`, etc.).

### 2.3 What "centered motivation" means (D-02 load-bearing)

"Centered" = the motivation is **the actual driver of the scene's events, not a pretextual label**. Failure modes:

- **Vestigial motivation:** `motivation: "to grieve"` declared, but the scene's prose has the character planning logistics, with no emotional through-line. → critic fail.
- **Drifted motivation:** `motivation: "to confront Cortés"`, but the scene ends with the character not confronting, not deciding-not-to-confront, and not failing-to-confront — the want simply evaporates. → critic fail.
- **Undeclared motivation for an on-screen character:** if `on_screen: true`, motivation MUST be present. Pre-flight rejects.

The critic's `motivation_fidelity` axis answers ONE question per on-screen character: *Did the scene's events, dialogue, and interior serve, frustrate, transform, or pivot on this declared motivation?* Yes → pass. Drift, evaporation, vestige → fail.

### 2.4 Operator-strong default: motivation FAIL is hard-stop (Claude's Discretion D-26 weight)

Per D-02, motivation is THE load-bearing axis. The engine treats `motivation_fidelity: FAIL` as `overall_pass: False` regardless of the other 12 axes. Other axis fails route through normal severity-weighting; motivation fail is unconditional. This implements the operator-stated "always center motivation" as a hard architectural property.

### PLANNER HOOK 2
- Pydantic: `characters_present: list[CharacterPresence]` on `SceneMetadata` with the inner model above.
- Pre-flight gate file: `physics/gates/motivation.py`. Function: `check(stub) -> GateResult`. Returns FAIL if any `on_screen=True` character has empty/short/stub-leak motivation.
- Critic axis: `motivation_fidelity` with HARD-STOP severity (FAIL → overall_pass=False unconditionally).
- Rubric prompt: per-character question above.

---

## 3. Action Shape — Scene/Sequel + Goal/Conflict/Outcome

### 3.1 Swain's scene/sequel (canonical)

Dwight Swain, *Techniques of the Selling Writer* (1965), engineered the most widely-cited scene-grain structure [CITED: en.wikipedia.org/wiki/Scene_and_sequel; septembercfawkes.com/2021/09/scene-structure-according-to-dwight-v.html]:

- **Scene** = goal-directed action unit. Three parts: **Goal** (the focal character's measurable, scene-level want, clear by mid-scene at latest) → **Conflict** (opposition encountered) → **Disaster** (outcome that introduces a new problem; pure goal-success without disaster is a story-killer).
- **Sequel** = reaction-recovery unit between scenes. Three parts: **Reaction** (emotional response to the prior disaster) → **Dilemma** (forced choice from the disaster's new constraints) → **Decision** (commitment that powers the next scene's Goal).

**Manual_concat duplication breach (D-21 canary):** the V7C ship cycle's `manual_concat` chapters duplicated content because the assembler had no sequel-vs-scene distinction. Scenes ran into scenes without sequels; the model's solution was to re-narrate the prior scene to manufacture a transition. **The engine treats sequel-skipped as a beat-ownership error, not a separate axis** — see §5.

### 3.2 McKee's three-act fractal

Robert McKee, *Story* (1997): every scene contains **inciting incident → progressive complication → crisis decision → climax → resolution** at miniature scale, fractally repeating the act-structure. McKee's scene-bones [CITED: mckeestory.com/do-your-scenes-turn/] reduce to: **a scene that doesn't TURN doesn't exist**. (See §4 on value charge.)

### 3.3 The engine's `contents` field

Every craft tradition wants the same three things explicit:

```python
class Contents(BaseModel):
    goal: str                  # the focal character's scene-level goal (≥1 phrase, ≤1 sentence)
    conflict: str              # the opposition (≥1 phrase)
    outcome: str               # disaster|partial-disaster|victory|partial-victory + brief description
    sequel_to_prior: str | None  # optional reaction/dilemma/decision sketch (None if this scene IS a sequel)
```

The drafter prompt receives `contents` at the top, like the canonical-quantity stamp (D-23). The critic's `content_ownership` axis (§5) checks that the produced scene actually delivered the goal-conflict-outcome triplet without smuggling in another scene's beats.

### PLANNER HOOK 3
- Pydantic: `contents: Contents` on `SceneMetadata`.
- No dedicated pre-flight gate (shape is enforced by Pydantic). Validation = "all three subfields present, ≥1 word each."
- Critic axis: `content_ownership` (§5) covers post-draft enforcement.

---

## 4. Value Charge — McKee Polarity & Treatment Vocabulary

### 4.1 McKee's polarity (canonical)

McKee's positive/negative scene-charge framework [CITED: mckeestory.com/do-your-scenes-turn/; socreate.it/en/blogs/screenwriting/how-to-use-positive-and-negative-charges-to-structure-great-scenes]:

> "A scene is an action through conflict in more or less continuous time and space that turns the value-charged condition of a character's life on at least one value with a degree of perceptible significance."

Values are binary: `alive/dead, love/hate, freedom/slavery, truth/lie, courage/cowardice, loyalty/betrayal, wisdom/stupidity, hope/despair, faith/doubt`, etc. Each scene picks one (or rarely two) value-axes; the scene's TURN is the polarity flip on that axis (or its escalation, +→++, or compounding inversion, +→−→+).

### 4.2 Truby's moral argument (parallel)

Truby's "moral argument" is the book-grain version: a thesis the protagonist's moral choices argue out. At scene grain, each scene contributes one move to that argument by turning a value.

### 4.3 Treatment vocabulary (D-26 operator examples + craft-derived expansion)

The operator listed: `dramatic, mournful, comedic, light, propulsive, contemplative`. These are tonal registers, not values. Treatment ≠ value-charge — treatment is HOW the value-charge is delivered (rhythm, diction, sensory weight); value-charge is WHAT MOVES.

Synthesizing operator examples with McKee value-axes and Stein's tonal register taxonomy [CITED: laurellecommunications.blog/2023/08/07/stein-on-writing-a-masterful-book-for-fiction-writers]:

```python
class Treatment(str, Enum):
    DRAMATIC = "dramatic"            # high-stakes, tightening sentences, inevitability
    MOURNFUL = "mournful"            # elegiac, slow rhythm, past-tense interior weight
    COMEDIC = "comedic"              # incongruity, timing-dependent diction
    LIGHT = "light"                  # low-stakes, buoyant rhythm, no shadow
    PROPULSIVE = "propulsive"        # action-forward, short clauses, present-tense pressure
    CONTEMPLATIVE = "contemplative"  # interior-heavy, long syntax, abstract register
    OMINOUS = "ominous"              # rising tension without release; foreshadowing dominates
    LITURGICAL = "liturgical"        # ritual rhythm, formal diction, repetition-as-sacrament
    REPORTORIAL = "reportorial"      # neutral, distanced (Booth's high "distance"), camera-eye
    INTIMATE = "intimate"            # low distance, sensory-close, second-person-ish even in 3rd
```

**Closed enum, not open string.** Reasoning:
- Voice-FT model needs a stable vocabulary. Open strings = drafter sees rare/novel treatment values it doesn't know how to render.
- Critic needs deterministic rubric. "Did the scene deliver `mournful`?" presupposes a shared definition of `mournful`.
- The cost of a closed vocabulary is rare-case mis-fit; we mitigate via (a) the 10 categories above covering the *Our Lady of Champion* manuscript's actual register variety and (b) future v1.1 may add a `treatment_secondary` field for blends (mournful-propulsive = grief-driven action, common in war fiction).

**Per-treatment rubric:** the critic's `treatment_fidelity` axis defines `mournful` (etc.) by criteria rubric:

| Treatment | Diction signature | Sentence rhythm | Sensory dominance | Pace |
|---|---|---|---|---|
| MOURNFUL | past-weighted; few present-tense action verbs; absence-words ("was no longer", "would never") | long syntactic units, comma-heavy, clausal subordination | sound (silenced things), tactile (cold) | slow |
| PROPULSIVE | concrete nouns; active transitive verbs | short coordinated clauses; absent subordinators | kinetic (motion, pursuit) | fast |
| CONTEMPLATIVE | abstract nouns; cognitive verbs (knew, thought, considered) | long; embedded clauses; metacognitive asides | interior; neutral exterior | slow |
| LITURGICAL | repetition; archaisms allowed; named-thing-as-sacred | parallelism; parataxis | sound, smell (incense, sound) | metronomic |

(Full table for all 10 in Tier 2 §A.4.)

### 4.4 Value-charge schema (separate from treatment)

```python
class ValueCharge(BaseModel):
    axis: str                      # "loyalty/betrayal" | "faith/doubt" | "freedom/slavery" | etc. (open string, McKee-style)
    starts_at: Literal["positive", "negative", "neutral"]
    ends_at: Literal["positive", "negative", "neutral", "compound_positive", "compound_negative"]
    # A scene that doesn't turn (starts == ends and not compound) is craft-suspect — critic flags as "no-turn".
```

### PLANNER HOOK 4
- Pydantic: `treatment: Treatment` (enum) + `value_charge: ValueCharge` on `SceneMetadata`.
- Pre-flight gate file: `physics/gates/treatment.py`. Function: `check(stub) -> GateResult` (validates enum membership; rejects unknown strings).
- Critic axes: `treatment_fidelity` (matches produced register against per-treatment rubric) + (Phase 7 deferred to v1.1) `value_turn` (no-turn detection).
- v1.1 stretch: open-vocabulary blends via `treatment_secondary` field.

---

## 5. Beat Ownership — The Sc01-Bleed Bug Class

### 5.1 The fault and its three lineages

Sources for "each beat = exactly one scene's responsibility":

- **Save the Cat** (Blake Snyder, 2005 [CITED: savethecat.com/beat-sheets; reedsy.com/blog/guide/story-structure/save-the-cat-beat-sheet/]): 15-beat sheet at book grain. Each beat (Catalyst, Debate, Break Into Two, B-Story, Fun and Games, Midpoint, Bad Guys Close In, All-Is-Lost, Dark Night of the Soul, Break Into Three, Finale) hits at one location. Re-narrating a beat = beat smear = the audience loses position-in-arc.
- **Story Grid** (Shawn Coyne): every scene has 5 commandments — Inciting incident, Turning point, Crisis, Climax, Resolution — and these belong to THAT scene. A scene's TP is not a recap of the prior scene's TP.
- **Truby 22-step**: each step = one location. Step 6 = ally; step 8 = first revelation; etc. If step 8's revelation is re-narrated in a later step's scene, the moral argument loses its load-bearing event.

### 5.2 The schema (D-13 lock)

```python
class SceneMetadata(BaseModel):
    # ... other fields ...
    owns: list[BeatTag]                   # discrete beats this scene owns. Free-text-but-controlled.
    do_not_renarrate: list[str]           # explicit beats from prior scenes that this scene MAY NOT recap
    callback_allowed: list[str] = []      # explicit list of prior-scene beats that THIS scene IS allowed to reference (not recap)
```

`BeatTag` is a structured string: `"sc01_arrival"`, `"ch04_sc02_decision_to_burn_ships"`. The CRITIC checks `content_ownership`:

> For each entry in `do_not_renarrate`: does the scene contain prose that recapitulates the named beat? If yes → FAIL. *Reference* (a sentence acknowledging the prior beat happened) is allowed; *recap* (re-rendering the beat as fresh narration) is forbidden.

### 5.3 Reference vs recap — the operational distinction

The line between reference and recap is the line between a sentence and a paragraph. A working heuristic for the critic prompt:

- **Reference (allowed):** ≤1 sentence acknowledging the prior beat without rendering its sensory texture. Example: *"Three days after the burning of the ships, Andrés walked the beach again."* — acknowledges, does not re-narrate.
- **Recap (forbidden):** ≥1 sentence rendering the prior beat's sensory texture, dialogue, or interior. Example: *"Andrés remembered the fires: the timber cracking, the smell of pitch, the boy with the torch."* — recap, rendered as if happening.

The critic prompt encodes this distinction; concrete edge cases live in the few-shot YAML.

### 5.4 Stub-leak as ownership-leak (D-17 canary)

ch11 sc03 line 119: `Establish: the friendship that will become Bernardo's death-witness in Ch 26.` This is the scene's **stub-frontmatter beat label** leaked into prose. The drafter received the beat-function string `"Establish: the friendship..."` in the prompt and reproduced it verbatim instead of dramatizing it.

The fix is two layers:

1. **Drafter prompt change (D-23 anchor pattern):** beat function in the prompt header is *not* a sentence the drafter can ape. It's a DIRECTIVE block, structurally distinct from the prose section. The block is fenced (e.g. `<beat>...</beat>`) so the drafter's pattern-match cannot smear directive into prose.
2. **Stub-leak critic axis (D-27 hard reject):** regex check for stub vocabulary `\b(?:Establish|Resolve|Set up|Beat|Function)\s*:` (case-insensitive, anchored to line-start or sentence-start). Match → FAIL → scene-kick → re-stub.

The stub-leak axis is a **black-and-white pattern check, not a critic judgment call.** The Anthropic critic doesn't need to opine; a regex run before the structured-output call short-circuits to FAIL.

### PLANNER HOOK 5
- Pydantic: `owns: list[BeatTag]`, `do_not_renarrate: list[str]`, `callback_allowed: list[str]` on `SceneMetadata`.
- Pre-flight gate file: `physics/gates/ownership.py`. Validates `owns` non-empty for committable scenes (drafts may be partial); validates `do_not_renarrate` does not overlap with `owns`.
- Critic axes: `content_ownership` (Anthropic LLM judgment per §5.3 reference-vs-recap heuristic) + `stub_leak` (deterministic regex — see 07-RESEARCH.md §7 for the regex set).
- The `stub_leak` axis fires at HARD severity = scene-kick on first detection.

---

## 6. Theater Staging — Operator's Theater of the Mind (D-04)

### 6.1 The radio-drama ancestry

Neil Verma's *Theater of the Mind: Imagination, Aesthetics, and American Radio Drama* (Chicago, 2012) [CITED: press.uchicago.edu/ucp/books/book/chicago/T/bo13040503.html; allarts.org/programs/theater-of-the-mind-radio-drama] establishes the canon for this metaphor:

> "Theater of the mind" describes any form of storytelling that relies on the audience's imagination to create sensory detail, action, and emotional texture rather than presenting them visually or materially.

The operator's directive (D-04) imports this directly: *the metadata schema is the playbook for the constructed mental theater the prose stages*. The schema's job is to make the staging EXPLICIT so the drafter doesn't improvise it (which is when continuity breaks: see Cempoala double-arrival — drafter improvised a re-arrival because the stub didn't pin first-arrival as already-staged).

### 6.2 Staging primitives (Aristotle + Stein + radio-drama)

Aristotle's *Poetics* gives us **opsis** (spectacle — staging) as one of six tragedy elements; Stein's *Stein on Writing* ch.17 gives us **5+1 senses** as a density metric [CITED: laurellecommunications.blog/2023/08/07/stein-on-writing-a-masterful-book-for-fiction-writers; mason.gmu.edu/~rnanian/Aristotle-poeticsexcerpt.pdf]; Verma gives us *anchor with a small number of precise sensory details, not exhaustive description*.

Synthesis schema:

```python
class Staging(BaseModel):
    location_canonical: str                  # canonical location name (CB-01-resolvable for verbatim injection)
    spatial_position: str                    # where the focalizer is in the location ("south steps of Templo Mayor")
    scene_clock: str                         # when, in scene-time, this scene occurs ("late morning, Toxcatl day 4")
    relative_clock: str | None = None        # relation to prior scene's clock ("three days after sc02")
    sensory_dominance: list[Literal["sight","sound","smell","taste","touch","kinesthetic"]]  # ≤2 entries — Stein density rule
    on_screen: list[str]                     # entities bodily present (matches characters_present where on_screen=True)
    off_screen_referenced: list[str] = []    # named entities referenced but not present
    witness_only: list[str] = []             # entities present-but-not-acting (Aristotle's chorus)
```

`sensory_dominance` is capped at 2 because Stein's density rule is *anchor with a few precise senses, not all five*; >2 = description-flooding.

### 6.3 Cempoala double-arrival case (continuity ↔ staging)

ch03 sc02 + ch04 sc02 both staged Cempoala-arrival. **Why:** ch04 sc02's stub didn't carry `relative_clock: "two weeks after ch03 sc02"` and didn't carry `do_not_renarrate: ["ch03_sc02_cempoala_arrival"]`. The drafter, lacking explicit "you are NOT re-arriving", arrived again.

Staging's `relative_clock` field plus ownership's `do_not_renarrate` together prevent this. Engine response is twofold:

1. Pre-flight gate `quantity` (CB-01) catches: stub references "Cempoala" + canon-bible has Cempoala-arrival owned by ch03_sc02 + this scene's `owns` doesn't include re-arrival → suspect. Soft warn at pre-flight (this is a corner case, hard reject would over-fire); critic post-draft hard-reject if double-arrival is rendered.
2. Drafter prompt header includes: "PRIOR SCENES OWN: ch03_sc02_cempoala_arrival. DO NOT re-render this beat."

### PLANNER HOOK 6
- Pydantic: `staging: Staging` on `SceneMetadata` (model above).
- Pre-flight gate: covered by `quantity` gate (cross-checks `staging.location_canonical` + `staging.scene_clock` against canon-bible).
- Critic axis: `treatment_fidelity` partially covers (sensory dominance match); the staging's structural correctness is checked by `content_ownership`. No new axis needed.

---

## 7. Failure-Mode Mapping (D-13..D-19, manuscript canaries)

This table is the canonical "every observed bug → which atomic was violated" mapping. Plan tasks check this table.

| Bug evidence | Atomic violated | Craft principle | Schema field that prevents | Pre-flight gate | Critic axis | Source citation |
|---|---|---|---|---|---|---|
| Andrés age 26→23→23 (D-15) | Drive context (book-grain Truby ghost) AND staging quantity | Verisimilitude / continuity | CB-01 canonical_quantity injected verbatim | `quantity` | `named_quantity_drift` | Truby (ghost), Aristotle Poetics (verisimilitude) |
| La Niña height 50→60→55→42 ft | Staging quantity | Continuity | CB-01 canonical_quantity | `quantity` | `named_quantity_drift` | (same as above) |
| Santiago del Paso 210/300 ft / 11 stories | Staging quantity | Continuity | CB-01 canonical_quantity | `quantity` | `named_quantity_drift` | (same) |
| Cholula stub Oct 30 vs canon Oct 18 | Staging clock + canon-bible | Verisimilitude | `staging.scene_clock` + CB-01 | `quantity` | `named_quantity_drift` | (same) |
| Cempoala double-arrival (ch03 sc02 + ch04 sc02) | Beat ownership + staging clock | Swain scene/sequel — second scene skipped its sequel | `do_not_renarrate` + `staging.relative_clock` | `ownership` | `content_ownership` | Swain 1965 |
| Itzcoatl 1st (ch01) → 3rd (ch06+) | Focalization | Genette internal-fixed breach | `pov_lock` per-character | `pov_lock` | `pov_fidelity` | Genette 1972 |
| Andrés POV recycled Itzcoatl interior (ch09 sc01, all 4 attempts) | Focalization | Genette internal-fixed breach (perceptual access) | `perspective` (per-scene) | `pov_lock` | `pov_fidelity` | Genette 1972 |
| Sc01 content as sc02 (drafter overlap) | Beat ownership | Swain scene/sequel + Save-the-Cat beat-uniqueness | `owns` + `do_not_renarrate` + scene-buffer dedup (D-14) | `ownership` | `content_ownership` + `scene_buffer_similarity` | Swain 1965, Snyder 2005 |
| Stub-leak "Establish: ..." (ch11 sc03) | Booth distance / meta-textual breach | Booth: showing-vs-telling — directive ≠ rendered prose | beat-function as fenced directive (D-23 anchor) | (drafter prompt change) | `stub_leak` (regex) | Booth 1961 |
| Degenerate loop "He did not sleep..." (ch10 sc02) | Voice/diction breakdown (not a single craft principle — it's craft failure to recognize the loop and stop) | Repetition violates virtually every diction tradition (Le Guin sentence rhythm, Stein density, McKee turn) | n/a — runtime safety check | (post-draft, before commit) | `repetition_loop` | Le Guin 2015, Stein 1995 |
| Manual_concat duplication | Beat ownership + sequel skipped | Swain — sequel is the architectural glue between scenes | `sequel_to_prior` field + scene-buffer dedup | `ownership` | `content_ownership` + `scene_buffer_similarity` | Swain 1965 |

**Two patterns surface from this mapping:**

1. **Continuity violations cluster on staging + CB-01.** Five of eleven canaries are quantity drift. The CB-01 retriever + `named_quantity_drift` axis is the highest-leverage gate in the engine.
2. **Drafter-prompt fixes complement gates.** D-23's verbatim-canonical-stamp + D-13's ownership-anchor-at-prompt-head are NOT redundant with gates — they prevent the gates from firing in the first place by giving the drafter the right anchors. Gates catch what slips past anchors.

---

## 8. The Engine's 13-Axis Critic Rubric (D-26 contract)

Synthesis of §1-7. Each axis has: **what it checks**, **how it scores**, **failure-action**.

| # | Axis | Origin | Checks | Severity model | On FAIL |
|---|---|---|---|---|---|
| 1 | `historical` | existing CRIT-01 | corpus historical-bible alignment | low/mid/high | regen |
| 2 | `metaphysics` | existing | engineering rules (engines, fuel) | low/mid/high | regen |
| 3 | `entity` | existing | entity-state continuity | low/mid/high | regen |
| 4 | `arc` | existing | beat-position vs outline | low/mid/high | regen |
| 5 | `donts` | existing | known-liberties / negative-constraint | low/mid/high | regen |
| 6 | `pov_fidelity` | NEW (§1) | perspective produced == declared | low/mid/high | regen if low/mid; scene-kick if high |
| 7 | `motivation_fidelity` | NEW (§2) | each on_screen char's motivation served | **HARD-STOP** (any FAIL = overall_pass=False) | regen |
| 8 | `treatment_fidelity` | NEW (§4) | tonal register matches enum value | low/mid/high | regen |
| 9 | `content_ownership` | NEW (§5) | scene N didn't recap scene M's owned beats | low/mid/high | scene-kick if high (drafter overlap pattern) |
| 10 | `named_quantity_drift` | NEW (§7 staging+CB-01) | values produced == CB-01 canonical | mid/high (no low — quantities are exact) | regen if mid (single drift); scene-kick if high (>1 quantity drifted) |
| 11 | `stub_leak` | NEW (§5.4) | regex pattern check | HARD (binary, no severity gradient) | scene-kick + re-stub |
| 12 | `repetition_loop` | NEW (§7) | n-gram repetition + sentence self-similarity | HARD on detection | scene-kick + re-stub |
| 13 | `scene_buffer_similarity` | NEW (D-14, D-28) | BGE-M3 cosine ≥0.80 vs prior committed scenes | HARD on detection | scene-kick + re-stub |

**Implementation note for the critic prompt:** axes 1-5 stay as-is in `templates/system.j2`; axes 6-13 are appended as a "Phase 7 atomics" block. The few-shot YAML grows accordingly. Token cost growth is the load-bearing economic question — see 07-RESEARCH.md §4 for cost analysis and the "split critic call" tradeoff.

---

## 9. Acceptance: What's Enforceable, What Isn't (in v1)

**Enforceable in v1 (all gates / axes implemented):**
- §1 Focalization (perspective + pov_lock)
- §2 Drive (motivation, hard-stop semantics)
- §3 Action shape (contents structural completeness)
- §4 Treatment (closed enum)
- §5 Beat ownership (owns + do_not_renarrate + stub_leak regex)
- §6 Theater staging (staging block + CB-01)
- §7 All 11 manuscript canaries

**Deferred to v1.1 (intentional scope clip):**
- §4 `value_turn` axis (no-turn detection — McKee polarity). Schema field `value_charge` ships in v1; axis-level enforcement of "every scene must turn" is too high-FP for v1's craft-rule maturity.
- §1 Bal focalizer/focalized split. Genette three-way is enough for the manuscript at hand.
- §4 `treatment_secondary` blends. Closed enum first; blends after operator validation.
- §2 Truby ghost/desire/opponent at scene grain. Stanislavskian per-scene objective covers v1; the book-grain Truby data lives in entity-state cards.

**Out of scope (D-21 forward-only):**
- Retrofitting ch01-14. Engine validates ch01-04 read-only as smoke test (zero-FP target), produces no commits.
- Re-DAG of ch05-14 — opportunistic, not gated.

---

# TIER 2 — Deep References Appendix

## A.1 Genette + Bal — Fuller Treatment

Gérard Genette's *Discours du récit* (1972, English: *Narrative Discourse*, 1980) is narratology's most-cited single work [CITED: 15orient.com/files/genette-on-narrative-discourse.pdf]. Three contributions matter for our engine:

**A.1.1 The voice/mood split.** Pre-Genette, "point of view" conflated *who speaks* (voice — "qui parle?") with *who sees* (mood — "qui voit?"). Genette splits these. A first-person narrator can focalize on a younger version of self; the voice is older-self (current narrator), the focalizer is younger-self (the "I" inside the action). Most traditional novels collapse these; sophisticated novels exploit the split.

For our engine, this matters because *the voice-FT model has its own voice* (Paul's) but the focalizer is the scene's POV character. The drafter must keep voice consistent (Paul-faithful prose) while focalizer rotates per scene. Genette gives us the vocabulary to express this requirement to the critic.

**A.1.2 The three focalization types in detail.**

- **Zero focalization** is what classical 19th-century novels do (Tolstoy, George Eliot, Trollope). The narrator KNOWS more than any character. Free indirect discourse can render any character's interior. Authorial commentary is licensed.
- **Internal focalization** is Henry James's invention as a deliberate program (*The Ambassadors*, 1903). Restricted to one character's perception. Genette's three subtypes:
  - *Fixed*: one character throughout the entire narrative. James's *The Ambassadors* via Strether.
  - *Variable*: shifts character per section. Flaubert's *Madame Bovary* alternates Charles and Emma.
  - *Multiple*: same event seen through different characters in succession. Faulkner's *As I Lay Dying*; the Nadia Comăneci sequence in *The Manchurian Candidate* (film).
- **External focalization** is camera-eye: only externally observable behavior. Hammett's *The Maltese Falcon*. Hemingway's "Hills Like White Elephants" (no character interior at all — meaning is in dialogue and refusal to render thought).

**A.1.3 Bal's correction.** Mieke Bal (*Narratology: Introduction to the Theory of Narrative*, 1985) argues Genette's "external focalization" is incoherent — externals are always *focalized BY someone* (often the narrator-as-camera). Bal substitutes a focalizer/focalized binary. For implementation, we keep Genette's externals because schema enums need finite types and Bal's argument doesn't change what the critic looks for.

## A.2 Swain Scene/Sequel — Fuller Treatment

Dwight V. Swain, *Techniques of the Selling Writer* (1965), offered the most engineering-flavored scene grammar in fiction craft [CITED: en.wikipedia.org/wiki/Scene_and_sequel].

**A.2.1 Scene mechanics:**
- **Goal:** specific, scene-bounded, conscious. NOT the book-spine want — the scene's local want. ("Get past the gate" not "earn redemption".)
- **Conflict:** opposition. Internal (focal char vs self) or external (vs another character, vs environment).
- **Disaster:** outcome that introduces a new problem. Pure goal-met-no-disaster scenes are story-killers because they release tension without recharging it. Even "goal met" outcomes need a complication (the kingdom is saved BUT the price is...).

**A.2.2 Sequel mechanics:**
- **Reaction:** emotional response to the disaster. Visceral, somatic, often interior.
- **Dilemma:** forced choice. The disaster's new problem doesn't resolve itself — it presents alternatives, all bad.
- **Decision:** commitment. Becomes the next scene's Goal.

**A.2.3 Sequels can be tiny or huge.** A whole chapter can be sequel; a half-page can be sequel within a scene. The engine doesn't enforce sequel grain — but the manual_concat duplication bug is exactly Swain's "scene followed by scene with no sequel between them" pathology. Hence schema field `sequel_to_prior` (§3.3): if the scene IS a sequel, render it; if it follows a scene that needs a sequel, declare what reaction-dilemma-decision lives in this scene's opening.

## A.3 McKee — Polarity & Scene-Bones Detail

Robert McKee, *Story* (1997), is the polarity-charge canonical reference [CITED: mckeestory.com/do-your-scenes-turn/; jenniferellis.ca/blog/2016/3/10/].

**A.3.1 The "turn" as scene-existence criterion.** McKee's claim: if the value-charged condition of the focal character's life is identical at scene-end vs scene-start, NOTHING HAPPENED. The scene has activity but no event. The scene should be cut.

This is harder to enforce than it sounds because:
- "no-turn" scenes do exist legitimately as transition pieces (especially in long-form fiction).
- The polarity may be sub-textual (visible only in retrospect once scene N+3 reveals scene N's significance).

Hence v1 schema captures `value_charge` but the `value_turn` critic axis is v1.1 deferred — too high false-positive for v1.

**A.3.2 Scene-bones (mini-arc structure).** McKee's scene contains: inciting incident → progressive complication → crisis decision → climax → resolution. This is structurally identical to Swain's goal-conflict-disaster but slices time finer (insertion of "crisis decision" between conflict and disaster — the moment where the focal character chooses how to act under pressure).

The engine's `contents.outcome` field absorbs both Swain's "disaster" and McKee's "climax + resolution" because rendering them separately is overengineering for the manuscript's actual needs.

## A.4 Treatment Vocabulary — Per-Treatment Rubric Detail

Full per-treatment criterion table (continuation of §4.3):

| Treatment | Diction signature | Sentence rhythm | Sensory dominance | Pace | Distance (Booth) | Worked example |
|---|---|---|---|---|---|---|
| DRAMATIC | active transitive verbs; concrete nouns; declarative present-tense possible | tightening syntactic units (long → short → short → snap) | sight + kinesthetic | accelerating | medium | climaxes generally |
| MOURNFUL | past-weighted; absence-words ("was no longer", "would never again"); few present-tense action verbs | long syntactic units; clausal subordination; comma-heavy | sound (silenced things), tactile (cold/damp) | slow, metronomic | high (narrator commentary often present) | post-loss interior |
| COMEDIC | unexpected diction collocations; understatement | timing-dependent: setup-pause-punch | sight (visual gag) or dialogue | varies by gag | low (close, conspiratorial) | sub-genre dependent |
| LIGHT | low-frequency abstractions; concrete nouns; positive valence | buoyant; no subordination tax | sight + sound (incidental, pleasant) | medium | low | scene transitions, breathers |
| PROPULSIVE | concrete nouns; active transitive verbs; minimal abstraction | short coordinated clauses; absent subordinators | kinetic (motion, pursuit) | fast | low | chase, flight, action |
| CONTEMPLATIVE | abstract nouns; cognitive verbs (knew, thought, considered, realized) | long; embedded clauses; metacognitive asides | interior; neutral exterior | slow | varies | reflection, sequel-grade interior |
| OMINOUS | foreshadowing words; conditional moods; passive voice for menace | rising tension without release | sound (small, off) + smell | slow build | medium | pre-disaster scenes |
| LITURGICAL | repetition; archaisms allowed; named-thing-as-sacred; epic register | parallelism; parataxis | sound (chant), smell (incense) | metronomic | high | ritual, ceremony |
| REPORTORIAL | neutral diction; no commentary | medium clauses; no subordination flourish | sight only | medium | high (Genette external) | chronicle, news-style |
| INTIMATE | sensory-close; second-person-feel even in 3rd | medium; thought-fragments interleaved | tactile + interior | slow | very low | romantic, post-trauma |

The drafter's prompt header includes the row for the declared treatment value: *"This scene is MOURNFUL: past-weighted diction; long syntactic units; sound and tactile dominance; slow pace; medium-high distance."* Critic checks compliance.

## A.5 Booth — Distance & Showing-Telling

Wayne Booth, *The Rhetoric of Fiction* (1961, 2nd ed. 1983) [CITED: en.wikipedia.org/wiki/Wayne_C._Booth; press.uchicago.edu/ucp/books/book/chicago/R/bo5965941.html].

**A.5.1 Showing vs telling — Booth's actual position.** Despite Booth's coining of the unreliable narrator, his showing-vs-telling treatment is *anti-dogmatic*. Booth argues that authors invariably both show and tell, and the "always show" prescription has produced its own pathologies. The engine reflects this: the `treatment_fidelity` axis does NOT enforce 100% showing. It enforces *appropriate proportion to declared treatment* — REPORTORIAL is more telling-tolerant than DRAMATIC.

**A.5.2 Distance.** Booth's "distance" is the gap between implied author/narrator and characters. High distance = narrator commentary is licensed, reader sees characters from outside; low distance = narrator dissolves into character interior. Distance is encoded implicitly in our `perspective` enum (3rd_external = high, 3rd_close = low) and explicitly in our treatment table column (A.4 above).

**A.5.3 Reliable/unreliable narrator.** In *Our Lady of Champion*, no current narrator is unreliable in Booth's sense (the implied author and narrator share norms). v1 doesn't add an `unreliable_narrator` field; if a future scene wants this, the schema can extend (additive-only per Phase 1 freeze policy).

## A.6 Truby — Ghost/Desire/Opponent at Book Grain

John Truby, *The Anatomy of Story* (2007). Truby's 22-step structure expands Aristotle and McKee with a moral-argument spine. Key concepts:

- **Ghost:** the past wound that drives current desire. Andrés in *Our Lady of Champion*: the excommunication, the Cuban escape, what he is fleeing.
- **Desire:** the conscious goal the protagonist pursues for most of the book.
- **Need:** the unconscious moral requirement the protagonist must meet to truly resolve the ghost.
- **Opponent:** whose desire blocks the protagonist's. May be human or institutional (the Inquisition, the Mexica state, gravity).

These are **book-grain**, not scene-grain. They live in `entity-state/` cards for the protagonist and major opponents. The drafter sees them at scene-prep time via the entity_state retriever, not via per-scene metadata.

The 22 steps themselves (1. self-revelation/need/desire establishment; 2. ghost & story world; 3. weakness & need; 4. inciting event; 5. desire; 6. ally(ies); 7. opponent/mystery; 8. fake-ally opponent; 9. first revelation & decision; 10. plan; 11. opponent's plan & main counterattack; 12. drive; 13. attack by ally; 14. apparent defeat; 15. second revelation & decision; 16. audience revelation; 17. third revelation & decision; 18. gate, gauntlet, visit to death; 19. battle; 20. self-revelation; 21. moral decision; 22. new equilibrium) [CITED: decodingcreativity.com/trubys-22-steps] map to the *outline.md* arc, not to per-scene metadata. The arc_position retriever already covers this.

## A.7 Save the Cat — 15-Beat Sheet at Book Grain

Blake Snyder, *Save the Cat!* (2005), and the novelist adaptation Jessica Brody, *Save the Cat! Writes a Novel* (2018) [CITED: savethecat.com/beat-sheets; reedsy.com/blog/guide/story-structure/save-the-cat-beat-sheet/].

The 15 beats: Opening Image, Theme Stated, Setup, Catalyst, Debate, Break Into Two, B Story, Fun and Games, Midpoint, Bad Guys Close In, All Is Lost, Dark Night of the Soul, Break Into Three, Finale, Final Image. Each hits at one location (one scene or short scene-cluster). Re-narration of a beat = beat smear.

Save-the-Cat beats are **book-grain**, like Truby's 22 steps. They live in `outline.md` and the arc_position retriever. The engine's `owns` field at scene grain references these beats for the scene that contains them (`owns: ["midpoint_falsefriend_revealed"]`).

## A.8 Sanderson — Promise/Progress/Payoff

Brandon Sanderson, "Plot Theory" lectures (BYU 2025) [CITED: faq.brandonsanderson.com/knowledge-base/what-are-sandersons-laws-of-magic/; standardstoryco.com/a-simple-storytelling-formula-promise-progress-payoff].

**Sanderson's Three Laws of Magic** apply to the *Our Lady of Champion* metaphysics (which is a magic system in McKee's sense):
1. Author's ability to solve conflict with magic = directly proportional to reader understanding of it. → *engineering.md is canonical; metaphysics retriever surfaces rules verbatim.*
2. Limitations > Powers. → *the engines' costs (bone-dust feed, pilot mortality, ritual constraints) are more interesting than their capabilities.*
3. Expand what you have before adding new. → *new metaphysics in late chapters needs to be foreshadowed early.*

**Promise/Progress/Payoff** maps onto book structure:
- Promise = setup chapters (1-9 in our outline)
- Progress = development chapters (10-22)
- Payoff = resolution chapters (23-27)

The engine's `value_charge` field (§4) and `arc_position` retriever together encode this — an engine that's been promised in ch01 (the hum) must progress through middle chapters and pay off late.

## A.9 Stein — Show-Don't-Tell as Density Metric

Sol Stein, *Stein on Writing* (1995) [CITED: laurellecommunications.blog/2023/08/07; livewritethrive.com/2013/01/09/show-dont-tell-but-how/]. Two contributions:

**A.9.1 Show, don't tell, BUT operationalized.** Stein explicitly avoids the dogma trap (matches Booth A.5.1). Stein's rule: characterization and emotion must be *shown through action and physical detail, not stated*. Description is fine; abstract emotional summary is not.

**A.9.2 Five-sense rule.** Stein's chapter 17 lists touch, smell, vision, hearing, taste — plus intuition as a sixth. Stein's prescription: a memorable scene foregrounds **a few senses, very precisely**, not all of them. (Verma's radio-drama craft says exactly the same thing — anchor with 2-3 sensory details, not exhaustive description.)

The engine's `staging.sensory_dominance: list[Literal[...]]` capped at 2 entries enforces Stein's density rule in schema.

## A.10 Le Guin — Steering the Craft

Ursula K. Le Guin, *Steering the Craft: A Twenty-First-Century Guide to Sailing the Sea of Story* (2015 revision; original 1998) [CITED: ursulakleguin.com/steering-the-craft]. Ch. 7 ("Point of View and Voice") is the load-bearing reference for our `perspective` enum's 3rd_close vs 3rd_limited distinction.

Le Guin teaches POV via exercises that ask the writer to render the same scene through (1) involved-author, (2) detached-author, (3) observer-narrator using "I", (4) observer-narrator using "she", (5) participant-narrator using "I", (6) limited 3rd, (7) close 3rd. The 3rd_close vs 3rd_limited split is exactly Le Guin's #6 vs #7.

Le Guin also emphasizes **sentence rhythm** as voice-load-bearing — Virginia Woolf "didn't deal in words, but in rhythm". Our `treatment` per-treatment rubric (A.4) encodes rhythm explicitly per treatment value.

## A.11 Aristotle — Six Elements & Mythos

Aristotle, *Poetics* (4th c. BCE) [CITED: en.wikipedia.org/wiki/Poetics_(Aristotle); mason.gmu.edu/~rnanian/Aristotle-poeticsexcerpt.pdf]. The six elements of tragedy:

1. **Mythos** (plot) — "soul of tragedy"; arrangement of incidents into a unified whole.
2. **Ethos** (character) — moral qualities revealed by choices.
3. **Dianoia** (thought) — what characters say to argue, persuade, express.
4. **Lexis** (diction) — language style.
5. **Melos** (song/melody) — chorus's musical element.
6. **Opsis** (spectacle) — visual/staging.

Mapping to our schema:
- Mythos → `contents` (goal/conflict/outcome) + `owns` (beats)
- Ethos → `characters_present[].motivation` (motivation reveals ethos)
- Dianoia → not a schema field; emerges from prose (critic's `arc` axis touches it)
- Lexis → `treatment` enum + diction rubric
- Melos → not applicable (we are not staging music)
- Opsis → `staging` block

Aristotle's verisimilitude requirement ("the probable impossible is preferable to the improbable possible") is our `named_quantity_drift` axis at its philosophical root.

## A.12 Theater of the Mind — Verma & Radio Drama

Neil Verma, *Theater of the Mind: Imagination, Aesthetics, and American Radio Drama* (Chicago, 2012) [CITED: press.uchicago.edu/ucp/books/book/chicago/T/bo13040503.html; chicago.universitypressscholarship.com/view/10.7208/chicago/9780226853529.001.0001/upso-9780226853505-chapter-1].

Verma's analysis of 6,000+ radio dramas (Depression to Cold War) extracts staging primitives that translate directly to prose theater-of-the-mind:

- **Anchor with 2-3 precise sensory details, not exhaustive description.** (Stein density rule, A.9.)
- **Active verbs + concrete nouns provoke clear imagery.** (Stein, Strunk-White.)
- **Pacing and silence: well-timed pauses let listeners complete images.** (Schema's `staging.scene_clock` + `relative_clock` encode pacing positions.)
- **Layer sound and dialogue to suggest off-stage action.** (Schema's `staging.off_screen_referenced`.)
- **Trust the audience: imply rather than enumerate.** (Stein, Hemingway iceberg.)

This is the doctrine the operator's "theater of the mind" frame imports. The engine's staging schema is its faithful Pydantic transcription.

---

## Bibliography

**Primary craft sources:**
- Aristotle, *Poetics* (4th c. BCE). [Selected passages: mason.gmu.edu/~rnanian/Aristotle-poeticsexcerpt.pdf](https://mason.gmu.edu/~rnanian/Aristotle-poeticsexcerpt.pdf)
- Bal, Mieke. *Narratology: Introduction to the Theory of Narrative*. University of Toronto Press, 1985.
- Booth, Wayne C. *The Rhetoric of Fiction*. University of Chicago Press, 1961 (2nd ed. 1983). [press.uchicago.edu/ucp/books/book/chicago/R/bo5965941.html](https://press.uchicago.edu/ucp/books/book/chicago/R/bo5965941.html)
- Brody, Jessica. *Save the Cat! Writes a Novel*. Ten Speed Press, 2018. [savethecat.com/beat-sheets](https://savethecat.com/beat-sheets)
- Genette, Gérard. *Narrative Discourse: An Essay in Method*. Cornell University Press, 1980 (French 1972). [15orient.com/files/genette-on-narrative-discourse.pdf](https://15orient.com/files/genette-on-narrative-discourse.pdf)
- Le Guin, Ursula K. *Steering the Craft: A Twenty-First-Century Guide to Sailing the Sea of Story*. Houghton Mifflin Harcourt, 2015. [ursulakleguin.com/steering-the-craft](https://www.ursulakleguin.com/steering-the-craft)
- McKee, Robert. *Story: Substance, Structure, Style and the Principles of Screenwriting*. ReganBooks, 1997. [mckeestory.com/do-your-scenes-turn/](https://mckeestory.com/do-your-scenes-turn/)
- Sanderson, Brandon. "Sanderson's Laws of Magic" + "Plot Theory" lectures. [faq.brandonsanderson.com/knowledge-base/what-are-sandersons-laws-of-magic/](https://faq.brandonsanderson.com/knowledge-base/what-are-sandersons-laws-of-magic/) ; [standardstoryco.com/a-simple-storytelling-formula-promise-progress-payoff](https://standardstoryco.com/a-simple-storytelling-formula-promise-progress-payoff/)
- Snyder, Blake. *Save the Cat! The Last Book on Screenwriting You'll Ever Need*. Michael Wiese Productions, 2005.
- Stein, Sol. *Stein on Writing*. St. Martin's Griffin, 1995. [laurellecommunications.blog/2023/08/07/stein-on-writing-a-masterful-book-for-fiction-writers](https://laurellecommunications.blog/2023/08/07/stein-on-writing-a-masterful-book-for-fiction-writers/)
- Swain, Dwight V. *Techniques of the Selling Writer*. University of Oklahoma Press, 1965. [Wikipedia: Scene and Sequel](https://en.wikipedia.org/wiki/Scene_and_sequel) ; [septembercfawkes.com/2021/09/scene-structure-according-to-dwight-v.html](https://www.septembercfawkes.com/2021/09/scene-structure-according-to-dwight-v.html) ; [septembercfawkes.com/2021/10/sequel-structure-according-to-swain.html](https://www.septembercfawkes.com/2021/10/sequel-structure-according-to-swain.html)
- Truby, John. *The Anatomy of Story: 22 Steps to Becoming a Master Storyteller*. Faber & Faber, 2007. [truby.com/the-anatomy-of-story](https://truby.com/the-anatomy-of-story/) ; [decodingcreativity.com/trubys-22-steps](https://www.decodingcreativity.com/trubys-22-steps/)
- Verma, Neil. *Theater of the Mind: Imagination, Aesthetics, and American Radio Drama*. University of Chicago Press, 2012. [press.uchicago.edu/ucp/books/book/chicago/T/bo13040503.html](https://press.uchicago.edu/ucp/books/book/chicago/T/bo13040503.html)

**Secondary / verification sources:**
- Wikipedia: [Focalisation](https://en.wikipedia.org/wiki/Focalisation) ; [Wayne C. Booth](https://en.wikipedia.org/wiki/Wayne_C._Booth) ; [Unreliable narrator](https://en.wikipedia.org/wiki/Unreliable_narrator) ; [Poetics (Aristotle)](https://en.wikipedia.org/wiki/Poetics_(Aristotle))
- [Living Handbook of Narratology — Focalization](https://www-archiv.fdm.uni-hamburg.de/lhn/node/18.html)
- [Estetika: Internal Focalization and Seeing through a Character's Eyes](https://estetikajournal.org/articles/10.33134/eeja.364)
- [SoCreate — Positive and Negative Charges Structure Great Scenes](https://www.socreate.it/en/blogs/screenwriting/how-to-use-positive-and-negative-charges-to-structure-great-scenes)
- [September C. Fawkes — Scene Structure According to Swain](https://www.septembercfawkes.com/2021/09/scene-structure-according-to-dwight-v.html)
- [Reedsy — Save the Cat Beat Sheet Ultimate Guide](https://reedsy.com/blog/guide/story-structure/save-the-cat-beat-sheet/)
- [Helping Writers Become Authors — Scene Structure](https://www.helpingwritersbecomeauthors.com/scene-structure/)
- [PBS — Theater of the Mind Radio Drama](https://www.pbs.org/show/theater-mind-radio-drama/)

---

*Phase 7 Narrative Physics — synthesized 2026-04-25 from craft canon for the* Our Lady of Champion *book pipeline. Engine implements Tier 1; Tier 2 supplies the canon Tier 1 was distilled from.*
