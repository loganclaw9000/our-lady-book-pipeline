"""Narrative Physics kernel package (Phase 7).

ADR-004 clean boundary — book-domain-free. Imports from
``book_pipeline.book_specifics`` are prohibited by import-linter contract 1;
imports into ``book_pipeline.interfaces`` are prohibited by contract 2
(EXCEPT for the additive-nullable scene_metadata field on DraftRequest;
TYPE_CHECKING import inside interfaces/types.py keeps the runtime cycle empty).

Single-file modules per ADR-004 (populated in Task 2):

- ``schema.py`` — SceneMetadata + Contents + CharacterPresence + Staging +
  ValueCharge + Perspective enum + Treatment enum (Plan 07-01).
- ``locks.py`` — PovLock model + load_pov_locks() YAML loader (Plan 07-01).
- ``canon_bible.py`` — CanonBibleView composer (Plan 07-03).
- ``stub_leak.py`` — STUB_LEAK_PATTERNS regex set + scan_stub_leak() pure fn (Plan 07-04).
- ``repetition_loop.py`` — n-gram repetition detector (Plan 07-04).
- ``scene_buffer.py`` — SceneEmbeddingCache + cosine_similarity_to_prior() (Plan 07-05).
- ``gates/`` — pov_lock, motivation, ownership, treatment, quantity pre-flight
  gates (Plan 07-03).

Task 2 of this plan replaces this docstring-only file with the full re-export list.
"""

__all__: list[str] = []
