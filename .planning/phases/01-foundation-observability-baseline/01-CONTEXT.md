# Phase 1: Foundation + Observability Baseline - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

A runnable package skeleton with EventLogger live and voice-pin SHA verification wired, such that every subsequent LLM call automatically produces a structured event. No prose is drafted in this phase, but the observability plane that watches drafting is already operational.

**In scope (REQs):** FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, OBS-01.

**Out of scope:** any LLM call; any corpus ingestion; any drafter/critic/regen code. Protocols in FOUND-04 are stub implementations with docstrings only.

</domain>

<decisions>
## Implementation Decisions

### Packaging (FOUND-01)
- Use `uv` (STACK.md decision) with pyproject.toml + uv.lock. Bootstrap documented in README.
- Package name: `book_pipeline` (snake_case, top-level); CLI entry point: `book-pipeline` (kebab-case, via `[project.scripts]`).
- Python version pin: ^3.12 (align with paul-thinkpiece-pipeline venv_cu130 conventions; uv handles interpreter resolution).
- Dev tooling: pytest, ruff (lint+format), mypy (strict where possible). CI-friendly install path: `uv sync` from clean clone produces a working dev env.

### Config (FOUND-02)
- Pydantic-Settings v2 + PyYAML (STACK.md).
- Four config files under `config/`: `voice_pin.yaml`, `rubric.yaml`, `rag_retrievers.yaml`, `mode_thresholds.yaml`.
- Secret-bearing config (Anthropic API key, Telegram token, future Gemini/GPT-5 keys) goes in `.env` (via pydantic-settings `.env` support) — NOT committed. `.env.example` template committed.
- Each config validated at startup; `book-pipeline validate-config` CLI command introduced for standalone verification.
- Voice pin target noted in `voice_pin.yaml` as V9/V10-or-latest-stable (per current /gsd-new-project decisions); actual SHA enforcement in Phase 3.

### openclaw (FOUND-03)
- `openclaw.json` at repo root (per STACK.md research — NOT `.openclaw/`).
- Initial workspace: `workspaces/drafter/` with AGENTS.md, SOUL.md, USER.md files (stub content; Phase 3 fills with real drafter logic).
- Use `openclaw cron add` native mechanism (NOT systemd timers); `book-pipeline openclaw bootstrap` CLI command registers the workspace and verifies gateway reachability.
- Mirror the `wipe-haus-state` reference install structure.

### Protocols (FOUND-04)
- 13 Protocols in `book_pipeline.interfaces` module (one module per Protocol; `book_pipeline/interfaces/__init__.py` re-exports all).
- Each Protocol uses `typing.Protocol` (PEP 544) with docstring contracts specifying pre/post conditions and event-emit expectations.
- Pydantic BaseModels used for structured types that cross Protocol boundaries (`SceneRequest`, `ContextPack`, `CriticReport`, `RegenResult`, `SceneState`, `EntityCard`, `RetrospectiveNote`, `ThesisEvidence`, `Event`).
- Stub implementations live in `book_pipeline.stubs` package; concrete implementations arrive in later phases.

### Module Boundaries (FOUND-05)
- Kernel-shaped modules (future extraction targets per ADR-004): `drafter/`, `critic/`, `regenerator/`, `rag/`, `observability/`, `orchestration/`, `interfaces/`.
- Book-specific modules: `book_specifics/` — anything that references *Our Lady of Champion* corpus paths, rubric axes names tied to the book, entity extraction schemas for Nahuatl-specific names, etc.
- Lint enforcement via `import-linter` (or equivalent) in `pyproject.toml`: kernel modules may NOT import from `book_specifics/`; book_specifics may import freely from kernel. Violation fails CI.

### Observability (OBS-01)
- Stdlib `logging` + `python-json-logger` writing to `runs/events.jsonl` (append-only).
- Event schema v1 (Pydantic-validated): `{timestamp, event_id, role, model, prompt_hash, input_tokens, cached_tokens, output_tokens, latency_ms, temperature, top_p, caller_context: {module, function, scene_id?, chapter_num?, ...}, output_hash, mode: "A"|"B"|null, rubric_version?, checkpoint_sha?}`.
- `EventLogger` Protocol implementation (`book_pipeline.observability.event_logger`) concrete in this phase (not stubbed) — every other phase will use it from day one.
- Smoke test: a dummy scene-request event round-trips through `EventLogger` and lands in `runs/events.jsonl` with well-formed JSON.
- Event schema frozen at end of this phase — later phases add OPTIONAL fields, never rename or remove; migration path via `events.jsonl` versioning tag.

### Claude's Discretion
All implementation file structure, naming within these constraints, test harness details, and CI workflow specifics. No specific file-layout or test-framework preferences stated.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — this is a greenfield repo. The paul-thinkpiece-pipeline sibling has patterns worth scanning for (venv layout, tooling choices) but should not be imported.

### Established Patterns
- From paul-thinkpiece-pipeline (sibling): bare venv + pip, shell-script-driven training. Book pipeline deliberately departs (uv + Python CLI per STACK.md ADR-like pick) because book pipeline is production-shaped, not research-shaped.
- From wipe-haus-state (sibling): openclaw workspace layout. To be mirrored — see STACK.md for specific file references.

### Integration Points
- `openclaw` gateway (systemd user unit already running) — reachable via openclaw CLI.
- paul-thinkpiece-pipeline voice-FT checkpoint (pinned via voice_pin.yaml; actual loading deferred to Phase 3).
- our-lady-of-champion corpus (read-only path referenced in rag_retrievers.yaml; actual ingest deferred to Phase 2).

</code_context>

<specifics>
## Specific Ideas

- Follow the repo layout documented in `README.md` (config/, canon/, drafts/, indexes/, entity-state/, runs/, theses/, retrospectives/, digests/) — these dirs already exist at scaffold time.
- CLAUDE.md already generated; subsequent phases should update its "Stack" and "Conventions" sections as components stabilize.
- EventLogger MUST be able to emit events before any LLM call is wired (per ADR-003: observability cannot be retroactive). Phase 1 exit criterion is a green smoke test.

</specifics>

<deferred>
## Deferred Ideas

- CI workflow (GitHub Actions) — valuable but deferred until Phase 2 needs it for golden-query CI gate (RAG-04). For Phase 1, pre-commit hooks via `pre-commit` framework are sufficient.
- Dependency upgrade automation (dependabot / renovate) — deferred until after Phase 6 first draft ships.
- `book-pipeline doctor` CLI command that verifies all deps + openclaw connectivity + anthropic API reachability — nice polish, deferred to Phase 5 when full orchestration lands.

</deferred>
