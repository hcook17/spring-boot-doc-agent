#!/usr/bin/env python3
"""
doc_tag_utils.py — the required evidence-tag grammar for the fourteen
document-spring-repo output files, and the fourteen-file name set itself.

Extracted out of test_pipeline_stages.py (which originally defined all of
this inline) so that run_manifest.py's evidence_tag_counts computation can
reuse the exact same regexes instead of a second, independently-maintained
copy that could silently drift out of sync with what the tests actually
enforce. Production code (run_manifest.py) and test code
(test_pipeline_stages.py) both import from here; neither imports from the
other.

Source of truth for the tag grammar itself:
skills/document-spring-repo/references/doc-taxonomy.md's "General rule
across all fourteen", five numbered forms, verbatim.
"""

import re

# The fourteen documentation files this pipeline produces — the doc-writer
# fan-out list and gap-analyzer's blocks_file allowlist both draw from this
# same set. Source of truth: skills/document-spring-repo/references/doc-taxonomy.md's
# fourteen numbered sections.
VALID_DOC_FILES = frozenset({
    "readme", "architecture", "integrations", "authorization", "database",
    "operations", "observability", "troubleshooting", "configuration",
    "change_impact", "glossary", "local_development", "testing",
    "known_limitations",
})

# doc-taxonomy.md's "General rule across all fourteen", five numbered forms,
# verbatim. A doc-writer output containing a bracketed tag that looks like
# one of these but doesn't match exactly (wrong dash, wrong case, missing
# the citation) is the specific failure class this pattern exists to catch.
TAG_PATTERNS = {
    "evidenced": re.compile(r"\[Evidenced — ([^\];]+?)(?::(\d+))?(?:; inference avoided beyond this)?\]"),
    "confirmed": re.compile(r"\[Confirmed — interview, [^\]]+\]"),
    "unknown": re.compile(r"\[Unknown — not evidenced in code, not covered in interview\]"),
    "per_existing_docs": re.compile(r"\[Per existing docs — [^,]+, unverified against code\]"),
}

# Any bracketed run that starts with one of the five tag *words* but doesn't
# match its exact required pattern above — malformed-tag detection works by
# finding all bracket spans that start with a known tag word, then checking
# whether they were also matched by TAG_PATTERNS.
TAG_WORD_SPAN = re.compile(r"\[(Evidenced|Confirmed|Unknown|Per existing docs)\b[^\]]*\]")


def find_malformed_tags(text):
    """Bracketed spans that start with a recognized tag word but don't match
    any of the five exact required forms in TAG_PATTERNS. Returns the raw
    malformed spans found, in order."""
    all_valid_spans = set()
    for pattern in TAG_PATTERNS.values():
        for m in pattern.finditer(text):
            all_valid_spans.add((m.start(), m.end()))

    malformed = []
    for m in TAG_WORD_SPAN.finditer(text):
        if (m.start(), m.end()) not in all_valid_spans:
            malformed.append(m.group(0))
    return malformed


def count_tags_by_kind(text):
    return {kind: len(pattern.findall(text)) for kind, pattern in TAG_PATTERNS.items()}
