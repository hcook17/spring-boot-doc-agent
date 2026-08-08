#!/usr/bin/env python3
"""
citation_coverage.py — finds claims in generated docs that carry *no*
evidence tag at all, the failure class every other checker here cannot see.

Usage:
    python -m doc_engine.tools.citation_coverage <docs_dir> --target-repo <repo>
    python -m doc_engine.tools.citation_coverage <docs_dir> --json     # machine-readable
    python -m doc_engine.tools.citation_coverage <docs_dir> --strict   # exit 1 on findings

Reports two worklists — untagged claims, and tags whose anchor looks weak —
and narrows where a human should look. It does not judge whether a tagged
claim is true; that is skills/semantic-pipeline-eval/'s job.

WHY THIS EXISTS AS A THIRD CHECKER

There are already two, and neither can see an absent citation:

  * check_pipeline_output.py (via doc_tag_utils.py) gates a run on tag
    *shape* and citation *resolvability*. Both of its checks iterate over
    tags that are already present: find_malformed_tags() only matches
    bracket spans that already start with a recognized tag word, and
    resolve_evidenced_citations() only iterates TAG_PATTERNS["evidenced"]
    matches. A sentence carrying no tag at all matches neither pattern, so
    it is not "failing" — it is invisible.

  * skills/semantic-pipeline-eval/ judges whether a claim next to a tag is
    actually true. It samples [Evidenced] claims — again, claims that
    already carry a tag.

So the pipeline's entire verification stack is keyed on tags that exist.
An omitted citation is the one defect none of it can report, which is
exactly the defect this file targets. This is a coverage checker, not a
truthfulness checker; the boundary is the same one test_pipeline_stages.py
and check_pipeline_output.py already draw around themselves.

THE TWO CHECKS

1. Untagged claims (find_untagged_claims)
   A sentence that names a concrete repo artifact -- a source path, an
   @Annotation, a CamelCase type, a method(), a dotted config key -- is a
   substantive claim under doc-taxonomy.md's "General rule across all
   fourteen" and must end in a tag. A sentence that names no artifact is
   commentary/connective prose and is deliberately exempt.

   That artifact gate is the whole false-positive story. Flagging every
   untagged sentence would drown a real finding in narration; a prior
   session hit exactly this while validating session-log entries and found
   most untagged bullets "legitimately shouldn't" carry a tag because they
   are context lines. "If you named a code artifact, cite where it lives"
   is the narrowest rule that still catches the real defect.

2. Weak anchors (find_weak_anchors)
   resolve_evidenced_citations() proves a cited path exists and that the
   file is at least that many lines long. It cannot tell "Foo.java:42",
   where the claim is genuinely supported, from "Foo.java:3", where the
   claim is about something at line 87 -- both resolve. This check reads
   the cited window and asks whether any identifier the claim actually
   names appears in it, splitting the answer into two findings that mean
   different things:

     symbol_absent_from_file   -- the named symbol appears nowhere in the
                                  cited file. The stronger signal: this is
                                  the shape of a citation invented to
                                  satisfy the tag grammar.
     symbol_outside_window     -- the symbol is in the file, but not near
                                  the cited line. A real file, an
                                  imprecise line anchor.

   Both are worklists, not verdicts -- the same framing
   semantic_eval_helpers.find_unmatched_confirmed_tags() uses, and for the
   same reason: a claim can paraphrase code that shares no literal token
   with it. A human or a model settles it; this script only narrows where
   to look.

DELIBERATELY NOT DONE HERE

Judging whether a well-anchored claim is *true*. That needs a model. Same
boundary as check_pipeline_output.py's docstring states; see
skills/semantic-pipeline-eval/.

No new dependency -- stdlib only, matching every other script here.
"""

import argparse
import json
import os
import re
import sys

from doc_engine.tools.doc_tag_utils import TAG_PATTERNS, TAG_WORD_SPAN

