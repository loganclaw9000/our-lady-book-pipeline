# Phase 7: Narrative Physics Engine — Pattern Map

**Mapped:** 2026-04-25
**Files analyzed:** 19 new files + 6 modified files (extensions)
**Analogs found:** 25 / 25

This phase is 80% extension of existing kernel patterns + 20% new (per RESEARCH.md "Don't Hand-Roll" insight). Every new file has a strong in-repo analog. Planner must NOT invent new patterns — all primitives (gate-as-pure-function, Pydantic-strict-frontmatter, retriever-with-LanceDBRetrieverBase, jinja2-system-prompt-with-cache, atomic-tmp+rename, Event-emit-per-call) already exist.

---

## File Classification

### NEW files (19) — `book_pipeline.physics` package + 1 retriever + 2 configs

| New File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/book_pipeline/physics/__init__.py` | package re-export | n/a | `src/book_pipeline/alerts/__init__.py` | exact |
| `src/book_pipeline/physics/schema.py` | Pydantic schema (strict) | request-response (validation) | `src/book_pipeline/rag/types.py` (Chunk) + `src/book_pipeline/interfaces/types.py` (Event) | exact |
| `src/book_pipeline/physics/locks.py` | config loader (typed) | file-I/O (YAML→Pydantic) | `src/book_pipeline/config/mode_preflags.py` | exact |
| `src/book_pipeline/physics/canon_bible.py` | composer/view (read-only) | pull-through cache | `src/book_pipeline/rag/bundler.py::ContextPackBundlerImpl` | role-match |
| `src/book_pipeline/physics/stub_leak.py` | regex-based detector | transform (text→hits) | `src/book_pipeline/chapter_assembler/scene_kick.py::extract_implicated_scene_ids` + `src/book_pipeline/drafter/memorization_gate.py::TrainingBleedGate.scan` | exact (regex+anchored) |
| `src/book_pipeline/physics/repetition_loop.py` | n-gram detector | transform (text→hits) | `src/book_pipeline/drafter/memorization_gate.py` (xxhash n-gram approach) | exact (n-gram math) |
| `src/book_pipeline/physics/scene_buffer.py` | embedding cache + cosine | persistent-cache + transform | `src/book_pipeline/alerts/cooldown.py::CooldownCache` (atomic persist) + `src/book_pipeline/rag/embedding.py::BgeM3Embedder` (embed call) | role-match (no SQLite cache exists yet) |
| `src/book_pipeline/physics/gates/__init__.py` | gate registry + composer | event-driven (sequential) | `src/book_pipeline/rag/bundler.py::bundle()` (orchestration loop) | role-match |
| `src/book_pipeline/physics/gates/base.py` | GateResult model + emit helper | shared types | `src/book_pipeline/drafter/memorization_gate.py::MemorizationHit` (small Pydantic model) + `src/book_pipeline/chapter_assembler/scene_kick.py::_emit_scene_kick_event` | exact |
| `src/book_pipeline/physics/gates/pov_lock.py` | pre-flight gate (pure fn) | request-response | `src/book_pipeline/drafter/preflag.py::is_preflagged` | exact (pure-fn boolean gate) |
| `src/book_pipeline/physics/gates/motivation.py` | pre-flight gate (pure fn) | request-response | `src/book_pipeline/drafter/preflag.py` | exact |
| `src/book_pipeline/physics/gates/ownership.py` | pre-flight gate (pure fn) | request-response | `src/book_pipeline/drafter/preflag.py` | exact |
| `src/book_pipeline/physics/gates/treatment.py` | pre-flight gate (pure fn) | request-response | `src/book_pipeline/drafter/preflag.py` | exact |
| `src/book_pipeline/physics/gates/quantity.py` | pre-flight gate (CB-01 reader) | request-response | `src/book_pipeline/drafter/memorization_gate.py::TrainingBleedGate` (loaded once, called per scene) | role-match |
| `src/book_pipeline/rag/retrievers/continuity_bible.py` | retriever (6th axis) | LanceDB query | `src/book_pipeline/rag/retrievers/negative_constraint.py` (simplest existing retriever; no SQL filter) | exact |
| `config/pov_locks.yaml` | invariant config | YAML | `config/mode_preflags.yaml` (parallel — list-of-string invariants) | exact |
| `config/canonical_quantities_seed.yaml` | invariant config | YAML | `config/mode_preflags.yaml` | exact |
| `tests/physics/test_*.py` (5 new test files) | unit/integration tests | test fixtures | `tests/critic/test_scene_critic.py` + `tests/critic/fixtures.py` (FakeAnthropicClient/FakeEventLogger pattern) + `tests/regenerator/test_scene_local.py` | exact |
| `tests/rag/test_continuity_bible_retriever.py` | slow integration test | LanceDB + BGE-M3 | `tests/rag/test_golden_queries.py` (`@pytest.mark.slow` + `@pytest.mark.skipif(not _indexes_populated())`) | exact |

### MODIFIED files (6) — extensions of existing kernel modules

| Modified File | Role | Change | Closest Analog (precedent) | Match Quality |
|---|---|---|---|---|
| `src/book_pipeline/drafter/mode_a.py` | drafter | inject pre-flight + canonical-stamp into Jinja2 render | EXISTING memorization_gate hook at lines 369-388; Jinja2 render at 289-298 | self-precedent |
| `src/book_pipeline/critic/scene.py` | critic | extend 5→13 axes; motivation hard-stop in `_post_process` | EXISTING `_post_process` at lines 403-448 | self-precedent |
| `src/book_pipeline/critic/templates/system.j2` | jinja2 template | append physics-axes block | EXISTING 5-axis block (axes_ordered loop) | self-precedent |
| `src/book_pipeline/critic/templates/scene_fewshot.yaml` | YAML fixture | add bad/good for new axes | EXISTING `bad`/`good` keys | self-precedent |
| `src/book_pipeline/chapter_assembler/concat.py` | assembler | quote-corruption normalizer pre-commit | EXISTING `_parse_scene_md` at lines 50-64 (frontmatter parser is the natural insertion point — text passes through this function on every chapter assembly) | role-match |
| `pyproject.toml` | build config | extend import-linter contracts | EXISTING `[tool.importlinter.contracts]` blocks (Plan 05-03 alerts append) | self-precedent |

---

## Pattern Assignments

### `src/book_pipeline/physics/__init__.py` (package re-export)

**Analog:** `src/book_pipeline/alerts/__init__.py` (Plan 05-03 precedent — same kernel-package shape)

**Pattern (lines 1-37 of analog):**
```python
"""Alerts kernel package (Phase 5 Plan 03).

ADR-004 clean boundary — book-domain-free. Imports from
``book_pipeline.book_specifics`` are prohibited by import-linter contract 1;
imports into ``book_pipeline.interfaces`` are prohibited by contract 2.

Single-file modules per ADR-004 ("single file unless proven otherwise"):
- ``taxonomy.py`` — HARD_BLOCK_CONDITIONS frozenset + MESSAGE_TEMPLATES dict + ALLOWED_DETAIL_KEYS whitelist.
- ``cooldown.py`` — CooldownCache class (LRU + TTL + atomic JSON persistence).
- ``telegram.py`` — TelegramAlerter class.
"""
from book_pipeline.alerts.cooldown import CooldownCache
from book_pipeline.alerts.taxonomy import (
    ALLOWED_DETAIL_KEYS,
    HARD_BLOCK_CONDITIONS,
    MESSAGE_TEMPLATES,
)
from book_pipeline.alerts.telegram import (
    TelegramAlerter,
    TelegramPermanentError,
    TelegramRetryAfter,
)

