"""Mechanical validators for LLM pipeline stage outputs (shipped, not test-only).

Promoted from tests/doc_engine/test_pipeline_stages.py so SKILL.md gates and
check_pipeline_output.py can import the same logic CI enforces.

Usage:
    python -m doc_engine.tools.pipeline_validators <run-directory> --target-repo <repo>
"""

from __future__ import annotations

import re

from doc_engine.pipeline.artifacts.signals import VALID_SPRING_ROLES
from doc_engine.pipeline.artifacts.vocab import (
    ResearchTiers,
    ResearchVerdict,
    ReviewLens,
    ReviewSeverity,
)
from doc_engine.tools.doc_tag_utils import VALID_DOC_FILES

FILE_SUMMARY_REQUIRED_KEYS = frozenset({
    "file", "cluster", "summary", "relationships",
    "cross_group_relationships", "group_function", "spring_role", "evidence",
})

GAP_EVIDENCE_CITATION_RE = re.compile(r"[\w][\w./-]*\.[A-Za-z0-9]+(?::\d+)?")
ELIDED_PATH_RE = re.compile(r"/\.\.\.(?:/|\b)")

# Single SoT: StrEnums on artifacts.vocab (encoding contract / DRY).
VALID_REVIEW_LENSES = frozenset(ReviewLens)
VALID_REVIEW_SEVERITIES = frozenset(ReviewSeverity)
VALID_RESEARCH_TIERS = frozenset(ResearchTiers)
VALID_RESEARCH_VERDICTS = frozenset(ResearchVerdict)

NODE_LABEL_PATTERN = re.compile(r'\[["\']?([^\]"\']+)["\']?\]')


def validate_file_summarizer_entries(entries):
    """agents/file-summarizer.md output shape. Returns (index, reason) problems."""
    problems = []
    for index, entry in enumerate(entries):
        missing = FILE_SUMMARY_REQUIRED_KEYS - entry.keys()
        if missing:
            problems.append((index, f"missing keys: {sorted(missing)}"))
            continue
        if entry["spring_role"] not in VALID_SPRING_ROLES:
            problems.append(
                (index, f"spring_role {entry['spring_role']!r} not in {sorted(VALID_SPRING_ROLES)}"),
            )
        for list_field in ("cluster", "relationships", "cross_group_relationships", "evidence"):
            if not isinstance(entry[list_field], list):
                problems.append(
                    (
                        index,
                        f"{list_field} must be a list, got {type(entry[list_field]).__name__}",
                    ),
                )
        if isinstance(entry.get("evidence"), list):
            problems.extend(
                (index, reason) for reason in _evidence_problems(entry["evidence"])
            )
    return problems


def _evidence_problems(evidence):
    reasons = []
    for evidence_index, item in enumerate(evidence):
        if not isinstance(item, dict):
            reasons.append(
                f"evidence[{evidence_index}] must be an object, got {type(item).__name__}",
            )
            continue
        missing = {"line", "what"} - item.keys()
        if missing:
            reasons.append(f"evidence[{evidence_index}] missing keys: {sorted(missing)}")
            continue
        if not isinstance(item["line"], int) or isinstance(item["line"], bool):
            reasons.append(
                f"evidence[{evidence_index}].line must be an int, "
                f"got {type(item['line']).__name__}",
            )
        elif item["line"] < 1:
            reasons.append(
                f"evidence[{evidence_index}].line must be >= 1, got {item['line']}",
            )
        if not isinstance(item["what"], str) or not item["what"].strip():
            reasons.append(f"evidence[{evidence_index}].what must be a non-empty string")
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
    for index, question in enumerate(questions):
        missing = required_keys - question.keys()
        if missing:
            problems.append((index, f"missing keys: {sorted(missing)}"))
            continue
        for reason in _gap_evidence_problems(question["evidence"]):
            problems.append((index, reason))
        if question["blocks_file"] not in VALID_DOC_FILES:
            problems.append(
                (
                    index,
                    f"blocks_file {question['blocks_file']!r} not one of the fourteen output files",
                ),
            )
        if not seen_files_order or seen_files_order[-1] != question["blocks_file"]:
            if question["blocks_file"] in seen_files_order:
                problems.append(
                    (
                        index,
                        f"blocks_file {question['blocks_file']!r} reappears non-contiguously — "
                        "output must be grouped by file",
                    ),
                )
            seen_files_order.append(question["blocks_file"])
    if len(questions) > max_questions:
        problems.append(
            (None, f"{len(questions)} questions exceeds sanity ceiling of {max_questions} — "
                   "gap-analyzer.md says not to pad the list"),
        )
    return problems


