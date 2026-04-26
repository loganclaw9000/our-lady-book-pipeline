"""PovLock + load_pov_locks tests (Plan 07-01 Task 2).

Covers Tests 6-10 from the plan <behavior> block:
- Test 6: PovLock.applies_to() handles INCLUSIVE active_from_chapter and
  excludes ch09 retry per OQ-01 (a) RESOLVED.
- Test 7: expires_at_chapter is EXCLUSIVE upper bound.
- Test 8: load_pov_locks() returns dict keyed by lowercase character name.
- Test 9: property test sweeps chapter 1..30 asserting the activation
  invariant holds for various lock configs.
- Test 10: extra="forbid" — unknown YAML field raises ValidationError.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from book_pipeline.physics.locks import PovLock, PovLockConfig, load_pov_locks
from book_pipeline.physics.schema import Perspective


def _make_lock(
    *,
    character: str = "itzcoatl",
    perspective: Perspective = Perspective.FIRST_PERSON,
    active_from_chapter: int = 15,
    expires_at_chapter: int | None = None,
    rationale: str = "test",
) -> PovLock:
    return PovLock(
        character=character,
        perspective=perspective,
        active_from_chapter=active_from_chapter,
        expires_at_chapter=expires_at_chapter,
        rationale=rationale,
    )


def test_applies_to_inclusive_active_from_chapter() -> None:
    """Test 6: applies_to(14)=False, applies_to(15)=True, applies_to(9)=False."""
    lock = _make_lock(active_from_chapter=15)
    assert lock.applies_to(14) is False
    assert lock.applies_to(15) is True
    assert lock.applies_to(9) is False  # OQ-01 (a) RESOLVED — ch09 retry not gated
    assert lock.applies_to(20) is True  # no upper bound — applies to all >= 15


def test_applies_to_exclusive_expires_at_chapter() -> None:
    """Test 7: expires_at_chapter is EXCLUSIVE — applies_to(20)=False, (19)=True."""
    lock = _make_lock(active_from_chapter=15, expires_at_chapter=20)
    assert lock.applies_to(15) is True
    assert lock.applies_to(19) is True
    assert lock.applies_to(20) is False  # exclusive upper
    assert lock.applies_to(21) is False


def test_load_pov_locks_returns_lowercase_keyed_dict() -> None:
    """Test 8: load_pov_locks() loads from default config/pov_locks.yaml.

    Reads config/pov_locks.yaml via PovLockConfig (settings sources). Asserts
    the Itzcoatl lock landed exactly per OQ-01 (a) RESOLVED.
    """
    locks = load_pov_locks()
    assert "itzcoatl" in locks
    itz = locks["itzcoatl"]
    assert itz.perspective is Perspective.FIRST_PERSON
    assert itz.active_from_chapter == 15
    # Verify ch09 retry NOT gated per OQ-01(a) RESOLVED.
    assert itz.applies_to(9) is False
    # Verify ch15+ IS gated.
    assert itz.applies_to(15) is True


def test_load_pov_locks_path_override(tmp_path: Path) -> None:
    """load_pov_locks accepts an explicit path override (test injection)."""
    yaml_path = tmp_path / "alt_locks.yaml"
    yaml_path.write_text(
        "locks:\n"
        "  - character: tlaloc\n"
        "    perspective: 3rd_close\n"
        "    active_from_chapter: 5\n"
        "    rationale: test override\n",
        encoding="utf-8",
    )
    locks = load_pov_locks(yaml_path=yaml_path)
    assert "tlaloc" in locks
    assert locks["tlaloc"].perspective is Perspective.THIRD_CLOSE
    assert locks["tlaloc"].active_from_chapter == 5


@pytest.mark.parametrize("active_from", [1, 10, 15, 27])
def test_applies_to_invariant_sweep_no_expiry(active_from: int) -> None:
    """Test 9 (property): activation invariant holds across chapter 1..30 with no expiry."""
    lock = _make_lock(active_from_chapter=active_from, expires_at_chapter=None)
    for chapter in range(1, 31):
        expected = chapter >= active_from
        assert lock.applies_to(chapter) is expected, (
            f"chapter={chapter}, active_from={active_from}, expected={expected}"
        )


@pytest.mark.parametrize(
    ("active_from", "expires_at"),
    [(10, 20), (1, 5), (15, 27), (5, 6)],
)
def test_applies_to_invariant_sweep_with_expiry(
    active_from: int, expires_at: int
) -> None:
    """Test 9 (property): activation invariant with explicit expiry."""
    lock = _make_lock(
        active_from_chapter=active_from, expires_at_chapter=expires_at
    )
    for chapter in range(1, 31):
        expected = active_from <= chapter < expires_at
        assert lock.applies_to(chapter) is expected, (
            f"chapter={chapter}, active_from={active_from}, "
            f"expires_at={expires_at}, expected={expected}"
        )


def test_extra_forbid_rejects_unknown_yaml_field(tmp_path: Path) -> None:
    """Test 10: unknown field in pov_locks.yaml raises ValidationError."""
    yaml_path = tmp_path / "bad_locks.yaml"
    yaml_path.write_text(
        "locks:\n"
        "  - character: itzcoatl\n"
        "    perspective: 1st_person\n"
        "    active_from_chapter: 15\n"
        "    rationale: test\n"
        "    priority: high\n",  # unknown field — should fail extra="forbid"
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_pov_locks(yaml_path=yaml_path)


def test_pov_lock_extra_forbid_at_root(tmp_path: Path) -> None:
    """Unknown root-level YAML key raises ValidationError."""
    yaml_path = tmp_path / "bad_root.yaml"
    yaml_path.write_text(
        "locks: []\n"
        "extra_key: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_pov_locks(yaml_path=yaml_path)


def test_pov_lock_chapter_bounds_enforced() -> None:
    """active_from_chapter outside [1, 999] raises ValidationError (T-07-02 echo)."""
    with pytest.raises(ValidationError):
        PovLock(
            character="x",
            perspective=Perspective.FIRST_PERSON,
            active_from_chapter=0,
            rationale="test",
        )
    with pytest.raises(ValidationError):
        PovLock(
            character="x",
            perspective=Perspective.FIRST_PERSON,
            active_from_chapter=1000,
            rationale="test",
        )


def test_pov_lock_config_class_loads_default() -> None:
    """PovLockConfig() reads config/pov_locks.yaml via Settings sources."""
    cfg = PovLockConfig()
    assert any(lock.character.lower() == "itzcoatl" for lock in cfg.locks)
