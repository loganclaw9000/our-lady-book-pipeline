---
phase: 04-chapter-assembly-post-commit-dag
reviewed: 2026-04-23T00:00:00Z
depth: standard
files_reviewed: 30
files_reviewed_list:
  - config/rubric.yaml
  - pyproject.toml
  - scripts/lint_imports.sh
  - src/book_pipeline/ablation/harness.py
  - src/book_pipeline/ablation/__init__.py
  - src/book_pipeline/book_specifics/outline_scene_counts.py
  - src/book_pipeline/chapter_assembler/concat.py
  - src/book_pipeline/chapter_assembler/dag.py
  - src/book_pipeline/chapter_assembler/git_commit.py
  - src/book_pipeline/chapter_assembler/__init__.py
  - src/book_pipeline/cli/ablate.py
  - src/book_pipeline/cli/chapter.py
  - src/book_pipeline/cli/chapter_status.py
  - src/book_pipeline/cli/main.py
  - src/book_pipeline/config/rubric.py
  - src/book_pipeline/critic/chapter.py
  - src/book_pipeline/critic/__init__.py
  - src/book_pipeline/critic/templates/chapter_fewshot.yaml
  - src/book_pipeline/critic/templates/chapter_system.j2
  - src/book_pipeline/entity_extractor/__init__.py
  - src/book_pipeline/entity_extractor/opus.py
  - src/book_pipeline/entity_extractor/schema.py
  - src/book_pipeline/entity_extractor/templates/extractor_system.j2
  - src/book_pipeline/interfaces/chapter_state_machine.py
  - src/book_pipeline/interfaces/types.py
  - src/book_pipeline/rag/reindex.py
  - src/book_pipeline/retrospective/__init__.py
  - src/book_pipeline/retrospective/lint.py
  - src/book_pipeline/retrospective/opus.py
  - src/book_pipeline/retrospective/templates/retrospective_system.j2
findings:
  critical: 2
  warning: 8
  info: 7
  total: 17
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-04-23
**Depth:** standard
**Files Reviewed:** 30
**Status:** issues_found

## Summary

Phase 4 lands the chapter-assembly / post-commit DAG: ConcatAssembler, ChapterCritic,
OpusEntityExtractor, OpusRetrospectiveWriter, ChapterDagOrchestrator, plus CLI glue
and the TEST-01 ablation harness. Kernel/book_specifics separation is clean — no
import-linter violations observed; all book-domain imports are confined to
`cli/chapter.py` and match the exemption list in `pyproject.toml`. B-3 voice_pin_sha
preservation is threaded correctly through `ConcatAssembler` into chapter
frontmatter; source_chapter_sha is force-overridden by the extractor (defense-in-
depth against LLM drift).

Two critical issues found: (1) a path-traversal vector in `cli/ablate.py` where
`--run-id "../"` is accepted by the regex and escapes the ablations root, and
(2) the RAG reindex idempotency break when LanceDB's bulk delete raises — the
code logs but does NOT prevent the subsequent `tbl.add(rows)`, producing
duplicated rows against a "stable chunk_id = entity_name" assumption.

Eight warnings cover: silent retro-commit-failure state leak, scene cross-
contamination in `ConcatAssembler.from_committed_scenes`, inconsistent
frontmatter-strip silent passthrough, orchestrator-vs-inferred chapter_num
divergence in retrospective writer, missing V-3 checkpoint_sha on chapter-
critic Events, `_step3_rag` commit dropping tracked revision updates, brittle
Pydantic sibling-attribute injection, and `cli/chapter.py` `repo_root =
Path.cwd()` assumption.

Protocol boundaries and ChapterStateMachine state transitions look correct.
The 4-step DAG resumability contract (`if record.dag_step < N`) is implemented
consistently. No threading/async issues (Phase 4 is all synchronous single-
process). Shell-injection is blocked by argv-list discipline in
`git_commit.py`. Kernel import-linter policy is honored.

## Critical Issues

### CR-01: Path traversal via `--run-id` in `cli/ablate.py`

