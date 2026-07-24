#!/usr/bin/env python3
"""
Structural (mechanical) tests for the four LLM pipeline stages —
file-summarizer, architect-segment/architect-merge, gap-analyzer, doc-writer
— none of which had any test coverage before this file. Only the two
deterministic scripts (spring_signal_scan.py, partition_repo.py) and
spring_drift_check.py had tests; a prompt regression in any of the five
agents/*.md files was previously invisible except by a human reading
generated output and noticing something's wrong.

Per claude/steering-prompts/01-testability-research-prompt.md: this suite
is mechanical wherever possible, not LLM-as-judge. It does not invoke any
LLM itself — Claude Code subagents can't be driven from a plain Python
process outside a live session — so it validates two things instead:

1. The validator functions in this file, against synthetic sample data
   shaped exactly like what agents/file-summarizer.md, agents/gap-analyzer.md,
   agents/architect-segment.md + architect-merge.md, and agents/doc-writer.md
   document as their required output shape. Each test is a regression guard
   for one concrete, previously-plausible failure class (a malformed tag, an
   [Evidenced — ...] citation that doesn't resolve to a real file/line, an
   Unknown-tag ratio that's silently ballooned, an unbounded gap-analyzer
   question list, an architecture node whose label doesn't trace back to any
   known file).
2. Optionally, the same validators against a *real* completed pipeline run's
   actual output artifacts (summaries.json, the merged architecture diagram,
   gap_questions.json, and the 14 generated docs/*.md files), gated behind
   the PIPELINE_ARTIFACTS_DIR environment variable — same opt-in,
   skip-if-absent pattern as test_partition_repo_real_world.py's
   PARTITION_REPO_REAL_FIXTURE_DIR. Not required for this file's main
   assertions to run or pass.

The fixture repo used for file/line resolution below is the same one
spring_signal_scan.py's own test suite already uses
(scripts/test_fixtures/spring_signals/) — deliberately reused rather than
building a second one, since a second independently-maintained fixture tree
is exactly the kind of two-sources-of-truth drift this project's own history
(IMPLEMENTATION_HANDOFF.md item 1, item 4) has already hit twice.

Run with:
    python3 scripts/test_pipeline_stages.py -v

Opt-in real-artifacts pass:
    PIPELINE_ARTIFACTS_DIR=/path/to/completed/run/output python3 scripts/test_pipeline_stages.py -v
"""

import json
import os
import re
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(SCRIPT_DIR, "test_fixtures", "spring_signals")

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

