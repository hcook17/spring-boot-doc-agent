#!/usr/bin/env python3
"""
java_perturbations.py — source edits that provably do or do not change a Java
file's meaning, for measuring spring_drift_check's false-positive rate.

Library-only: imported by test_drift_normalization.py, never run, so it carries
no Usage: block by design (CONTRIBUTING.md's docstring contract exempts modules
with no __main__ entry point).

WHY THIS EXISTS

spring_drift_check tier 2 answers "did this citation actually move?" for a file
tier 1 saw change. It is only worth having if it says no when nothing moved. To
measure that, you need edits whose correct answer is known in advance:

  FORMATTING_ONLY   a Type-1 clone in Zhang & Saber's taxonomy (arXiv:2506.14470
                    section II-A): identical except for formatting and comments.
                    Every "drifted" verdict after one of these is a false
                    positive, with no judgement call involved in scoring it.

  DELIBERATELY_BROKEN
                    not formatting-only, and not honestly labelled as such. See
                    below -- these exist to test the harness, not the checker.

WHY A BROKEN PERTURBATION IS SHIPPED ON PURPOSE

The first version of wrap_annotation_args rewrote annotation-looking text
*inside comments*. That broke a doc comment's closing quote, left the file
unparseable, and made ast-grep return nothing -- so every citation in the file
read as drift. The measured false-positive rate came out at 7/208 when the true
figure was 2/208: a 3.5x overstatement, caught only by opening the files by
hand.

The lesson is that "this edit preserves meaning" is a claim about the harness,
and an unverified claim about the harness is indistinguishable from a finding
about the checker. So broken_wrap_annotation_args is kept, exactly as it was
written, as a test input: test_drift_normalization.py asserts that the validity
gate REJECTS it. A gate that has never been shown to reject anything is not a
gate.
"""
import re
from typing import Callable, Dict, List

Transform = Callable[[str], str]


def add_comment(src: str) -> str:
    """Insert a line comment above the first annotation. Comments appear in no
    AST, so this is the purest Type-1 edit available."""
    out: List[str] = []
    done = False
    for line in src.splitlines(keepends=True):
        if not done and line.lstrip().startswith("@"):
            indent = line[:len(line) - len(line.lstrip())]
            out.append(indent + "// reviewed during a drift measurement\n")
            done = True
        out.append(line)
    return "".join(out)


def reindent(src: str) -> str:
    """Double every leading indent. Java is whitespace-insensitive, so this
    cannot move a single token."""
    out: List[str] = []
    for line in src.splitlines(keepends=True):
        if not line.strip():
            out.append(line)
            continue
        lead = line[:len(line) - len(line.lstrip())]
        out.append(lead + line)
    return "".join(out)


def blank_lines(src: str) -> str:
    """Insert a blank line early, shifting every later line number without
    touching a token. Separates "the citation moved" from "the citation's line
    number moved", which are different questions."""
    return src.replace("\n\n", "\n\n\n", 1)


_ANNOTATION_CALL = re.compile(r"(@\w+)\(([^()]+)\)\s*")


def wrap_annotation_args(src: str) -> str:
    '''Split @GetMapping("/x") across three lines. Same tree, different FIRST
    line -- and the first line is what java_extract.first_line_match()
    keeps, so this is the one formatting class tier 2 currently mis-reads.

    Line-scoped, and only for a line that is itself an annotation at statement
    position: block-comment interiors are tracked and skipped, and any line
    carrying // is left alone. That skipping is the entire difference between
    this and broken_wrap_annotation_args below.'''
    out: List[str] = []
    in_block = False
    for line in src.splitlines(keepends=True):
        stripped = line.lstrip()
        if in_block:
            out.append(line)
            if "*/" in line:
                in_block = False
            continue
        if stripped.startswith("/*"):
            out.append(line)
            in_block = "*/" not in line
            continue
        if not stripped.startswith("@") or "//" in line:
            out.append(line)
            continue
        m = _ANNOTATION_CALL.fullmatch(stripped)
        if m is None:
            out.append(line)
            continue
        indent = line[:len(line) - len(stripped)]
        out.append(indent + m.group(1) + "(\n")
        out.append(indent + "        " + m.group(2) + "\n")
        out.append(indent + ")\n")
    return "".join(out)


def broken_wrap_annotation_args(src: str) -> str:
    """The original, defective wrap_annotation_args, preserved verbatim.

    It matches anywhere in the file, including inside comments, so a comment
    quoting an annotation gets rewritten across lines and the file stops
    parsing. NOT formatting-only, despite looking like it. Kept as the input
    that proves the validity gate can reject something -- see this module's
    docstring."""
    def repl(m: "re.Match[str]") -> str:
        return f"{m.group(1)}(\n        {m.group(2)}\n    )"
    return re.sub(r"(@\w+)\(([^()\n]+)\)", repl, src, count=99)


FORMATTING_ONLY: Dict[str, Transform] = {
    "add_comment": add_comment,
    "reindent": reindent,
    "blank_lines": blank_lines,
    "wrap_annotation_args": wrap_annotation_args,
}

DELIBERATELY_BROKEN: Dict[str, Transform] = {
    "broken_wrap_annotation_args": broken_wrap_annotation_args,
}
