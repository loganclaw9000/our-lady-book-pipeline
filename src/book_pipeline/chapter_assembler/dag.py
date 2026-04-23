"""ChapterDagOrchestrator — 4-step strict post-commit DAG (LOOP-02 + LOOP-03).

Wires the Phase 4 concretes (Plans 04-02 + 04-03) into a single orchestrator:

    PENDING_SCENES
      -> ASSEMBLING (ConcatAssembler.from_committed_scenes)
      -> ASSEMBLED
      -> CHAPTER_CRITIQUING (bundler.bundle + ChapterCritic.review — FRESH pack)
      -> {CHAPTER_FAIL | CHAPTER_PASS}
      -> COMMITTING_CANON (git commit `canon(ch{NN}): commit ...`)
      -> POST_COMMIT_DAG
          step 2: OpusEntityExtractor.extract -> entity-state/*.json + commit
          step 3: reindex_entity_state_from_jsons + arc_position reindex +
                  `resolved_model_revision.json` update + (allow-empty) commit
          step 4: OpusRetrospectiveWriter.write -> retrospectives/*.md + commit
      -> DAG_COMPLETE (+ scene buffer archive + clear drafts/ch{NN}/)

Resumability: `ChapterStateRecord.dag_step` persisted via atomic tmp+rename;
re-running `orchestrator.run(N)` on a partial record resumes at `dag_step+1`.
Earlier steps are skipped (no re-invocation of the chapter critic, bundler,
assembler, or extractor if their step already committed).

Ungated posture (04-CONTEXT.md): retrospective failure is SOFT — the writer
returns a stub and we still commit step 4 to DAG_COMPLETE. Entity extraction
is HARD — EntityExtractorBlocked -> DAG_BLOCKED; next chapter gated closed.

Kernel discipline: no book-domain imports. Paths derive from int-cast
chapter numbers (path-traversal blocked). Commit messages use argv lists
(shell injection blocked). Pre-commit hooks are NEVER skipped (CLAUDE.md).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from book_pipeline.chapter_assembler.concat import ConcatAssembler
from book_pipeline.chapter_assembler.git_commit import (
    GitCommitError,
    commit_paths,
)
from book_pipeline.entity_extractor.opus import EntityExtractorBlocked
from book_pipeline.entity_extractor.schema import EntityExtractionResponse
from book_pipeline.interfaces.chapter_state_machine import transition
from book_pipeline.interfaces.types import (
    ChapterState,
    ChapterStateRecord,
    ContextPack,
    CriticRequest,
    EntityCard,
    Event,
    Retrospective,
    SceneRequest,
)
from book_pipeline.rag.reindex import reindex_entity_state_from_jsons

logger = logging.getLogger(__name__)


class ChapterGateError(Exception):
    """Pre-flight gate failure — scene count mismatch, missing files.

    Carries structured context (`expected`, `actual`, `missing`) so the
    caller (CLI wrapper) can produce an actionable error message.
    """

    def __init__(
        self,
        reason: str,
        *,
        expected: int | None = None,
        actual: int | None = None,
        missing: list[str] | None = None,
    ) -> None:
        self.reason = reason
        self.expected = expected
        self.actual = actual
        self.missing = list(missing) if missing is not None else []
        self.context: dict[str, Any] = {
            "reason": reason,
            "expected": expected,
            "actual": actual,
            "missing": self.missing,
        }
        super().__init__(f"ChapterGateError: {reason} | {self.context}")


# --------------------------------------------------------------------- #
# Helpers — filesystem + state persistence                              #
# --------------------------------------------------------------------- #


def _persist(record: ChapterStateRecord, state_path: Path) -> None:
    """Atomic tmp+rename write of a ChapterStateRecord."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp_path, state_path)


def _load_or_init_record(
    chapter_num: int, state_path: Path
) -> ChapterStateRecord:
    """Load an existing ChapterStateRecord or initialize a PENDING one."""
    if state_path.exists():
        return ChapterStateRecord.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
    return ChapterStateRecord(
        chapter_num=chapter_num,
        state=ChapterState.PENDING_SCENES,
        scene_ids=[],
        chapter_sha=None,
        dag_step=0,
        history=[],
        blockers=[],
    )


def _write_pipeline_state(
    pipeline_state_path: Path, data: dict[str, Any]
) -> None:
    """Atomic write of `.planning/pipeline_state.json` via tmp+replace."""
    pipeline_state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pipeline_state_path.with_suffix(
        pipeline_state_path.suffix + ".tmp"
    )
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp, pipeline_state_path)