__all__ = [
    "ALLOWED_DETAIL_KEYS",
    "HARD_BLOCK_CONDITIONS",
    "MESSAGE_TEMPLATES",
    "CooldownCache",
    "TelegramAlerter",
    "TelegramPermanentError",
    "TelegramRetryAfter",
]
```

**Notes for new file:**
- Mirror exactly: top docstring naming the ADR-004 boundary + import-linter contracts that protect it
- Per-file responsibility list in docstring
- Re-export every public symbol; sorted `__all__` list (alphabetical)
- New file's symbols enumerated in RESEARCH.md "Pattern 1" example (lines 326-353)

---

### `src/book_pipeline/physics/schema.py` (Pydantic strict-validation)

**Analogs:**
- Strict-frozen pattern: `src/book_pipeline/rag/types.py::Chunk` (lines 22-43)
- Frozen-schema-with-discriminated-fields: `src/book_pipeline/interfaces/types.py::Event` (lines 325-354)
- Strict-output Pydantic for LLM-parse: `src/book_pipeline/interfaces/types.py::CriticResponse` (used by `client.messages.parse(output_format=CriticResponse)` in `critic/scene.py:393`)

**Strict-validation pattern (rag/types.py lines 22-43):**
```python
from pydantic import BaseModel, ConfigDict


class Chunk(BaseModel):
    """One persisted RAG chunk row.

    Fields map 1:1 to CHUNK_SCHEMA in lance_schema.py (minus `embedding`, which
    is populated at ingest time from a BgeM3Embedder and written directly to the
    LanceDB row — it is not kept on the Chunk model itself because the embedding
    vector is derived, not authored content).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    text: str
    source_file: str
    heading_path: str
    rule_type: str = "rule"
    ingestion_run_id: str
    chapter: int | None = None
    # Plan 05-03: additive nullable column (SC6 closure / D-11). Non-null only
    # on entity_state rows (_card_to_row stamps it); corpus-ingest rows write
    # None. Used by bundler.scan_for_stale_cards.
    source_chapter_sha: str | None = None


__all__ = ["Chunk"]
```

**Notes for new file:**
- **Stricter than Chunk** — use `extra="forbid"` AND `field_validator` decorators (RESEARCH Example 1 lines 733-738, 795-804). Schema rejects unknown frontmatter keys + custom validators on motivation min-words + on-screen+motivation joint constraint.
- DO NOT freeze `SceneMetadata` itself — the post-load motivation cross-validator wants joint access; freeze child models (`Contents`, `CharacterPresence`, `Staging`, `ValueCharge`) per RESEARCH Example 1.
- Use `Enum`-based Literals for `Perspective` and `Treatment` (RESEARCH Example 1 lines 705-723) — closed enum makes schema-level rejection cheaper than runtime check.
- The full schema body is in RESEARCH §"Code Examples → Example 1" (lines 695-805) — copy verbatim, deviate only on operator-strong default about whether `value_charge` is required (recommend optional in v1 per Pitfall A3).

---

### `src/book_pipeline/physics/locks.py` (typed YAML loader)

**Analog:** `src/book_pipeline/config/mode_preflags.py` (47 lines — same shape: list of invariants loaded once)

**Full loader pattern (lines 1-47):**
```python
"""PreflagConfig — typed loader for config/mode_preflags.yaml (Plan 05-01 D-04)."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from book_pipeline.config.sources import YamlConfigSettingsSource


class PreflagConfig(BaseSettings):
    """Root loader — validates and exposes ``preflagged_beats`` list."""

    preflagged_beats: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        yaml_file="config/mode_preflags.yaml",
        extra="forbid",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


__all__ = ["PreflagConfig"]
```

**Notes for new file:**
- `physics/locks.py` placement deviates from the convention (sibling files in `config/`). Operator's anti-pattern note in RESEARCH §"Anti-Patterns to Avoid" (line 500) demands STATIC location. Recommend: keep the loader class in `physics/locks.py` (kernel-package-internal — gates import it directly without leaking through `config/`); the YAML stays at `config/pov_locks.yaml`. PovLock model lives in `physics/locks.py` alongside `load_pov_locks()`.
- Add `applies_to(chapter: int) -> bool` method on PovLock (RESEARCH Example 2 line 831) — captures the D-21 "activates starting ch15" rule.
- `extra="forbid"` is mandatory (catches typos like `1st` vs `1st_person`).
- The YamlConfigSettingsSource boilerplate (lines 30-44) is copy-paste verbatim.

---

### `src/book_pipeline/physics/canon_bible.py` (composer/view)

**Analog:** `src/book_pipeline/rag/bundler.py::ContextPackBundlerImpl` (lines 157-272 — composes 5 retrievers + conflicts + budget into a ContextPack)

**Composition-of-retrievers pattern (lines 190-272):**
```python
def bundle(
    self, request: SceneRequest, retrievers: list[Retriever]
) -> ContextPack:
    """Run all retrievers; detect conflicts; enforce budget; emit 6 events; return pack."""
    bundle_start_ns = time.monotonic_ns()
    scene_id = (
        f"ch{int(request.chapter):02d}_sc{int(request.scene_index):02d}"
    )
    request_fp = hash_text(request.model_dump_json())

    retrievals: dict[str, RetrievalResult] = {}
    for retriever in retrievers:
        retrievals[retriever.name] = self._run_one_retriever(
            retriever, request, request_fp, scene_id
        )

    # Conflict detection BEFORE budget trimming so we see the full data.
    conflicts: list[ConflictReport] = detect_conflicts(
        retrievals, entity_list=self.entity_list
    )
    # ... (stale-card scan, budget enforce, fingerprint)
    pack = ContextPack(
        scene_request=request,
        retrievals=trimmed,
        total_bytes=total_bytes,
        assembly_strategy="round_robin",
        fingerprint=pack_fingerprint,
        conflicts=conflicts if conflicts else None,
        ingestion_run_id=self.ingestion_run_id,
    )
    # ... (emit one bundler event)
    return pack
