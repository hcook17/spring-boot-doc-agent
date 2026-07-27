#!/usr/bin/env python3
"""
Structural (mechanical) tests for the LLM pipeline stages —
file-summarizer, architect-segment/architect-merge, gap-analyzer,
software-architect-and-testing, doc-writer — none of which had any test
coverage before this file. Only the two deterministic scripts
(spring_signal_scan.py, partition_repo.py) and spring_drift_check.py had
tests; a prompt regression in any of the six agents/*.md files was
previously invisible except by a human reading generated output and
noticing something's wrong.

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
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(SCRIPT_DIR, "test_fixtures", "spring_signals")
sys.path.insert(0, SCRIPT_DIR)

# TAG_PATTERNS, TAG_WORD_SPAN, find_malformed_tags(), count_tags_by_kind(),
# and VALID_DOC_FILES moved to doc_tag_utils.py so run_manifest.py's
# evidence_tag_counts computation can import the exact same tag grammar
# instead of a second copy that could drift out of sync with what this
# suite enforces. Re-imported here under their original names so the rest
# of this file (and its own tests, which assert against these names
# directly) is unchanged.
from doc_tag_utils import (  # noqa: E402
    VALID_DOC_FILES,
    count_tags_by_kind,
    find_malformed_tags,
    resolve_evidenced_citations,
)

# agents/file-summarizer.md step 4's exact enumerated list.
#
# These two are copies of what the prompt says, and a copy that nothing reads
# back is how a validator ends up enforcing a contract the pipeline no longer
# produces. scripts/test_prompt_contracts.py asserts both still equal what
# scripts/prompt_contracts.py parses out of agents/file-summarizer.md, so
# editing the prompt without editing these fails the build.
VALID_SPRING_ROLES = frozenset({
    "controller", "service", "repository", "entity", "config", "security",
    "messaging-producer", "messaging-consumer", "test", "other",
})

# Top-level keys of file-summarizer.md's per-file output object.
FILE_SUMMARY_REQUIRED_KEYS = frozenset({
    "file", "cluster", "summary", "relationships",
    "cross_group_relationships", "group_function", "spring_role", "evidence",
})


# resolve_evidenced_citations moved to doc_tag_utils.py (imported below),
# for the same reason VALID_DOC_FILES did: check_pipeline_output.py needs it
# to gate a real run's output, and a checker importing from a test module
# would make the test file a runtime dependency of the pipeline.


def validate_file_summarizer_entries(entries):
    """agents/file-summarizer.md's documented output: a JSON array, one
    object per file, with exactly these keys and spring_role drawn from its
    step-4 enumerated list. Returns a list of (entry_index, reason) for
    anything malformed."""
    required_keys = FILE_SUMMARY_REQUIRED_KEYS
    problems = []
    for i, entry in enumerate(entries):
        missing = required_keys - entry.keys()
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
    """file-summarizer.md step 4's `evidence` field: the line anchors behind a
    summary's semantic claims, as {"line": int, "what": str}.

    This is the field that lets doc-writer cite anything the ast-grep pass
    didn't already find. Stage 0 records a line per mechanical hit and Stage 5
    is required to emit `path:line`, but every carrier between them used to be
    line-free — so a business-purpose claim reached doc-writer with a path and
    no line, leaving it to re-read the file, cite the file alone, or invent a
    number. An empty list is legitimate (a genuinely whole-file summary); a
    malformed entry is not, which is why the shape is enforced here rather
    than merely described in the prompt."""
    reasons = []
    for j, item in enumerate(evidence):
        if not isinstance(item, dict):
            reasons.append(f"evidence[{j}] must be an object, got {type(item).__name__}")
            continue
        missing = {"line", "what"} - item.keys()
        if missing:
            reasons.append(f"evidence[{j}] missing keys: {sorted(missing)}")
            continue
        # bool is a subclass of int; True is not a line number.
        if not isinstance(item["line"], int) or isinstance(item["line"], bool):
            reasons.append(f"evidence[{j}].line must be an int, got {type(item['line']).__name__}")
        elif item["line"] < 1:
            reasons.append(f"evidence[{j}].line must be >= 1, got {item['line']}")
        if not isinstance(item["what"], str) or not item["what"].strip():
            reasons.append(f"evidence[{j}].what must be a non-empty string")
    return reasons


# A path with an extension, optionally with a :line suffix. Deliberately
# permissive about the path shape (repos differ) and strict about only one
# thing: that something citable is present at all.
GAP_EVIDENCE_CITATION_RE = re.compile(r"[\w][\w./-]*\.[A-Za-z0-9]+(?::\d+)?")
# An elided path -- `src/.../InvoiceService.java`. gap-analyzer.md's own
# example shipped this shape, so it is the one malformed citation guaranteed
# to have been modeled for the agent.
ELIDED_PATH_RE = re.compile(r"/\.\.\.(?:/|\b)")


def _gap_evidence_problems(evidence):
    """gap-analyzer.md requires `evidence` to carry a real, resolvable
    path:line.

    Why this is enforced at all: a gap question becomes an interview
    question, which becomes an `interview_answers.json` entry, which a
    doc-writer turns into a `[Confirmed — interview, <date>]` claim. That is
    the only tag whose provenance never touches code again, so this field is
    the single point where the [Confirmed] lane is anchored to a real
    location. Unconstrained prose here makes every downstream [Confirmed]
    claim unfalsifiable."""
    if not isinstance(evidence, str) or not evidence.strip():
        return ["evidence must be a non-empty string"]
    if ELIDED_PATH_RE.search(evidence):
        return ["evidence cites an elided path (`/.../`) — it must resolve"]
    if not GAP_EVIDENCE_CITATION_RE.search(evidence):
        return ["evidence carries no file citation — gap-analyzer.md requires a resolvable path/File.java:line"]
    return []


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
        for reason in _gap_evidence_problems(q["evidence"]):
            problems.append((i, reason))
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


VALID_REVIEW_LENSES = frozenset({"ddia", "testing"})
VALID_REVIEW_SEVERITIES = frozenset({"informational", "worth-flagging"})
VALID_RESEARCH_TIERS = frozenset({"A", "B", "C"})
VALID_RESEARCH_VERDICTS = frozenset({"CONFIRMED", "PLAUSIBLE", "REFUTED", "UNRESOLVED"})


def validate_architecture_testing_review_findings(findings, max_findings=60):
    """agents/software-architect-and-testing.md's documented output: a JSON
    array of {lens, concept, claim, evidence, external_research, severity}.
    Every finding needs a real evidence anchor the same way a file-summarizer
    entry does — the DDIA/Effective-Software-Testing concept is attributed
    prose, never a substitute for one. external_research is optional and, when
    present, its sources must never claim Tier C is sufficient on its own
    (claude/steering-prompts/10-review-persona-and-standards.md §2: "Tier C
    may never appear as a citation") — this is the mechanical half of that
    rule; the agent file states it, this suite is what would catch a
    regression that quietly violated it."""
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
                problems.append((i, f"external_research verdict {verdict!r} not one of {sorted(VALID_RESEARCH_VERDICTS)}"))
            sources = external.get("sources", [])
            only_tier_c = bool(sources) and all(s.get("tier") == "C" for s in sources)
            if only_tier_c:
                problems.append((i, "external_research rests entirely on Tier C sources — Tier C is orientation-only and may never be the sole ground for a claim"))
            for source in sources:
                if source.get("tier") not in VALID_RESEARCH_TIERS:
                    problems.append((i, f"external_research source tier {source.get('tier')!r} not one of {sorted(VALID_RESEARCH_TIERS)}"))
    if len(findings) > max_findings:
        problems.append((None, f"{len(findings)} findings exceeds sanity ceiling of {max_findings} — "
                                f"agents/software-architect-and-testing.md says not to force a quota"))
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
            "evidence": [{"line": 42, "what": "creates invoices from the POST handler"}],
        }]
        self.assertEqual(validate_file_summarizer_entries(entries), [])

    def test_missing_key_flagged(self):
        entries = [{"file": "X.java", "cluster": [], "summary": "s",
                    "relationships": [], "group_function": "", "spring_role": "other",
                    "evidence": []}]
        problems = validate_file_summarizer_entries(entries)
        self.assertEqual(len(problems), 1)
        self.assertIn("cross_group_relationships", problems[0][1])

    def test_invalid_spring_role_flagged(self):
        entries = [{"file": "X.java", "cluster": [], "summary": "s", "relationships": [],
                    "cross_group_relationships": [], "group_function": "",
                    "spring_role": "controllerish", "evidence": []}]
        problems = validate_file_summarizer_entries(entries)
        self.assertEqual(len(problems), 1)
        self.assertIn("spring_role", problems[0][1])

    def _entry(self, **overrides):
        entry = {"file": "X.java", "cluster": [], "summary": "s", "relationships": [],
                 "cross_group_relationships": [], "group_function": "",
                 "spring_role": "other", "evidence": []}
        entry.update(overrides)
        return entry

    def test_missing_evidence_key_flagged(self):
        """The whole point of the field: a summarizer that silently stops
        emitting it drops every semantic line anchor in the run."""
        entry = self._entry()
        del entry["evidence"]
        problems = validate_file_summarizer_entries([entry])
        self.assertEqual(len(problems), 1)
        self.assertIn("evidence", problems[0][1])

    def test_empty_evidence_list_is_legitimate(self):
        """A genuinely whole-file summary has no single anchor. Requiring a
        non-empty list would just buy back invented line numbers."""
        self.assertEqual(validate_file_summarizer_entries([self._entry()]), [])

    def test_evidence_must_be_a_list(self):
        problems = validate_file_summarizer_entries([self._entry(evidence={"line": 1, "what": "x"})])
        self.assertTrue(any("must be a list" in p[1] for p in problems))

    def test_evidence_entry_missing_line_flagged(self):
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"what": "x"}])])
        self.assertTrue(any("missing keys" in p[1] for p in problems))

    def test_evidence_line_must_be_an_int(self):
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"line": "42", "what": "x"}])])
        self.assertTrue(any("must be an int" in p[1] for p in problems))

    def test_evidence_line_bool_rejected(self):
        """bool subclasses int; True is not a line number."""
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"line": True, "what": "x"}])])
        self.assertTrue(any("must be an int" in p[1] for p in problems))

    def test_evidence_line_must_be_positive(self):
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"line": 0, "what": "x"}])])
        self.assertTrue(any(">= 1" in p[1] for p in problems))

    def test_evidence_what_must_be_non_empty(self):
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"line": 5, "what": "  "}])])
        self.assertTrue(any("non-empty string" in p[1] for p in problems))


class GapAnalyzerShapeTest(unittest.TestCase):
    def test_valid_bounded_list_passes(self):
        questions = [
            {"blocks_file": "database", "topic": "write ownership", "question": "q1", "evidence": "src/main/java/A.java:10 is the only writer"},
            {"blocks_file": "database", "topic": "write ownership 2", "question": "q2", "evidence": "src/main/java/B.java:20 has no guard"},
            {"blocks_file": "authorization", "topic": "endpoint", "question": "q3", "evidence": "src/main/java/C.java:30 is unmapped"},
        ]
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_invalid_blocks_file_flagged(self):
        questions = [{"blocks_file": "faq", "topic": "t", "question": "q", "evidence": "src/main/java/A.java:10 is the only writer"}]
        problems = validate_gap_analyzer_questions(questions)
        self.assertEqual(len(problems), 1)
        self.assertIn("not one of the fourteen", problems[0][1])

    def test_non_contiguous_grouping_flagged(self):
        # Regression: gap-analyzer.md requires output "grouped by which file
        # they block" so the orchestrator can present them grouped. A
        # blocks_file that reappears after another file's questions have
        # already started is the mechanical signature of that rule breaking.
        questions = [
            {"blocks_file": "database", "topic": "t1", "question": "q1", "evidence": "src/main/java/A.java:10 is the only writer"},
            {"blocks_file": "authorization", "topic": "t2", "question": "q2", "evidence": "src/main/java/B.java:20 has no guard"},
            {"blocks_file": "database", "topic": "t3", "question": "q3", "evidence": "src/main/java/C.java:30 is unmapped"},
        ]
        problems = validate_gap_analyzer_questions(questions)
        self.assertEqual(len(problems), 1)
        self.assertIn("non-contiguously", problems[0][1])

    def test_elided_path_in_evidence_flagged(self):
        """gap-analyzer.md's own example used to ship `(src/.../Foo.java)`,
        so this malformed shape was actively modeled for the agent."""
        questions = [{"blocks_file": "database", "topic": "t", "question": "q",
                      "evidence": "InvoiceService.markPaid (src/.../InvoiceService.java) is the only writer"}]
        problems = validate_gap_analyzer_questions(questions)
        self.assertTrue(any("elided path" in p[1] for p in problems))

    def test_evidence_without_any_citation_flagged(self):
        """Unconstrained prose here leaves every downstream
        [Confirmed — interview, <date>] claim unanchored to any location."""
        questions = [{"blocks_file": "database", "topic": "t", "question": "q",
                      "evidence": "this table looks like it has one writer"}]
        problems = validate_gap_analyzer_questions(questions)
        self.assertTrue(any("no file citation" in p[1] for p in problems))

    def test_evidence_with_path_and_line_passes(self):
        questions = [{"blocks_file": "database", "topic": "t", "question": "q",
                      "evidence": "src/main/java/com/example/InvoiceService.java:88 is the only write path"}]
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_evidence_with_bare_path_passes(self):
        """A path without a line is weaker but still resolvable; the taxonomy
        allows whole-file citations, so this is not the failure being caught."""
        questions = [{"blocks_file": "database", "topic": "t", "question": "q",
                      "evidence": "declared in src/main/resources/schema.sql"}]
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_padded_list_exceeds_sanity_ceiling(self):
        questions = [{"blocks_file": "database", "topic": f"t{i}", "question": f"q{i}", "evidence": f"src/main/java/A{i}.java:10 is the only writer"}
                     for i in range(41)]
        problems = validate_gap_analyzer_questions(questions, max_questions=40)
        self.assertTrue(any("sanity ceiling" in p[1] for p in problems))


class ArchitectureTestingReviewShapeTest(unittest.TestCase):
    def test_valid_finding_passes(self):
        findings = [{
            "lens": "ddia", "concept": "DDIA ch.6 — no version field",
            "claim": "InvoiceLedger has no @Version field.",
            "evidence": [{"file": "InvoiceLedger.java", "line": 22, "what": "@Entity with no @Version"}],
            "external_research": None, "severity": "worth-flagging",
        }]
        self.assertEqual(validate_architecture_testing_review_findings(findings), [])

    def test_missing_evidence_flagged(self):
        findings = [{"lens": "testing", "concept": "c", "claim": "x", "evidence": [], "severity": "informational"}]
        problems = validate_architecture_testing_review_findings(findings)
        self.assertTrue(any("non-empty array" in p[1] for p in problems))

    def test_invalid_lens_flagged(self):
        findings = [{"lens": "security", "concept": "c", "claim": "x",
                     "evidence": [{"line": 1, "what": "w"}], "severity": "informational"}]
        problems = validate_architecture_testing_review_findings(findings)
        self.assertTrue(any("not one of" in p[1] and "lens" in str(p) for p in problems) or
                        any("security" in p[1] for p in problems))

    def test_tier_c_only_external_research_flagged(self):
        """Regression for claude/steering-prompts/10-review-persona-and-standards.md
        §2's "Tier C may never appear as a citation" — a finding whose
        external_research rests entirely on deepwiki.com (Tier C) with no
        Tier A/B backing must be caught, not silently accepted."""
        findings = [{
            "lens": "ddia", "concept": "c", "claim": "x",
            "evidence": [{"line": 1, "what": "w"}], "severity": "informational",
            "external_research": {
                "question": "q",
                "sources": [{"tier": "C", "identifier": "deepwiki.com/x/y"}],
                "verdict": "PLAUSIBLE",
            },
        }]
        problems = validate_architecture_testing_review_findings(findings)
        self.assertTrue(any("Tier C" in p[1] for p in problems))

    def test_tier_a_backed_external_research_passes(self):
        findings = [{
            "lens": "ddia", "concept": "c", "claim": "x",
            "evidence": [{"line": 1, "what": "w"}], "severity": "informational",
            "external_research": {
                "question": "q",
                "sources": [{"tier": "A", "identifier": "github.com/x/y"}],
                "verdict": "CONFIRMED",
            },
        }]
        self.assertEqual(validate_architecture_testing_review_findings(findings), [])

    def test_invalid_verdict_flagged(self):
        findings = [{
            "lens": "ddia", "concept": "c", "claim": "x",
            "evidence": [{"line": 1, "what": "w"}], "severity": "informational",
            "external_research": {"question": "q", "sources": [], "verdict": "MAYBE"},
        }]
        problems = validate_architecture_testing_review_findings(findings)
        self.assertTrue(any("verdict" in p[1] for p in problems))

    def test_padded_list_exceeds_sanity_ceiling(self):
        findings = [{"lens": "ddia", "concept": f"c{i}", "claim": f"x{i}",
                     "evidence": [{"line": i, "what": "w"}], "severity": "informational"}
                    for i in range(61)]
        problems = validate_architecture_testing_review_findings(findings, max_findings=60)
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
