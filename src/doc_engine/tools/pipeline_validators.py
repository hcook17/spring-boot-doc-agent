"""Mechanical validators for LLM pipeline stage outputs (shipped, not test-only).

Promoted from tests/test_pipeline_stages.py so SKILL.md gates and
check_pipeline_output.py can import the same logic CI enforces.

Usage:
    python3 scripts/pipeline_validators.py <run-directory> --target-repo <repo>
"""

from __future__ import annotations

import re

from doc_engine.tools.doc_tag_utils import VALID_DOC_FILES

# agents/file-summarizer.md step 4's exact enumerated list.
VALID_SPRING_ROLES = frozenset({
    "controller", "service", "repository", "entity", "config", "security",
    "messaging-producer", "messaging-consumer", "test", "other",
})

FILE_SUMMARY_REQUIRED_KEYS = frozenset({
    "file", "cluster", "summary", "relationships",
    "cross_group_relationships", "group_function", "spring_role", "evidence",
})

GAP_EVIDENCE_CITATION_RE = re.compile(r"[\w][\w./-]*\.[A-Za-z0-9]+(?::\d+)?")
ELIDED_PATH_RE = re.compile(r"/\.\.\.(?:/|\b)")

VALID_REVIEW_LENSES = frozenset({"ddia", "testing"})
VALID_REVIEW_SEVERITIES = frozenset({"informational", "worth-flagging"})
VALID_RESEARCH_TIERS = frozenset({"A", "B", "C"})
VALID_RESEARCH_VERDICTS = frozenset({"CONFIRMED", "PLAUSIBLE", "REFUTED", "UNRESOLVED"})

NODE_LABEL_PATTERN = re.compile(r'\[["\']?([^\]"\']+)["\']?\]')


def validate_file_summarizer_entries(entries):
    """agents/file-summarizer.md output shape. Returns (index, reason) problems."""
    problems = []
    for i, entry in enumerate(entries):
        missing = FILE_SUMMARY_REQUIRED_KEYS - entry.keys()
        if missing:
            problems.append((i, f"missing keys: {sorted(missing)}"))
            continue
        if entry["spring_role"] not in VALID_SPRING_ROLES:
            problems.append((i, f"spring_role {entry['spring_role']!r} not in {sorted(VALID_SPRING_ROLES)}"))
        for list_field in ("cluster", "relationships", "cross_group_relationships", "evidence"):
            if not isinstance(entry[list_field], list):
                problems.append((i, f"{list_field} must be a list, got {type(entry[list_field]).__name__}"))
        if isinstance(entry.get("evidence"), list):
            problems.extend((i, r) for r in _evidence_problems(entry["evidence"]))
    return problems


def _evidence_problems(evidence):
    reasons = []
    for j, item in enumerate(evidence):
        if not isinstance(item, dict):
            reasons.append(f"evidence[{j}] must be an object, got {type(item).__name__}")
            continue
        missing = {"line", "what"} - item.keys()
        if missing:
            reasons.append(f"evidence[{j}] missing keys: {sorted(missing)}")
            continue
        if not isinstance(item["line"], int) or isinstance(item["line"], bool):
            reasons.append(f"evidence[{j}].line must be an int, got {type(item['line']).__name__}")
        elif item["line"] < 1:
            reasons.append(f"evidence[{j}].line must be >= 1, got {item['line']}")
        if not isinstance(item["what"], str) or not item["what"].strip():
            reasons.append(f"evidence[{j}].what must be a non-empty string")
    return reasons


def _gap_evidence_problems(evidence):
    if not isinstance(evidence, str) or not evidence.strip():
        return ["evidence must be a non-empty string"]
    if ELIDED_PATH_RE.search(evidence):
        return ["evidence cites an elided path (`/.../`) — it must resolve"]
    if not GAP_EVIDENCE_CITATION_RE.search(evidence):
        return [
            "evidence carries no file citation — gap-analyzer.md requires a resolvable path/File.java:line",
        ]
    return []


def validate_gap_analyzer_questions(questions, max_questions=40):
    problems = []
    required_keys = {"blocks_file", "topic", "question", "evidence"}
    seen_files_order = []
    for i, q in enumerate(questions):
        missing = required_keys - q.keys()
        if missing:
            problems.append((i, f"missing keys: {sorted(missing)}"))
            continue
        for reason in _gap_evidence_problems(q["evidence"]):
            problems.append((i, reason))
        if q["blocks_file"] not in VALID_DOC_FILES:
            problems.append((i, f"blocks_file {q['blocks_file']!r} not one of the fourteen output files"))
        if not seen_files_order or seen_files_order[-1] != q["blocks_file"]:
            if q["blocks_file"] in seen_files_order:
                problems.append(
                    (i, f"blocks_file {q['blocks_file']!r} reappears non-contiguously — output must be grouped by file"),
                )
            seen_files_order.append(q["blocks_file"])
    if len(questions) > max_questions:
        problems.append(
            (None, f"{len(questions)} questions exceeds sanity ceiling of {max_questions} — "
                   "gap-analyzer.md says not to pad the list"),
        )
    return problems


