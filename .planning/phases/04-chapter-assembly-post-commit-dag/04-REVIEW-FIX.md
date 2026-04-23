---
phase: 04-chapter-assembly-post-commit-dag
fixed_at: 2026-04-23T00:00:00Z
review_path: .planning/phases/04-chapter-assembly-post-commit-dag/04-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-04-23
**Source review:** .planning/phases/04-chapter-assembly-post-commit-dag/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 10 (2 Critical + 8 Warning; Info findings deferred)
- Fixed: 10
- Skipped: 0

All fixes verified via syntax check (`ast.parse`) plus the full
non-slow pytest suite (516 passed, 4 deselected) after each commit.
No LLM calls, no vLLM boot, no remote push.

## Fixed Issues

### CR-01: Path traversal via `--run-id` in `cli/ablate.py`

**Files modified:** `src/book_pipeline/cli/ablate.py`, `src/book_pipeline/ablation/harness.py`
**Commit:** 7892aba
**Applied fix:**
- Tightened `_RUN_ID_RE` to `^(?![.-])[A-Za-z0-9_.-]{1,64}(?<![.])$` — rejects leading `.`/`-` and trailing `.`.
- Added `_validate_run_id` helper with defense-in-depth dot-sequence check (rejects `.`, `..`, `...`, any pure-dot string).
- Hardened `create_ablation_run_skeleton` to `resolve()` both `ablations_root` and `run_dir`, then assert `run_dir` is a descendant via `relative_to` containment check before any `mkdir`. Protects programmatic callers that bypass the CLI regex.

### CR-02: RAG reindex loses idempotency when LanceDB delete fails

**Files modified:** `src/book_pipeline/rag/reindex.py`
**Commit:** 54ca353
**Applied fix:** Removed the log-and-proceed swallowing of bulk-delete failures. On `tbl.delete("true")` failure the code now falls back to a per-row `tbl.delete("chunk_id = 'X'")` loop (with single-quote escaping), and raises `RuntimeError` if the fallback also fails — caller `_step3_rag` routes to `DAG_BLOCKED`. Preserves the "full regenerate" invariant from CONTEXT.md grey-area d; eliminates duplicate-row contamination against the stable `chunk_id = entity_name` assumption.

### WR-01: `_step4_retro` proceeds to `DAG_COMPLETE` even when retrospective commit fails

**Files modified:** `src/book_pipeline/chapter_assembler/dag.py`
**Commit:** 0fae2a6
**Applied fix:** The `except GitCommitError` handler now appends `f"retro_commit_failed:{exc}"` to `record.blockers` before falling through to `dag_step=4`. Phase 6 digest can now surface the retrospective-untracked state via `record.blockers` instead of seeing a silently "clean" DAG with no git log entry for the retrospective.

### WR-02: `ConcatAssembler.from_committed_scenes` does not filter by chapter number

**Files modified:** `src/book_pipeline/chapter_assembler/concat.py`
**Commit:** 54c33ef
**Applied fix:** Replaced module-level `_SCENE_MD_RE` usage inside `from_committed_scenes` with a chapter-scoped regex `rf"^ch{chapter_num:02d}_sc(\d+)\.md$"` — matches the `_preflight_scene_count_gate` in dag.py. A stray `ch01_sc01.md` under `drafts/ch02/` is now ignored instead of cross-contaminating the ch02 assembly. Tuple shape simplified from `(ch_num, sc_idx, path)` to `(sc_idx, path)`.

### WR-03: `_strip_chapter_frontmatter` silently returns input on malformed frontmatter

**Files modified:** `src/book_pipeline/chapter_assembler/dag.py`
**Commit:** 858c32c
**Applied fix:** When opening `---\n` fence is present but closing `\n---\n` is missing, `_strip_chapter_frontmatter` now raises `RuntimeError` with a clear diagnostic. Prevents leaking chapter frontmatter (chapter_num, voice_pin_shas, assembled_from_scenes) into the entity extractor user prompt — which previously could cause Opus to extract `chapter_num` or `voice_pin_shas` as entity cards.

### WR-04: Retrospective `chapter_num` in body can diverge from DAG's chapter_num

**Files modified:** `src/book_pipeline/retrospective/opus.py`, `src/book_pipeline/chapter_assembler/dag.py`
**Commit:** a3f2221
**Applied fix:**
- Extended `OpusRetrospectiveWriter.write()` with a keyword-only `chapter_num: int | None = None` parameter; when supplied it overrides the `_infer_chapter_num` fallback.
- DAG `_step4_retro` now calls the writer through a `_call_retrospective_writer` shim that passes `chapter_num=chapter_num` (authoritative from the DAG). Shim catches `TypeError` to stay compatible with legacy test fakes that implement the older 3-positional signature (no test churn).