def _strip_chapter_frontmatter(chapter_md: str) -> str:
    """Return the body of a chapter markdown document (post-frontmatter).

    WR-03: if the chapter markdown starts with the opening `---\\n` fence
    but has NO closing `\\n---\\n`, raise — silently returning the whole
    document would leak frontmatter YAML (chapter_num, voice_pin_shas,
    assembled_from_scenes) into the entity extractor's user prompt, and
    Opus would extract those keys as entities ("chapter_num" cards are
    corrosive downstream).
    """
    if not chapter_md.startswith("---\n"):
        return chapter_md  # no frontmatter at all: OK as-is
    _, rest = chapter_md.split("---\n", 1)
    # Second `---\n` divider ends the frontmatter block.
    if "\n---\n" not in rest:
        raise RuntimeError(
            "chapter markdown has opening `---` fence without closing "
            "fence; refusing to ship frontmatter-tainted text to the "
            "entity extractor"
        )
    _, body = rest.split("\n---\n", 1)
    return body


def _load_chapter_events(
    events_jsonl_path: Path, chapter_num: int
) -> list[Event]:
    """Stream events.jsonl and filter by caller_context.chapter|chapter_num.

    Tolerates both key names:
      - `caller_context.chapter` stamped by the scene loop (Plan 03-07).
      - `caller_context.chapter_num` stamped by chapter critic (Plan 04-02).
    Malformed lines are skipped.
    """
    out: list[Event] = []
    if not events_jsonl_path.exists():
        return out
    with events_jsonl_path.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(
                    "dag: skipping malformed events.jsonl line"
                )
                continue
            caller = payload.get("caller_context") or {}
            ch = caller.get("chapter")
            if ch is None:
                ch = caller.get("chapter_num")
            if ch != chapter_num:
                continue
            try:
                out.append(Event.model_validate(payload))
            except Exception:
                logger.exception(
                    "dag: events.jsonl row didn't validate as Event; "
                    "skipping"
                )
                continue
    return out


# --------------------------------------------------------------------- #
# Retrospective markdown renderer + parser                              #
# --------------------------------------------------------------------- #


def _render_retrospective_md(retro: Retrospective) -> str:
    """Serialize a Retrospective to markdown with YAML frontmatter."""
    import yaml

    fm: dict[str, Any] = {
        "chapter_num": retro.chapter_num,
        "candidate_theses": list(retro.candidate_theses),
    }
    fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    return (
        f"---\n{fm_text}---\n\n"
        f"# Chapter {retro.chapter_num:02d} Retrospective\n\n"
        f"## What Worked\n{retro.what_worked}\n\n"
        f"## What Drifted\n{retro.what_didnt}\n\n"
        f"## Emerging Patterns\n{retro.pattern}\n\n"
        f"## Open Questions for Next Chapter\n"
        f"{_open_questions_section(retro)}\n"
    )


def _open_questions_section(retro: Retrospective) -> str:
    if not retro.candidate_theses:
        return "(none)"
    lines: list[str] = []
    for entry in retro.candidate_theses:
        desc = str(entry.get("description", "")) if isinstance(entry, dict) else str(entry)
        if desc:
            lines.append(f"- {desc}")
    return "\n".join(lines) if lines else "(none)"


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
_SECTION_RE = re.compile(
    r"^##\s+(What Worked|What Drifted|Emerging Patterns|Open Questions for Next Chapter)\s*\n(.*?)(?=\n##\s+|\Z)",
    re.DOTALL | re.MULTILINE,
)


def _parse_retro_md(path: Path) -> Retrospective:
    """Inverse of _render_retrospective_md for loading prior retros."""
    import yaml

    text = path.read_text(encoding="utf-8")
    frontmatter: dict[str, Any] = {}
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m is not None:
        try:
            loaded = yaml.safe_load(m.group(1))
            if isinstance(loaded, dict):
                frontmatter = loaded
        except yaml.YAMLError:
            frontmatter = {}
        body = m.group(2)
    sections: dict[str, str] = {}
    for header, section_text in _SECTION_RE.findall(body):
        sections[header] = section_text.strip()
    try:
        ch_num = int(frontmatter.get("chapter_num", 0))
    except (TypeError, ValueError):
        ch_num = 0
    theses_raw = frontmatter.get("candidate_theses")
    theses: list[dict[str, object]] = []
    if isinstance(theses_raw, list):
        for idx, entry in enumerate(theses_raw, start=1):
            if isinstance(entry, dict):
                theses.append(
                    {
                        "id": str(entry.get("id", f"q{idx}")),
                        "description": str(entry.get("description", "")),
                    }
                )
    return Retrospective(
        chapter_num=ch_num,
        what_worked=sections.get("What Worked", ""),
        what_didnt=sections.get("What Drifted", ""),
        pattern=sections.get("Emerging Patterns", ""),
        candidate_theses=theses,
    )


