"""Ingress adapters."""

from stf.ingest.review import (
    findings_to_spec_seed,
    ingest_review_markdown,
    ingest_review_path,
)

__all__ = [
    "findings_to_spec_seed",
    "ingest_review_markdown",
    "ingest_review_path",
]
