#!/usr/bin/env python3
"""
semantic_eval_helpers.py — the mechanical pre-pass for the
semantic-pipeline-eval skill.

test_pipeline_stages.py already proves an [Evidenced — path:line] citation
*resolves* to a real file/line; it explicitly does not judge whether the
claim next to that citation is actually *true*, whether a
[Confirmed — interview, <date>] tag is really backed by a real interview
answer, or whether two doc-writer files quietly contradict each other.
Those three are genuine semantic-judgment tasks and belong in
skills/semantic-pipeline-eval/SKILL.md's own LLM-driven steps, not here.

But two sub-checks that sound semantic are actually mechanical, and doing
them with an LLM would be wasted judgment budget:

1. find_unmatched_confirmed_tags() — matching a [Confirmed — ...] tag's
   claim text against interview_answers.json's entries is a string/overlap
   lookup, not a judgment call about truth.
2. check_mermaid_syntax() — checking a Mermaid block's bracket/subgraph
   balance, plus whether every edge endpoint is a labeled node somewhere in
   the diagram (find_undefined_node_refs()), is a grammar/structural check,
   not a rendering or semantic judgment. Deliberately not a full Mermaid
   parser (no new dependency) — structural only, sufficient to catch the
   failure class it exists for. Note this is deliberately narrower than
   test_pipeline_stages.py's find_untraceable_nodes(): that function checks
   whether a *labeled* node's label text traces back to a real file/class
   name (a semantic traceability check, already covered there — not
   duplicated here); find_undefined_node_refs() only checks whether a node
   *has* a label at all, a purely structural question.

Running this first narrows what semantic-pipeline-eval's own LLM-driven
Step 2/3/4 actually has to look at, the same "mechanical wherever possible,
narrow LLM-judge only where genuinely needed" split
claude/steering-prompts/01-testability-research-prompt.md already
prescribed for test_pipeline_stages.py.

ASSUMED interview_answers.json SHAPE (not schema-validated anywhere in this
project — see claude/steering-prompts/02-pluggability-research-prompt.md's
still-open "no schema, no validation" gap; this is a consumer of that
prose-only contract, not a fix for it): a JSON array of objects, each with
at least `topic`, `question`, `status` ("answered" or "skipped"), and
(when answered) `answer` and `date` — per skills/document-spring-repo/
SKILL.md's Stage 3 description of what the orchestrator records.

Run with:
    python -m doc_engine.tools.semantic_eval_helpers <artifacts_dir> [--target-repo <path>]
                                      [--out mechanical_findings.json]

<artifacts_dir> is expected to contain interview_answers.json, docs/*.md,
and architecture.md (or a file containing a fenced ```mermaid block) — the
same PIPELINE_ARTIFACTS_DIR layout test_pipeline_stages.py's opt-in
real-artifacts pass already uses. --target-repo is accepted for CLI-shape
parity with that layout and reserved for semantic-pipeline-eval's own
LLM-driven citation-truthfulness step (Step 2 of that skill) — the two
mechanical checks in this file don't need it themselves.
"""

import argparse
import json
import os
import re
import sys

CONFIRMED_TAG_RE = re.compile(r"\[Confirmed — interview, ([^\]]+)\]")

STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "this", "that", "it",
    "its", "to", "of", "in", "on", "for", "and", "or", "not", "be", "by",
    "as", "with", "at", "if", "so", "than", "then", "will", "would",
})

DEFAULT_OVERLAP_THRESHOLD = 0.15