# --------------------------------------------------------------------- #
# Retrospective-writer call shim                                         #
# --------------------------------------------------------------------- #


def _call_retrospective_writer(
    writer: Any,
    chapter_text: str,
    chapter_events: list[Event],
    prior_retros: list[Retrospective],
    *,
    chapter_num: int,
) -> Retrospective:
    """Call ``writer.write`` with ``chapter_num`` when supported.

    WR-04: OpusRetrospectiveWriter.write() accepts a keyword-only
    ``chapter_num`` (authoritative path/body consistency). Legacy test
    fakes may implement the older 3-positional signature; retry without
    the kwarg on TypeError so those continue to work unchanged.
    """
    try:
        return writer.write(
            chapter_text,
            chapter_events,
            prior_retros,
            chapter_num=chapter_num,
        )
    except TypeError:
        return writer.write(chapter_text, chapter_events, prior_retros)


# --------------------------------------------------------------------- #
# Orchestrator                                                          #
# --------------------------------------------------------------------- #


class ChapterDagOrchestrator:
    """Drive the 4-step post-commit DAG for a single chapter.

    Constructor DI of the 4 concrete Phase 4 writers + bundler + retrievers
    + event logger + filesystem anchors. Every component is swappable per
    test fixture or Plan 04-05 CLI composition root.

    Public surface:
      - `run(chapter_num, *, expected_scene_count=None) -> ChapterStateRecord`
        drives the DAG end-to-end; terminal state in
        {DAG_COMPLETE, CHAPTER_FAIL, DAG_BLOCKED}.
    """

    def __init__(
        self,
        *,
        assembler: Any,
        chapter_critic: Any,
        entity_extractor: Any,
        retrospective_writer: Any,
        bundler: Any,
        retrievers: list[Any],
        embedder: Any,
        event_logger: Any | None,
        repo_root: Path,
        canon_dir: Path,
        entity_state_dir: Path,
        retros_dir: Path,
        scene_buffer_dir: Path,
        chapter_buffer_dir: Path,
        commit_dir: Path,
        indexes_dir: Path,
        pipeline_state_path: Path,
        events_jsonl_path: Path,
        rubric_version: str = "chapter.v1",
        git_binary: str = "git",
    ) -> None:
        self.assembler = assembler
        self.chapter_critic = chapter_critic
        self.entity_extractor = entity_extractor
        self.retrospective_writer = retrospective_writer
        self.bundler = bundler
        self.retrievers = retrievers
        self.embedder = embedder
        self.event_logger = event_logger
        self.repo_root = Path(repo_root)
        self.canon_dir = Path(canon_dir)
        self.entity_state_dir = Path(entity_state_dir)
        self.retros_dir = Path(retros_dir)
        self.scene_buffer_dir = Path(scene_buffer_dir)
        self.chapter_buffer_dir = Path(chapter_buffer_dir)
        self.commit_dir = Path(commit_dir)
        self.indexes_dir = Path(indexes_dir)
        self.pipeline_state_path = Path(pipeline_state_path)
        self.events_jsonl_path = Path(events_jsonl_path)
        self.rubric_version = rubric_version
        self.git_binary = git_binary

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def run(
        self,
        chapter_num: int,
        *,
        expected_scene_count: int | None = None,
    ) -> ChapterStateRecord:
        """Execute the 4-step DAG to a terminal ChapterState.

        Raises:
            ChapterGateError: expected_scene_count mismatch or missing dir.
        """
        # Int-cast sanitization (T-04-04: path traversal blocked).
        ch = int(chapter_num)

        # Pre-flight scene-count gate.
        self._preflight_scene_count_gate(ch, expected_scene_count)

        state_path = self._chapter_state_path(ch)
        record = _load_or_init_record(ch, state_path)

        # Step 1 — canon commit.
        if record.dag_step < 1:
            record = self._step1_canon(record, state_path, ch)
            if record.state == ChapterState.CHAPTER_FAIL:
                return record

        # Step 2 — entity extraction + commit.
        if record.dag_step < 2:
            record = self._step2_entity(record, state_path, ch)
            if record.state == ChapterState.DAG_BLOCKED:
                return record

        # Step 3 — RAG reindex + commit (allow-empty if no tracked file changed).
        if record.dag_step < 3:
            record = self._step3_rag(record, state_path, ch)
            if record.state == ChapterState.DAG_BLOCKED:
                return record

        # Step 4 — retrospective + commit (ungated).
        if record.dag_step < 4:
            record = self._step4_retro(record, state_path, ch)

        # Scene buffer archival (post-DAG bookkeeping only).
        self._archive_scene_buffer(ch)
        self._clear_chapter_draft_dir(ch)

        return record

    # ------------------------------------------------------------------ #
    # Pre-flight                                                         #
    # ------------------------------------------------------------------ #

    def _preflight_scene_count_gate(
        self, chapter_num: int, expected: int | None
    ) -> None:
        ch_dir = self.commit_dir / f"ch{chapter_num:02d}"
        if not ch_dir.is_dir():
            if expected is None:
                # First-pass path — maybe we're resuming from a committed state.
                # Only raise if dag_step < 1.
                state_path = self._chapter_state_path(chapter_num)
                record = _load_or_init_record(chapter_num, state_path)
                if record.dag_step >= 1:
                    return
            raise ChapterGateError(
                "missing_chapter_dir",
                expected=expected,
                actual=0,
                missing=[f"ch{chapter_num:02d}/"],
            )
        # Count scene md files.
        scene_re = re.compile(
            rf"^ch{chapter_num:02d}_sc(\d+)\.md$"
        )
        found: set[int] = set()
        for path in ch_dir.iterdir():
            if not path.is_file():
                continue
            m = scene_re.match(path.name)
            if m is not None:
                found.add(int(m.group(1)))
        actual = len(found)
        if expected is None:
            if actual < 1:
                # Resume path tolerance.
                state_path = self._chapter_state_path(chapter_num)
                record = _load_or_init_record(chapter_num, state_path)
                if record.dag_step >= 1:
                    return
                raise ChapterGateError(
                    "no_scenes_found",
                    expected=1,
                    actual=0,
                    missing=[f"ch{chapter_num:02d}_sc??.md"],
                )
            return
        if actual != expected:
            # List missing scene ids.
            expected_ids = {i + 1 for i in range(expected)}
            missing_ids = sorted(expected_ids - found)
            missing_names = [
                f"ch{chapter_num:02d}_sc{i:02d}" for i in missing_ids
            ]
            raise ChapterGateError(
                "scene_count_mismatch",
                expected=expected,
                actual=actual,
                missing=missing_names,
            )

    # ------------------------------------------------------------------ #
    # Step 1 — canon commit                                              #
    # ------------------------------------------------------------------ #

    def _step1_canon(
        self, record: ChapterStateRecord, state_path: Path, chapter_num: int
    ) -> ChapterStateRecord:
        # PENDING_SCENES -> ASSEMBLING.
        record = transition(record, ChapterState.ASSEMBLING, "start concat")
        _persist(record, state_path)

        # Run the assembler.
        drafts, chapter_text = self._invoke_assembler(chapter_num)
        scene_ids = [
            f"ch{chapter_num:02d}_sc{i + 1:02d}"
            for i in range(len(drafts))
        ]
        record = record.model_copy(update={"scene_ids": scene_ids})

        record = transition(record, ChapterState.ASSEMBLED, "concat ok")
        _persist(record, state_path)

        record = transition(
            record, ChapterState.CHAPTER_CRITIQUING, "fresh pack"
        )
        _persist(record, state_path)

        # Build a FRESH chapter-scoped pack — caller-contract invariant (C-4
        # mitigation). SceneRequest captures chapter-level routing.
        primary_pov = _first_frontmatter_value(drafts, "pov") or "unknown"
        first_date = _first_frontmatter_value(drafts, "date_iso") or "1519-01-01"
        first_location = (
            _first_frontmatter_value(drafts, "location") or "unknown"
        )
        chapter_scene_request = SceneRequest(
            chapter=chapter_num,
            scene_index=0,
            pov=primary_pov,
            date_iso=first_date,
            location=first_location,
            beat_function="chapter_overview",
        )
        chapter_pack: ContextPack = self.bundler.bundle(
            chapter_scene_request, self.retrievers
        )

        # Call the critic. WR-05: thread voice_pin_shas so ChapterCritic
        # can stamp Event.checkpoint_sha with the most-recent pin (V-3
        # continuity at chapter grain — matches B-3 latest-pin convention
        # and lets Phase 6 digest compute voice-pin drift across chapter
        # boundaries from events alone).
        voice_pin_shas_from_drafts = [
            d.voice_pin_sha for d in drafts if d.voice_pin_sha
        ]
        critic_req = CriticRequest(
            scene_text=chapter_text,
            context_pack=chapter_pack,
            rubric_id="chapter.v1",
            rubric_version=self.rubric_version,
            chapter_context={
                "chapter_num": chapter_num,
                "assembly_commit_sha": None,
                "voice_pin_shas": voice_pin_shas_from_drafts,
            },
        )
        critic_resp = self.chapter_critic.review(critic_req)

        if not critic_resp.overall_pass:
            record = transition(
                record,
                ChapterState.CHAPTER_FAIL,
                note="axis fail",
            )
            record = record.model_copy(
                update={
                    "blockers": [
                        *record.blockers,
                        "chapter_critic_axis_fail",
                    ]
                }
            )
            _persist(record, state_path)
            return record

        # Update chapter frontmatter's chapter_critic_pass = True in the
        # assembled markdown. We re-render by splitting frontmatter + body.
        chapter_text_canon = _stamp_chapter_critic_pass(
            chapter_text, chapter_critic_pass=True
        )

        record = transition(record, ChapterState.CHAPTER_PASS, "5/5 >=3")
        _persist(record, state_path)

        record = transition(
            record, ChapterState.COMMITTING_CANON, "git commit"
        )
        _persist(record, state_path)

        canon_path = self.canon_dir / f"chapter_{chapter_num:02d}.md"
        canon_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_canon = canon_path.with_suffix(".md.tmp")
        tmp_canon.write_text(chapter_text_canon, encoding="utf-8")
        os.replace(tmp_canon, canon_path)

        rel_canon = canon_path.relative_to(self.repo_root).as_posix()
        try:
            chapter_sha = commit_paths(
                [rel_canon],
                message=f"canon(ch{chapter_num:02d}): commit chapter {chapter_num}",
                repo_root=self.repo_root,
                git_binary=self.git_binary,
            )
        except GitCommitError as exc:
            logger.error("step 1 canon commit failed: %s", exc)
            record = transition(
                record,
                ChapterState.DAG_BLOCKED,
                note="canon_commit_failed",
            )
            record = record.model_copy(
                update={
                    "blockers": [
                        *record.blockers,
                        f"canon_commit:{exc}",
                    ]
                }
            )
            _persist(record, state_path)
            self._write_pipeline_state_view(record)
            return record

        record = record.model_copy(
            update={"chapter_sha": chapter_sha, "dag_step": 1}
        )
        _persist(record, state_path)

        record = transition(
            record,
            ChapterState.POST_COMMIT_DAG,
            note="entity extraction",
        )
        _persist(record, state_path)
        self._write_pipeline_state_view(record)

        return record

    # ------------------------------------------------------------------ #
    # Step 2 — entity extraction + commit                                #
    # ------------------------------------------------------------------ #

    def _step2_entity(
        self, record: ChapterStateRecord, state_path: Path, chapter_num: int
    ) -> ChapterStateRecord:
        assert record.chapter_sha is not None, (
            "step 2 requires chapter_sha from step 1"
        )
        canon_path = self.canon_dir / f"chapter_{chapter_num:02d}.md"
        chapter_text = _strip_chapter_frontmatter(
            canon_path.read_text(encoding="utf-8")
        )

        # Load prior cards (all chapters < chapter_num).
        prior_cards: list[EntityCard] = []
        if self.entity_state_dir.is_dir():
            for path in sorted(self.entity_state_dir.iterdir()):
                if not path.is_file() or not path.name.startswith("chapter_"):
                    continue
                if path.suffix != ".json":
                    continue
                if path.name == f"chapter_{chapter_num:02d}_entities.json":
                    # Ourselves; skip on resume.
                    continue
                try:
                    resp = EntityExtractionResponse.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                except Exception:
                    logger.exception(
                        "step 2: skipping malformed prior entity json at %s",
                        path,
                    )
                    continue
                prior_cards.extend(resp.entities)

        try:
            new_cards = self.entity_extractor.extract(
                chapter_text,
                chapter_num,
                record.chapter_sha,
                prior_cards,
            )
        except EntityExtractorBlocked as exc:
            record = transition(
                record,
                ChapterState.DAG_BLOCKED,
                note=f"entity_extractor_blocked:{exc.reason}",
            )
            record = record.model_copy(
                update={
                    "blockers": [
                        *record.blockers,
                        f"entity_extraction:{exc.reason}",
                    ]
                }
            )
            _persist(record, state_path)
            self._write_pipeline_state_view(
                record, last_hard_block=f"entity_extraction:{exc.reason}"
            )
            return record
        except Exception as exc:
            logger.exception("step 2: unexpected entity extractor failure")
            record = transition(
                record,
                ChapterState.DAG_BLOCKED,
                note="entity_extractor_unexpected",
            )
            record = record.model_copy(
                update={
                    "blockers": [
                        *record.blockers,
                        f"entity_extraction:unexpected:{exc}",
                    ]
                }
            )
            _persist(record, state_path)
            self._write_pipeline_state_view(
                record, last_hard_block="entity_extraction:unexpected"
            )
            return record

        # Write per-chapter entities JSON atomically.
        out = EntityExtractionResponse(
            entities=list(new_cards),
            chapter_num=chapter_num,
            extraction_timestamp=_now_iso(),
        )
        json_path = (
            self.entity_state_dir / f"chapter_{chapter_num:02d}_entities.json"
        )
        json_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = json_path.with_suffix(".json.tmp")
        tmp.write_text(
            out.model_dump_json(indent=2), encoding="utf-8"
        )
        os.replace(tmp, json_path)

        rel = json_path.relative_to(self.repo_root).as_posix()
        try:
            commit_paths(
                [rel],
                message=f"chore(entity-state): ch{chapter_num:02d} extraction",
                repo_root=self.repo_root,
                git_binary=self.git_binary,
            )
        except GitCommitError as exc:
            logger.error("step 2 entity-state commit failed: %s", exc)
            record = transition(
                record,
                ChapterState.DAG_BLOCKED,
                note="entity_state_commit_failed",
            )
            record = record.model_copy(
                update={
                    "blockers": [
                        *record.blockers,
                        f"entity_state_commit:{exc}",
                    ]
                }
            )
            _persist(record, state_path)
            self._write_pipeline_state_view(
                record, last_hard_block="entity_state_commit"
            )
            return record

        record = record.model_copy(update={"dag_step": 2})
        _persist(record, state_path)
        self._write_pipeline_state_view(record)
        return record

    # ------------------------------------------------------------------ #
    # Step 3 — RAG reindex                                               #
    # ------------------------------------------------------------------ #

    def _step3_rag(
        self, record: ChapterStateRecord, state_path: Path, chapter_num: int
    ) -> ChapterStateRecord:
        try:
            reindex_entity_state_from_jsons(
                entity_state_dir=self.entity_state_dir,
                indexes_dir=self.indexes_dir,
                embedder=self.embedder,
            )
            # Reindex any retriever whose name is 'arc_position'.
            for r in self.retrievers:
                if getattr(r, "name", None) == "arc_position":
                    try:
                        r.reindex()
                    except Exception as inner:
                        logger.exception(
                            "step 3: arc_position reindex failed"
                        )
                        raise RuntimeError(
                            f"arc_position_reindex_failed: {inner}"
                        ) from inner
            # Touch `resolved_model_revision.json` (tracked? — see note below).
            self._stamp_resolved_model_revision(chapter_num)
        except Exception as exc:
            logger.exception("step 3: RAG reindex failed")
            record = transition(
                record,
                ChapterState.DAG_BLOCKED,
                note="rag_reindex_failed",
            )
            record = record.model_copy(
                update={
                    "blockers": [
                        *record.blockers,
                        f"rag_reindex:{exc}",
                    ]
                }
            )
            _persist(record, state_path)
            self._write_pipeline_state_view(
                record, last_hard_block="rag_reindex"
            )
            return record

        # Commit. `indexes/resolved_model_revision.json` is typically
        # gitignored per the existing .gitignore — but if a project
        # decision later tracks the ingestion-pointer file, we stage it
        # so the audit-trail commit carries a meaningful diff. WR-06:
        # detect the tracked state at runtime (via `git ls-files
        # --error-unmatch`) and stage only when tracked. `allow_empty`
        # stays True so the commit lands either way.
        rel_revision = (
            self.indexes_dir.relative_to(self.repo_root).as_posix()
            + "/resolved_model_revision.json"
        )
        paths_to_stage: list[str] = []
        try:
            check = subprocess.run(
                [
                    self.git_binary,
                    "ls-files",
                    "--error-unmatch",
                    rel_revision,
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if check.returncode == 0:
                paths_to_stage.append(rel_revision)
        except Exception:
            # Best-effort detection — if `git ls-files` itself fails we
            # fall back to the allow-empty audit commit (prior behavior).
            logger.exception(
                "step 3: failed to probe tracked state of %s; "
                "proceeding with allow-empty audit commit",
                rel_revision,
            )

        try:
            commit_paths(
                paths_to_stage,
                message=f"chore(rag): reindex after ch{chapter_num:02d}",
                repo_root=self.repo_root,
                git_binary=self.git_binary,
                allow_empty=True,
            )
        except GitCommitError as exc:
            logger.error("step 3 rag commit failed: %s", exc)
            record = transition(
                record,
                ChapterState.DAG_BLOCKED,
                note="rag_commit_failed",
            )
            record = record.model_copy(
                update={
                    "blockers": [*record.blockers, f"rag_commit:{exc}"]
                }
            )
            _persist(record, state_path)
            self._write_pipeline_state_view(
                record, last_hard_block="rag_commit"
            )
            return record

        record = record.model_copy(update={"dag_step": 3})
        _persist(record, state_path)
        self._write_pipeline_state_view(record)
        return record

    # ------------------------------------------------------------------ #
    # Step 4 — retrospective                                             #
    # ------------------------------------------------------------------ #

    def _step4_retro(
        self, record: ChapterStateRecord, state_path: Path, chapter_num: int
    ) -> ChapterStateRecord:
        canon_path = self.canon_dir / f"chapter_{chapter_num:02d}.md"
        chapter_text = canon_path.read_text(encoding="utf-8")

        chapter_events = _load_chapter_events(
            self.events_jsonl_path, chapter_num
        )
        prior_retros: list[Retrospective] = []
        if self.retros_dir.is_dir():
            for path in sorted(self.retros_dir.iterdir()):
                if not path.is_file() or path.suffix != ".md":
                    continue
                if path.name == f"chapter_{chapter_num:02d}.md":
                    continue
                try:
                    prior_retros.append(_parse_retro_md(path))
                except Exception:
                    logger.exception(
                        "step 4: skipping malformed prior retro at %s", path
                    )
                    continue

        # UNGATED — never raises. Writer returns a stub on failure.
        # WR-04: pass the authoritative chapter_num so the retrospective's
        # body cannot diverge from the file path the DAG is about to write
        # to (retros_dir / f"chapter_{chapter_num:02d}.md"). The writer
        # retains its inference path as a fallback for legacy callers.
        retro = _call_retrospective_writer(
            self.retrospective_writer,
            chapter_text,
            chapter_events,
            prior_retros,
            chapter_num=chapter_num,
        )

        md = _render_retrospective_md(retro)
        retro_path = self.retros_dir / f"chapter_{chapter_num:02d}.md"
        retro_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = retro_path.with_suffix(".md.tmp")
        tmp.write_text(md, encoding="utf-8")
        os.replace(tmp, retro_path)

        rel = retro_path.relative_to(self.repo_root).as_posix()
        try:
            commit_paths(
                [rel],
                message=f"docs(retro): ch{chapter_num:02d}",
                repo_root=self.repo_root,
                git_binary=self.git_binary,
            )
        except GitCommitError as exc:
            logger.error("step 4 retro commit failed: %s", exc)
            # Retrospective is ungated — a commit failure here still
            # transitions to DAG_COMPLETE. CONTEXT.md says retrospective
            # failure -> log + skip; next chapter unblocks. Treat as
            # DAG_COMPLETE but add a blocker tag for digest visibility so
            # the retrospective-untracked state is observable downstream
            # (WR-01: without this the blocker tag was described in the
            # comment but never actually appended).
            logger.warning(
                "retrospective commit failed (ungated); proceeding to "
                "DAG_COMPLETE with blocker tag"
            )
            record = record.model_copy(
                update={
                    "blockers": [
                        *record.blockers,
                        f"retro_commit_failed:{exc}",
                    ]
                }
            )

        record = record.model_copy(update={"dag_step": 4})
        record = transition(
            record, ChapterState.DAG_COMPLETE, "retro written"
        )
        _persist(record, state_path)
        self._write_pipeline_state_view(record)
        return record

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _chapter_state_path(self, chapter_num: int) -> Path:
        return self.chapter_buffer_dir / f"ch{chapter_num:02d}.state.json"

    def _invoke_assembler(
        self, chapter_num: int
    ) -> tuple[list[Any], str]:
        """Call the injected assembler's `from_committed_scenes`.

        Supports both the canonical ConcatAssembler (classmethod) and test-
        supplied wrapper fakes that expose an instance method of the same
        name. If neither attribute is available we fall back to calling
        ConcatAssembler directly.
        """
        from_committed = getattr(
            self.assembler, "from_committed_scenes", None
        )
        if callable(from_committed):
            result: tuple[list[Any], str] = from_committed(
                chapter_num, self.commit_dir
            )
            return result
        return ConcatAssembler.from_committed_scenes(
            chapter_num, self.commit_dir
        )

    def _write_pipeline_state_view(
        self,
        record: ChapterStateRecord,
        *,
        last_hard_block: str | None = None,
    ) -> None:
        dag_complete = (
            record.state == ChapterState.DAG_COMPLETE
            and record.dag_step == 4
        )
        data = {
            "last_committed_chapter": record.chapter_num,
            "last_committed_dag_step": record.dag_step,
            "dag_complete": dag_complete,
            "last_hard_block": last_hard_block,
        }
        _write_pipeline_state(self.pipeline_state_path, data)

    def _stamp_resolved_model_revision(self, chapter_num: int) -> None:
        """Update `indexes/resolved_model_revision.json` with the latest reindex
        chapter number. The file is gitignored, so we emit an allow-empty
        commit when tracking it is not possible."""
        path = self.indexes_dir / "resolved_model_revision.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    existing = {}
            except json.JSONDecodeError:
                existing = {}
        existing["last_reindex_chapter"] = int(chapter_num)
        existing["last_reindex_ts_iso"] = _now_iso()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def _archive_scene_buffer(self, chapter_num: int) -> None:
        """Move drafts/scene_buffer/ch{NN}/* into archive/ch{NN}/ (gitignored)."""
        src = self.scene_buffer_dir / f"ch{chapter_num:02d}"
        if not src.is_dir():
            return
        dst = self.scene_buffer_dir / "archive" / f"ch{chapter_num:02d}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            # Merge rather than clobber on re-run.
            for child in src.iterdir():
                target = dst / child.name
                if child.is_dir():
                    shutil.copytree(child, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(child, target)
            shutil.rmtree(src)
        else:
            shutil.move(str(src), str(dst))

    def _clear_chapter_draft_dir(self, chapter_num: int) -> None:
        """Remove drafts/ch{NN}/*.md after DAG_COMPLETE (scenes are in canon)."""
        ch_dir = self.commit_dir / f"ch{chapter_num:02d}"
        if not ch_dir.is_dir():
            return
        for child in list(ch_dir.iterdir()):
            if child.is_file() and child.suffix == ".md":
                try:
                    child.unlink()
                except OSError:
                    logger.exception(
                        "could not remove %s during post-DAG cleanup", child
                    )


# --------------------------------------------------------------------- #
# Frontmatter helpers                                                   #
# --------------------------------------------------------------------- #


def _first_frontmatter_value(
    drafts: list[Any], key: str
) -> str | None:
    """Return the first draft's frontmatter value for `key`, or None."""
    for d in drafts:
        val = getattr(d, key, None)
        if isinstance(val, str) and val:
            return val
    return None


def _stamp_chapter_critic_pass(chapter_md: str, *, chapter_critic_pass: bool) -> str:
    """Rewrite the chapter frontmatter block with `chapter_critic_pass` set."""
    import yaml

    if not chapter_md.startswith("---\n"):
        return chapter_md
    _, rest = chapter_md.split("---\n", 1)
    if "\n---\n" not in rest:
        return chapter_md
    fm_text, body = rest.split("\n---\n", 1)
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return chapter_md
    fm["chapter_critic_pass"] = chapter_critic_pass
    new_fm_text = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return f"---\n{new_fm_text}---\n{body}"


def _now_iso() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


__all__ = [
    "ChapterDagOrchestrator",
    "ChapterGateError",
    "GitCommitError",
]