**File:** `src/book_pipeline/cli/ablate.py:76`
**Issue:** `_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")` accepts `..`,
`.`, `...`, and any dot-sequence of length 1-64. `run_dir = Path(ablations_root)
/ run.run_id` therefore happily composes `runs/ablations/..`, which
`mkdir(parents=True, exist_ok=True)` treats as "create the parent of ablations".
Downstream `(run_dir / "a").mkdir(exist_ok=True)` then lands under
`runs/a/`, and `(run_dir / "ablation_config.json")` writes to
`runs/ablation_config.json` — outside the intended ablations root.

An attacker (or careless operator) invoking `book-pipeline ablate --variant-a
... --variant-b ... --n 1 --run-id ..` would silently create directories and
files outside `runs/ablations/`. In an unattended cron-driven pipeline (Phase 5
openclaw scheduling), even non-malicious test-config typos could produce
confusing filesystem state. The regex was clearly intended to prevent path
traversal; it doesn't.

**Fix:**
```python
_RUN_ID_RE = re.compile(r"^(?![.-])[A-Za-z0-9_.-]{1,64}(?<![.])$")

def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run_id {run_id!r}")
    # Defense-in-depth: reject any segment of only dots.
    if run_id in {".", ".."} or set(run_id) == {"."}:
        raise ValueError(f"run_id must not be a dot-sequence: {run_id!r}")
```
Also harden `create_ablation_run_skeleton` in `ablation/harness.py` to
`resolve()` both `ablations_root` and `run_dir` and assert `run_dir` is a
descendant of `ablations_root` before any `mkdir`.

---

### CR-02: RAG reindex loses idempotency when LanceDB delete fails

**File:** `src/book_pipeline/rag/reindex.py:101-111`
**Issue:**
```python
try:
    tbl.delete("true")
except Exception:
    logger.exception("reindex: entity_state bulk delete via `true` predicate failed")

if rows:
    tbl.add(rows)
```
The comment above the except says "Fall back to a per-row pattern — most
LanceDB 0.30.x versions accept `true` as the predicate" but the code does NOT
fall back. On delete failure the handler just logs and then proceeds to
`tbl.add(rows)`. Because `chunk_id = card.entity_name` is reused as the logical
identity (not enforced unique by LanceDB), the next call to
`reindex_entity_state_from_jsons` produces DUPLICATE rows for every entity.
Retrievers filtering on `chunk_id` would now return multiple hits for one
entity, or compute aggregated scores over phantom duplicates.

Grey-area d in 04-CONTEXT.md explicitly mandates "regenerate FULLY from
`entity-state/chapter_*.json` (idempotent, cheap at ≤500 rows)." The current
code violates that invariant the moment delete raises.

**Fix:**
```python
try:
    tbl.delete("true")
except Exception as exc:
    # Attempt a per-row fallback, then re-verify emptiness.
    logger.warning(
        "reindex: bulk delete(`true`) failed (%s); falling back to row-by-row",
        exc,
    )
    try:
        existing_ids = [r["chunk_id"] for r in tbl.to_pandas().to_dict("records")]
        for chunk_id in existing_ids:
            tbl.delete(f"chunk_id = '{chunk_id}'")
    except Exception:
        logger.exception("reindex: per-row fallback also failed")
        raise RuntimeError("entity_state reindex could not clear prior rows") from exc

# Only reach here if table is verified empty.
if rows:
    tbl.add(rows)
```
Alternatively: drop-and-recreate the table on delete failure. Either way the
contract is "on success: rows equal the JSON source; on failure: raise." Never
"log + proceed + silently double-insert."

## Warnings

### WR-01: `_step4_retro` proceeds to DAG_COMPLETE even when retrospective commit fails

**File:** `src/book_pipeline/chapter_assembler/dag.py:867-884`
**Issue:** The `except GitCommitError` in step 4 logs a warning and falls
through (no `return`) to `record.model_copy(update={"dag_step": 4})` and
`transition(record, ChapterState.DAG_COMPLETE, "retro written")`. A code
comment at line 871-872 says "Treat as DAG_COMPLETE but add a blocker tag for
digest visibility." The blocker tag is never actually appended. Downstream
consumers reading `record.blockers` have no visibility that step 4 commit
failed — `dag_complete=True` in `.planning/pipeline_state.json`, yet the
retrospective is untracked (file written to working tree but never committed).
Phase 6 digest would see "clean" but git log wouldn't contain the retro
commit.