```

**Notes for new file:**
- `CanonBibleView` is a READER (no event emission, no composition orchestration). It's a higher-level convenience wrapper that takes already-bundled retrieval data + entity-state + retrospectives and exposes structured queries (`get_canonical_quantity(name) -> str | None`, `get_pov_lock(character) -> PovLock | None`).
- Unlike bundler, CanonBibleView does NOT itself call retrievers — it CONSUMES their output. Constructor takes `(retrievals: dict[str, RetrievalResult], pov_locks: dict[str, PovLock])`.
- Build via `build_canon_bible_view(scene_request, retrievers, pov_locks_path) -> CanonBibleView` — module-level helper that orchestrates the read.
- DO NOT use `lru_cache` at module scope (RESEARCH Pitfall 11 lines 673-682; same trap as Plan 05-03 SC6). Per-bundle dict memoization only (precedent: bundler `sha_by_chapter` local dict at line 122).

---

### `src/book_pipeline/physics/stub_leak.py` (regex-based detector)

**Analogs:**
- Regex-based scene-id parsing: `src/book_pipeline/chapter_assembler/scene_kick.py::extract_implicated_scene_ids` (lines 54-79) — module-scope compiled `_SCENE_REF_RE = re.compile(r"\bch(\d+)_sc(\d+)\b")`, then `re.findall` per-input.
- Detector returning a list of typed hits (empty=pass): `src/book_pipeline/drafter/memorization_gate.py::TrainingBleedGate.scan` (lines 112-128) — pure scan returning `list[MemorizationHit]`.

**Module-scope regex pattern (scene_kick.py lines 47-79):**
```python
# Widened vs cli/draft.py::_SCENE_ID_RE (which is ^ch(\d+)_sc(\d+)$) because
# CriticIssue.location is free-text with embedded refs.
_SCENE_REF_RE = re.compile(r"\bch(\d+)_sc(\d+)\b")

# Matches files like "ch99_sc02_rev07.md" — extract the rev integer.
_REV_SUFFIX_RE = re.compile(r"_rev(\d+)\.md$")


def extract_implicated_scene_ids(
    response: CriticResponse,
) -> tuple[set[str], list[str]]:
    """..."""
    implicated: set[str] = set()
    non_specific: list[str] = []
    for issue in response.issues:
        matches = _SCENE_REF_RE.findall(issue.location or "")
        if not matches and issue.evidence:
            matches = _SCENE_REF_RE.findall(issue.evidence)
        if matches:
            for ch_str, sc_str in matches:
                ch, sc = int(ch_str), int(sc_str)
                implicated.add(f"ch{ch:02d}_sc{sc:02d}")
        else:
            non_specific.append(issue.claim)
    return implicated, non_specific
```

**Hit-list-from-scan pattern (memorization_gate.py lines 112-128):**
```python
def scan(self, scene_text: str) -> list[MemorizationHit]:
    """Return all positions where a 12-gram of scene_text matches the corpus.

    Empty list = pass. Any non-empty list = caller raises
    ModeADrafterBlocked("training_bleed").
    """
    if not scene_text:
        return []
    tokens = scene_text.split()
    if len(tokens) < self.ngram:
        return []
    hits: list[MemorizationHit] = []
    for i in range(len(tokens) - self.ngram + 1):
        gram = " ".join(tokens[i : i + self.ngram])
        if xxhash.xxh64_intdigest(gram.encode("utf-8")) in self._hashes:
            hits.append(MemorizationHit(ngram=gram, position=i))
    return hits
```

**Notes for new file:**
- Combine both: module-scope `STUB_LEAK_PATTERNS` tuple of compiled patterns (RESEARCH Example 3 lines 862-872) + `scan_stub_leak(scene_text) -> list[StubLeakHit]` pure function.
- Use `re.MULTILINE | re.IGNORECASE` and anchor with `^` (Pitfall 4 — line-by-line, no nested quantifiers, no `.*` followed by `\s*$`).
- `StubLeakHit` is a tiny Pydantic BaseModel mirroring `MemorizationHit` shape (line + matched_text instead of position + ngram).
- Iterate via `scene_text.splitlines()` then `.match(line)` per line — RESEARCH Example 3 lines 884-890.

---

### `src/book_pipeline/physics/repetition_loop.py` (n-gram detector)

**Analog:** `src/book_pipeline/drafter/memorization_gate.py` (full file) — same n-gram tokenize+hash approach, just self-similarity instead of corpus-similarity.

**Token-window iteration pattern (memorization_gate.py lines 95-104):**
```python
tokens = value.split()
if len(tokens) < self.ngram:
    continue
self.row_count += 1
for i in range(len(tokens) - self.ngram + 1):
    gram = " ".join(tokens[i : i + self.ngram])
    self._hashes.add(xxhash.xxh64_intdigest(gram.encode("utf-8")))
    self.ngram_count += 1
