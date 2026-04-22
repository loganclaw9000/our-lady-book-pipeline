# ADR-004: Build book pipeline first, extract kernel when pipeline #2 arrives

**Status:** accepted
**Date:** 2026-04-21

## Context

Plan is to build multiple writing pipelines (book, blog, thinkpiece, short-story). They will share structure: drafter → critic → regenerator → escape-hatch → observability. Tempting to build a generic `writing-pipeline-kernel` first and make the book a thin config-driven instance.

## Decision

**Don't.** Build the book pipeline as a single cohesive repo with clean internal boundaries. When pipeline #2 (blog) begins, extract the shared kernel then — with the benefit of two real callers.

## Rationale

- **Premature abstraction tax.** Abstractions built against one caller tend to encode that caller's assumptions as "universal" and break when a second caller disagrees. Book-specific assumptions (chapter-commit grain, 5-axis rubric, beat-function-driven retrieval) may not survive contact with blog generation (no chapters, different rubric axes, maybe no outline).
- **Rule of two.** Don't abstract until you've written it twice. We've written it zero times.
- **Clean internal boundaries are enough for v1.** The book pipeline will organize code into `drafter/`, `critic/`, `regenerator/`, `rag/`, `observability/` etc. When extraction happens, those modules move to the kernel repo with their public APIs intact.

## Signals that pipeline #2 is close enough to extract

Don't extract until:

1. Pipeline #2 requirements are written down.
2. At least one confirmed divergence from book pipeline assumptions (forces the abstraction to reckon with variance).
3. Book pipeline is running stably — extraction under active development of both is painful.

## Consequences

**Positive:**

- Book pipeline ships sooner.
- Abstractions get designed against real variance, not imagined variance.
- No versioning complexity between kernel and instance until there's a real reason for it.

**Negative:**

- Some duplication when pipeline #2 lands. Cost is paid once, at extraction time.
- Easy to let internal boundaries rot because "it's all in one repo anyway." Mitigated by reviewing module APIs at each phase boundary.

## Extraction plan (for future reference)

When conditions met:

1. Create `~/Source/writing-pipeline-kernel/` repo.
2. Move generic modules: `drafter/`, `critic/`, `regenerator/`, `rag/`, `observability/`, `orchestration/`.
3. Book pipeline becomes an instance: imports kernel, supplies `config/*.yaml`, keeps book-specific code in `book_ext/` if any.
4. Blog pipeline is built from day one as an instance.
5. Kernel gets its own semver'd releases from that point.

## Related

- ADR-003 (testbed framing — most of the investment here is observability, which extracts cleanly)
- `docs/ARCHITECTURE.md` "Proposed repo layout" section (shows both the current single-repo state and the target two-repo state)
