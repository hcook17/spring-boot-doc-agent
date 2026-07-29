#!/usr/bin/env python3
"""Thin shim — implementation: doc_engine.tools.doc_tag_utils."""

from doc_engine.tools.doc_tag_utils import *  # noqa: F403
from doc_engine.tools.doc_tag_utils import (  # noqa: F401
    TAG_PATTERNS,
    TAG_WORD_SPAN,
    VALID_DOC_FILES,
    count_tags_by_kind,
    find_malformed_tags,
    resolve_evidenced_citations,
)