def validate_architecture_testing_review_findings(findings, max_findings=60):
    problems = []
    required_keys = {"lens", "concept", "claim", "evidence", "severity"}
    for i, f in enumerate(findings):
        missing = required_keys - f.keys()
        if missing:
            problems.append((i, f"missing keys: {sorted(missing)}"))
            continue
        if f["lens"] not in VALID_REVIEW_LENSES:
            problems.append((i, f"lens {f['lens']!r} not one of {sorted(VALID_REVIEW_LENSES)}"))
        if f["severity"] not in VALID_REVIEW_SEVERITIES:
            problems.append((i, f"severity {f['severity']!r} not one of {sorted(VALID_REVIEW_SEVERITIES)}"))
        evidence = f["evidence"]
        if not isinstance(evidence, list) or not evidence:
            problems.append((i, "evidence must be a non-empty array — a claim with no anchor is unfalsifiable"))
        else:
            for anchor in evidence:
                if not isinstance(anchor, dict) or "line" not in anchor or "what" not in anchor:
                    problems.append((i, f"evidence entry missing line/what: {anchor!r}"))
        external = f.get("external_research")
        if external:
            verdict = external.get("verdict")
            if verdict not in VALID_RESEARCH_VERDICTS:
                problems.append(
                    (i, f"external_research verdict {verdict!r} not one of {sorted(VALID_RESEARCH_VERDICTS)}"),
                )
            sources = external.get("sources", [])
            only_tier_c = bool(sources) and all(s.get("tier") == "C" for s in sources)
            if only_tier_c:
                problems.append(
                    (i, "external_research rests entirely on Tier C sources — Tier C is orientation-only "
                     "and may never be the sole ground for a claim"),
                )
            for source in sources:
                if source.get("tier") not in VALID_RESEARCH_TIERS:
                    problems.append(
                        (i, f"external_research source tier {source.get('tier')!r} "
                         f"not one of {sorted(VALID_RESEARCH_TIERS)}"),
                    )
    if len(findings) > max_findings:
        problems.append(
            (None, f"{len(findings)} findings exceeds sanity ceiling of {max_findings} — "
                   "agents/software-architect-and-testing.md says not to force a quota"),
        )
    return problems


def extract_mermaid_node_labels(mermaid_text):
    return NODE_LABEL_PATTERN.findall(mermaid_text)


def find_untraceable_nodes(mermaid_text, known_names):
    untraceable = []
    for label in extract_mermaid_node_labels(mermaid_text):
        if not any(label in known or known in label for known in known_names):
            untraceable.append(label)
    return untraceable


def run_stage5_gate(artifacts_dir, target_repo):
    """Stage 5 mechanical checks on summaries and gap_questions when present.

    Returns a list of human-readable failure strings (empty if all pass).
    """
    import json
    import os

    failures: list[str] = []
    summaries_path = os.path.join(artifacts_dir, "summaries.json")
    if os.path.isfile(summaries_path):
        with open(summaries_path, encoding="utf-8") as fh:
            entries = json.load(fh)
        for idx, reason in validate_file_summarizer_entries(entries):
            failures.append(f"summaries.json entry {idx}: {reason}")

    gap_path = os.path.join(artifacts_dir, "gap_questions.json")
    if os.path.isfile(gap_path):
        with open(gap_path, encoding="utf-8") as fh:
            questions = json.load(fh)
        for idx, reason in validate_gap_analyzer_questions(questions):
            failures.append(f"gap_questions.json entry {idx}: {reason}")

    return failures


def main(argv=None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Mechanical pipeline output validators (summaries, gap_questions).",
    )
    parser.add_argument("artifacts_dir", help="directory containing summaries.json / gap_questions.json")
    parser.add_argument(
        "--target-repo",
        default=None,
        help="target repo path (reserved for future citation checks; optional today)",
    )
    args = parser.parse_args(argv)

    failures = run_stage5_gate(args.artifacts_dir, args.target_repo or args.artifacts_dir)
    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