```

**Notes for new file:**
- Reuse `xxhash.xxh64_intdigest` for the gram-hash dedup math (already a dep; no new imports). Stable across processes — no PYTHONHASHSEED risk (memorization_gate docstring line 24-26).
- New twist: count GRAM REPETITIONS within a single scene (Counter), flag when (max_repeat / total_grams) > threshold. Threshold lives in `config/mode_thresholds.yaml` per D-19 + Claude's Discretion in CONTEXT.md line 144.
- Treatment-conditional thresholds (Pitfall 10 lines 650-672) — `liturgical` treatment gets a higher tolerance for "repetition is the form". Plan must surface this — test_repetition_loop.py is the calibration site.
- Pure function: `scan_repetition_loop(scene_text, treatment, thresholds) -> list[RepetitionHit]`. Empty list = pass (matching memorization_gate.scan return shape).

---

### `src/book_pipeline/physics/scene_buffer.py` (SQLite embedding cache + cosine)

**Analogs:**
- Atomic-persist + load-on-init: `src/book_pipeline/alerts/cooldown.py::CooldownCache` (lines 35-99) — load file → in-memory dict → persist on every mutation.
- Embedder usage: `src/book_pipeline/rag/embedding.py::BgeM3Embedder.embed_texts` (lines 93-119) — returns unit-normalized `(N, EMBEDDING_DIM)` float32 numpy.
- No SQLite cache exists in the codebase yet — this is the first one. Closest SQLite use is the implicit ledger in `observability/ledger.py` (not analogous shape).

**Persist-on-mutation pattern (cooldown.py lines 86-99):**
```python
def _persist(self) -> None:
    """Atomic write: serialize → tmp file → os.replace to final path."""
    self.cooldown_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = self.cooldown_path.with_suffix(
        self.cooldown_path.suffix + ".tmp"
    )
    payload = {
        "entries": [
            {"condition": c, "scope": s, "ts": t}
            for (c, s), t in self._data.items()
        ]
    }
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(str(tmp), str(self.cooldown_path))
```

**Embedder call pattern (embedding.py lines 93-119):**
```python
def embed_texts(self, texts: list[str]) -> np.ndarray:
    """Return a (len(texts), EMBEDDING_DIM) float32 array of unit-normalized embeddings.

    Degenerate: embed_texts([]) returns an empty (0, EMBEDDING_DIM) float32 array
    without loading the model.
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
    self._ensure_loaded()
    assert self._model is not None
    raw = self._model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    arr: np.ndarray = np.asarray(raw)
    # ... (dtype + shape assertion)
    return arr
```

**Notes for new file:**
- DO NOT re-implement cosine math — BGE-M3 returns unit-normalized vectors, so cosine == dot product. Pitfall 3 (lines 540-549): `np.dot(a, b)` directly; do NOT import `numpy.linalg.norm`. Add an `assert abs(np.linalg.norm(a) - 1.0) < 1e-3` for safety.
- SQLite via stdlib `sqlite3` (no new dep). RESEARCH Example 4 lines 904-948 has the full body — copy verbatim. Schema is one table `(scene_id TEXT, bge_m3_revision_sha TEXT, embedding BLOB, computed_at TEXT, PRIMARY KEY (scene_id, bge_m3_revision_sha))`.
- Cache key MUST include `embedder.revision_sha` (Pitfall 7 lines 594-613) — voice-FT pin bumps invalidate naturally. Read via `self.embedder.revision_sha` property (already exists).
- Cache file location: `.planning/intel/scene_embeddings.sqlite` per RESEARCH Recommended Project Structure (line 302). Tests inject `tmp_path` (Pitfall 12 lines 683-692).

---

### `src/book_pipeline/physics/gates/__init__.py` + `physics/gates/base.py`

**Analogs:**
- Per-event emission helper: `src/book_pipeline/chapter_assembler/scene_kick.py::_emit_scene_kick_event` (lines 112-148) — exact shape for `role='physics_gate'` Event emission.
- Sequential composer with short-circuit: `src/book_pipeline/rag/bundler.py::bundle` `for retriever in retrievers` loop at lines 206-209.
- Small Pydantic value-object: `src/book_pipeline/drafter/memorization_gate.py::MemorizationHit` (lines 37-41).

**Event emission pattern (scene_kick.py lines 112-148):**
```python
def _emit_scene_kick_event(
    event_logger: EventLogger,
    *,
    kicked_scenes: list[str],
    chapter_num: int,
    issue_refs: list[str],
) -> None:
    """Emit exactly one role='scene_kick' Event per invocation."""
    ts_iso = _now_iso()
    caller = f"chapter_assembler.scene_kick:ch{chapter_num:02d}"
    prompt_h = hash_text(f"scene_kick:ch{chapter_num}:{','.join(kicked_scenes)}")
    eid = event_id(ts_iso, "scene_kick", caller, prompt_h)
    caller_context: dict[str, Any] = {
        "module": "chapter_assembler.scene_kick",
        "function": "kick_implicated_scenes",
        "chapter_num": chapter_num,
    }
    extra: dict[str, Any] = {
        "kicked_scenes": list(kicked_scenes),
        "chapter_num": chapter_num,
        "issue_refs": list(issue_refs),
    }
    event = Event(
        event_id=eid,
        ts_iso=ts_iso,
        role="scene_kick",
        model="n/a",
        prompt_hash=prompt_h,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        latency_ms=0,
        caller_context=caller_context,
        output_hash=hash_text("scene_kick"),
        extra=extra,
    )
    event_logger.emit(event)
```

**Notes for new files:**
- `gates/base.py` defines `GateResult` Pydantic value object (RESEARCH Pattern 2 lines 395-407) + `emit_gate_event(event_logger, *, gate_name, scene_id, chapter_num, result)` helper that mirrors `_emit_scene_kick_event` shape but stamps `role='physics_gate'` and `model='n/a'`.
- `gates/__init__.py` exports `GateResult`, `GateError`, `run_pre_flight(stub, deps) -> list[GateResult]`. The composer loops the 5 gate functions sequentially; per RESEARCH Pattern 2 (line 388-407) it short-circuits on first `severity='high'` FAIL but accumulates lower severities.
- Gates RETURN `GateResult` (don't raise). Cleaner than memorization_gate's exception-as-bool (RESEARCH Pattern 2 line 388 — "cleaner than memorization_gate's exception-as-bool, simpler than preflag's bool-only").
- Severity enum maps to `CriticIssue.severity` taxonomy (low/mid/high) for uniform reasoning across gate-time and critic-time.

---

### `src/book_pipeline/physics/gates/{pov_lock,motivation,ownership,treatment,quantity}.py` (5 pre-flight gates)

**Analog:** `src/book_pipeline/drafter/preflag.py` (full file, 38 lines — pure-function gate)

**Pure-function gate pattern (preflag.py lines 15-27):**
```python
def is_preflagged(scene_id: str, preflag_set: frozenset[str]) -> bool:
    """Return True iff ``scene_id`` is in ``preflag_set``.

    Args:
        scene_id: canonical "ch{NN:02d}_sc{II:02d}" string (or beat_id when
            the scene loop uses beat-grain preflags).
        preflag_set: immutable set of preflagged identifiers; typically the
            return of ``load_preflag_set()``.

    Returns:
        True if preflagged → route directly to Mode-B. False → Mode-A first.
    """
    return scene_id in preflag_set
```

**Pre-flight gate signature pattern for physics (RESEARCH Example 2 lines 819-849):**
```python
GATE_NAME = "pov_lock"

def check(stub: SceneMetadata, locks: dict[str, PovLock]) -> GateResult:
    """Pre-flight: stub.perspective must match per-character pov_lock unless overridden."""
    on_screen_chars = [c.name for c in stub.characters_present if c.on_screen]
    breaches: list[str] = []
    for char in on_screen_chars:
        lock = locks.get(char.lower())
        if lock is None or not lock.applies_to(stub.chapter):
            continue
        if lock.perspective != stub.perspective:
            if stub.pov_lock_override:
                continue
            breaches.append(...)
    if not breaches:
        return GateResult(gate_name=GATE_NAME, passed=True, severity="pass")
    return GateResult(
        gate_name=GATE_NAME,
        passed=False,
        severity="high",
        reason="pov_lock_breach",
        detail={"breaches": breaches, "scene_id": f"ch{stub.chapter:02d}_sc{stub.scene_index:02d}"},
    )
```

**Notes for each gate file:**
- Each gate exports a single `GATE_NAME` constant + `check(stub, deps) -> GateResult` pure function. NO classes (preflag is the precedent — pure-fn, single-purpose, ~30 lines each).
- Gates do NOT emit events directly (matches retriever pattern in `rag/retrievers/base.py` docstring line 28-29: "Retrievers NEVER log observability events directly... the bundler is the event-emission site"). The composer (`gates/__init__.py::run_pre_flight`) emits per-gate events via `gates/base.py::emit_gate_event`.
- `motivation.check(stub)` — verifies every on_screen character has a non-empty motivation field (the schema validator already guarantees this at parse-time; gate is the runtime safety belt for non-Pydantic call paths).
- `ownership.check(stub, prior_committed_metadata)` — verifies `stub.do_not_renarrate` references resolve to prior scenes' `owns` declarations.
- `treatment.check(stub)` — verifies `stub.treatment` is in the closed enum (also Pydantic-guaranteed; redundant safety belt).
- `quantity.check(stub, canon_bible_view)` — verifies every named quantity in `stub.contents.goal/conflict/outcome` resolves to a CB-01 canonical row. This is the heaviest gate (CB-01 query); analog is `TrainingBleedGate` (loaded once, called per scene).

---

### `src/book_pipeline/rag/retrievers/continuity_bible.py` (6th retriever)

**Analog:** `src/book_pipeline/rag/retrievers/negative_constraint.py` (51 lines — simplest existing retriever; NO custom `_where_clause`, like CB-01)

**Full negative_constraint pattern (lines 28-49):**
```python
class NegativeConstraintRetriever(LanceDBRetrieverBase):
    def __init__(
        self,
        *,
        db_path: Path,
        embedder: BgeM3Embedder,
        reranker: BgeReranker,
        **kw: Any,
    ) -> None:
        super().__init__(name="negative_constraint", db_path=db_path, embedder=embedder, reranker=reranker, **kw)

    def _build_query_text(self, request: SceneRequest) -> str:
        return (
            f"landmines and things to avoid when {request.pov} is at "
            f"{request.location} on {request.date_iso}; beat: {request.beat_function}"
        )

    def _where_clause(self, request: SceneRequest) -> str | None:
        # DELIBERATE NO-OP — per PITFALLS R-5 we MUST return top-K unconditionally
        # and let the bundler filter on match. Do NOT add tag filtering here.
        return None
```

**Base-class `retrieve()` flow (base.py lines 97-158):**
- Calls `_build_query_text(request)` → embeds → searches LanceDB top-K → reranks → returns `RetrievalResult`. Subclasses override the two hooks only.
- Empty-table tolerance is built in (line 104) — returns valid empty `RetrievalResult` instead of raising. CB-01 inherits this for free.

**Notes for new file:**
- Subclass `LanceDBRetrieverBase` exactly like NegativeConstraintRetriever. Keyword-only `__init__` (W-2 compliance per docstring lines 13-14).
- `super().__init__(name="continuity_bible", ...)` — name MUST match the LanceDB table name (used by `open_or_create_table`).
- `_build_query_text(request)` returns a query naming the entities-and-quantities-of-interest (RESEARCH Pattern 3 lines 449-452: "Primary: entity-name fuzzy semantic match. Query is the scene's entity-and-context (e.g., `\"Andrés age and origin\"`), retrieves canonical-quantity rows...").
- `_where_clause(request)` returns `"rule_type = 'canonical_quantity'"` (filter to CB-01 rows only — the table is shared schema across all axes per `lance_schema.py`, so the filter is what specializes it). Precedent: `MetaphysicsRetriever` returns `"rule_type IN ('rule')"`.
- LanceDB shape (from RESEARCH Pattern 3 lines 437-446): `chunk_id="canonical:andres_age:ch01"`, `text="Andrés Olivares: age 26 at start of ch01..."`, `rule_type="canonical_quantity"`, `chapter=1`. NO new column needed (additive nullable per D-22 + Plan 05-03 D-11 contract).

**ALSO: Update `src/book_pipeline/rag/retrievers/__init__.py`** to export `ContinuityBibleRetriever`. Same import-guarded pattern as `EntityStateRetriever` lines 38-49 of analog.

---

### `src/book_pipeline/critic/scene.py` 13-axis extension

**Analog:** EXISTING `_post_process` at lines 403-448 of the same file (self-precedent — extend, don't rewrite).

**Existing post-process pattern (lines 403-448):**
```python
def _post_process(self, parsed: CriticResponse) -> tuple[list[str], bool]:
    """Fill missing axes + enforce overall_pass invariant + override
    rubric_version. Returns (filled_axes, invariant_fixed)."""
    filled_axes: list[str] = []
    for axis in sorted(REQUIRED_AXES):
        if axis not in parsed.pass_per_axis:
            parsed.pass_per_axis[axis] = False
            filled_axes.append(axis)
            logger.warning(
                "critic-response omitted axis=%s; filling pass=False "
                "(scene will be routed to regen — critic protocol violation)",
                axis,
            )
        if axis not in parsed.scores_per_axis:
            parsed.scores_per_axis[axis] = _FILLED_AXIS_SCORE

    expected_overall = all(parsed.pass_per_axis.values())
    invariant_fixed = parsed.overall_pass != expected_overall
    if invariant_fixed:
        # ... fixes overall_pass
    # ... rubric_version stamp
    return filled_axes, invariant_fixed
```

**Anthropic structured-output call (lines 380-396):**
```python
@tenacity.retry(
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def _call_opus_inner(self, *, messages: list[dict[str, Any]]) -> Any:
    """Raw Anthropic messages.parse call with tenacity retry on transient errors."""
    from anthropic import APIConnectionError, APIStatusError
    try:
        return self.anthropic_client.messages.parse(
            model=self.model_id,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=self._system_blocks,
            messages=messages,
            output_format=CriticResponse,
        )
    except (APIConnectionError, APIStatusError):
        raise
```

**Notes for the extension:**
- DO NOT change the call signature or the tenacity decorator — physics axes ride on the same `client.messages.parse()` call (RESEARCH Pattern 4 line 469 — "RECOMMEND single call").
- Add motivation hard-stop AFTER the existing axis-fill loop (RESEARCH Pattern 4 lines 482-495):
```python
PHYSICS_REQUIRED_AXES = ("pov_fidelity", "motivation_fidelity", "treatment_fidelity",
                         "content_ownership", "named_quantity_drift",
                         "scene_buffer_similarity",
                         # stub_leak, repetition_loop are pre-LLM short-circuits
                         )
for axis in PHYSICS_REQUIRED_AXES:
    if axis not in parsed.pass_per_axis:
        parsed.pass_per_axis[axis] = False
        filled_axes.append(axis)
# D-02 hard-stop semantics:
if parsed.pass_per_axis.get("motivation_fidelity") is False:
    if parsed.overall_pass:
        logger.warning("motivation_fidelity FAIL forces overall_pass=False (D-02)")
    parsed.overall_pass = False
```
- `REQUIRED_AXES` extends from `book_pipeline.config.rubric.REQUIRED_AXES` — Plan 07-04 also bumps `rubric_version` (Pitfall 9 lines 640-649) so the audit trail distinguishes 5-axis vs 13-axis runs.
- 8 new axes — but only 6 are LLM-judged; `stub_leak` + `repetition_loop` are deterministic pre-LLM short-circuits. They appear in `pass_per_axis` only via the deterministic path.
- `scene_buffer_similarity` requires the SceneEmbeddingCache be wired into SceneCritic.__init__ (new optional dep). Cosine result is computed BEFORE the LLM call and surfaced into the prompt as a numerical input.

---

### `src/book_pipeline/critic/templates/system.j2` extension (5→13 axes)

**Analog:** EXISTING template body at `src/book_pipeline/critic/templates/system.j2` (45 lines — self-precedent).

**Existing structure:**
```jinja2
{#- system.j2 — Critic system prompt. Rubric verbatim + 5-axis instructions + 1 bad + 1 good few-shot. -#}
You are the scene critic for the historical-fiction novel "Our Lady of Champion". You score a drafted scene against a 5-axis rubric...

Rubric (version {{ rubric.rubric_version }}):
{% for axis in axes_ordered -%}
- {{ axis }}: {{ rubric.axes[axis].description }}
  severity thresholds (normalized 0-1): low=..., mid=..., high=...
  gate weight: {{ rubric.axes[axis].weight }}
{% endfor %}

Per-axis instructions:
- historical: verify dates, place names, events against the corpus 'historical' retriever output. Factual drift = FAIL.
- metaphysics: verify engine-tier + fuel-class claims against 'metaphysics' rule-cards...
- entity: verify named-entity states...
- arc: verify the scene hits the stated beat function...
- donts: verify no violations of 'negative_constraint'...

Few-shot (bad example — scene fails historical axis):
Scene: "{{ few_shot_bad.scene_text }}"
Expected response: {{ few_shot_bad.expected_critic_response | tojson }}
```

**Notes for the extension:**
- APPEND a "Physics axes" block AFTER the 5 existing per-axis instructions. Use the same `- {axis_name}: {description}` shape.
- Token budget cap is hot (Pitfall 2 lines 530-539): max **8** new few-shot entries total across the 8 new axes (NOT 16). Few-shots ONLY for `pov_fidelity`, `content_ownership`, `treatment_fidelity` (subjective). Deterministic axes (`stub_leak`, `repetition_loop`) get NO few-shots (short-circuit before LLM).
- `axes_ordered` in `critic/scene.py:40` extends from `("historical", "metaphysics", "entity", "arc", "donts")` to include the 6 LLM-judged physics axes. ORDER matters for cache hit (Pitfall 9 lines 640-649) — append, don't insert mid-list. Recommended order: existing 5 + `pov_fidelity, motivation_fidelity, treatment_fidelity, content_ownership, named_quantity_drift, scene_buffer_similarity`.

---

### `pyproject.toml` import-linter contract update

**Analog:** EXISTING `[tool.importlinter.contracts]` blocks at lines 60-191 — Plan 05-03 alerts append at lines 96-97 + 188-189 is the direct precedent.

**Existing alerts append pattern (contract 1, lines 95-97):**
```toml
    # Phase 5 plan 03 added: alerts (TelegramAlerter + CooldownCache + taxonomy).
    "book_pipeline.alerts",
]
```

**Existing alerts append pattern (contract 2, lines 187-189):**
```toml
    # Phase 5 plan 03 added: alerts (TelegramAlerter + CooldownCache + taxonomy).
    "book_pipeline.alerts",
]
```

**Notes for the extension (RESEARCH Pattern 1 lines 355-376):**
- Append `"book_pipeline.physics"` to BOTH source_modules (contract 1) AND forbidden_modules (contract 2). Two locations, identical comment-prefixed rationale ("Phase 7 plan 01 added: physics (SceneMetadata + gates + canon_bible).").
- DO NOT modify `ignore_imports` — physics is a kernel package and must stay book-domain-free. If a gate needs book-domain knowledge (e.g., the canonical Mesoamerican entity list), the CLI composition layer injects it at construction time (precedent: `cli._entity_list -> book_specifics.nahuatl_entities` exemption at line 111).
- Also: extend `scripts/lint_imports.sh` mypy-targets policy to include `book_pipeline.physics` (D-25 contract end).

---

### `tests/physics/test_*.py` (new test files) + `tests/rag/test_continuity_bible_retriever.py`

**Analogs:**
- Fast-path unit tests with FakeAnthropicClient + FakeEventLogger: `tests/critic/fixtures.py` (lines 198-221) + `tests/critic/test_scene_critic.py`
- Pure-function gate tests (no fakes needed): `tests/regenerator/test_scene_local.py` (lines 1-80 — direct Jinja2 render + pure-fn assertions)
- Slow integration test with real BGE-M3 + real LanceDB: `tests/rag/test_golden_queries.py` lines 156-200

**FakeAnthropicClient/FakeEventLogger pattern (fixtures.py lines 198-221):**
```python
class FakeAnthropicClient:
    """Mimics anthropic.Anthropic() surface used by SceneCritic."""

    def __init__(
        self,
        parsed_response: CriticResponse | None = None,
        side_effect: list[Any] | None = None,
        usage: FakeUsage | None = None,
    ) -> None:
        self.messages = FakeMessages(
            parsed_response=parsed_response,
            side_effect=side_effect,
            usage=usage,
        )


class FakeEventLogger:
    """Captures emitted Events for test assertions."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)
