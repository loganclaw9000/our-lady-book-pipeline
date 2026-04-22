"""book_pipeline.corpus_ingest — kernel-eligible ingestion pipeline.

Reads corpus files (paths injected by the caller; kernel does NOT hardcode
any book-specific paths), chunks + embeds + writes to 5 LanceDB tables under
`indexes/`, emits one ingestion_run Event per non-skipped run. Heading-level
axis classification for multi-axis files (brief.md) is a caller-provided
callable (DI seam to the book-specific heading-classifier module).

Phase 2 Plan 02. CORPUS-01.

Kernel boundary: this package imports nothing from the book-specific package.
Import-linter contract 1 enforces this on every commit. The CLI composition
seam (book_pipeline.cli.ingest) is the only place allowed to bridge the
book-specific corpus-paths and heading-classifier modules into this kernel;
that cross-boundary import is documented in pyproject.toml's ignore_imports
for contract 1.
"""

from book_pipeline.corpus_ingest.ingester import CorpusIngester, IngestionReport
from book_pipeline.corpus_ingest.router import AXIS_NAMES, route_file_to_axis

__all__ = [
    "AXIS_NAMES",
    "CorpusIngester",
    "IngestionReport",
    "route_file_to_axis",
]
