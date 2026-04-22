"""book_pipeline.rag.retrievers — 5 typed Retriever implementations + shared base.

Plan 02-03 Task 1 lands the base class + reranker. Task 2 rewrites this file
to pre-declare all 5 concrete retrievers (B-1 sole-ownership).
"""

from book_pipeline.rag.retrievers.base import LanceDBRetrieverBase

__all__ = ["LanceDBRetrieverBase"]
