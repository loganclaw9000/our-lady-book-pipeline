"""ConcatAssembler — deterministic scene-join for LOOP-02.

Joins committed scene drafts (`drafts/ch{NN}/*.md` with YAML frontmatter per
B-3 invariant from Plan 03-07) into a single chapter markdown document:

  ---
  <chapter frontmatter yaml block>
  ---

  <!-- scene: ch{NN}_sc{II} -->
  <scene 1 body>

  ---

  <!-- scene: ch{NN}_sc{II+1} -->
  <scene 2 body>
  ...

The assembler is a PURE deterministic function — identical input lists produce
byte-identical output strings (no timestamps in output, no sort instability).
Chapter-level frontmatter aggregates scene-level metadata (voice_pin_shas,
word_count, voice_fidelity_aggregate, …) so Plan 04-04's DAG orchestrator
can read a single file at chapter scale.

C-4 mitigation boundary: this module produces only the assembled text. It
does NOT produce, reuse, or touch any ContextPack — the caller in Plan 04-04
runs a FRESH `bundler.bundle()` against a chapter-scoped SceneRequest before
handing the result to ChapterCritic. This separation is what breaks
drafter/critic pack collusion (PITFALLS C-4).

Kernel discipline: no book-domain imports. Scene-file discovery uses a
regex-validated filename pattern — path-traversal blocked per T-04-02-01.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from book_pipeline.interfaces.types import DraftResponse

# Regex-validated filename pattern for `from_committed_scenes`. Filenames not
# matching this pattern are ignored (not an error — the dir may carry sibling
# assets like .gitkeep).
_SCENE_MD_RE = re.compile(r"^ch(\d+)_sc(\d+)\.md$")


def _parse_scene_md(path: Path) -> tuple[dict[str, Any], str]:
    """Parse `---\\n<yaml>\\n---\\n<body>` markdown into (frontmatter, body).

    Matches the shape produced by Plan 03-07's `cli.draft._commit_scene`.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise RuntimeError(
            f"scene md at {path} is missing YAML frontmatter fence — "
            f"B-3 invariant requires `---\\n<yaml>\\n---\\n<body>` shape."
        )
    _, rest = text.split("---\n", 1)
    yaml_block, body = rest.split("\n---\n", 1)
    fm: dict[str, Any] = yaml.safe_load(yaml_block) or {}
    return fm, body