```

**Slow-marker pattern (test_golden_queries.py lines 156-163):**
```python
@pytest.mark.slow
@pytest.mark.skipif(
    not _indexes_populated(),
    reason=(
        "indexes/ is empty; run `uv run book-pipeline ingest --force` first. "
        "This is the RAG-04 baseline-pinned slow gate."
    ),
)
def test_golden_queries_pass_on_baseline_ingest() -> None:
    """..."""
```

**Notes for new tests:**
- `tests/physics/` is a new directory. Add `__init__.py` (empty) + `conftest.py` ONLY if shared fixtures emerge; otherwise inline.
- Fast tests (`test_schema.py`, `test_locks.py`, `test_gates.py`, `test_stub_leak.py`, `test_repetition_loop.py`) use NO fakes and NO marker — pure-function inputs/outputs. Each ~12 tests covering the matrix per RESEARCH §"Validation Architecture" lines 980-993.
- Slow tests (`test_scene_buffer.py` — needs BGE-M3 load; `tests/rag/test_continuity_bible_retriever.py` — needs LanceDB) use `@pytest.mark.slow + @pytest.mark.skipif(...)` matching the golden-queries gate. See A1 in RESEARCH assumptions log: ship empirical calibration tests, not just type tests.
- For 13-axis critic test (`tests/critic/test_scene_13axis.py`): reuse FakeAnthropicClient with a `parsed_response` carrying a 13-key `pass_per_axis`. Test motivation_fidelity hard-stop by setting it False and asserting `overall_pass=False` regardless of others. The `tests/critic/fixtures.py` fixture ALREADY has `make_canonical_critic_response()` — extend it (don't fork) to surface 13 keys.

---

### `src/book_pipeline/drafter/mode_a.py` extension (canonical-quantity prompt header)

**Analog:** EXISTING template render at `src/book_pipeline/drafter/mode_a.py:289-298` (self-precedent).

**Existing render call pattern (lines 287-302):**
```python
# 3-5: render Jinja2, split on sentinels, assemble messages.
word_target = _to_int(request.generation_config.get("word_target"), default=1000)
rendered = self._template.render(
    voice_description=VOICE_DESCRIPTION,
    rubric_awareness=RUBRIC_AWARENESS,
    retrievals=request.context_pack.retrievals,
    scene_request=scene_request,
    prior_scenes=request.prior_scenes,
    word_target=word_target,
    scene_type=scene_type,
)
system_text, user_text = _split_on_sentinels(rendered)
messages = [
    {"role": "system", "content": system_text},
    {"role": "user", "content": user_text},
]
```

**Existing memorization-gate hook (lines 369-388 — gate insertion precedent):**
```python
# 9: memorization gate (V-2 HARD BLOCK).
if self.memorization_gate is not None:
    hits: list[MemorizationHit] = self.memorization_gate.scan(scene_text)
    if hits:
        hit_grams = [h.ngram for h in hits[:5]]
        self._emit_error_event(
            reason="training_bleed",
            scene_id=scene_id,
            chapter=scene_request.chapter,
            ...
        )
        raise ModeADrafterBlocked(
            "training_bleed",
            scene_id=scene_id,
            hits=hit_grams,
            attempt_number=attempt_number,
        )
