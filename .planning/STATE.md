---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 03-03-PLAN.md (vLLM bootstrap plane + V-3 handshake SHA gate live)
last_updated: "2026-04-22T18:27:58.724Z"
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 20
  completed_plans: 15
  percent: 75
---

# STATE: our-lady-book-pipeline

**Last updated:** 2026-04-22 after Plan 03-03 (vLLM bootstrap plane + V-3 boot_handshake SHA gate live; DRAFT-01 complete)
**Status:** Executing Phase 03

---

## Project Reference

- **Project doc:** `.planning/PROJECT.md`
- **Requirements:** `.planning/REQUIREMENTS.md` (41 v1 REQ-IDs)
- **Roadmap:** `.planning/ROADMAP.md` (6 phases)
- **Research synthesis:** `.planning/research/SUMMARY.md`
- **Architecture:** `docs/ARCHITECTURE.md`
- **Locked decisions:** `docs/ADRs/001-004`

### Core value (one line)

Autonomously produce first-draft novel chapters that are both voice-faithful (Paul's prose via pinned FT local checkpoint) and internally consistent (5-axis critic enforced pre-commit), while capturing enough experiment telemetry that learnings transfer to every future writing pipeline.

### Current focus

Phase 3 executing. Plan 03-03 LANDED (vLLM bootstrap plane + V-3 boot_handshake SHA gate live): `book_pipeline.drafter.vllm_client.VllmClient` is an httpx+tenacity client (3x exponential backoff 1→4s on transient transport errors) with `get_models`, `chat_completion` (OpenAI-compatible payload with vLLM `repetition_penalty` under `extra_body`), `health_ok`, and `boot_handshake(pin)` — the V-3 PITFALLS mitigation LIVE end-to-end (recomputes `compute_adapter_sha(pin.checkpoint_path)`, asserts `paul-voice` is in `/v1/models` data, emits `role="vllm_boot_handshake"` OBS-01 Event with `checkpoint_sha` + served `vllm_version`, raises `VoicePinMismatch` on drift with an error-status Event emitted BEFORE the raise for observability trail); `book_pipeline.drafter.systemd_unit` ships `render_unit` (Jinja2 StrictUndefined→KeyError), atomic `write_unit` via tmp+os.replace, `systemctl_user` + `daemon_reload` returning `(ok, stdout, stderr)` tuples with 60s subprocess timeouts (failures don't crash the CLI), and pure-httpx `poll_health` with bounded timeout (separate from VllmClient's retry profile); `book-pipeline vllm-bootstrap` CLI composes unit-render + write + (optional) enable + (optional) start + boot_handshake with structured exit codes (0=ok, 2=config/render, 3=SHA mismatch, 4=handshake error, 5=systemctl/poll failure) + `role="vllm_bootstrap"` summary Event even on `--dry-run`; `config/systemd/vllm-paul-voice.service.j2` Jinja2 template renders against Plan 03-01's real V6 pin to `--model Qwen/Qwen3-32B --enable-lora --lora-modules paul-voice=/home/admin/finetuning/output/paul-v6-qwen3-32b-lora --port 8002 --dtype bfloat16 --max-model-len 8192 --tensor-parallel-size 1 --gpu-memory-utilization 0.85`; `book_specifics/vllm_endpoints.py` holds `DEFAULT_BASE_URL` + `LORA_MODULE_NAME` + poll timeouts (CLI-composition seam — kernel `drafter/vllm_client.py` + `drafter/systemd_unit.py` both grep-clean on book_specifics); jinja2 declared explicitly in pyproject (was transitive); 18 new tests via `httpx.MockTransport` + subprocess monkeypatches (320 total, from 302 baseline). REQUIREMENTS.md DRAFT-01 marked COMPLETE (Plan 03-01 pin + verify_pin helper + Plan 03-03 boot-handshake live). Plan 03-04 (Mode-A drafter: Jinja2 prompt template + sampling profiles + memorization gate) ready to start.

---

## Current Position

Phase: 03 (Mode-A Drafter + Scene Critic + Basic Regen) — EXECUTING
Plan: 3 of 8

- **Phase:** 3
- **Plan:** 4 (03-04 next)
- **Status:** Plan 03-03 complete (vLLM bootstrap plane live: VllmClient httpx+tenacity+boot_handshake + systemd unit template + book-pipeline vllm-bootstrap CLI; V-3 PITFALLS enforcement LIVE end-to-end; DRAFT-01 marked complete). Ready for Plan 03-04 Mode-A drafter.
- **Plans complete:** 3 / 8 (Phase 3); 15 / 20 total (Phase 1: 6; Phase 2: 6; Phase 3: 3)
- **Progress:** [████████░░] 75%

### Roadmap progress

- [x] **Phase 1:** Foundation + Observability Baseline (6/6 plans)
- [x] **Phase 2:** Corpus Ingestion + Typed RAG (6/6 plans — 02-01 RAG kernel + 02-02 corpus ingester + 02-03 3-of-5 retrievers + 02-04 entity_state/arc_position + outline_parser + 02-05 ContextPackBundler + 02-06 RAG-04 golden-query CI gate + nightly cron)
- [~] **Phase 3:** Mode-A Drafter + Scene Critic + Basic Regen (3/8 plans — 03-01 kernel skeletons + REAL V6 voice pin; 03-02 OBS-03 voice-fidelity anchor curation; 03-03 vLLM bootstrap plane + boot_handshake SHA gate [DRAFT-01 complete])
- [ ] **Phase 4:** Chapter Assembly + Post-Commit DAG
- [ ] **Phase 5:** Mode-B Escape + Regen Budget + Alerting + Nightly Orchestration
- [ ] **Phase 6:** Testbed Plane + Production Hardening + First Draft

---

## Performance Metrics

No prose-generation metrics yet — pipeline has not produced artifacts. First real metrics land in Phase 3 (first Mode-A scene scored against anchor set) and Phase 5 (first full nightly loop run).

### Plan execution metrics

| Plan  | Duration (min) | Tasks | Files created | Files modified | Tests added | Tests passing | Completed   |
| ----- | -------------- | ----- | ------------- | -------------- | ----------- | ------------- | ----------- |
| 02-01 | 45             | 1     | 11            | 3              | 20          | 131           | 2026-04-22  |
| 02-02 | 16             | 2     | 14            | 6              | 36          | 167           | 2026-04-22  |
| 02-03 | 14             | 2     | 11            | 0              | 25          | 192           | 2026-04-22  |
| 02-04 | 12             | 2     | 7             | 0              | 17          | 209           | 2026-04-22  |
| 02-05 | 12             | 2     | 7             | 3              | 26          | 235           | 2026-04-22  |
| 02-06 | 45             | 3     | 10            | 11             | 19          | 254           | 2026-04-22  |
| 03-01 | 12             | 3     | 12            | 6              | 14          | 280           | 2026-04-22  |
| Phase 03 P02 | 32 | 2 tasks | 9 files |
| Phase 03 P03 | 10 | 2 tasks | 10 files |

### Target metrics (will populate once pipeline runs)

- Mode-B escape rate (target: 20-30% for Act 1, per research)
- Voice-fidelity cosine vs anchor set (target band: 0.60-0.88 — too-high indicates memorization)
- Per-axis critic pass rate (scene + chapter)
- Regen iteration distribution
- Anthropic spend per chapter
- Thesis closure rate (target: >=3 closed by FIRST-01)

---

## Accumulated Context

### Decisions logged

- **Granularity: standard, 6 phases.** Requirements (41) clustered into 6 coherent delivery boundaries per research SUMMARY.md recommendation; dependencies (EventLogger before LLM calls, RAG before Drafter, scene flow before chapter flow, core loop before testbed) forced this ordering.
- **Observability is Phase 1, not Phase 6.** Per ADR-003 + pitfall V-3 + V-1/V-2, EventLogger + voice-pin SHA canary + anchor-set curation protocol all land before any prose commits. Retroactive observability baselines are impossible.
- **Mode-B is Phase 5, not earlier.** Mode-B is an escape from Mode-A failure; Mode-A (Phase 3) must exist and be characterized before Mode-B's escalation logic is meaningful. Moving Mode-B earlier would invert the testbed question ("is voice-FT reach sufficient?") into "how cheap is Mode-B?" — wrong question.
- **Testbed plane (theses, digest, ablations) is Phase 6.** Requires >=3 committed chapters before evidence is meaningful. Retrospective writer (TEST-01) is in Phase 4 so the first retrospective proves the template + lint before Phase 6 depends on it.
- **No UI phase.** Markdown is the v1 interface (PROJECT.md out-of-scope for dashboard); every phase carries `UI hint: no`.
- **Parallelization hints encoded per phase.** Config is `parallel=true`. Each phase's detail section notes which plans are safely parallelizable (e.g., the 5 retrievers in Phase 2, Drafter + Critic in Phase 3 once schemas pin).
- **(02-01) chapter column on CHUNK_SCHEMA at chunk time (W-5 revision).** Over `heading_path LIKE 'Chapter N %'` at retrieval time. LIKE would false-match `Chapter 10/11/...` under a `Chapter 1` prefix; int-column exact equality sidesteps the whole class. Plan 04 arc_position retriever consumes this.
- **(02-01) pin-once revision_sha for BGE-M3.** Explicit `revision=<sha>` at construction is returned verbatim and respected; `revision=None` opts into HfApi HEAD resolution on first access (bootstrap path — Plan 02 uses this on its first ingest to fill `model_revision: TBD-phase2` in config/rag_retrievers.yaml).
- **(02-01) Import-linter contract-2 extension semantics.** Contract 2's source_modules is frozen at `[interfaces]`; new kernel concretes land in `forbidden_modules` instead (deviated from plan's literal "source_modules in BOTH" instruction; plan-author conflated growth points). Intent preserved (each new kernel is in both contracts). Future plans extending kernel packages (drafter, critic, orchestration) will follow this clarified pattern.
- **(02-02) CLI-composition exemption is the only sanctioned bridge across the kernel/book_specifics line.** Documented in 3 places: pyproject.toml `ignore_imports`, `tests/test_import_contracts.py` `documented_exemptions` set, and the CLI module docstring. Reusable pattern for Phase 3+ drafter/critic/regenerator CLI seams (e.g., loading `voice_pin.yaml`).
- **(02-02) `indexes/resolved_model_revision.json` (gitignored) replaces the planned YAML write-back (W-4).** `{sha, model, resolved_at_iso}` shape; written only after successful ingest; `config/rag_retrievers.yaml` is READ-ONLY to the ingester. Regression-guarded by `test_w4_yaml_config_is_not_modified` (asserts byte-identical yaml pre/post ingest).
- **(02-02) `BRIEF_HEADING_AXIS_MAP` is an explicit 12-entry allowlist (W-3).** Hand-authored from the real `brief.md` H2 headings (4 metaphysics + 8 historical). Regex-absence is asserted by `test_heading_classifier_module_has_no_regex`. Unmapped headings default to the file's primary axis (`historical`). `classify_brief_heading` accepts either the full breadcrumb OR the trailing segment.
- **(02-02) `ingestion_run_id` mixes microsecond timestamp + mtime-snapshot hash to stay unique across rapid rebuilds.** Plan's literal digest input (sorted paths + revision_sha) would have collided on back-to-back `--force` runs; the extra entropy closes the hole. Plan 05 bundler stamps `ContextPack.ingestion_run_id` with this format.
- **(02-03) B-1 sole ownership of `retrievers/__init__.py` — Plan 03 owns, Plan 04 never modifies.** All 5 retriever symbols pre-declared; Plan 02-04's `entity_state` + `arc_position` loaded via `importlib.import_module` inside `contextlib.suppress(ImportError)` (dynamic import needed to bypass mypy's import-untyped static complaint on modules-not-yet-on-disk). Pre-Plan-04: attributes are `None`. Post-Plan-04: attributes are the real classes.
- **(02-03) B-2 frozen Protocol `reindex(self) -> None` on every concrete retriever.** Axis-specific reindex state (Plan 02-04's ArcPositionRetriever outline_path, embedder, ingestion_run_id) is stored on `self` at `__init__` and read during `reindex()`. Runtime-checkable `isinstance(r, Retriever)` passes — verified by dedicated test in each retriever test file + `inspect.signature(r.reindex).parameters` emptiness check.
- **(02-03) W-2 explicit-kwargs retriever __init__ template.** `def __init__(self, *, db_path, embedder, reranker, **kw) -> None: super().__init__(name="axis", db_path=db_path, embedder=embedder, reranker=reranker, **kw)`. No positional-splat forwarding. Plan 02-04's two retrievers MUST follow this template.
- **(02-03) candidate_k=50 -> final_k=8 pipeline cemented on LanceDBRetrieverBase.** Plan 02-05 bundler's 40KB ContextPack cap math assumes 8 hits per axis × 5 axes = up to 40 hits. `final_k` is an `__init__` kwarg for future tuning without API break.
- **(02-03) MetaphysicsRetriever `[a-z_]+` regex injection guard on `include_rule_types`.** Defense in depth; today's callers are all trusted (Plan 02-05 bundler reads from `config/rag_retrievers.yaml`) but the guard prevents a future regression from leaking unsanitized input into the where clause. Raises `ValueError` on any non-conformant value.
- **(02-03) NegativeConstraintRetriever `_where_clause` is UNCONDITIONALLY `None` (PITFALLS R-5).** Tag-based filtering lives in Plan 02-05 bundler, NEVER in this retriever. Prevents the silent-miss failure where a scene's tag set doesn't match and the constraint never surfaces.
- **(02-03) RetrievalHit.metadata carries 5 keys (added `vector_distance` beyond the plan's literal 4).** `{rule_type, heading_path, ingestion_run_id, chapter, vector_distance}` — zero-cost additive signal for Plan 02-05 bundler + Plan 02-06 CI baseline introspection.
- **(02-04) outline_parser has two modes: STRICT (synthetic `# Chapter N:` / `## Block X:` / `### Beat N:`) + LENIENT FALLBACK (real OLoC `# ACT N —` / `## BLOCK N —` / `### Chapter N —`).** Strict regexes are CASE-SENSITIVE so ALL-CAPS fallback headings don't get shadowed as orphaned strict matches. Each `### Chapter N` in fallback mode becomes one beat (beat=1) under its enclosing `## BLOCK N`. Real outline parses to 27 beats; canary threshold is `len >= 20` so minor future edits don't fail CI.
- **(02-04) Beat ID schema `ch{chapter:02d}_b{block_id}_beat{beat:02d}` is load-bearing for RAG-02 stability.** Determined ENTIRELY by chapter/block/beat numbering — body-text edits don't shift IDs. Zero-padded so lex order matches numeric (ch01 < ch10 < ch27). block_id is letter-lowercase in strict mode (a/b/c...), digit-string in fallback mode (1..9).
- **(02-04) W-5 chapter filter shipped: `_where_clause` returns `f"chapter = {int(request.chapter)}"`.** int() cast is defense-in-depth despite Pydantic's `chapter: int` typing. Exact-equality on the int column eliminates the prefix-match class of bug ("Chapter 1" vs "Chapter 10..19"). Tests 2+3 prove: chapter=1 returns only chapter-1 hits, chapter=99 returns empty. Plan 02-06 golden queries can pin on this semantic.
- **(02-04) ArcPositionRetriever uses state-in-__init__ + zero-arg reindex.** `outline_path` + `ingestion_run_id` stored at construction; `reindex(self) -> None` matches frozen Protocol exactly. No classmethod workaround, no method-level args. CorpusIngester (Plan 02-02) ingests outline.md generically; ArcPositionRetriever.reindex() overwrites arc_position table with beat-ID-stable rows (`tbl.delete("true")` + `tbl.add(rows)`). Plan 06 CLI composes: construct retriever + call reindex().
- **(02-04) B-1 honored: Plan 02-04 did NOT modify `retrievers/__init__.py`.** `git log --oneline --all -- src/book_pipeline/rag/retrievers/__init__.py` shows only Plan 02-03 commits (`4ea3dac`, `e7acc52`). Plan 02-03's `importlib.import_module(...)` + `contextlib.suppress(ImportError)` guards now resolve to real classes (verified: `from book_pipeline.rag.retrievers import EntityStateRetriever, ArcPositionRetriever` returns non-None classes).
- **(02-04) All 5 concrete retrievers satisfy runtime-checkable `isinstance(r, Retriever)` + `inspect.signature(r.reindex).parameters == {}`.** B-2 complete across the retriever surface. Plan 02-05 bundler can safely accept `list[Retriever]` without further validation.
- **(02-05) Bundler is the SOLE event-emission site for retrieval Events.** Exactly 6 Events per `bundle()` call: 5 `role="retriever"` + 1 `role="context_pack_bundler"`. Retrievers never emit (grep-guarded from Plan 02-03 + count-asserted from Plan 02-05). `test_d_retrievers_do_not_emit_events` locks the invariant.
- **(02-05) detect_conflicts runs on FULL retrievals BEFORE enforce_budget trims.** Rationale: key claims may sit in low-score hits the budget pass drops; catching them early preserves the safety signal. Reject silent-concat; Phase 3 critic reads `drafts/retrieval_conflicts/{stem}.json` alongside scene text.
- **(02-05) W-1 entity_list DI seam — kernel stays book-domain-free.** `ContextPackBundlerImpl.__init__(entity_list=None)` + `detect_conflicts(retrievals, entity_list=None)`; `grep -c "book_specifics" src/book_pipeline/rag/{bundler,conflict_detector}.py` returns 0. Plan 06 CLI flattens `NAHUATL_CANONICAL_NAMES` keys+values and passes into the bundler. Mesoamerican accented names (Motecuhzoma, Malintzin, Tenochtitlán) surface via entity_list that English-capitalization regex would miss.
- **(02-05) ContextPack additive-only extension — 2 new OPTIONAL fields (`conflicts`, `ingestion_run_id`) under Phase 1 freeze.** Old-schema JSON round-trips cleanly. All 5 pre-existing fields (scene_request, retrievals, total_bytes, assembly_strategy, fingerprint) unchanged in name/type/order. Event v1.0 18-field schema untouched — `test_f_event_schema_v1_fields_preserved` regression-guards every emitted event.
- **(02-05) Budget is PURE: deep-copy input, trim on copy, return (trimmed, trim_log).** Sentinel test (`test_enforce_budget_never_mutates_input`) uses `copy.deepcopy` compare to prove no input mutation. Per-axis soft caps (12/8/8/6/6 KB = 40KB total) enforced first; global hard cap (40960) enforced second via lowest-score-globally scan. trim_log surfaces inside the bundler Event's `extra` field for observability.
- **(02-05) Graceful retriever failure (T-02-05-04).** Retriever exceptions yield empty RetrievalResult + Event with `extra["error"]`; bundle still emits exactly 6 Events. Empty conflicts coerce to None on `ContextPack.conflicts` so downstream critic doesn't see false-positive "review needed" signals.
- **(02-06) RAG-04 baseline pinned at ing_20260422T082448725590Z_2264c687.** BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`; 237 chunks distributed 45/51/54/27/45 across historical/metaphysics/entity_state/arc_position(beat-ID-stable)/negative_constraint. Baseline fixture `tests/rag/fixtures/expected_chunks.jsonl` (222 rows) is the probe set for golden-query diagnosis (distinguishes "chunk not indexed" from "chunk didn't rank top-8").
- **(02-06) openclaw CLI 2026.4.5 uses `--agent` NOT `--session-agent`, and `--message` NOT `--system-event` for isolated-session agent jobs.** Phase 1 placeholder cron had the wrong flag names from the start; caught for the first time in Plan 02-06 Gate 4 when the real CLI was exercised. Both Phase 1 + Phase 2 cron wiring corrected. Manual commands in the fallback diagnostic strings match.
- **(02-06) Golden-query `forbidden_chunks` uses a single universally-forbidden cross-axis negative (`engineering.md > Byzantine Orthodox`).** Initial seed queries used axis-local forbidden chunks that conflicted with each retriever's own source files (e.g., negative_constraint reads known-liberties.md, so forbidding known-liberties on ANY retriever is logically inconsistent). Refined to an always-forbidden background section no retriever should surface on Spanish/Mexica scenes. Phase 6 thesis 005 can refine per-query anti-leak cases.
- **(02-06) 6-event-per-bundle invariant held on real corpus (Gate 5).** SceneRequest(Cortés@Tenochtitlan, ch=8, arrival) produced ContextPack total_bytes=31573, 5 axes populated (8+4+4+1+6=23 hits), exactly 6 new events (5 retriever + 1 context_pack_bundler), 38 W-1 conflicts detected. Plan 02-05's invariants survive the jump to real BGE-M3 + real BGE reranker-v2-m3 + 237-chunk corpus.
- **(02-06) Cron registration blocked by missing OPENCLAW_GATEWAY_TOKEN; fallback committed to openclaw/cron_jobs.json.** openclaw CLI is on PATH and the book-pipeline wires the correct flags; gateway auth is a deferred user action. Phase 5 stale-cron detector will alert if `book-pipeline:nightly-ingest` hasn't fired in >36h.
- **(03-01) compute_adapter_sha algorithm pinned: SHA256(adapter_model.safetensors bytes || adapter_config.json bytes), 1 MiB chunks, fixed file order.** Two machines reproduce the same digest. Tokenizer files + checkpoint-*/ subdirs intentionally excluded (change every training iteration, don't affect inference weights). Plan 03-03 boot handshake calls `verify_pin(pin, strict=True)` at vLLM startup; mismatch → `HARD_BLOCKED("checkpoint_sha_mismatch")`.
- **(03-01) REAL V6 pin committed: SHA `3f0ac5e2290dab633a19b6fb7a37d75f59d4961497e7957947b6428e4dc9d094`** (first 16: `3f0ac5e2290dab63`, last 4: `d094`). ft_run_id=v6_qwen3_32b, checkpoint_path=/home/admin/finetuning/output/paul-v6-qwen3-32b-lora, base_model=Qwen/Qwen3-32B, source_commit_sha=c571bb7b... (real paul-thinkpiece-pipeline HEAD). Compute wall time 10.7s over the 537MB safetensors.
- **(03-01) All 4 Phase 3 kernel packages (drafter/, critic/, regenerator/, voice_fidelity/) land in the SAME plan as their import-linter contract extension and scripts/lint_imports.sh mypy-scope extension.** Append-only: +4 entries in contract 1 source_modules, +4 in contract 2 forbidden_modules, +4 mypy target dirs. Plan 01-06 extension policy precedent; Plans 03-02..05 add concrete impls INSIDE these packages without touching pyproject.toml.
- **(03-01) voice_fidelity/__init__.py uses importlib+contextlib.suppress for BOTH sha AND scorer.** Plan spec only covered scorer; extending to sha keeps the 3-task commit chain atomic (Task 1's GREEN state doesn't depend on Task 2 having landed sha.py). Downstream pattern: Plan 03-02 replaces scorer stub body WITHOUT touching __init__.py — `score_voice_fidelity` attribute re-resolves through the fallback.
- **(03-01) VoicePinConfig round-trip skip for non-canonical --yaml-path in pin-voice CLI.** pydantic-settings hardcodes `yaml_file='config/voice_pin.yaml'` via SettingsConfigDict; tests using tmp_path for yaml_path fall back to direct `VoicePinData(**payload)` construction (same schema gate). Happy path (real `book-pipeline pin-voice` against canonical path) takes the full VoicePinConfig branch and exercises the pydantic-settings loader end-to-end.
- **(03-01) Pre-existing SIM105 ruff violation in rag/bundler.py auto-fixed under Rule 3 (blocker).** `bash scripts/lint_imports.sh` was failing before Plan 03-01 started (Phase 2 Plan 05's try/except/pass block from commit d4f35ac). Fixed to `contextlib.suppress(Exception)` — same semantics, unblocks the aggregate gate. Regression likely introduced by a ruff version bump between Plan 02-06 close and Plan 03-01 start (both on 2026-04-22).
- **(03-02) anchor_set_sha algorithm pinned: SHA256 over `JSON.dumps(sorted([(a.id, a.text, a.sub_genre) for a in anchors]), sort_keys=True, ensure_ascii=False)`.** Sort on tuple → shuffle-stable. ensure_ascii=False preserves em-dashes + smart quotes byte-exact across machines. Real V3 curation SHA `28fd890bc4c8afc1d0e8cc33b444bc0978002b96fbd7516ca50460773e97df31`. Plan 03-04 drafter boot handshake: recompute vs `cfg.voice_fidelity.anchor_set_sha` → HARD_BLOCK on drift.
- **(03-02) ANALYTIC keyword set EXTENDED beyond plan-original narrow ML-jargon list** to include metric/data/analysis/system/measure/pattern/signal/framework/tradeoff/infrastructure/protocol/api/algorithm. Rule 2 deviation: plan-original 6-keyword set yielded only 5 analytic-passing rows from paul-thinkpiece-pipeline v3_data/train_filtered.jsonl vs V-1 minimum 6. Widened set honors Paul's actual tech-culture analytic register (founders, infra, institutional dynamics — not just ML benchmarks). Post-widening distribution: 191 essay / 15 analytic / 22 narrative — 8/8/6 quotas met with headroom.
- **(03-02) check_anchor_dominance(threshold=0.15) flagged all 22 curated anchors** — threshold mis-calibration artifact, not real dominance. Actual contribution range 0.6355-0.7573 (mean 0.7014, spread 19%). 0.15 threshold was calibrated for random-orthogonal baseline (3× 1/sqrt(22)); same-author BGE-M3 embeddings cluster too tightly for that bar. Phase 6 should switch to MEDIAN-relative threshold (flag when contribution > 2× median) or equivalent z-score. Plan 03-02 warning is logged + non-fatal.
- **(03-02) VoiceFidelityConfig Pydantic validator enforces 4 interval invariants at construction time:** fail_threshold == flag_band_min (==0.75), pass_threshold == flag_band_max (==0.78), fail_threshold <= pass_threshold, pass_threshold < memorization_flag_threshold (0.78 < 0.95). Prevents silent-threshold-drift class of bug. Test 5 in test_curate_anchors.py regression-guards the rejection path.
- **(03-02) curate-anchors atomic YAML rewrite strips comments — known limitation of yaml.safe_dump.** Documented inline in mode_thresholds.yaml header; operators re-adding comments is manual. NOT fixing via ruumel.yaml dep per STACK.md ("PyYAML unless we round-trip-edit YAML programmatically — we don't"). File's load-bearing bytes are the data, not comments.
- **(03-02) Plan 03-01 stub test `tests/voice_fidelity/test_scorer.py` DELETED.** The stub test asserted `NotImplementedError`; replacing the stub body with the real BGE-M3 cosine impl (Plan 03-02 Task 1) makes it false-fail. Plan 03-01 summary explicitly anticipated this sunset. 5 new centroid-behavior tests in `tests/voice_fidelity/test_scorer_centroid.py` supersede.
- **(03-02) env-var override pattern for CLI-tested paths: OBS_CURATE_ANCHORS_{THINKPIECE,BLOG}_PATH.** Lets tests swap corpus locations without monkeypatching module constants. Production uses default paths inside anchor_sources.py. Same idiom as Phase 2 path overrides — keep in mind for future book-specifics CLI pointer tables.
- **(03-03) VllmClient boot_handshake is the V-3 enforcement live site.** Recomputes `compute_adapter_sha(pin.checkpoint_path)` on first vLLM contact, asserts `paul-voice` is served, emits `role="vllm_boot_handshake"` Event with `checkpoint_sha` + served `vllm_version`, raises `VoicePinMismatch` on drift. Error-status Event is emitted BEFORE the raise so ops investigation has an auditable trail — the attempted pin-check is observable even when it fails. Plan 03-04 drafter will call this at startup before every Mode-A scene draft; SHA mismatch routes to `HARD_BLOCKED("checkpoint_sha_mismatch")`.
- **(03-03) tenacity.Retrying as a context manager (not @tenacity.retry decorator) on VllmClient._http_get / _http_post.** Same semantics (3 attempts, exponential 1→4s, httpx.TimeoutException/ConnectError/RequestError). Cleaner typing — yields httpx.Response uniformly inside a for-loop rather than wrestling a decorator's captured-method annotations. Production behavior identical.
- **(03-03) Test seam via optional `_http_client` kwarg on VllmClient.__init__ instead of adding respx as a dep.** Plan allowed either; MockTransport is stdlib-shaped + already transitive via httpx + zero new deps. Tests pass `httpx.Client(transport=MockTransport(...))`; production leaves it None and builds its own httpx.Client(base_url, timeout). Retry semantics exercise against real-shaped httpx.Response objects in the mock.
- **(03-03) Pure-httpx poll_health in systemd_unit.py — does NOT compose VllmClient.health_ok().** VllmClient retry tuning is for post-up responsiveness (3×, 1→4s); boot-poll wants "keep-trying-quietly" semantics for a cold-starting server. poll_health loops on `httpx.get({url}/models, timeout=2s)` every interval_s until 200 or deadline. Cleaner CLI lifecycle + simpler timeout reporting than re-using the handshake client.
- **(03-03) LoRA-adapter mode, NOT merged-weights, for vLLM serving (W-4 closure).** Template renders `--enable-lora --lora-modules paul-voice=<adapter_path>` against base `Qwen/Qwen3-32B`. Rationale: no re-merge on every pin bump (saves ~30min + 65GB per bump), hot-swap potential for future Phase 5 Mode-B experiments, and faster boot_handshake (~10.7s for 537MB adapter vs ~2-3min for 65GB merged base). Trade-off: ~5-10% per-token latency penalty vs merged. Acceptable for Phase 3 nightly cadence. Documented upgrade path: `peft merge_and_unload` + `book-pipeline pin-voice <merged_dir>` + re-bootstrap.
- **(03-03) CLI exit-code taxonomy for book-pipeline vllm-bootstrap:** 0=ok, 2=config/render failure, 3=SHA mismatch (V-3 fired), 4=handshake error (LoRA not loaded), 5=systemctl/poll failure. Plan 03-08 smoke + future cron will distinguish infrastructure failures from SHA drift. Documented in the CLI module docstring; threat T-03-03-07 (DoS via hanging subprocess) mitigated by bounded timeouts at every stage.
- **(03-03) --dry-run still emits role='vllm_bootstrap' Event** (with caller_context.dry_run=True + all enable/start/handshake statuses = 'skipped'). Observability is load-bearing even for dry-runs — Plan 03-08 smoke asserts ANY role='vllm_bootstrap' event, not just live-side-effect runs.

### Open todos

- **Operator action (low-priority):** set OPENCLAW_GATEWAY_TOKEN in env and run `book-pipeline openclaw register-cron --ingest-only` (or apply `openclaw/cron_jobs.json` manually) to activate the nightly-ingest cron.
- **Plan 02-06 deferred:** re-run `pytest tests/rag/test_golden_queries.py -m slow` with the refined `forbidden_chunks` seed to confirm the >=90% pass + 0 forbidden-leaks criterion on the pinned baseline. Plumbing proven to work (Gate 3 initial run ran 11m31s end-to-end; deterministic test passed).
- Watch: `lancedb.table_names()` deprecation — migrate to `list_tables().tables` when old API is actually removed (4 call sites now including `_capture_expected_chunks.py`). `rag/retrievers/base.py` goes through `open_or_create_table` so it benefits from a single-site migration.
- Optional: T-02-02-04 harden — wrap 5-table rebuild in try/except that restores prior mtime_index.json on failure. Current ordering (write mtime last) is equivalent in practice but the explicit safety net is deferred.

### Blockers

None. Phase 3 readiness confirmed by Plan 02-06 Gate 5 end-to-end smoke.

### Research flags per phase

- **Phase 2 (RAG):** BGE-M3 vs jina-embeddings-v3 on domain corpus; LlamaIndex ingestion utilities vs custom chunking for rule-card boundaries. Decide before retriever implementations begin.
- **Phase 3 (Core loop):** Critic rubric prompt architecture (per-axis prompts vs single-schema output); Opus 4.7 token budget per scene; voice-fidelity cosine threshold calibration.
- **Phase 5 (Mode-B):** Anthropic workspace-scoped cache behavior with openclaw per-agent workspace model (changed 2026-02-05); Sonnet 4.6 viability as Mode-B fallback for non-structurally-complex beats.

---

## Session Continuity

### Last session

- **Date:** 2026-04-22
- **Action:** Executed Plan 03-01 — Phase 3 kernel skeletons (drafter/, critic/, regenerator/, voice_fidelity/) + import-linter extension + scripts/lint_imports.sh mypy-scope extension + `book_pipeline.voice_fidelity.sha` (compute_adapter_sha + verify_pin + VoicePinMismatch) + `book_pipeline.voice_fidelity.scorer` signature stub + `book-pipeline pin-voice <adapter_dir>` CLI + REAL V6 qwen3-32b LoRA SHA pinned in config/voice_pin.yaml. TDD: 3 RED/GREEN commit pairs (6 commits total).
- **Outcome:** 12 files created (4 kernel __init__.py + sha.py + scorer.py + pin_voice.py CLI + 4 test files); 6 files modified (pyproject.toml, scripts/lint_imports.sh, cli/main.py, voice_fidelity/__init__.py's eager-vs-fallback choice, config/voice_pin.yaml obliterated Phase 1 placeholder, rag/bundler.py Rule-3 auto-fix for pre-existing SIM105). 14 tests added (3 import-contract structural + 7 sha non-slow + 1 scorer + 4 pin_voice); 280 total passing (was 266 baseline). REAL V6 SHA `3f0ac5e2290dab63…d094` computed in 10.7s over the 537MB safetensors at /home/admin/finetuning/output/paul-v6-qwen3-32b-lora/. Source commit SHA `c571bb7b...` from paul-thinkpiece-pipeline HEAD. Aggregate gate `bash scripts/lint_imports.sh` green (2 contracts kept, ruff clean, mypy clean on 82 source files). 6 per-task commits: d547ae8 (T1 RED) + e785525 (T1 GREEN + Rule-3 bundler fix) + 26df024 (T2 RED) + c987a3e (T2 GREEN) + 42bcdf9 (T3 RED) + 9c1b9c1 (T3 GREEN + REAL V6 pin).
- **Stopped at:** Completed 03-03-PLAN.md (vLLM bootstrap plane + V-3 handshake SHA gate live)

### Next session

- **Expected action:** `/gsd-execute-phase 3` wave 3 — execute Plan 03-03 (vLLM bootstrap + scene critic + SceneState orchestration). Plan 03-03 lands `book-pipeline vllm-bootstrap` subcommand writing the systemd --user unit, calls verify_pin(strict=True) at boot with HARD_BLOCK("checkpoint_sha_mismatch") on drift, wires SceneCritic against Opus 4.7 with `client.messages.parse(response_format=CriticResponse)`, and ships the SceneStateMachine orchestrator that composes drafter + critic + regenerator per `book-pipeline draft <scene_id>`.
- **Key continuation notes:**
  - Plan 03-02 pinned the anchor set SHA `28fd890bc4c8afc1d0e8cc33b444bc0978002b96fbd7516ca50460773e97df31` in `config/mode_thresholds.yaml voice_fidelity.anchor_set_sha`. Plan 03-04 drafter boot handshake will recompute `AnchorSet.load_from_yaml(...).sha` and compare — HARD_BLOCK on drift (T-03-02-01 mitigation).
  - Plan 03-04 drafter imports: `from book_pipeline.voice_fidelity import AnchorSet, compute_centroid, score_voice_fidelity` + `from book_pipeline.rag import BgeM3Embedder`. Construct centroid ONCE per CLI tick; pass to scorer per scene. Score → `Event.caller_context.voice_fidelity_score`.
  - Plan 03-04 MUST NOT touch `voice_fidelity/__init__.py` — Plan 03-01's B-1 fallback pattern resolves all 10 exports (VoicePinMismatch, compute_adapter_sha, verify_pin, score_voice_fidelity, Anchor, AnchorSet, compute_centroid, compute_per_sub_genre_centroids, compute_anchor_set_sha, check_anchor_dominance).
  - Plan 03-03..05 MUST NOT touch `pyproject.toml` import-linter contracts — all 4 Phase 3 kernel packages are already in both contracts (Plan 03-01). New files inside the packages land without contract churn.
  - REAL V6 SHA: `3f0ac5e2290dab633a19b6fb7a37d75f59d4961497e7957947b6428e4dc9d094` (Plan 03-01). Plan 03-04 drafter stamps this onto `DraftResponse.voice_pin_sha` + `Event.checkpoint_sha`.
  - BGE-M3 resolved revision: `5617a9f61b028005a4858fdac845db406aefb181`. Plan 03-02 used this same revision as Phase 2 RAG. If Plan 03-04 drafter detects a different revision from the anchor-curation run, that's a drift signal — Phase 5 stale-pin detector will eventually catch this.
- **Key precedent:** Plan 03-02 established: (a) classifier-first-match-wins heuristic with essay as default register; (b) deterministic `anchor_set_sha` algorithm over sorted (id, text, sub_genre) tuples; (c) pre-flight quota check with structured stderr + exit 3 (W-3/W-5 pattern); (d) CLI-composition seam to book_specifics.anchor_sources mirroring Plan 02-06 cli/_entity_list; (e) role='anchor_curator' Event emission pattern for curation runs; (f) VoiceFidelityConfig Pydantic interval validator for threshold consistency; (g) check_anchor_dominance as a V-1 warning-sign guard (Phase 6 refinement pending — 0.15 threshold mis-calibrated for same-author prose).
- **Phase 3 progress:** 2/8 plans complete. Kernel skeletons + voice pin (03-01) + OBS-03 anchor curation + real cosine scorer (03-02) = drafter-ready foundation. Plans 03-03..08 build on top without further config/pyproject churn.

### Session continuity invariants

- All mutable project state lives on disk under `.planning/` and the artifact directories (`canon/`, `drafts/`, `runs/`, `indexes/`, `entity-state/`, `theses/`, `retrospectives/`, `digests/`).
- No in-memory state is assumed to survive between sessions. The event log (`runs/events.jsonl`, not yet live) is append-only truth; every derived view is rebuildable from it.

---

*State file is updated after each plan completion, phase transition, and milestone boundary.*