class ConcatAssembler:
    """Concrete ChapterAssembler: deterministic scene-join + frontmatter aggregation.

    Satisfies the frozen `book_pipeline.interfaces.chapter_assembler.ChapterAssembler`
    Protocol at runtime (`isinstance(a, ChapterAssembler)` → True).

    Public API:
      - `assemble(scene_drafts, chapter_num)` — pure join, matches Protocol.
      - `from_committed_scenes(chapter_num, commit_dir)` — classmethod sibling
        that reads `commit_dir/ch{NN:02d}/*.md`, builds DraftResponse list,
        and calls `.assemble(...)`. Returns `(drafts, assembled_text)`.
    """

    def assemble(self, scene_drafts: list[DraftResponse], chapter_num: int) -> str:
        """Join `scene_drafts` in caller-provided order into a chapter document.

        Preconditions:
          - `scene_drafts` is non-empty.
          - Caller guarantees list order matches `scene_index` 1..N; the
            assembler derives scene ids by position (`ch{NN}_sc{i+1:02d}`).
          - `d.voice_pin_sha` is populated per B-3 (required for COMMITTED scenes).

        Postconditions:
          - Output starts with a YAML frontmatter block.
          - Scene bodies are separated by `\\n\\n---\\n\\n`.
          - Each scene body is preceded by an HTML comment marker
            `<!-- scene: ch{NN}_sc{II} -->` for Phase 6 traceability.
          - No Event emitted — this is a pure (non-LLM) operation.
        """
        if not scene_drafts:
            raise ValueError("ConcatAssembler.assemble: scene_drafts is empty")

        # Defensive copy of input (paranoid — the list shouldn't be mutated
        # anywhere, but a shallow copy insulates future edits from caller state).
        drafts = list(scene_drafts)

        # Aggregate chapter frontmatter.
        scene_ids: list[str] = [
            f"ch{chapter_num:02d}_sc{i + 1:02d}" for i in range(len(drafts))
        ]
        word_count = sum(len(d.scene_text.split()) for d in drafts)

        # Dedup voice_pin_shas preserving first-seen order (size > 1 signals
        # a mid-chapter pin upgrade — flagged in retrospective per CONTEXT.md).
        pin_shas: list[str] = []
        for d in drafts:
            pin = d.voice_pin_sha
            if pin is not None and pin not in pin_shas:
                pin_shas.append(pin)

        # Voice-fidelity aggregate: mean of per-scene scores when ALL present;
        # None if any scene is missing the attribute.
        fidelities: list[float] = []
        any_missing = False
        for d in drafts:
            val = getattr(d, "voice_fidelity_score", None)
            if val is None:
                any_missing = True
                break
            fidelities.append(float(val))
        voice_fidelity_aggregate: float | None = (
            None if any_missing or not fidelities else sum(fidelities) / len(fidelities)
        )

        frontmatter: dict[str, Any] = {
            "chapter_num": chapter_num,
            "assembled_from_scenes": scene_ids,
            "chapter_critic_pass": None,  # filled by DAG orchestrator Plan 04-04
            "voice_fidelity_aggregate": voice_fidelity_aggregate,
            "word_count": word_count,
            "thesis_events": [],  # filled by retrospective writer Plan 04-03
            "voice_pin_shas": pin_shas,
        }
        yaml_text = yaml.safe_dump(
            frontmatter,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )

        # Build scene blocks: HTML marker + scene body.
        scene_blocks: list[str] = []
        for sid, d in zip(scene_ids, drafts, strict=True):
            scene_blocks.append(f"<!-- scene: {sid} -->\n{d.scene_text}")

        body = "\n\n---\n\n".join(scene_blocks)

        return f"---\n{yaml_text}---\n\n{body}\n"

    # ------------------------------------------------------------------ #
    # Sibling classmethod — disk → (drafts, assembled_text)              #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_committed_scenes(
        cls,
        chapter_num: int,
        commit_dir: Path,
    ) -> tuple[list[DraftResponse], str]:
        """Read `commit_dir/ch{NN:02d}/*.md`, build DraftResponse list, assemble.

        Returns `(drafts, assembled_chapter_text)`. The drafts are ordered by
        filename-parsed `scene_index` (ascending). Raises FileNotFoundError
        if the chapter dir does not exist (fail-fast — Plan 04-04's DAG
        orchestrator gate-checks before calling).

        Raises RuntimeError if any scene md is missing the `voice_pin_sha`
        frontmatter key (B-3 invariant violation — T-04-02-01 mitigation).
        """
        chapter_dir = Path(commit_dir) / f"ch{chapter_num:02d}"
        if not chapter_dir.is_dir():
            raise FileNotFoundError(
                f"committed-scene dir not found: {chapter_dir} "
                f"(expected `{commit_dir}/ch{chapter_num:02d}/`)"
            )

        # Narrow regex to THIS chapter only (WR-02). Matches the gate in
        # ChapterDagOrchestrator._preflight_scene_count_gate — a stray
        # ch01_sc01.md left in drafts/ch02/ (crash residue, manual copy-
        # paste, git rebase artifact) must NOT cross-contaminate the ch02
        # assembly. Previous code used the module-level _SCENE_MD_RE which
        # accepted any chNN prefix regardless of the chapter_dir location.
        scene_re = re.compile(rf"^ch{chapter_num:02d}_sc(\d+)\.md$")
        entries: list[tuple[int, Path]] = []
        for path in chapter_dir.iterdir():
            if not path.is_file():
                continue
            m = scene_re.match(path.name)
            if m is None:
                continue
            sc_idx = int(m.group(1))
            entries.append((sc_idx, path))
        entries.sort(key=lambda t: t[0])

        if not entries:
            raise FileNotFoundError(
                f"no scene md files matching `ch{chapter_num:02d}_scNN.md` "
                f"found under {chapter_dir}"
            )

        drafts: list[DraftResponse] = []
        for _sc_idx, path in entries:
            fm, body = _parse_scene_md(path)
            pin_sha = fm.get("voice_pin_sha")
            if not isinstance(pin_sha, str) or not pin_sha:
                raise RuntimeError(
                    f"scene md {path} missing voice_pin_sha frontmatter — "
                    f"B-3 invariant violated for ch{chapter_num:02d}"
                )
            # Build a DraftResponse whose telemetry fields are zeroed (this
            # instance represents a RE-READ of a committed scene, not a fresh
            # drafter invocation). output_sha is recomputed downstream.
            # WR-07: voice_fidelity_score is now a proper optional field on
            # DraftResponse; no more object.__setattr__ sibling-attr injection.
            fid_raw = fm.get("voice_fidelity_score")
            fid_value: float | None
            if fid_raw is None:
                fid_value = None
            else:
                try:
                    fid_value = float(fid_raw)
                except (TypeError, ValueError):
                    fid_value = None
            drafts.append(
                DraftResponse(
                    scene_text=body,
                    mode=str(fm.get("mode", "A")),
                    model_id="paul-voice",
                    voice_pin_sha=pin_sha,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=0,
                    output_sha="",  # re-read artifact; downstream recomputes if needed
                    attempt_number=int(fm.get("attempt_count", 1)),
                    voice_fidelity_score=fid_value,
                )
            )

        assembled = cls().assemble(drafts, chapter_num)
        return drafts, assembled


__all__ = ["ConcatAssembler"]