```

**Notes for the extension (D-23 stamp + D-24 pre-flight gate composition):**
- ADD a `physics_pre_flight_gates` optional ctor arg (defaults None — backward compatible). Insert pre-flight call BEFORE the Jinja2 render (line 287) so the gate fires before any vLLM call (D-24 — "cheap, before any model call").
- Stamp canonical quantities at the TOP of the rendered system prompt. Two implementation options:
  - **(a)** Pass `canonical_stamp: str` into the Jinja2 render call (extends current `self._template.render(...)` kwargs); template injects via `{{ canonical_stamp }}` block at the top of the system body.
  - **(b)** Wrap the rendered output: prepend `f"CANONICAL: {stamp}\n\n"` to `system_text` after `_split_on_sentinels`.
- Recommend **(a)** — matches the existing `voice_description=`/`rubric_awareness=` pattern (in-template injection). Less prose-fragility than (b).
- The pre-flight gate output (per `physics/gates/__init__.py::run_pre_flight`) returns a list of GateResult. On any FAIL with severity='high': emit error Event (mirror lines 269-284 invalid_scene_type pattern) + raise `ModeADrafterBlocked("physics_pre_flight_fail", ...)`.
- New ModeADrafterBlocked reason: `physics_pre_flight_fail` (added to docstring at lines 144-148 alongside training_bleed/etc).

---

### `src/book_pipeline/chapter_assembler/concat.py` extension (quote-corruption normalizer)

**Analog:** EXISTING `_parse_scene_md` at lines 50-64 of the same file (self-precedent — same insertion point).

**Existing scene-md parser (lines 50-64):**
```python
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
```

**Scene-block assembly point (lines 147-152):**
```python
# Build scene blocks: HTML marker + scene body.
scene_blocks: list[str] = []
for sid, d in zip(scene_ids, drafts, strict=True):
    scene_blocks.append(f"<!-- scene: {sid} -->\n{d.scene_text}")

