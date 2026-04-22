"""book_pipeline.book_specifics — code coupled to *Our Lady of Champion*.

At kernel extraction (ADR-004, post-pipeline-#2-arrival), this package moves to
a separate book_ext/ repo. Until then, import-linter guards the boundary:
kernel modules (drafter/, critic/, rag/, observability/, interfaces/, etc.)
MUST NOT import from here.
"""