def _tokenize(text):
    """Lowercased word-set tokenization, stopwords removed, for a cheap
    Jaccard-overlap comparison — not a semantic embedding, just enough to
    tell "clearly related" from "clearly unrelated" text."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if w not in STOPWORDS and len(w) > 1}


def _claim_clause(text, tag_start):
    """The sentence (or sentence fragment) immediately preceding a tag —
    the thing the tag is actually claiming to confirm, not the whole
    surrounding paragraph."""
    prefix = text[:tag_start]
    pieces = re.split(r"(?<=[.!?])\s+", prefix)
    return pieces[-1] if pieces else prefix


def find_unmatched_confirmed_tags(text, interview_answers, overlap_threshold=DEFAULT_OVERLAP_THRESHOLD):
    """For every [Confirmed — interview, <date>] tag in text, check whether
    its preceding claim clause has meaningful word overlap with any
    "answered" entry in interview_answers.json. A tag with no reasonably
    close entry is a candidate hallucinated-Confirmed finding — flagged
    here for a human/LLM to look at (see semantic-pipeline-eval's Step 4),
    not asserted as a confirmed hallucination by this function alone: a
    genuine paraphrase can score a low overlap too, which is exactly why
    this is a worklist, not a verdict."""
    answered = [e for e in interview_answers if e.get("status") == "answered"]
    entry_tokens = [
        (_tokenize(" ".join(str(e.get(k, "")) for k in ("topic", "question", "answer"))), e)
        for e in answered
    ]

    findings = []
    for m in CONFIRMED_TAG_RE.finditer(text):
        clause = _claim_clause(text, m.start())
        clause_tokens = _tokenize(clause)
        if not clause_tokens:
            findings.append({
                "tag": m.group(0),
                "claim_clause": clause.strip(),
                "best_overlap": 0.0,
                "closest_entry_topic": None,
                "reason": "empty or unparseable claim clause preceding the tag",
            })
            continue

        best_ratio, best_entry = 0.0, None
        for tokens, entry in entry_tokens:
            if not tokens:
                continue
            overlap = len(clause_tokens & tokens) / len(clause_tokens | tokens)
            if overlap > best_ratio:
                best_ratio, best_entry = overlap, entry

        if best_ratio < overlap_threshold:
            findings.append({
                "tag": m.group(0),
                "claim_clause": clause.strip(),
                "best_overlap": round(best_ratio, 3),
                "closest_entry_topic": best_entry.get("topic") if best_entry else None,
                "reason": "no interview_answers.json entry closely matches this claim — "
                          "candidate hallucinated Confirmed tag, needs semantic confirmation",
            })
    return findings


SUBGRAPH_RE = re.compile(r"^\s*subgraph\b", re.MULTILINE)
END_RE = re.compile(r"^\s*end\s*$", re.MULTILINE)

# A "declared" node: an identifier immediately followed by a label in one of
# Mermaid's three bracket shapes (A["Label"], A(Label), A{Label}).
NODE_DECL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})")

# An edge: two identifiers joined by an arrow (-->, --, -.->,  ==>, etc.),
# each optionally immediately followed by its own label, with an optional
# |edge label| between the arrow and the target. Deliberately permissive
# (not a full grammar) — this only needs the two endpoint identifiers.
EDGE_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})?"
    r"\s*(?:--+>|--+|-\.+->?|==+>?)\s*(?:\|[^|]*\|\s*)?"
    r"([A-Za-z_]\w*)\b"
)


def find_undefined_node_refs(mermaid_text):
    """Every node in this pipeline's diagrams is supposed to carry a real
    file/class label (agents/architect-segment.md rule 3 forbids inventing a
    'friendlier' label, and forbids a bare/unlabeled node in the first
    place) — so an identifier that shows up as an edge endpoint but never
    receives a label anywhere in the diagram is not "implicitly a valid
    unlabeled node" the way it would be in Mermaid generally; for this
    project's diagrams specifically it's the signature of a truncated or
    malformed diagram (a node whose label-bearing declaration got cut off,
    or an architect-merge dedup that dropped a label during stitching).
    Returns the sorted list of such identifiers, empty if none."""
    declared = {m.group(1) for m in NODE_DECL_RE.finditer(mermaid_text)}
    referenced = set()
    for m in EDGE_RE.finditer(mermaid_text):
        referenced.add(m.group(1))
        referenced.add(m.group(2))
    return sorted(referenced - declared)


def check_mermaid_syntax(mermaid_text):
    """Structural (not a full grammar/renderer) checks: bracket/paren/brace
    balance, subgraph/end balance, double-quote balance, and undefined node
    references (find_undefined_node_refs). Sufficient to catch the failure
    class this exists for (a doc-writer or architect subagent emitting a
    truncated or malformed diagram) without adding a Mermaid-parsing
    dependency this project doesn't otherwise need."""
    findings = []
    for open_c, close_c, label in (("[", "]", "square_brackets"), ("(", ")", "parentheses"), ("{", "}", "braces")):
        opens, closes = mermaid_text.count(open_c), mermaid_text.count(close_c)
        if opens != closes:
            findings.append({
                "type": f"unbalanced_{label}",
                "detail": f"{opens} '{open_c}' vs {closes} '{close_c}'",
            })

    subgraph_count, end_count = len(SUBGRAPH_RE.findall(mermaid_text)), len(END_RE.findall(mermaid_text))
    if subgraph_count != end_count:
        findings.append({
            "type": "unbalanced_subgraph_end",
            "detail": f"{subgraph_count} 'subgraph' vs {end_count} 'end'",
        })

    quote_count = mermaid_text.count('"')
    if quote_count % 2 != 0:
        findings.append({
            "type": "unbalanced_quotes",
            "detail": f"{quote_count} double-quote characters (odd count)",
        })

    undefined_refs = find_undefined_node_refs(mermaid_text)
    if undefined_refs:
        findings.append({
            "type": "undefined_node_ref",
            "detail": f"referenced in an edge but never labeled anywhere in the diagram: {undefined_refs}",
        })

    return findings


def _extract_mermaid_block(text):
    """Pulls the first fenced ```mermaid ... ``` block out of a markdown
    file. Returns None if there isn't one."""
    m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else None


def _load_interview_answers(artifacts_dir):
    path = os.path.join(artifacts_dir, "interview_answers.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run(artifacts_dir, overlap_threshold=DEFAULT_OVERLAP_THRESHOLD):
    interview_answers = _load_interview_answers(artifacts_dir)

    confirmed_findings = {}
    docs_dir = os.path.join(artifacts_dir, "docs")
    if os.path.isdir(docs_dir):
        for name in sorted(os.listdir(docs_dir)):
            if not name.endswith(".md"):
                continue
            with open(os.path.join(docs_dir, name), encoding="utf-8") as f:
                text = f.read()
            findings = find_unmatched_confirmed_tags(text, interview_answers, overlap_threshold)
            if findings:
                confirmed_findings[name] = findings

    mermaid_findings = []
    arch_path = os.path.join(artifacts_dir, "docs", "architecture.md")
    if not os.path.isfile(arch_path):
        arch_path = os.path.join(artifacts_dir, "architecture.md")
    if os.path.isfile(arch_path):
        with open(arch_path, encoding="utf-8") as f:
            arch_text = f.read()
        mermaid = _extract_mermaid_block(arch_text)
        if mermaid is not None:
            mermaid_findings = check_mermaid_syntax(mermaid)

    return {
        "artifacts_dir": os.path.abspath(artifacts_dir),
        "unmatched_confirmed_tags_by_file": confirmed_findings,
        "mermaid_syntax_findings": mermaid_findings,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("artifacts_dir", help="Directory containing a completed pipeline run's output (docs/*.md, interview_answers.json, architecture.md)")
    ap.add_argument("--target-repo", default=None,
                     help="Reserved for semantic-pipeline-eval's own LLM-driven citation-truthfulness step; unused by this script's mechanical checks")
    ap.add_argument("--overlap-threshold", type=float, default=DEFAULT_OVERLAP_THRESHOLD,
                     help=f"Jaccard word-overlap threshold below which a [Confirmed] tag is flagged (default: {DEFAULT_OVERLAP_THRESHOLD})")
    ap.add_argument("--out", default=None, help="Optional path to write findings as JSON")
    args = ap.parse_args()

    if not os.path.isdir(args.artifacts_dir):
        print(f"error: not a directory: {args.artifacts_dir}", file=sys.stderr)
        sys.exit(1)

    report = run(args.artifacts_dir, args.overlap_threshold)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    total_confirmed = sum(len(v) for v in report["unmatched_confirmed_tags_by_file"].values())
    print(f"semantic_eval_helpers: {total_confirmed} unmatched [Confirmed] tag(s) across "
          f"{len(report['unmatched_confirmed_tags_by_file'])} file(s); "
          f"{len(report['mermaid_syntax_findings'])} Mermaid syntax finding(s).")


if __name__ == "__main__":
    main()