**Fix:**
```python
except GitCommitError as exc:
    logger.error("step 4 retro commit failed: %s", exc)
    logger.warning(
        "retrospective commit failed (ungated); proceeding to "
        "DAG_COMPLETE with blocker tag"
    )
    record = record.model_copy(
        update={
            "blockers": [*record.blockers, f"retro_commit_failed:{exc}"]
        }
    )
```
(Prepend this update before the subsequent `record.model_copy(update={"dag_step": 4})`.)

---

### WR-02: `ConcatAssembler.from_committed_scenes` does not filter by chapter number

**File:** `src/book_pipeline/chapter_assembler/concat.py:183-200`
**Issue:** The regex `_SCENE_MD_RE = re.compile(r"^ch(\d+)_sc(\d+)\.md$")`
accepts any `chNN_scII.md` filename regardless of which chapter directory it
lives in. If a stray `ch01_sc01.md` is left in `drafts/ch02/` (crash residue,
manual copy-paste, git rebase artifact), it is ingested into the ch02
assembly. This violates the contract stated in the docstring ("reads
`commit_dir/ch{NN:02d}/*.md`, builds DraftResponse list") because the
filename prefix is not enforced to match `chapter_num`.

Note the DAG's own `_preflight_scene_count_gate` (dag.py:417-418) DOES
filter by chapter_num via `rf"^ch{chapter_num:02d}_sc(\d+)\.md$"`. The gate
and the assembler disagree on scope.

**Fix:** In `from_committed_scenes`, narrow the regex to the passed-in chapter:
```python
scene_re = re.compile(rf"^ch{chapter_num:02d}_sc(\d+)\.md$")
for path in chapter_dir.iterdir():
    if not path.is_file():
        continue
    m = scene_re.match(path.name)
    if m is None:
        continue
    sc_idx = int(m.group(1))
    entries.append((sc_idx, path))
```
(And drop the unused `ch_num` tuple component; the sort becomes 1-dim.)

---

### WR-03: `_strip_chapter_frontmatter` silently returns input on malformed frontmatter

**File:** `src/book_pipeline/chapter_assembler/dag.py:139-148`
**Issue:**
```python
def _strip_chapter_frontmatter(chapter_md: str) -> str:
    if not chapter_md.startswith("---\n"):
        return chapter_md
    _, rest = chapter_md.split("---\n", 1)
    if "\n---\n" in rest:
        _, body = rest.split("\n---\n", 1)
        return body
    return chapter_md
```
If the chapter markdown starts with `---\n` but has no closing `\n---\n` (a
corrupted or truncated canon commit), the function silently returns the
WHOLE document including the frontmatter YAML. The caller is `_step2_entity`
which feeds that text straight into the entity extractor's user prompt. Opus
then sees `chapter_num: 4` / `voice_pin_shas: [...]` as though they were
chapter prose, potentially extracting them as entities. Entity cards with
names like "chapter_num" are corrosive downstream.

**Fix:** Raise (or log + skip step 2) on malformed frontmatter; don't silently
leak it into the extractor prompt:
```python
def _strip_chapter_frontmatter(chapter_md: str) -> str:
    if not chapter_md.startswith("---\n"):
        return chapter_md  # no frontmatter at all: OK as-is
    _, rest = chapter_md.split("---\n", 1)
    if "\n---\n" not in rest:
        raise RuntimeError(
            "chapter markdown has opening `---` fence without closing fence; "
            "refusing to ship frontmatter-tainted text to entity extractor"
        )
    _, body = rest.split("\n---\n", 1)
    return body
```

---

### WR-04: Retrospective `chapter_num` in body can diverge from DAG's chapter_num

**File:** `src/book_pipeline/retrospective/opus.py:487-499` and
`src/book_pipeline/chapter_assembler/dag.py:848-853`
**Issue:** `ChapterDagOrchestrator._step4_retro` calls
`self.retrospective_writer.write(chapter_text, chapter_events, prior_retros)`
WITHOUT passing the chapter_num. `OpusRetrospectiveWriter.write()` then
infers chapter_num via `_infer_chapter_num(chapter_events, prior_retros)`,
which falls back to `1` if neither source carries it.

The DAG then writes the retro to `retros_dir / f"chapter_{chapter_num:02d}.md"`
(using the DAG's chapter_num) while the file CONTENTS
(`_render_retrospective_md(retro)`) emit `chapter_num: <inferred>` and a
header `# Chapter {retro.chapter_num:02d} Retrospective`. Path and contents
can disagree — e.g., for the Plan 04-06 integration-test chapter 99 with
synthetic events that may not carry chapter_num, `chapter_99.md` might say
`chapter_num: 1`.

**Fix:** Extend the RetrospectiveWriter Protocol to accept an explicit
`chapter_num` parameter (or pass it via a new `caller_context_hint`). The
DAG already has the authoritative number; don't re-infer it downstream:
```python
# retrospective/opus.py
def write(
    self,
    chapter_text: str,
    chapter_events: list[Event],
    prior_retros: list[Retrospective],
    *,
    chapter_num: int | None = None,
) -> Retrospective:
    if chapter_num is None:
        chapter_num = _infer_chapter_num(chapter_events, prior_retros)
    ...

# dag.py:848
retro = self.retrospective_writer.write(
    chapter_text, chapter_events, prior_retros, chapter_num=chapter_num
)
```

---

### WR-05: ChapterCritic Event sets `checkpoint_sha=None`, losing V-3 continuity at chapter grain

**File:** `src/book_pipeline/critic/chapter.py:347`
**Issue:** Per the Phase 1 OBS-01 Event contract, `checkpoint_sha` is the V-3
stale-card correlation field. Scene-level drafter Events stamp the voice
checkpoint SHA; scene critic Events do NOT (critic isn't a Mode-A call). But
for chapter-level events, the `voice_pin_shas` list is known from the chapter
frontmatter (written by `ConcatAssembler`). Setting `checkpoint_sha=None`
drops the chapter→voice-pin correlation in the event log, making Phase 6
digest reports on "voice-pin drift across chapter boundaries" (stated as a
Phase 6 deferred item in 04-CONTEXT.md) impossible to compute from events
alone without cross-referencing canon frontmatter.

**Fix:** If the CriticRequest.chapter_context carries `voice_pin_shas`,
stamp the most-recent pin onto `checkpoint_sha` (match B-3 latest-pin
convention). Suggest:
```python
# critic/chapter.py: after _derive_chapter_num
voice_pin_shas = (request.chapter_context or {}).get("voice_pin_shas", [])
latest_pin = voice_pin_shas[-1] if isinstance(voice_pin_shas, list) and voice_pin_shas else None
# ... in Event(...)
checkpoint_sha=latest_pin,
```
And teach the DAG orchestrator to populate `voice_pin_shas` into
`critic_req.chapter_context`:
```python
# dag.py:508
chapter_context={
    "chapter_num": chapter_num,
    "assembly_commit_sha": None,
    "voice_pin_shas": [d.voice_pin_sha for d in drafts if d.voice_pin_sha],
},
```

---

### WR-06: `_step3_rag` commit drops tracked `resolved_model_revision.json` updates

**File:** `src/book_pipeline/chapter_assembler/dag.py:780-812`
**Issue:** The commit call is `commit_paths([], message=..., allow_empty=True)`.
The surrounding comment (lines 777-779) notes "if it is ignored, we use
`--allow-empty`" but the code unconditionally passes empty `paths` AND
`allow_empty=True`. If `indexes/resolved_model_revision.json` is actually
tracked (e.g., a future project decision to version the ingestion pointer),
its write in `_stamp_resolved_model_revision` would NOT be staged and the
commit would land empty with no meaningful audit-trail diff. Worse, `rel_revision`
is computed (line 780-783) and immediately discarded via `_ = rel_revision`
(line 812) — dead code that signals the author intended to stage it.

**Fix:** Detect tracked state at runtime and branch:
```python
# After _stamp_resolved_model_revision:
paths_to_stage: list[str] = []
try:
    check = subprocess.run(
        [self.git_binary, "ls-files", "--error-unmatch", rel_revision],
        cwd=self.repo_root, capture_output=True, text=True,
    )
    if check.returncode == 0:
        paths_to_stage.append(rel_revision)
except Exception:
    pass

try:
    commit_paths(
        paths_to_stage,
        message=f"chore(rag): reindex after ch{chapter_num:02d}",
        repo_root=self.repo_root,
        git_binary=self.git_binary,
        allow_empty=True,  # allow_empty is safe whether staged or not
    )
except GitCommitError as exc:
    ...
```
At minimum remove the dead `_ = rel_revision` assignment and document why the
staging is deliberately omitted.

---

### WR-07: Brittle Pydantic sibling-attribute injection in `ConcatAssembler.from_committed_scenes`

**File:** `src/book_pipeline/chapter_assembler/concat.py:229-231`
**Issue:**
```python
if fid is not None:
    object.__setattr__(drafts[-1], "voice_fidelity_score", fid)
```
`DraftResponse` is a Pydantic v2 `BaseModel`. Pydantic's `model_config`
default does NOT disallow extra attributes at runtime, but `object.__setattr__`
bypasses Pydantic's own validation machinery entirely — it writes directly
to `__dict__` (or `__pydantic_extra__` depending on config). This works TODAY
but silently depends on: (a) DraftResponse never adopting `frozen=True`, and
(b) Pydantic v2 not locking down arbitrary attribute writes in future patch
releases.

Downstream consumers (`assemble()` at concat.py:122) then read via
`getattr(d, "voice_fidelity_score", None)` — equally brittle. The right shape
is either an explicit optional field on DraftResponse, or a parallel
`list[float | None]` passed through.

**Fix (minimal, non-breaking):** Add `voice_fidelity_score: float | None =
None` to `DraftResponse` in `interfaces/types.py`. Phase 1's freeze policy
explicitly allows OPTIONAL additive fields. Then the assignment becomes
proper model construction:
```python
drafts.append(
    DraftResponse(
        scene_text=body,
        ...
        voice_fidelity_score=fm.get("voice_fidelity_score"),
    )
)
```

---

### WR-08: `cli/chapter.py` hardcodes `repo_root = Path.cwd()`

**File:** `src/book_pipeline/cli/chapter.py:236`
**Issue:** `repo_root = Path.cwd()` assumes the CLI is invoked from the repo
root. Every `relative_to(self.repo_root)` call in the DAG orchestrator
(dag.py:552, 695, 859) will raise `ValueError: 'X' is not in the subpath of
'Y'` if the user runs `book-pipeline chapter 4` from a subdirectory. The
Plan 04-05 rationale comment (lines 233-235) describes a prior bug fix that
switched from bare relative paths to `Path.cwd()`, but the underlying
fragility remains.

For cron-driven nightly runs (Phase 5 ORCH-01), openclaw sets cwd to the
workspace, not the repo. If `openclaw.json` lives at `~/Source/our-lady-book-
pipeline` but the cron entry doesn't `cd` first, `Path.cwd()` is wrong.

**Fix:** Discover repo root via `git rev-parse --show-toplevel`:
```python
def _discover_repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            f"book-pipeline chapter must be run inside a git repo: {exc}"
        ) from exc

repo_root = _discover_repo_root()
```
Same pattern as `openclaw.json` at repo root (STACK.md convention).

## Info

### IN-01: Error-path `prompt_hash` uses `user_prompt_sha` instead of `user_prompt` text

**File:** `src/book_pipeline/critic/chapter.py:545`; also
`src/book_pipeline/entity_extractor/opus.py:367`
**Issue:** Success path: `prompt_hash = hash_text(self._system_prompt +
"\n---\n" + user_prompt)` (full text). Failure path: `prompt_hash =
hash_text(self._system_prompt + "\n---\n" + user_prompt_sha)` (sha instead
of text). These produce different hashes for the "same" logical request,
making success/failure event correlation harder in retrospective analysis.
**Fix:** Use `user_prompt` (full text) in both paths. `user_prompt_sha` is
already an independent field on the audit record.

---

### IN-02: `ChapterCritic._call_opus_inner` try/except re-raise is a no-op

**File:** `src/book_pipeline/critic/chapter.py:399-411`
**Issue:**
```python
try:
    return self.anthropic_client.messages.parse(...)
except (APIConnectionError, APIStatusError):
    raise
```
`@tenacity.retry(reraise=True)` already propagates all exceptions. Catching
then re-raising the same exception is dead code — tenacity will re-try on
APIConnectionError/APIStatusError OR any other exception identically. Same
pattern exists in `entity_extractor/opus.py:322-332` and
`retrospective/opus.py:326-335`.
**Fix:** Remove the try/except blocks (tenacity handles retry; exceptions
propagate). If the intent is to RESTRICT retry to specific exception classes,
use `tenacity.retry_if_exception_type(...)`.

---

### IN-03: Hardcoded `attempts_made = 5` duplicates tenacity `stop_after_attempt(5)`

**File:** `src/book_pipeline/critic/chapter.py:517`
**Issue:** `attempts_made = 5` is a literal that duplicates
`tenacity.stop_after_attempt(5)` at line 393. If someone changes the stop
count, the failure-audit `attempts_made` silently lies. The
`OpusEntityExtractor` and `OpusRetrospectiveWriter` both do this correctly
(using `_TENACITY_MAX_ATTEMPTS` constant).
**Fix:** Introduce `_CHAPTER_CRITIC_MAX_ATTEMPTS = 5` at module scope and
reference it in both the decorator and the failure handler.

---

### IN-04: `_load_or_init_record` doesn't validate `chapter_num` match

**File:** `src/book_pipeline/chapter_assembler/dag.py:106-122`
**Issue:** If a stale `drafts/chapter_buffer/ch04.state.json` on disk has
`chapter_num: 3` (copy-paste residue, git restore gone sideways), the DAG
happily loads it for a `chapter 4` invocation. No assertion that the on-disk
record matches the caller-requested chapter.
**Fix:**
```python
if record.chapter_num != chapter_num:
    raise ChapterGateError(
        "chapter_num_mismatch",
        expected=chapter_num,
        actual=record.chapter_num,
    )
```

---

### IN-05: Edge case: empty YAML frontmatter raises `ValueError` in `_parse_scene_md`

**File:** `src/book_pipeline/chapter_assembler/concat.py:61-62`
**Issue:** `rest.split("\n---\n", 1)` assumes the YAML block has at least one
body line between its open and close fences. A scene file with `---\n---\n<body>`
(empty YAML block) produces `rest = "---\n<body>"`, which doesn't contain
`"\n---\n"` and so `.split(..., 1)` returns a single-element list; the tuple
unpacking `yaml_block, body = ...` raises `ValueError: not enough values to
unpack`. Unlikely but unguarded.
**Fix:** Wrap in try/except with a clear error message citing the path; or
use a regex like `re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)`
and raise `RuntimeError` with the path on mismatch.

---

### IN-06: `_parse_retro_md` (dag.py) and `_parse_retrospective_markdown`
(retrospective/opus.py) duplicate markdown parsing

**File:** `src/book_pipeline/chapter_assembler/dag.py:229-276` and
`src/book_pipeline/retrospective/opus.py:514-585`
**Issue:** Both modules define near-identical `_FRONTMATTER_RE` + `_SECTION_RE`
+ section-collection logic. The DAG's version exists because `_step4_retro`
reads prior retrospectives; the writer's version parses Opus's own output.
Drift risk on either edit — e.g., if the writer adds a 5th H2 section, the
DAG parser won't pick it up.
**Fix:** Factor into a shared helper, e.g., `book_pipeline.retrospective.parse:
parse_retrospective_markdown(markdown, *, chapter_num_hint: int) -> Retrospective`.
Both callers import it. Kernel-clean (no book-domain deps).

---

### IN-07: `from_committed_scenes` returned drafts have `tokens_in=0 / output_sha=""` (re-read artifacts)

**File:** `src/book_pipeline/chapter_assembler/concat.py:211-226`
**Issue:** The docstring (line 211-213) correctly notes "this instance
represents a RE-READ of a committed scene, not a fresh drafter invocation."
But callers downstream of `ConcatAssembler.assemble()` may consume
`d.output_sha` as a scene-content identity hash (e.g., Phase 6 dedup). An
empty string is a weaker identity than the real SHA. Not a correctness bug
for Phase 4 (chapter assembly only uses `scene_text`, `voice_pin_sha`, and
optional `voice_fidelity_score`), but a trap for future consumers.
**Fix:** Recompute `output_sha = hash_text(body)` on re-read, so the invariant
"output_sha is always the xxhash of scene_text" holds regardless of origin.
```python
drafts.append(
    DraftResponse(
        ...
        output_sha=hash_text(body),
        ...
    )
)
```

---

_Reviewed: 2026-04-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
