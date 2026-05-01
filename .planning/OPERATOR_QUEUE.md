# Operator queue — actions only the operator can take

Items the autonomous agent has staged but cannot execute. Each entry has:
- **Why agent can't do it**
- **What's blocked downstream**
- **Estimated time**
- **Steps**

Last updated: 2026-04-30T23:11Z (after V7D overnight session).

---

## 1. Deploy the Cloudflare Worker for anonymous reader feedback

**Why agent can't:** Wrangler not installed; no Cloudflare account credentials on the machine; `wrangler login` requires interactive browser OAuth.

**Blocks:** Anonymous reader feedback. Until deploy, the JS form on every chapter page falls back to a `mailto:pauljflogan+ourlady@gmail.com` draft.

**Time:** ~5 min.

**Steps:**
```sh
cd worker
npm install -g wrangler
wrangler login                                 # browser OAuth
wrangler secret put GITHUB_PAT                 # paste fine-grained PAT
                                                # repo: loganclaw9000/our-lady-book-pipeline
                                                # perms: Issues read+write only
wrangler deploy
```
Then paste the `*.workers.dev` URL into `docs/_config.yml :: feedback_worker_url` and `git push`. No chapter file edits — Jekyll picks up the URL from `_config.yml`.

**Verify:**
```sh
curl -X POST https://<worker-url> \
  -H 'Content-Type: application/json' \
  -d '{"chapter":"smoke","kind":"other","body":"deploy verify"}'
# expect: {"ok":true,"issue_number":N,"url":"..."}
```

---

## 2. Relax / re-tune chapter critic for ch16, ch25

**Why agent can't:** Architectural decision. Both chapters now have all 3 scenes drafted+committed individually but `chapter_critic` flags coherence issues that scene-kick can't resolve in 3 cycles. Returning `CHAPTER_FAIL_SCENE_KICKED`. The threshold or rubric for chapter-level coherence is operator-tier judgment.

**Forge insight (2026-05-01T08:55Z):** "chapter-critic too aggressive on V7D" is a **calibration mismatch**, not a model regression — V7D's rewrite_para retraining produces longer / denser paragraphs which the existing chapter-critic thresholds (calibrated for V7C density) flag as coherence drift. Forge's thinkpiece batch v1 (25k words, 100% qpass, voice fidelity 4.72/5) corroborates V7D quality. **Calibration adjustment, not retrain.**

**Blocks:** ch16 + ch25 canon shipping. 24 of 27 chapters canon, gap is here.

**Time:** ~30 min once decided.

**Options:**
- (a) Lower the chapter-critic pass threshold (loosens overall;)
- (b) Raise scene-kick max cycles 3 → 5 (more wall time, may converge)
- (c) Manual: `scripts/ship_chapter.sh 16 && scripts/ship_chapter.sh 25` (skips chapter critic, uses concat-and-ship from V7C ramp era)
- (d) Investigate what specifically chapter-critic flags — `runs/critic_audit/ch16_chapter_*.json`

**Recommended:** (d) first — read the audit, then pick (a) or (b). Per forge insight, the FAILs are likely "paragraph-density too high" or "scene-spanning rhythm shift" axes that need their thresholds nudged for V7D's longer-paragraph baseline.

---

## 3. Backfill ch27 RAG arc_position

**Why agent can't:** Corpus edit — needs operator decision on what ch27 *should* establish in the lore. The `arc_position` retriever returns 0 hits for ch27, which hard-blocks the drafter.

**Blocks:** ch27 canon. Last chapter of the book.

**Time:** ~15 min if outline is in head.

**Steps:**
1. Add ch27 beat outline to `our-lady-of-champion/arc_outline.md` (or wherever arc_position chunks live).
2. `uv run python -m book_pipeline ingest` to re-bind LanceDB. Should report ch27 chunk added.
3. Re-kick: `uv run python -m book_pipeline draft ch27_sc01 --max-regen 3`.

---

## 4. (Cosmetic) Run `npx gitnexus analyze` once

**Why agent can't:** Heavy operation; defers to operator session to avoid mid-overnight resource contention. Repeated PostToolUse hook reminders.

**Blocks:** GitNexus knowledge graph stale → no impact on pipeline output, only on Claude's code-search tool quality in future sessions.

**Time:** ~3-5 min.

**Step:**
```sh
npx gitnexus analyze
```

---

## 5. (Optional) Review V7D rewrite_para output quality

**Why agent can't:** Subjective judgment on prose quality. forge's eval shipped V7D on rewrite_para 49% → 88% qpass + retained continuation/adversarial. New chapters ch18/20/21/23 are V7D output; eyes-on read confirms voice match.

**Blocks:** Nothing — V7D is the new pin and shipped scenes pass critic. This is a sanity check before scaling further generation.

**Time:** ~15 min (read 1-2 V7D scenes vs the V7C-era equivalent).

**Steps:**
- Open `canon/chapter_18.md` (V7D) vs `canon/chapter_15.md` (V7C-mixed).
- Listen for voice continuity. If V7D drifts, signal forge for V7D2 with adjusted training data.