body = "\n\n---\n\n".join(scene_blocks)
```

**Notes for the extension (D-18 PHYSICS-11):**
- Insert a `_normalize_quote_corruption(body: str) -> tuple[str, list[QuoteRepair]]` step BEFORE the `scene_blocks.append(...)` line (line 150). It returns the normalized body plus a list of repairs (for telemetry).
- Pattern set targets the ch13 sc02/sc03 corruption (`., ` sequences mangling dialogue). Per RESEARCH Pitfall analysis: anchor regexes line-by-line, no `.*` followed by `\s*` (Pitfall 4 risk applies here too).
- This is a NORMALIZER not a critic axis (per Claude's Discretion in CONTEXT.md line 145 — "side-fix in chapter_assembler pre-commit normalizer" recommended). The function name + return shape mirrors `_parse_scene_md` (pure function returning tuple of (text, side-info)).
- If repairs were applied, emit a `role='quote_normalizer'` Event from the calling site (DAG orchestrator) — but the normalizer itself stays pure (matches `_parse_scene_md`'s no-side-effects discipline).
- ALTERNATIVE placement: gate at `_parse_scene_md` itself (catch corruption AT scene-load time, not at chapter-assemble time). Operator hint in CONTEXT D-18: "rolled into the canon-bible commit gate." Planner picks; recommend AT-PARSE for earliest detection.

---

## Shared Patterns (cross-cutting concerns)

### Event Emission (ALL physics gates + retriever + scene-buffer cosine + normalizer)

**Source:** `src/book_pipeline/chapter_assembler/scene_kick.py::_emit_scene_kick_event` (lines 112-148) — closest in-repo precedent for a non-LLM event emitter (`role='scene_kick'`, `model='n/a'`, zero token counts).

**Apply to:** every physics-gate call in `physics/gates/__init__.py::run_pre_flight`, every CB-01 retriever call (auto-emitted by the EXISTING bundler at `rag/bundler.py:_run_one_retriever`), every scene-buffer cosine compute.

**Concrete excerpt:** see `pov_lock.py` Notes above. Three-tuple key for emit:
- `role` — new value `'physics_gate'` (NEVER reuse existing roles per OBS-01 docstring at `interfaces/types.py:338`)
- `model` — `'n/a'` for all physics gates (no LLM); `'paul-voice'` for scene-buffer cosine if it routes through the embedder; CB-01 retriever uses `retriever_name` (auto by bundler).
- `caller_context` — must include `{module: 'physics.gates.<gate_name>', function: 'check', scene_id, chapter_num}` per OBS-01 contract.

### Strict Pydantic Validation (all schema models)

**Source:** `src/book_pipeline/rag/types.py::Chunk` — `model_config = ConfigDict(extra="forbid", frozen=True)`.

**Apply to:** SceneMetadata, GateResult, PovLock, StubLeakHit, RepetitionHit, all gate Pydantic outputs.

**Concrete excerpt:** see physics/schema.py Notes above. Two variants:
- `frozen=True` for value objects (StubLeakHit, RepetitionHit, GateResult, Chunk) — immutable post-construction
- `extra="forbid"` for ALL — rejects unknown YAML frontmatter keys. SceneMetadata is NOT frozen because its `field_validator` cross-checks need joint access during validation.

### Atomic File Persist (any state file)

**Source:** `src/book_pipeline/alerts/cooldown.py::_persist` (lines 86-99) AND `src/book_pipeline/chapter_assembler/scene_kick.py::_persist_scene_state` (lines 96-101).

**Apply to:** scene_buffer cache writes (SQLite `commit()` is atomic; no extra work needed), pov_locks.yaml hand-edits (pre-commit hook validates schema; no runtime writes).

**Concrete excerpt:**
```python
def _persist_scene_state(record: SceneStateRecord, state_path: Path) -> None:
    """Atomic tmp+rename write — reuse Plan 03-07 _persist pattern."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    tmp_path.replace(state_path)
```

### Test Fixtures (FakeAnthropicClient + FakeEventLogger)

**Source:** `tests/critic/fixtures.py` lines 198-221.

**Apply to:** every test in `tests/physics/test_gates.py`, `tests/critic/test_scene_13axis.py`. Pure-function gate tests (test_schema.py, test_stub_leak.py) need NEITHER fake — direct call + assert on return value.

**Concrete excerpt:** see fixtures.py Notes above. Reuse the existing FakeEventLogger (no need for a physics-specific variant) — the `events: list[Any]` capture is generic.

### Tenacity Retry Decorator

**Source:** `src/book_pipeline/critic/scene.py::_call_opus_inner` lines 375-396.

**Apply to:** ANY new Anthropic call. NONE expected in Phase 7 — physics gates are local; CB-01 retriever is local; scene-buffer is local. The 13-axis critic call REUSES the existing decorator (don't add a parallel one — RESEARCH "Don't Hand-Roll" lines 511-512).

---

## No Analog Found

ZERO files. Every new file has a strong in-repo analog. Phase 7 is pure extension by design (RESEARCH §"Don't Hand-Roll" key insight at line 516: "Phase 7's surface area is 80% extension of existing kernel + 20% new... Phase 7 should NOT introduce a new pattern unless the existing ones cannot be made to work.").

The closest thing to "novel": the SQLite-backed `SceneEmbeddingCache` is the first SQLite-as-cache use in the codebase. The persistence pattern (atomic write) is from `alerts/cooldown.py`; the call pattern is from `rag/embedding.py`; SQLite itself is stdlib. No new dep, no new pattern category — just a new combination.

---

## Metadata

**Analog search scope:**
- `src/book_pipeline/{alerts,drafter,critic,rag,chapter_assembler,regenerator,observability,interfaces,config}/`
- `tests/{critic,drafter,rag,regenerator,alerts}/`
- `pyproject.toml`
- `src/book_pipeline/critic/templates/`

**Files scanned:** 25 source files + 6 test files + 1 pyproject.toml + 1 jinja2 template = 33 total

**Pattern extraction date:** 2026-04-25

**Key reuse counts (sanity check — patterns Phase 7 leverages):**
- Pure-function gate (preflag.py): 5 new files (each gate)
- Pydantic strict-frozen (rag/types.py::Chunk): 6 new files (schema + 5 typed value objects)
- LanceDBRetrieverBase: 1 new file (continuity_bible.py)
- Event emission (scene_kick._emit_scene_kick_event): 5+ new sites (each gate, normalizer, scene-buffer)
- Jinja2 render kwargs append (mode_a.py + critic/scene.py): 2 modified files
- Atomic tmp+rename (scene_kick._persist_scene_state): 1 reuse (scene_buffer SQLite)
- import-linter contract append (Plan 05-03 alerts): 1 reuse (physics package)
- @pytest.mark.slow + skipif(not _indexes_populated()): 2 new slow tests

**Critical rule reminder (RESEARCH §"Anti-Patterns to Avoid" line 499-503):**
1. DO NOT put physics gates inside `chapter_assembler.dag` — D-24 locks pre-flight at drafter only
2. DO NOT put pov_locks in `entity-state/` — must be operator-edited static config
3. The bundler currently emits 6 events; after Phase 7 = 7 events. Update `test_event_count_invariant`
4. DO NOT make stub_leak a critic-prompt axis — pre-LLM short-circuit, hard reject
5. DO NOT re-embed scene text per critic call — cache on FIRST commit
