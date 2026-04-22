# Session Log — 2026-04-21

**Project:** our-lady-book-pipeline (new, just scaffolded)
**Sibling context:** paul-thinkpiece-pipeline (ongoing voice FT), our-lady-of-champion (corpus)
**Session type:** greenfield architecture exploration + scaffold

## What happened

Paul rsync'd the `our-lady-of-champion/` lore corpus to this machine from another host. Opened `/gsd-do` asking to scope a full book-writing pipeline — first full pipeline of a planned family (blog, thinkpiece, short-story, ...) — with factual-consistency RAG and architectural-diagram-first delivery.

Routed via `/gsd-explore` (Socratic ideation) after confirming three blockers:

1. **Route:** `/gsd-explore` over `/gsd-new-project` because Paul wanted opinionated shape before committing scope.
2. **openclaw clarification:** Paul already runs openclaw locally (npm-installed, systemd gateway, used in `wipe-haus-state/` with 8 personas). Free tokens, cron-capable. Claude Code subagents are better for quality-critical reasoning but cost tokens. Hybrid decision: openclaw as orchestrator + bulk drafter, CC / Anthropic API as critic + retrospective writer.
3. **Location:** new sibling `~/Source/our-lady-book-pipeline/` (keep OLC corpus read-only).

## Architecture decisions made

Four ADRs locked:

1. **ADR-001 — Mode dial over promotion ladder.** Paul rejected my initial capability-promotion-ladder proposal because no non-frontier model 1-shots >1000w cleanly. Replaced with Mode A (voice-FT local, scene-level, default) + Mode B (frontier, opt-in for complex beats, tracked in digest).
2. **ADR-002 — Scene-gen + chapter-commit.** Scenes (~1000w) are the drafting unit, chapters (~3000w, matching outline grain) are the canon unit. 27 chapters = 27 commits.
3. **ADR-003 — Testbed framing.** Pipeline is over-instrumented deliberately. Structured event log, per-axis critic scores, retrospective writer per chapter, thesis registry. Paul explicitly said learnings must translate back to FT and sibling pipelines.
4. **ADR-004 — Book-first, extract kernel on pipeline #2.** Don't abstract until we've written it twice. Clean internal boundaries in the book repo; kernel extraction waits for blog pipeline or similar.

## Diagrams produced (in `docs/ARCHITECTURE.md`)

1. System context — who talks to what (user, voice model source, corpus, frontier, canon).
2. Core drafting loop — scene request → RAG → Mode A drafter → critic → (pass=commit / fail=regen / exhaust=Mode B / still-fail=hard-block) → chapter assembly → chapter critic → commit.
3. Typed RAG topology — 5 parallel retrievers (historical, metaphysics, entity-state, arc-position, negative-constraint), each with its own index, bundled into context pack.
4. Mode dial — Mode A / Mode B trade description and pre-flagged Mode-B beats (Cholula stirring, two-thirds reveal, siege climax).
5. Runtime layout — openclaw workspace on the DGX Spark, consumes voice checkpoint from paul-thinkpiece-pipeline, calls Anthropic API for critic, writes to `canon/` / `drafts/` / `indexes/` / etc.

## Seeded open theses

Five theses now in `theses/open/`, all with test design + success metric:

- **001** — Thinkpiece voice FT transfers to fiction.
- **002** — Mode-B escape rate stabilizes below 30% across Act 1.
- **003** — Entity-state auto-extraction catches continuity errors.
- **004** — 5-axis critic rubric outperforms monolith for regen targeting.
- **005** — RAG context relevance degrades past ~30-40KB.

These are the pipeline's first hypotheses. Resolved theses produce transferable artifacts to future pipelines and to FT corpus decisions.

## Artifacts produced this session

- `~/Source/our-lady-book-pipeline/` — new repo (git init, main branch, empty git tree so far; no commits yet).
- `docs/ARCHITECTURE.md` — full architecture with 5 diagrams.
- `docs/ADRs/{001..004}-*.md` — four decisions.
- `theses/README.md` + `theses/open/{001..005}-*.md` — thesis registry primed.
- `README.md` — project 1-pager.
- `SESSION_LOG_2026_04_21.md` — this file.

## What was NOT done

- No code. No `kernel/` or `rag/` or `drafter/` Python packages yet.
- No `PROJECT.md`, no roadmap, no phase plans. That's the next step via `/gsd-new-project` in the new repo.
- No pipeline runs. No ingestion of the OLC corpus.
- No venv / dependency management decisions yet. (Python is safe bet given paul-thinkpiece-pipeline.)
- No initial commit. Leaving that for after `/gsd-new-project` produces its first planning artifacts, so the initial commit captures the whole scaffold + planning in one shot.

## Next step

Hand off to `/gsd-new-project` in `~/Source/our-lady-book-pipeline/`. That command will:

- Deep-context gather (it should read the ADRs and ARCHITECTURE.md as primary inputs, rather than re-interviewing Paul from scratch).
- Produce `PROJECT.md` with scope, success criteria, non-goals.
- Generate `ROADMAP.md` with phases — phase 1 likely "repo skeleton + Python packaging + corpus ingestion", phase 2 "first RAG retriever end-to-end on a stub scene", etc.
- Set up `.planning/` workspace.

## Signals to watch in the first production run

- **Voice fidelity on Mode-A scenes.** If <0.7 embedding cosine vs reference, thesis 001 is headed to refuted and we need a book-voice FT branch.
- **Mode-B escape rate.** >30% on non-pre-flagged scenes signals the voice model isn't carrying its weight.
- **Critic false-positive rate.** >10% on clean scenes means rubric axes are mis-calibrated.
- **Regen loop termination.** Stuck regens = rubric conflict or ambiguous issue phrasing.

## References

- paul-thinkpiece-pipeline memory: voice-FT infra, v6 checkpoint active, cu130 + packing breakthrough in place.
- openclaw: `/home/admin/.npm-global/lib/node_modules/openclaw/`, systemd gateway at `openclaw-gateway.service`.
- Corpus: `/home/admin/Source/our-lady-of-champion/` — 10 .md files, ~250KB total, rsync'd ~2h before this session started.