### WR-05: ChapterCritic Event sets `checkpoint_sha=None`, losing V-3 continuity at chapter grain

**Files modified:** `src/book_pipeline/critic/chapter.py`, `src/book_pipeline/chapter_assembler/dag.py`
**Commit:** 63ae023
**Applied fix:**
- Added `_derive_voice_pin_shas` helper that extracts a typed `list[str]` from `CriticRequest.chapter_context["voice_pin_shas"]` (tolerates None, non-list, mixed-type entries).
- Both success and failure `Event` constructions in `ChapterCritic.review` now stamp `checkpoint_sha=latest_pin` (last entry of the list, matches B-3 latest-pin convention).
- DAG orchestrator `_step1_canon` now populates `voice_pin_shas_from_drafts = [d.voice_pin_sha for d in drafts if d.voice_pin_sha]` into `critic_req.chapter_context`, enabling Phase 6 digest to correlate chapter-critic events with the voice-FT pin without cross-referencing canon frontmatter.

### WR-06: `_step3_rag` commit drops tracked `resolved_model_revision.json` updates

**Files modified:** `src/book_pipeline/chapter_assembler/dag.py`
**Commit:** 02f822a
**Applied fix:** Replaced the dead `_ = rel_revision` with a runtime tracked-state probe: `git ls-files --error-unmatch rel_revision`. If the file is tracked, it is staged in the commit; if gitignored (current default), the commit stays empty via `allow_empty=True`. Subprocess failure is caught and logged without aborting the step. Correct behavior either way.

### WR-07: Brittle Pydantic sibling-attribute injection in `ConcatAssembler.from_committed_scenes`

**Files modified:** `src/book_pipeline/interfaces/types.py`, `src/book_pipeline/chapter_assembler/concat.py`
**Commit:** 88f95eb
**Applied fix:**
- Added `voice_fidelity_score: float | None = None` as an additive-optional field on `DraftResponse` (Phase 1 freeze policy allows this).
- Replaced `object.__setattr__(drafts[-1], "voice_fidelity_score", fid)` with proper construction: `DraftResponse(..., voice_fidelity_score=fid_value)`, with a try/float-coerce/fall-back-to-None path for non-numeric frontmatter values.
- Existing `getattr(d, "voice_fidelity_score", None)` in `assemble` continues to work (attribute access of a Pydantic field is identical to `__dict__` access for read-only consumers). Tests that still inject via `object.__setattr__` (e.g., `test_concat.py::_make_draft`) remain green.

### WR-08: `cli/chapter.py` hardcodes `repo_root = Path.cwd()`

**Files modified:** `src/book_pipeline/cli/chapter.py`, `tests/cli/test_chapter_cli.py`
**Commit:** 1d24810
**Applied fix:**
- Added `_discover_repo_root()` helper that calls `git rev-parse --show-toplevel` via `subprocess.run(..., check=True)`. Raises `RuntimeError("must be run inside a git repo")` on failure (subprocess error / git not on PATH); caller `_run()` returns exit 2.
- Replaced `repo_root = Path.cwd()` in `_build_dag_orchestrator` with `repo_root = _discover_repo_root()`. CLI now works from any subdirectory and from cron (Phase 5 ORCH-01) where openclaw sets cwd to the workspace, not the repo.
- Updated `test_build_orchestrator_wires_all_deps` in `tests/cli/test_chapter_cli.py` to `git init` the `tmp_path` so the discovery succeeds in the test fixture. Other tests in the file monkeypatch `_build_dag_orchestrator` and are unaffected.

---

## Skipped Issues

None — all in-scope findings were successfully fixed and committed.

## Deferred (out of scope)

The following Info-level findings were NOT in scope (`fix_scope: critical_warning`):
- IN-01: Error-path `prompt_hash` uses `user_prompt_sha` instead of `user_prompt`
- IN-02: `_call_opus_inner` try/except re-raise is a no-op
- IN-03: Hardcoded `attempts_made = 5` duplicates tenacity stop count
- IN-04: `_load_or_init_record` doesn't validate `chapter_num` match
- IN-05: Empty YAML frontmatter raises `ValueError` in `_parse_scene_md`
- IN-06: Duplicate retrospective-markdown parsers in dag.py + retrospective/opus.py
- IN-07: `from_committed_scenes` returns drafts with empty `output_sha`

These can be addressed in a follow-up fix pass or deferred to Phase 5/6.

---

_Fixed: 2026-04-23_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
