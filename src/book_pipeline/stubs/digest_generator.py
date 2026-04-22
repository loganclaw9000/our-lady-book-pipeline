"""Stub DigestGenerator — NotImplementedError. Concrete impl lands in Phase 5 (DIGEST-01)."""

from __future__ import annotations

from book_pipeline.interfaces.digest_generator import DigestGenerator
from book_pipeline.interfaces.types import Event


class StubDigestGenerator:
    """Structurally satisfies DigestGenerator Protocol. NotImplementedError on every call."""

    def generate(
        self,
        week_start_iso: str,
        events: list[Event],
        metrics: dict[str, object],
        theses: list[dict[str, object]],
    ) -> str:
        raise NotImplementedError(
            "StubDigestGenerator.generate: concrete impl lands in Phase 5 (DIGEST-01)."
        )


_: DigestGenerator = StubDigestGenerator()