# A window of +/- this many lines around a cited line counts as "near" the
# citation for the weak-anchor check. Wide enough to cover a method whose
# signature is cited but whose body carries the detail; narrow enough that
# "somewhere else in a 900-line file" is still reported.
DEFAULT_ANCHOR_WINDOW = 8

# Concrete repo artifacts. A sentence naming any of these is making a claim
# about the code and therefore needs a citation; a sentence naming none of
# them is prose. Ordered most-specific first only for readability -- all are
# applied together.
ARTIFACT_PATTERNS = (
    # a source/config path: Foo.java, application.yml, build.gradle, Dockerfile
    re.compile(r"\b[\w./-]+\.(?:java|kt|xml|ya?ml|properties|gradle|sql|json|tf|sh)\b"),
    re.compile(r"\bDockerfile\b"),
    # a Spring/Java annotation
    re.compile(r"@[A-Z]\w+"),
    # a method or constructor call: save(), findByOwnerId()
    re.compile(r"\b[a-z]\w*\(\)"),
    # a CamelCase type: OwnerController, JpaRepository
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b"),
    # a dotted config key: spring.datasource.url (>=3 segments, so ordinary
    # prose like "e.g." or a sentence-ending abbreviation can't trigger it)
    re.compile(r"\b[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+){2,}\b"),
    # SCREAMING_SNAKE constants and env vars
    re.compile(r"\b[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+)+\b"),
)

# Identifier-ish tokens pulled out of a claim to look for near its citation.
# Deliberately narrower than ARTIFACT_PATTERNS: these are things that would
# appear *verbatim in source*, so a path (`src/main/java/...`) is excluded --
# a Java file does not contain its own path.
CLAIM_SYMBOL_PATTERNS = (
    re.compile(r"@[A-Z]\w+"),
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b"),
    re.compile(r"\b([a-z]\w*)\(\)"),
    re.compile(r"\b[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+)+\b"),
    re.compile(r"\b[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+){2,}\b"),
)

# Structural boilerplate the taxonomy explicitly asks writers to emit. These
# are not claims and must never be flagged as uncited.
EXEMPT_LINE_RE = re.compile(
    r"^\s*(?:none found|not applicable|n/?a|asked,\s*not answered|tbd)\s*\.?\s*$",
    re.IGNORECASE,
)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
HEADING_RE = re.compile(r"^\s*#")
TABLE_RULE_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


# A URL's host and path look exactly like a dotted config key and a source
# path respectively (`ast-grep.github.io`, `docs/spec/run-cycle/`), so links
# are removed before artifact detection. Citing a code artifact is the
# trigger for needing evidence; linking to a website is not.
URL_RE = re.compile(r"<?https?://[^\s>)\]]+>?")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((?:[^)]*)\)")


def _strip_inline_code(text):
    """Backticked spans keep their content -- an identifier is just as much a
    claim inside backticks as outside -- but the backticks themselves are
    dropped so patterns anchored on \\b behave predictably. URLs are removed
    entirely, for the reason given at URL_RE."""
    text = MD_LINK_RE.sub(r"\1", text)
    text = URL_RE.sub(" ", text)
    return text.replace("`", "")


def _skip_claim_line(line):
    """True when a stripped markdown line cannot carry a claim unit."""
    if not line or HEADING_RE.match(line) or TABLE_RULE_RE.match(line):
        return True
    if line.startswith("<!--") or line.startswith(">"):
        return True
    return bool(EXEMPT_LINE_RE.match(BULLET_PREFIX_RE.sub("", line)))


def _sentences_from_line(line):
    body = BULLET_PREFIX_RE.sub("", line)
    for sentence in SENTENCE_SPLIT_RE.split(body):
        sentence = sentence.strip()
        if sentence:
            yield sentence


def _advance_fence(raw, in_fence):
    """Toggle fence state when ``raw`` is a fence marker; else return unchanged."""
    if FENCE_RE.match(raw):
        return (not in_fence), True
    return in_fence, False