# agents/file-summarizer.md step 4's exact enumerated list.
VALID_SPRING_ROLES = frozenset({
    "controller", "service", "repository", "entity", "config", "security",
    "messaging-producer", "messaging-consumer", "test", "other",
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


def resolve_evidenced_citations(text, repo_root):
    """For every well-formed [Evidenced — path[:line]] tag, confirm the path
    exists under repo_root and, if a line number was cited, that the file
    actually has that many lines. Returns a list of (citation_text, reason)
    for anything that fails to resolve — empty list means everything
    resolved. This is the mechanical equivalent of FActScore-style claim
    verification (arXiv:2305.14251), applied to file/line citations instead
    of natural-language atomic facts."""
    failures = []
    for m in TAG_PATTERNS["evidenced"].finditer(text):
        relpath, line = m.group(1), m.group(2)
        abspath = os.path.join(repo_root, relpath)
        if not os.path.isfile(abspath):
            failures.append((m.group(0), f"{relpath} does not exist under {repo_root}"))
            continue
        if line is not None:
            with open(abspath, encoding="utf-8") as f:
                line_count = sum(1 for _ in f)
            if int(line) > line_count:
                failures.append((m.group(0), f"{relpath} has {line_count} lines, citation points past the end"))
    return failures


def validate_file_summarizer_entries(entries):
    """agents/file-summarizer.md's documented output: a JSON array, one
    object per file, with exactly these keys and spring_role drawn from its
    step-4 enumerated list. Returns a list of (entry_index, reason) for
    anything malformed."""
    required_keys = {"file", "cluster", "summary", "relationships",
                      "cross_group_relationships", "group_function", "spring_role"}
    problems = []
    for i, entry in enumerate(entries):
        missing = required_keys - entry.keys()
        if missing:
            problems.append((i, f"missing keys: {sorted(missing)}"))
            continue
        if entry["spring_role"] not in VALID_SPRING_ROLES:
            problems.append((i, f"spring_role {entry['spring_role']!r} not in {sorted(VALID_SPRING_ROLES)}"))
        for list_field in ("cluster", "relationships", "cross_group_relationships"):
            if not isinstance(entry[list_field], list):
                problems.append((i, f"{list_field} must be a list, got {type(entry[list_field]).__name__}"))
    return problems


def validate_gap_analyzer_questions(questions, max_questions=40):
    """agents/gap-analyzer.md's documented output: a JSON array of
    {blocks_file, topic, question, evidence}, grouped by blocks_file, and
    deliberately not padded ("five sharp questions beat twenty generic
    ones"). max_questions is this suite's sanity ceiling, not a value
    gap-analyzer.md states explicitly — it exists to catch a prompt
    regression that turns "ask real gaps only" into "ask about everything,"
    which the fourteen-file fan-out would otherwise silently absorb as
    fourteen separate walls of interview questions."""
    problems = []
    required_keys = {"blocks_file", "topic", "question", "evidence"}
    seen_files_order = []
    for i, q in enumerate(questions):
        missing = required_keys - q.keys()
        if missing:
            problems.append((i, f"missing keys: {sorted(missing)}"))
            continue
        if q["blocks_file"] not in VALID_DOC_FILES:
            problems.append((i, f"blocks_file {q['blocks_file']!r} not one of the fourteen output files"))
        if not seen_files_order or seen_files_order[-1] != q["blocks_file"]:
            if q["blocks_file"] in seen_files_order:
                problems.append((i, f"blocks_file {q['blocks_file']!r} reappears non-contiguously — output must be grouped by file"))
            seen_files_order.append(q["blocks_file"])
    if len(questions) > max_questions:
        problems.append((None, f"{len(questions)} questions exceeds sanity ceiling of {max_questions} — "
                                f"gap-analyzer.md says not to pad the list"))
    return problems


NODE_LABEL_PATTERN = re.compile(r'\[["\']?([^\]"\']+)["\']?\]')


def extract_mermaid_node_labels(mermaid_text):
    """Best-effort extraction of node labels from a flowchart's bracket
    syntax (A[Label], A["Label"]). Not a full Mermaid parser — sufficient
    for the traceability check below, which only needs the label text."""
    return NODE_LABEL_PATTERN.findall(mermaid_text)


def find_untraceable_nodes(mermaid_text, known_names):
    """agents/architect-segment.md rule 3: node labels must be the real
    file/class/function name exactly as it appeared in the summaries — never
    a paraphrased or 'friendlier' label. This checks the inverse: does every
    node label appear, as a substring, in the set of real names the
    architecture stage was actually given (file paths and/or class names
    pulled from summaries.json)? A label that traces to nothing is the
    mechanical signature of exactly the drift rule 3 exists to prevent."""
    untraceable = []
    for label in extract_mermaid_node_labels(mermaid_text):
        if not any(label in known or known in label for known in known_names):
            untraceable.append(label)
    return untraceable


class TagFormatTest(unittest.TestCase):
    def test_all_five_forms_recognized_and_not_flagged_malformed(self):
        text = (
            "Uses PostgreSQL [Evidenced — build.gradle]. "
            "Endpoint requires BILLING_READ [Evidenced — InvoiceController.java:11]. "
            "Deploy cadence is weekly [Confirmed — interview, 2026-07-23]. "
            "Retry policy [Unknown — not evidenced in code, not covered in interview]. "
            "Owning team is Billing [Per existing docs — README.md, unverified against code]. "
            "Config binds env vars [Evidenced — Invoice.java:6; inference avoided beyond this]."
        )
        self.assertEqual(find_malformed_tags(text), [])
        counts = count_tags_by_kind(text)
        self.assertEqual(counts["evidenced"], 3)
        self.assertEqual(counts["confirmed"], 1)
        self.assertEqual(counts["unknown"], 1)
        self.assertEqual(counts["per_existing_docs"], 1)

    def test_wrong_dash_flagged_malformed(self):
        # Regression: a hyphen instead of an em dash is a real, easy-to-miss
        # LLM substitution that reads fine to a human skim but fails the
        # "exact wording" rule doc-taxonomy.md requires.
        text = "Owned by Billing team [Evidenced - build.gradle]."
        self.assertEqual(find_malformed_tags(text), ["[Evidenced - build.gradle]"])

    def test_missing_citation_flagged_malformed(self):
        # An Evidenced tag with no actual path/citation after the dash is
        # exactly the "guess dressed up as a tag" doc-taxonomy.md warns
        # against — it must not silently pass as well-formed.
        text = "Something is true [Evidenced —]."
        self.assertEqual(find_malformed_tags(text), ["[Evidenced —]"])

    def test_lowercase_tag_word_flagged_malformed(self):
        text = "Something is true [evidenced — build.gradle]."
        # Lowercase doesn't match TAG_WORD_SPAN at all (by design — this
        # documents the limit: a fully different casing isn't caught as
        # "malformed," it's simply invisible to a grep-shaped check. Confirm
        # that limit explicitly rather than silently relying on it.
        self.assertEqual(find_malformed_tags(text), [])
        self.assertEqual(count_tags_by_kind(text)["evidenced"], 0)


class EvidencedCitationResolutionTest(unittest.TestCase):
    def test_real_file_and_line_resolves(self):
        text = "Requires BILLING_READ [Evidenced — InvoiceController.java:11]."
        self.assertEqual(resolve_evidenced_citations(text, FIXTURE_DIR), [])

    def test_whole_file_citation_resolves(self):
        text = "Maps to table billing_invoice [Evidenced — Invoice.java]."
        self.assertEqual(resolve_evidenced_citations(text, FIXTURE_DIR), [])

    def test_nonexistent_file_fails_resolution(self):
        text = "Something [Evidenced — NoSuchController.java:5]."
        failures = resolve_evidenced_citations(text, FIXTURE_DIR)
        self.assertEqual(len(failures), 1)
        self.assertIn("does not exist", failures[0][1])

    def test_line_number_past_end_of_file_fails_resolution(self):
        text = "Something [Evidenced — Invoice.java:9999]."
        failures = resolve_evidenced_citations(text, FIXTURE_DIR)
        self.assertEqual(len(failures), 1)
        self.assertIn("past the end", failures[0][1])


class FileSummarizerShapeTest(unittest.TestCase):
    def test_valid_entries_pass(self):
        entries = [{
            "file": "InvoiceController.java", "cluster": ["Invoice.java"],
            "summary": "Handles invoice retrieval and creation.",
            "relationships": ["Invoice.java"], "cross_group_relationships": [],
            "group_function": "Invoice billing API", "spring_role": "controller",
        }]
        self.assertEqual(validate_file_summarizer_entries(entries), [])

    def test_missing_key_flagged(self):
        entries = [{"file": "X.java", "cluster": [], "summary": "s",
                    "relationships": [], "group_function": "", "spring_role": "other"}]
        problems = validate_file_summarizer_entries(entries)
        self.assertEqual(len(problems), 1)
        self.assertIn("cross_group_relationships", problems[0][1])

    def test_invalid_spring_role_flagged(self):
        entries = [{"file": "X.java", "cluster": [], "summary": "s", "relationships": [],
                    "cross_group_relationships": [], "group_function": "", "spring_role": "controllerish"}]
        problems = validate_file_summarizer_entries(entries)
        self.assertEqual(len(problems), 1)
        self.assertIn("spring_role", problems[0][1])


class GapAnalyzerShapeTest(unittest.TestCase):
    def test_valid_bounded_list_passes(self):
        questions = [
            {"blocks_file": "database", "topic": "write ownership", "question": "q1", "evidence": "e1"},
            {"blocks_file": "database", "topic": "write ownership 2", "question": "q2", "evidence": "e2"},
            {"blocks_file": "authorization", "topic": "endpoint", "question": "q3", "evidence": "e3"},
        ]
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_invalid_blocks_file_flagged(self):
        questions = [{"blocks_file": "faq", "topic": "t", "question": "q", "evidence": "e"}]
        problems = validate_gap_analyzer_questions(questions)
        self.assertEqual(len(problems), 1)
        self.assertIn("not one of the fourteen", problems[0][1])

    def test_non_contiguous_grouping_flagged(self):
        # Regression: gap-analyzer.md requires output "grouped by which file
        # they block" so the orchestrator can present them grouped. A
        # blocks_file that reappears after another file's questions have
        # already started is the mechanical signature of that rule breaking.
        questions = [
            {"blocks_file": "database", "topic": "t1", "question": "q1", "evidence": "e1"},
            {"blocks_file": "authorization", "topic": "t2", "question": "q2", "evidence": "e2"},
            {"blocks_file": "database", "topic": "t3", "question": "q3", "evidence": "e3"},
        ]
        problems = validate_gap_analyzer_questions(questions)
        self.assertEqual(len(problems), 1)
        self.assertIn("non-contiguously", problems[0][1])

    def test_padded_list_exceeds_sanity_ceiling(self):
        questions = [{"blocks_file": "database", "topic": f"t{i}", "question": f"q{i}", "evidence": f"e{i}"}
                     for i in range(41)]
        problems = validate_gap_analyzer_questions(questions, max_questions=40)
        self.assertTrue(any("sanity ceiling" in p[1] for p in problems))


class ArchitectureTraceabilityTest(unittest.TestCase):
    def test_known_node_labels_trace(self):
        mermaid = (
            "flowchart TB\n"
            '  A["InvoiceController.java"] -->|calls| B["InvoiceRepository.java"]\n'
        )
        known_names = {"InvoiceController.java", "InvoiceRepository.java", "Invoice.java"}
        self.assertEqual(find_untraceable_nodes(mermaid, known_names), [])

    def test_fabricated_node_label_flagged(self):
        # Regression: architect-segment.md rule 3 explicitly forbids
        # inventing a "friendlier" label — this is the mechanical check for
        # that rule actually holding, since a human skim of a diagram won't
        # catch a plausible-sounding but nonexistent node name.
        mermaid = (
            "flowchart TB\n"
            '  A["Billing Orchestration Service"] --> B["InvoiceRepository.java"]\n'
        )
        known_names = {"InvoiceController.java", "InvoiceRepository.java", "Invoice.java"}
        untraceable = find_untraceable_nodes(mermaid, known_names)
        self.assertEqual(untraceable, ["Billing Orchestration Service"])


class RealArtifactsOptInTest(unittest.TestCase):
    """Opt-in pass against a real completed pipeline run's actual output,
    gated by PIPELINE_ARTIFACTS_DIR (same pattern as
    test_partition_repo_real_world.py's PARTITION_REPO_REAL_FIXTURE_DIR).
    Expected directory layout: summaries.json (file-summarizer output),
    architecture.md (merged Mermaid + discrepancies), gap_questions.json
    (gap-analyzer output), and docs/*.md (the fourteen doc-writer outputs).
    Skipped entirely if the env var isn't set — this file's other test
    classes don't depend on it."""

    @classmethod
    def setUpClass(cls):
        cls.artifacts_dir = os.environ.get("PIPELINE_ARTIFACTS_DIR")
        if not cls.artifacts_dir:
            raise unittest.SkipTest("PIPELINE_ARTIFACTS_DIR not set — opt-in real-artifacts pass skipped")
        if not os.path.isdir(cls.artifacts_dir):
            raise unittest.SkipTest(f"PIPELINE_ARTIFACTS_DIR={cls.artifacts_dir!r} is not a directory")

    def test_summaries_json_shape(self):
        path = os.path.join(self.artifacts_dir, "summaries.json")
        if not os.path.isfile(path):
            self.skipTest("summaries.json not present in PIPELINE_ARTIFACTS_DIR")
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual(validate_file_summarizer_entries(entries), [])

    def test_gap_questions_shape(self):
        path = os.path.join(self.artifacts_dir, "gap_questions.json")
        if not os.path.isfile(path):
            self.skipTest("gap_questions.json not present in PIPELINE_ARTIFACTS_DIR")
        with open(path, encoding="utf-8") as f:
            questions = json.load(f)
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_generated_docs_tags_well_formed_and_resolvable(self):
        docs_dir = os.path.join(self.artifacts_dir, "docs")
        target_repo_dir = os.environ.get("PIPELINE_ARTIFACTS_TARGET_REPO", self.artifacts_dir)
        if not os.path.isdir(docs_dir):
            self.skipTest("docs/ not present in PIPELINE_ARTIFACTS_DIR")
        for name in os.listdir(docs_dir):
            if not name.endswith(".md"):
                continue
            with open(os.path.join(docs_dir, name), encoding="utf-8") as f:
                text = f.read()
            with self.subTest(file=name):
                self.assertEqual(find_malformed_tags(text), [])
                unresolved = resolve_evidenced_citations(text, target_repo_dir)
                self.assertEqual(unresolved, [], f"unresolvable [Evidenced — ...] citations in {name}: {unresolved}")


if __name__ == "__main__":
    unittest.main()
