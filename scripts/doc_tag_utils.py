#!/usr/bin/env python3
"""Thin shim — implementation: doc_engine.tools.doc_tag_utils."""

from doc_engine.tools.doc_tag_utils import *  # noqa: F403
from doc_engine.tools.doc_tag_utils import (  # noqa: F401
    VALID_DOC_FILES,
    TAG_PATTERNS,
    TAG_WORD_SPAN,
    find_malformed_tags,
    count_tags_by_kind,
    resolve_evidenced_citations,
)