def _claim_units_from_raw_line(lineno, raw, in_fence):
    """Yield claim units from one raw line; return updated fence state."""
    in_fence, is_fence = _advance_fence(raw, in_fence)
    if is_fence or in_fence or _skip_claim_line(raw.strip()):
        return in_fence, ()
    return in_fence, tuple((lineno, sentence) for sentence in _sentences_from_line(raw.strip()))


def iter_claim_units(text):
    """Yield (line_number, sentence) for every sentence in the document that
    could carry a claim.

    Skipped: fenced blocks (code and mermaid alike), headings, blank lines,
    table rules, HTML comments, and the taxonomy's structural placeholders.
    Everything else is split into sentences, because doc-taxonomy.md's rule
    is per-claim, not per-bullet -- a bullet whose second sentence is tagged
    does not thereby cite its first.
    """
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        in_fence, units = _claim_units_from_raw_line(lineno, raw, in_fence)
        yield from units


# TAG_WORD_SPAN is case-sensitive, which leaves a documented hole: a tag
# written `[evidenced — Foo.java:6]` matches neither TAG_PATTERNS (so it
# counts as zero tags) nor TAG_WORD_SPAN (so find_malformed_tags() never
# sees it either). A prior session named this exactly -- "a fully different
# casing isn't caught as malformed, it's simply invisible to a grep-shaped
# check." It is a citation the writer did make and every counter scores as
# absent, so it is reported here as its own finding rather than being folded
# into untagged_claim, which would describe the wrong defect.
ANY_CASE_TAG_SPAN = re.compile(
    r"\[(?:evidenced|confirmed|unknown|per existing docs)\b[^\]]*\]", re.IGNORECASE)


def _has_tag(sentence):
    """True if the sentence carries any bracketed span starting with a
    recognized tag word, in any casing.

    Deliberately loose on two axes. It uses the tag-word span rather than
    TAG_PATTERNS' exact forms, because a *malformed* tag is still an attempt
    to cite and find_malformed_tags() already reports it -- counting it as
    untagged too would file one defect as two. And it is case-insensitive
    for the same reason: a miscased tag is reported by find_miscased_tags()
    below, so it must not also surface as a missing one."""
    return bool(ANY_CASE_TAG_SPAN.search(sentence))


def find_miscased_tags(text):
    """Bracketed spans that read as a tag in some casing other than the
    required one. These are invisible to every other counter in the repo:
    doc_tag_utils' patterns are all case-sensitive, so such a span is
    neither a valid tag nor a malformed one."""
    findings = []
    for m in ANY_CASE_TAG_SPAN.finditer(text):
        if TAG_WORD_SPAN.match(m.group(0)):
            continue
        findings.append({
            "kind": "miscased_tag",
            "tag": m.group(0),
            "claim": _claim_clause(text, m.start()).strip(),
            "reason": "tag word is not in its required casing — invisible to "
                      "both find_malformed_tags() and the tag counters, so "
                      "this citation is scored as absent everywhere",
        })
    return findings


def _named_artifacts(sentence):
    found = []
    stripped = _strip_inline_code(sentence)
    for pattern in ARTIFACT_PATTERNS:
        for m in pattern.finditer(stripped):
            found.append(m.group(0))
    return found


def find_untagged_claims(text):
    """Sentences that name a concrete repo artifact but carry no tag of any
    kind. Returns a list of finding dicts."""
    findings = []
    for lineno, sentence in iter_claim_units(text):
        if _has_tag(sentence):
            continue
        artifacts = _named_artifacts(sentence)
        if not artifacts:
            continue
        findings.append({
            "kind": "untagged_claim",
            "line": lineno,
            "claim": sentence,
            "named_artifacts": sorted(set(artifacts)),
            "reason": "names a code artifact but carries no evidence tag — "
                      "every substantive claim must end in one of the five "
                      "forms in doc-taxonomy.md",
        })
    return findings


