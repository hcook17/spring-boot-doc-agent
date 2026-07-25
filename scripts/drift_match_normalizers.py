#!/usr/bin/env python3
"""
drift_match_normalizers.py — candidate equivalence relations on ast-grep match
text, for spring_drift_check tier 2's generic per-rule comparison.

Library-only: imported by test_drift_normalization.py, never run, so it carries
no Usage: block by design (CONTRIBUTING.md's docstring contract exempts modules
with no __main__ entry point).

WHAT THIS IS FOR

spring_signal_scan._first_line_match() is the identity function tier 2 compares
citations under for every rule that has no specialized extractor -- all of them
except raw_queries__query, persistence__entity and persistence__repository. It
keeps the match's FIRST LINE. ast-grep returns the whole match, so when an
annotation is wrapped across lines the stored identity degrades to
"@RequestMapping(" -- which compares equal to nothing, and the citation reads
as drifted although not one token moved.

MEASURED, on scripts/test_fixtures/spring_signals across four formatting-only
perturbations (test_drift_normalization.py re-derives all of these):

    normalizer                 false pos    missed real changes
    first_line (status quo)      2 / 208           0 / 2
    collapse_ws                  2 / 208           0 / 2
    strip_ws_outside_strings     0 / 208           0 / 2
    tokens                       0 / 208           0 / 2

Two arms, because the first is trivially winnable: a normalizer mapping every
input to "" scores zero false positives and detects nothing. No candidate may
buy a lower false-positive count with a missed real change.

NOTHING HERE IS WIRED IN YET, AND THAT IS THE POINT OF LANDING IT SEPARATELY

Adopting `tokens` is not a drop-in substitution, because _first_line_match()
does two jobs at once: it decides what tier 2 COMPARES, and it decides what
spring_signals.json STORES in each citation's `match` field -- which is
human-readable evidence a doc-writer agent reads. A token sequence joined by
\\x1f is a fine identity and unreadable evidence. Separating those two jobs
changes the stored schema, so it is a decision with its own blast radius and
its own PR, and it should be made against this table rather than against an
intuition. See claude/drift-normalization-measurement-2026-07-25.md.
"""
import re
from typing import Callable, Dict, List

Normalizer = Callable[[str], str]

# spring_signal_scan._first_line_match truncates here; candidates match it so
# the comparison is between relations, not between length limits.
MAX_LEN = 200


def first_line(text: str) -> str:
    """Status quo, copied from spring_signal_scan._first_line_match. Present so
    the table above has a baseline row measured by the same harness as the
    candidates, rather than quoted from another run."""
    if not text:
        return ""
    return text.splitlines()[0].strip()[:MAX_LEN]


def collapse_ws(text: str) -> str:
    """Every whitespace run to one space, over the whole match. Recovers what
    first_line discards, but '@Get( "/x" )' still differs from '@Get("/x")',
    so wrapping is only half-addressed -- which the table confirms: it scores
    exactly as the status quo does."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()[:MAX_LEN]


_STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"')


def strip_ws_outside_strings(text: str) -> str:
    """Delete all whitespace except inside string literals.

    Reaches zero false positives, but is NOT injective on Java: the identifier
    `inta` and the declaration `int a` normalize to the same string. Whether
    that collision is reachable from ast-grep match text is an empirical
    question nobody has answered, which is why `tokens` is preferred at equal
    measured cost -- an unproven collision is still a collision."""
    if not text:
        return ""
    out: List[str] = []
    last = 0
    for m in _STRING_LITERAL.finditer(text):
        out.append(re.sub(r"\s+", "", text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(re.sub(r"\s+", "", text[last:]))
    return "".join(out)[:MAX_LEN]


# Java tokens in priority order. Not a grammar -- enough to tokenize the
# annotation and declaration fragments ast-grep actually returns as match text,
# which is a far smaller language than Java.
_TOKEN = re.compile(
    r'"(?:[^"\\]|\\.)*"'          # string literal
    r"|'(?:[^'\\]|\\.)*'"         # char literal
    r"|//[^\n]*"                  # line comment
    r"|/\*.*?\*/"                 # block comment
    r"|[A-Za-z_$][A-Za-z0-9_$]*"  # identifier or keyword
    r"|\d[\d._A-Za-z]*"           # numeric literal
    r"|@"                         # annotation marker
    r"|[^\s]",                    # any other single punctuation character
    re.DOTALL,
)
_IS_COMMENT = re.compile(r"^(//|/\*)")

# Chosen because it cannot occur in Java source, so no two distinct token
# sequences can join to the same string. That is what makes `tokens` injective
# where strip_ws_outside_strings is not.
TOKEN_SEP = "\x1f"


def tokens(text: str) -> str:
    """Token sequence with comments dropped, joined by an unrepresentable
    separator. This is Type-1 for real: whitespace and comments cannot move it,
    and distinct token sequences cannot collide."""
    if not text:
        return ""
    toks = [t for t in _TOKEN.findall(text) if not _IS_COMMENT.match(t)]
    return TOKEN_SEP.join(toks)[:MAX_LEN]


CANDIDATES: Dict[str, Normalizer] = {
    "first_line": first_line,
    "collapse_ws": collapse_ws,
    "strip_ws_outside_strings": strip_ws_outside_strings,
    "tokens": tokens,
}

# The status quo, named so a test can assert the baseline row is the baseline
# rather than hardcoding the string in two places.
STATUS_QUO = "first_line"
