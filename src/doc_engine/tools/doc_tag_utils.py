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

import os
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


def _valid_tag_spans(text):
    spans = set()
    for pattern in TAG_PATTERNS.values():
        for match in pattern.finditer(text):
            spans.add((match.start(), match.end()))
    return spans


def find_malformed_tags(text):
    """Bracketed spans that start with a recognized tag word but don't match
    any of the five exact required forms in TAG_PATTERNS. Returns the raw
    malformed spans found, in order."""
    all_valid_spans = _valid_tag_spans(text)
    return [
        match.group(0)
        for match in TAG_WORD_SPAN.finditer(text)
        if (match.start(), match.end()) not in all_valid_spans
    ]


def count_tags_by_kind(text):
    return {kind: len(pattern.findall(text)) for kind, pattern in TAG_PATTERNS.items()}


def _line_count(path: str) -> int:
    with open(path, encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _citation_failure(match, repo_root: str):
    """Return (citation, reason) when the citation does not resolve, else None."""
    relpath, line = match.group(1), match.group(2)
    abspath = os.path.join(repo_root, relpath)
    if not os.path.isfile(abspath):
        return match.group(0), f"{relpath} does not exist under {repo_root}"
    if line is None:
        return None
    line_count = _line_count(abspath)
    if int(line) > line_count:
        return match.group(0), (
            f"{relpath} has {line_count} lines, citation points past the end"
        )
    return None


def resolve_evidenced_citations(text, repo_root):
    """For every well-formed [Evidenced — path[:line]] tag, confirm the path
    exists under repo_root and, if a line number was cited, that the file
    actually has that many lines. Returns a list of (citation_text, reason)
    for anything that fails to resolve — empty list means everything
    resolved. This is the mechanical equivalent of FActScore-style claim
    verification (arXiv:2305.14251), applied to file/line citations instead
    of natural-language atomic facts.

    Lives here rather than in test_pipeline_stages.py because
    check_pipeline_output.py gates a real run's output with it, and a
    runtime checker importing from a test module would make that test file
    a dependency of the pipeline itself."""
    failures = []
    for match in TAG_PATTERNS["evidenced"].finditer(text):
        failure = _citation_failure(match, repo_root)
        if failure is not None:
            failures.append(failure)
    return failures