def _claim_clause(text, tag_start):
    """The sentence immediately preceding a tag. Same definition (and same
    one-line implementation) as semantic_eval_helpers._claim_clause; kept
    local rather than imported so this script does not depend on a module
    that exists to serve a different skill."""
    prefix = text[:tag_start]
    pieces = SENTENCE_SPLIT_RE.split(prefix)
    return pieces[-1] if pieces else prefix


def claim_symbols(clause):
    """Identifiers from a claim that would plausibly appear verbatim in
    source. The cited file's own path is not one of them, which is why this
    uses CLAIM_SYMBOL_PATTERNS rather than ARTIFACT_PATTERNS."""
    stripped = _strip_inline_code(clause)
    return {
        (m.group(1) if m.re.groups else m.group(0))
        for pattern in CLAIM_SYMBOL_PATTERNS
        for m in pattern.finditer(stripped)
    }


def _read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def _weak_anchor_finding(kind, match, clause, symbols, in_file, reason):
    return {
        "kind": kind,
        "citation": match.group(0),
        "claim": clause.strip(),
        "symbols": sorted(symbols),
        "found_elsewhere_in_file": sorted(in_file),
        "reason": reason,
    }


def _symbols_for_evidenced_match(text, match, relpath):
    """Claim symbols for one Evidenced tag, minus the cited file's own stem."""
    clause = _claim_clause(text, match.start())
    symbols = claim_symbols(clause)
    stem = os.path.splitext(os.path.basename(relpath))[0]
    symbols.discard(stem)
    return clause, symbols


def _classify_weak_anchor(match, clause, symbols, lines, target, relpath, window):
    """Return one weak-anchor finding dict, or None when the window is fine."""
    lo = max(0, target - 1 - window)
    hi = min(len(lines), target + window)
    window_text = "\n".join(lines[lo:hi])
    if any(symbol in window_text for symbol in symbols):
        return None

    file_text = "\n".join(lines)
    in_file = {s for s in symbols if s in file_text}
    if in_file:
        return _weak_anchor_finding(
            "symbol_outside_window",
            match,
            clause,
            symbols,
            in_file,
            (
                f"none of the claim's symbols appear within +/-{window} "
                f"lines of {relpath}:{target}, though they exist elsewhere "
                f"in the file — the line anchor looks imprecise"
            ),
        )
    return _weak_anchor_finding(
        "symbol_absent_from_file",
        match,
        clause,
        symbols,
        (),
        (
            f"none of the claim's symbols appear anywhere in "
            f"{relpath} — candidate fabricated citation"
        ),
    )


def _weak_anchor_for_match(text, match, repo_root, window):
    """Evaluate one Evidenced match; return a finding or None."""
    relpath, line = match.group(1), match.group(2)
    if line is None:
        return None
    abspath = os.path.join(repo_root, relpath)
    if not os.path.isfile(abspath):
        return None

    clause, symbols = _symbols_for_evidenced_match(text, match, relpath)
    if not symbols:
        return None

    lines = _read_lines(abspath)
    target = int(line)
    if target > len(lines):
        return None  # past end of file: resolve_evidenced_citations()'s report
    return _classify_weak_anchor(match, clause, symbols, lines, target, relpath, window)


def find_weak_anchors(text, repo_root, window=DEFAULT_ANCHOR_WINDOW):
    """For every [Evidenced — path:line] tag whose claim names at least one
    symbol, check whether that symbol appears near the cited line.

    Only line-bearing citations are checked: a whole-file citation
    ([Evidenced — build.gradle]) is a legitimate form under the taxonomy and
    has no anchor to be weak. Citations that do not resolve at all are
    skipped silently here -- resolve_evidenced_citations() owns that report,
    and duplicating it would file one defect twice.
    """
    findings = []
    for match in TAG_PATTERNS["evidenced"].finditer(text):
        finding = _weak_anchor_for_match(text, match, repo_root, window)
        if finding:
            findings.append(finding)
    return findings