def _validate_review_evidence(index: int, evidence) -> list:
    """Return problems for one finding's evidence array."""
    problems = []
    if not isinstance(evidence, list) or not evidence:
        problems.append(
            (index, "evidence must be a non-empty array — a claim with no anchor is unfalsifiable"),
        )
        return problems
    for anchor in evidence:
        if not isinstance(anchor, dict) or "line" not in anchor or "what" not in anchor:
            problems.append((index, f"evidence entry missing line/what: {anchor!r}"))
    return problems


def _validate_external_research(index: int, external: dict) -> list:
    """Return problems for one finding's optional external_research block."""
    problems = []
    verdict = external.get("verdict")
    if verdict not in VALID_RESEARCH_VERDICTS:
        problems.append(
            (index, f"external_research verdict {verdict!r} not one of {sorted(VALID_RESEARCH_VERDICTS)}"),
        )
    sources = external.get("sources", [])
    only_tier_c = bool(sources) and all(
        source.get("tier") == ResearchTiers.C for source in sources
    )
    if only_tier_c:
        problems.append(
            (index, "external_research rests entirely on Tier C sources — Tier C is orientation-only "
             "and may never be the sole ground for a claim"),
        )
    for source in sources:
        if source.get("tier") not in VALID_RESEARCH_TIERS:
            problems.append(
                (index, f"external_research source tier {source.get('tier')!r} "
                 f"not one of {sorted(VALID_RESEARCH_TIERS)}"),
            )
    return problems


def _validate_review_finding(index: int, finding: dict) -> list:
    """Return problems for a single architecture/testing review finding."""
    required_keys = {"lens", "concept", "claim", "evidence", "severity"}
    missing = required_keys - finding.keys()
    if missing:
        return [(index, f"missing keys: {sorted(missing)}")]

    problems = []
    if finding["lens"] not in VALID_REVIEW_LENSES:
        problems.append((index, f"lens {finding['lens']!r} not one of {sorted(VALID_REVIEW_LENSES)}"))
    if finding["severity"] not in VALID_REVIEW_SEVERITIES:
        problems.append(
            (index, f"severity {finding['severity']!r} not one of {sorted(VALID_REVIEW_SEVERITIES)}"),
        )
    problems.extend(_validate_review_evidence(index, finding["evidence"]))
    external = finding.get("external_research")
    if external:
        problems.extend(_validate_external_research(index, external))
    return problems


def validate_architecture_testing_review_findings(findings, max_findings=60):
    problems = []
    for index, finding in enumerate(findings):
        problems.extend(_validate_review_finding(index, finding))
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
    """Stage 5 mechanical checks on summaries, gap_questions, and review when present.

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

    # B4 — wire unused DDIA/testing findings validator into the live Stage 5 gate.
    review_path = os.path.join(artifacts_dir, "architecture_testing_review.json")
    if os.path.isfile(review_path):
        with open(review_path, encoding="utf-8") as fh:
            findings = json.load(fh)
        if not isinstance(findings, list):
            failures.append(
                "architecture_testing_review.json: expected a JSON array of findings, "
                f"got {type(findings).__name__}",
            )
        else:
            for idx, reason in validate_architecture_testing_review_findings(findings):
                label = "entry" if idx is not None else "file"
                failures.append(f"architecture_testing_review.json {label} {idx}: {reason}")

    return failures


def main(argv=None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Mechanical pipeline output validators (summaries, gap_questions, architecture_testing_review).",
    )
    parser.add_argument(
        "artifacts_dir",
        help="directory containing summaries.json / gap_questions.json / architecture_testing_review.json",
    )
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
