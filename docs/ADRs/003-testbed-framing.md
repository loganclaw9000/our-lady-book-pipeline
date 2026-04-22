# ADR-003: Pipeline is a testbed, instrument accordingly

**Status:** accepted
**Date:** 2026-04-21

## Context

This is pipeline #1 of a planned family (blog, thinkpiece, short-story, possibly others). A one-shot book pipeline would cut corners on observability and experiment tracking; a testbed cannot.

## Decision

Treat the book pipeline as a deliberate experiment platform. Accept 2-3× the engineering cost of a one-shot pipeline in exchange for:

1. **Structured event log.** Every LLM call (drafter, critic, regenerator, entity extractor, retrospective writer) emits a JSONL event with: timestamp, role, model, prompt hash, token counts, latency, temperature, top_p, caller context, output hash. `runs/events.jsonl`.
2. **Per-axis critic scoring persisted.** Not just pass/fail. The rubric has 5 axes (historical, metaphysics, entity, arc, don'ts); all 5 scores + issue lists + severities are persisted per run.
3. **Retrospective writer** runs after every chapter commit. Opus reads the chapter + the run events that produced it + prior retrospectives and writes a markdown note: what worked, what didn't, what's the pattern. `retrospectives/chapter_NN.md`.
4. **Thesis registry.** Open questions about the pipeline itself are captured as theses with hypothesis + test design + success metric. Retrospectives feed candidate theses; ablation runs close them. `theses/open/` and `theses/closed/`.
5. **Ablation harness.** Every config variable that matters (temperature, top_p, RAG retriever weights, prompt variants, rubric axis weights) can be ablated via a harness that runs N scenes under variant A vs variant B on held-fixed corpus state. Outputs to `runs/ablations/`.

## Transferable artifacts to other pipelines

When a thesis closes, it produces a transferable artifact:

- **Config recommendation** ("voice-FT temp=0.7 optimal for narrative prose; adopt in next FT run")
- **Architectural lesson** ("monolith RAG underperforms 5-typed RAG for consistency checks")
- **Known failure mode** ("voice-FT model cannot stage apex-scale action; pre-flag for Mode B")
- **Corpus-curation implication** ("thinkpiece training corpus lacks dialogue examples; next FT iteration should include fiction-sample blend")

These become inputs to:
- `paul-thinkpiece-pipeline` (next FT run config)
- Pipeline #2 (blog) starts from lessons, not from zero
- Global writing-pipeline kernel (when extracted per ADR-004)

## Consequences

**Positive:**

- Every failure teaches something. Pipelines 2-N start from a much better baseline.
- FT training runs are informed by production evidence, not guesses.
- Claims about what works ("voice FT transfers to fiction") become defensible or refuted with evidence.

**Negative:**

- Engineering cost is higher. Observability plane is non-optional, not a v2 polish item.
- Disk use grows: every prompt + output hashed and kept, retrospectives accumulate.
- Discipline required to keep thesis registry fresh — it's easy for open theses to rot if nobody periodically reviews them.

## Hygiene

- Weekly digest auto-surfaces theses that have been open >30 days with no evidence accrued (candidates for pruning or rewriting).
- Ablation harness only runs when tagged in run metadata — no silent experiments polluting production traces.
- Event log rotates monthly into compressed archive; metric ledger carries summary statistics forward.

## Related

- ADR-004 (book-first, extract kernel on pipeline #2)
- `theses/README.md` (thesis registry format)
- `docs/ARCHITECTURE.md` "Testbed framing" section