def check_docs(docs_dir, target_repo, window=DEFAULT_ANCHOR_WINDOW):
    """Run both checks over every .md in docs_dir. Returns
    {filename: {"untagged_claims": [...], "weak_anchors": [...]}}."""
    report = {}
    for name in sorted(os.listdir(docs_dir)):
        if not name.endswith(".md"):
            continue
        text = open(os.path.join(docs_dir, name), encoding="utf-8").read()
        entry = {
            "untagged_claims": find_untagged_claims(text),
            "miscased_tags": find_miscased_tags(text),
            "weak_anchors": [],
        }
        if target_repo is not None:
            entry["weak_anchors"] = find_weak_anchors(text, target_repo, window)
        report[name] = entry
    return report


def total_findings(report):
    return sum(len(v["untagged_claims"]) + len(v["miscased_tags"]) + len(v["weak_anchors"])
               for v in report.values())


def _format_untagged_lines(findings):
    lines = []
    for finding in findings:
        lines.append(f"  [untagged_claim] line {finding['line']}: {finding['claim'][:110]}")
        lines.append(
            f"      names {', '.join(finding['named_artifacts'][:5])} — no evidence tag"
        )
    return lines


def _format_miscased_lines(findings):
    lines = []
    for finding in findings:
        lines.append(f"  [miscased_tag] {finding['tag']}")
        lines.append(f"      {finding['reason']}")
    return lines


def _format_weak_anchor_lines(findings):
    lines = []
    for finding in findings:
        lines.append(f"  [{finding['kind']}] {finding['citation']}")
        lines.append(f"      claim: {finding['claim'][:110]}")
        lines.append(f"      {finding['reason']}")
    return lines


def _format_file_findings(name, entry):
    items = entry["untagged_claims"] + entry["miscased_tags"] + entry["weak_anchors"]
    if not items:
        return []
    lines = [f"{name}:"]
    lines.extend(_format_untagged_lines(entry["untagged_claims"]))
    lines.extend(_format_miscased_lines(entry["miscased_tags"]))
    lines.extend(_format_weak_anchor_lines(entry["weak_anchors"]))
    return lines


def format_report(report, target_repo):
    lines = []
    for name in sorted(report):
        lines.extend(_format_file_findings(name, report[name]))
    if target_repo is None:
        lines.append(
            "NOTE: no --target-repo given, so the weak-anchor check did not run. "
            "Only untagged-claim coverage was checked."
        )
    if not lines:
        lines.append("No citation-coverage findings.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Report claims that carry no evidence tag, and citations "
                    "whose line anchor does not appear to support the claim."
    )
    parser.add_argument("docs_dir", help="directory of generated .md docs")
    parser.add_argument("--target-repo", default=None,
                        help="the documented repo, needed for the weak-anchor check")
    parser.add_argument("--window", type=int, default=DEFAULT_ANCHOR_WINDOW,
                        help=f"lines each side of a citation that count as 'near' "
                             f"(default {DEFAULT_ANCHOR_WINDOW})")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="emit the raw finding objects instead of prose")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 when there are findings. Off by default: "
                             "both checks are worklists, and a run should not "
                             "fail on a heuristic the way it fails on an "
                             "unresolvable citation.")
    args = parser.parse_args()

    if not os.path.isdir(args.docs_dir):
        print(f"error: not a directory: {args.docs_dir}", file=sys.stderr)
        return 2

    report = check_docs(args.docs_dir, args.target_repo, args.window)

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report, args.target_repo))
        print(f"\n{total_findings(report)} finding(s) across {len(report)} file(s).")

    return 1 if (args.strict and total_findings(report)) else 0


if __name__ == "__main__":
    sys.exit(main())
