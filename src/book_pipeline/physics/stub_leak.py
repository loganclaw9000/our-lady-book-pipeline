"""stub_leak deterministic detector (Plan 07-04 PHYSICS-08).

Pattern set per D-17 + D-27 + Pitfall 4: anchored line-start patterns, no
nested quantifiers. Bounded by line length, not whole-text length. The canary
case (drafts/ch11/ch11_sc03.md line 119: ``Establish: the friendship that will
become Bernardo's death-witness in Ch 26.``) is line 1 of test_stub_leak.py.

WARNING #5 mitigation: ``Goal``, ``Conflict``, ``Outcome`` are EXCLUDED from
the directive whitelist because they have legitimate prose uses (e.g.
"His goal: to warn Xochitl.", "The conflict: father versus son.",
"The outcome: she died."). Cases where a stub-author types
``Goal: ... / Conflict: ... / Outcome: ...`` inline at line-start are rare AND
covered by (a) the bracketed-label pattern for ``[character intro]:`` style,
and (b) the motivation gate's narrower stub-leak guard. The calibration test
(``tests/physics/test_stub_leak.py::test_3c_zero_false_positive_on_canon``)
runs the pattern against ch01-04 canon files and asserts zero matches.

Pure function; no side effects; no LLM call. Run BEFORE the Anthropic critic
call to short-circuit at FAIL severity (Plan 07-05 wires this into the critic
flow).
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

# Anchored line-start DIRECTIVE pattern. Whitelist after WARNING #5 calibration:
# ``Establish | Resolve | Set up | Setup | Beat | Function | Disaster |
# Reaction | Dilemma | Decision``. Goal / Conflict / Outcome EXCLUDED — see
# module docstring.
#
# Pitfall 4 (regex DoS) mitigations applied:
#   - ``re.MULTILINE`` so ``^`` anchors at the start of every line; matching
#     bounded by line length, not whole-text length.
#   - ``re.IGNORECASE`` so ``ESTABLISH:`` / ``establish:`` both match.
#   - NO nested quantifiers (no ``(.*)``, no ``(\s+)+``, no ``(.+)+``).
#   - Alternation across literal keywords + bounded ``\s*:`` tail.
_PATTERN_DIRECTIVE = re.compile(
    r"^\s*(?:Establish|Resolve|Set up|Setup|Beat|Function|"
    r"Disaster|Reaction|Dilemma|Decision)\s*:",
    re.MULTILINE | re.IGNORECASE,
)

# Anchored line-start BRACKETED-LABEL pattern: ``[character intro]:``,
# ``[opening tableau]:``, etc. — bracket-wrapped label followed by colon.
# Bounded character class + line-anchor + no nested quantifier.
_PATTERN_BRACKETED_LABEL = re.compile(
    r"^\s*\[[a-z_ ]+\]\s*:",
    re.MULTILINE,
)


STUB_LEAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    _PATTERN_DIRECTIVE,
    _PATTERN_BRACKETED_LABEL,
)


class StubLeakHit(BaseModel):
    """One stub-leak detection. ``pattern_id`` ∈ {"directive", "bracketed_label"}."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern_id: str
    line_number: int  # 1-indexed
    matched_text: str  # the offending line (capped at 200 chars)


def scan_stub_leak(scene_text: str) -> list[StubLeakHit]:
    """Return the list of stub-leak hits in ``scene_text``. Empty list = pass.

    Pure function; no side effects; deterministic; no LLM call. Iterates
    line-by-line so a hit's ``line_number`` is meaningful for downstream
    issue-citation in critic responses.
    """
    if not scene_text:
        return []
    hits: list[StubLeakHit] = []
    for line_no, line in enumerate(scene_text.splitlines(), start=1):
        if _PATTERN_DIRECTIVE.match(line):
            hits.append(
                StubLeakHit(
                    pattern_id="directive",
                    line_number=line_no,
                    matched_text=line[:200],
                )
            )
        elif _PATTERN_BRACKETED_LABEL.match(line):
            hits.append(
                StubLeakHit(
                    pattern_id="bracketed_label",
                    line_number=line_no,
                    matched_text=line[:200],
                )
            )
    return hits


__all__ = ["STUB_LEAK_PATTERNS", "StubLeakHit", "scan_stub_leak"]
