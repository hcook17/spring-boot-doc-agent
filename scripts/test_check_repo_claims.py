#!/usr/bin/env python3
"""
Tests for check_repo_claims.py.

Most of these exist for non-vacuity rather than for coverage. A gate that
silently passes everything is indistinguishable from a working one at the
green checkmark, so every check here is exercised in both directions: a
clean tree passes, and a specific injected defect reaches a non-zero exit
code. test_check_code_quality.py is organized the same way for the same
reason.

The injection-safety class (TestNoShellExecution) is a regression test for
a defect this repo actually shipped: verify_llms_docs.py extracted spans
from LLM-authored markdown and ran them through `bash -c` with GH_TOKEN in
scope, and was deleted rather than hardened (2f82971). check_repo_claims.py
reads markdown too, so the property that markdown can never name anything
but a dict key has to be pinned, not assumed.

Run with:
    python3 scripts/test_check_repo_claims.py -v
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_repo_claims as crc  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_tree(root: Path) -> None:
    """A miniature repo with the shape the checker cares about. Deliberately
    not a copy of the real one: a fixture that tracks the real tree would
    drift with it, which is the failure this whole script is about."""
    (root / ".git").mkdir()
    (root / "scripts").mkdir()
    (root / "skills").mkdir()
    (root / "claude" / "steering-prompts").mkdir(parents=True)
    (root / ".github" / "workflows").mkdir(parents=True)

    (root / "scripts" / "widget.py").write_text(
        "def do_a_thing():\n    return 1\n", encoding="utf-8")
    (root / "scripts" / "test_widget.py").write_text(
        "def test_one():\n    pass\n\n\ndef test_two():\n    pass\n",
        encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  test:\n    steps:\n"
        "      - name: test_widget.py\n        run: python3 scripts/test_widget.py\n",
        encoding="utf-8")
    (root / "README.md").write_text(
        "See `scripts/widget.py` and `do_a_thing()`.\n", encoding="utf-8")
    (root / "claude" / "steering-prompts" / "01-x-research-prompt.md").write_text(
        "---\nstatus: resolved\nverify:\n  - path_exists:scripts/widget.py\n---\n\nBody.\n",
        encoding="utf-8")


class TreeCase(unittest.TestCase):
    """Runs the checker against a temp tree. `git ls-files` is stubbed rather
    than a real repo being initialized: the tests must not depend on git
    being installed, configured, or on this machine's global gitignore --
    one of which has already surprised a session here."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        build_tree(self.dir)
        self._real_tracked = crc.tracked_files
        crc.tracked_files = self._fake_tracked  # type: ignore[assignment]

    def tearDown(self) -> None:
        crc.tracked_files = self._real_tracked  # type: ignore[assignment]
        shutil.rmtree(self.dir, ignore_errors=True)

    def _fake_tracked(self, root: Path) -> list:
        return [p.relative_to(root).as_posix()
                for p in sorted(root.rglob("*"))
                if p.is_file() and ".git" not in p.parts]

    def run_check(self) -> int:
        return crc.main(["--root", str(self.dir),
                         "--baseline", str(self.dir / "missing_baseline.json")])

    def write(self, rel: str, text: str) -> None:
        (self.dir / rel).write_text(text, encoding="utf-8")


class TestCleanTree(TreeCase):
    def test_clean_tree_passes(self) -> None:
        self.assertEqual(self.run_check(), 0)


class TestDerivedBlocks(TreeCase):
    """Check A."""

    def test_correct_derived_value_passes(self) -> None:
        self.write("README.md", "There are <!-- derived: test_suite_count -->1<!-- /derived --> suites.\n")
        self.assertEqual(self.run_check(), 0)

    def test_stale_derived_value_fails(self) -> None:
        self.write("README.md", "There are <!-- derived: test_suite_count -->9<!-- /derived --> suites.\n")
        self.assertEqual(self.run_check(), 1)

    def test_fix_rewrites_the_stale_value(self) -> None:
        self.write("README.md", "There are <!-- derived: test_suite_count -->9<!-- /derived --> suites.\n")
        crc.main(["--root", str(self.dir), "--fix"])
        self.assertIn("-->1<!-- /derived -->",
                      (self.dir / "README.md").read_text(encoding="utf-8"))
        self.assertEqual(self.run_check(), 0)

    def test_method_count_counts_test_functions(self) -> None:
        self.assertEqual(crc.derive_test_method_count(self.dir), "2")

    def test_fenced_example_is_not_a_claim(self) -> None:
        """CLAUDE.md documents this syntax by showing it. On the first run
        the checker read its own documentation as a false claim and failed
        the build -- found by the gate firing on its own author, the same way
        check_code_quality.py's statement-count metric was."""
        self.write("README.md",
                   "Wrap it like this:\n\n```\n"
                   "runs <!-- derived: test_suite_count -->N<!-- /derived --> suites\n"
                   "```\n")
        self.assertEqual(self.run_check(), 0)

    def test_fix_does_not_rewrite_a_fenced_example(self) -> None:
        original = ("```\n<!-- derived: test_suite_count -->N<!-- /derived -->\n```\n")
        self.write("README.md", original)
        crc.main(["--root", str(self.dir), "--fix"])
        self.assertEqual((self.dir / "README.md").read_text(encoding="utf-8"), original)

    def test_a_real_block_outside_a_fence_still_fails(self) -> None:
        """The fence exemption must not leak past the closing marker."""
        self.write("README.md",
                   "```\nexample\n```\n\n"
                   "runs <!-- derived: test_suite_count -->99<!-- /derived --> suites\n")
        self.assertEqual(self.run_check(), 1)

    def test_fenced_path_reference_IS_still_resolved(self) -> None:
        """The fence exemption covers values, not paths. Fences here hold
        commands to run and files to read; exempting them hid the launcher
        incident entirely (see TestBacktest)."""
        self.write("README.md", "```\nsee scripts/hypothetical.py\n```\n")
        self.assertEqual(self.run_check(), 1)

    def test_derived_block_is_checked_in_historical_files_too(self) -> None:
        """Check B is scoped to current-state docs; check A is not. A number
        is a claim about now no matter which file it sits in."""
        self.write("claude/session-log.md",
                   "Ran <!-- derived: test_suite_count -->77<!-- /derived --> suites.\n")
        self.assertEqual(self.run_check(), 1)


class TestNoShellExecution(TreeCase):
    """The 2f82971 regression class: markdown must never name anything but a
    key in a dict this file defines."""

    def test_unknown_key_is_an_error_not_a_silent_skip(self) -> None:
        self.write("README.md", "<!-- derived: no_such_key -->1<!-- /derived -->\n")
        self.assertEqual(self.run_check(), 1)

    def test_unknown_key_is_not_rewritten_by_fix(self) -> None:
        """--fix must not invent a value for a key it cannot compute. Doing so
        would turn an error into a silent pass, which is the gate-that-cannot-
        fail shape check E exists to prevent elsewhere."""
        original = "<!-- derived: no_such_key -->1<!-- /derived -->\n"
        self.write("README.md", original)
        crc.main(["--root", str(self.dir), "--fix"])
        self.assertEqual((self.dir / "README.md").read_text(encoding="utf-8"), original)
        self.assertEqual(self.run_check(), 1)

    def test_shell_metacharacters_cannot_form_a_key(self) -> None:
        """The regex charset is the boundary. A span carrying a command is not
        a malformed key -- it does not match the block syntax at all, so it is
        inert text."""
        for payload in ("ls; rm -rf /", "$(whoami)", "`id`", "a && b", "../../etc/passwd"):
            with self.subTest(payload=payload):
                self.write("README.md", f"<!-- derived: {payload} -->x<!-- /derived -->\n")
                self.assertEqual(len(crc.DERIVED_RE.findall(
                    (self.dir / "README.md").read_text(encoding="utf-8"))), 0)

    def test_no_subprocess_call_takes_markdown_derived_input(self) -> None:
        """Belt and braces: fail loudly if any subprocess call in the module
        ever grows an argument that isn't a literal. Today the only one is
        `git ls-files`."""
        import ast
        tree = ast.parse((REPO_ROOT / "scripts" / "check_repo_claims.py")
                         .read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", getattr(func, "id", ""))
            if name not in {"run", "call", "check_output", "Popen", "system", "eval", "exec"}:
                continue
            self.assertTrue(node.args, "subprocess call with no argv")
            argv = node.args[0]
            self.assertIsInstance(argv, ast.List,
                                  "argv must be a literal list, never a built string")
            for element in argv.elts:
                self.assertIsInstance(element, ast.Constant,
                                      "every argv element must be a literal")


class TestReferences(TreeCase):
    """Check B."""

    def test_missing_path_fails(self) -> None:
        self.write("README.md", "See `scripts/nope.py`.\n")
        self.assertEqual(self.run_check(), 1)

    def test_missing_symbol_fails(self) -> None:
        self.write("README.md", "See `never_defined_anywhere()`.\n")
        self.assertEqual(self.run_check(), 1)

    def test_existing_symbol_passes(self) -> None:
        self.write("README.md", "See `do_a_thing()`.\n")
        self.assertEqual(self.run_check(), 0)

    def test_camel_case_method_is_not_treated_as_a_python_symbol(self) -> None:
        """The pipeline documents hundreds of Java methods. None are Python."""
        self.write("README.md", "The service calls `findAllByStatus()`.\n")
        self.assertEqual(self.run_check(), 0)

    def test_glob_matching_a_file_passes(self) -> None:
        self.write("README.md", "Suites live at `scripts/test_*.py`.\n")
        self.assertEqual(self.run_check(), 0)

    def test_glob_matching_nothing_fails(self) -> None:
        self.write("README.md", "See `scripts/nomatch_*.py`.\n")
        self.assertEqual(self.run_check(), 1)

    def test_placeholder_path_is_not_resolved(self) -> None:
        self.write("README.md", "Write `claude/llms/pr-N.md`.\n")
        self.assertEqual(self.run_check(), 0)

    def test_target_repo_path_is_out_of_scope(self) -> None:
        """These docs describe *other* people's services constantly."""
        self.write("README.md", "Reads `src/main/java/com/x/Foo.java` and `application.yml`.\n")
        self.assertEqual(self.run_check(), 0)

    def test_line_anchor_beyond_end_of_file_fails(self) -> None:
        self.write("README.md", "See `scripts/widget.py:900`.\n")
        self.assertEqual(self.run_check(), 1)

    def test_line_anchor_inside_the_file_passes(self) -> None:
        self.write("README.md", "See `scripts/widget.py:2`.\n")
        self.assertEqual(self.run_check(), 0)

    def test_historical_record_is_not_reference_checked(self) -> None:
        """An append-only log correctly cites files that existed when it was
        written. verify_llms_docs.py was real for 19 PRs."""
        self.write("claude/session-log.md", "Added `scripts/long_since_deleted.py`.\n")
        self.assertEqual(self.run_check(), 0)

    def test_tombstone_line_is_exempt(self) -> None:
        self.write("README.md",
                   "- ~~`scripts/gone.py`~~ — deleted as a security defect.\n")
        self.assertEqual(self.run_check(), 0)

    def test_tombstone_exemption_is_line_scoped(self) -> None:
        """A tombstone must not excuse the next claim down."""
        self.write("README.md",
                   "- ~~`scripts/gone.py`~~ — deleted.\n"
                   "- `scripts/also_missing.py` is current.\n")
        self.assertEqual(self.run_check(), 1)


class TestVerifyPredicates(TreeCase):
    """Check C."""

    PROMPT = "claude/steering-prompts/01-x-research-prompt.md"

    def test_satisfied_predicate_passes(self) -> None:
        self.assertEqual(self.run_check(), 0)

    def test_contradicted_path_exists_fails(self) -> None:
        (self.dir / "scripts" / "widget.py").unlink()
        self.assertEqual(self.run_check(), 1)

    def test_path_absent_contradicted_fails(self) -> None:
        """The direction that actually bit: `status: not started` while the
        deliverable already exists."""
        self.write(self.PROMPT,
                   "---\nstatus: not started\nverify:\n"
                   "  - path_absent:scripts/widget.py\n---\n")
        self.assertEqual(self.run_check(), 1)

    def test_contains_predicate_both_directions(self) -> None:
        self.write(self.PROMPT,
                   "---\nstatus: resolved\nverify:\n"
                   "  - contains:scripts/widget.py:do_a_thing\n---\n")
        self.assertEqual(self.run_check(), 0)
        self.write(self.PROMPT,
                   "---\nstatus: resolved\nverify:\n"
                   "  - contains:scripts/widget.py:absent_literal\n---\n")
        self.assertEqual(self.run_check(), 1)

    def test_contains_on_a_missing_file_fails(self) -> None:
        self.write(self.PROMPT,
                   "---\nstatus: resolved\nverify:\n"
                   "  - contains:scripts/nope.py:anything\n---\n")
        self.assertEqual(self.run_check(), 1)

    def test_unknown_predicate_fails_rather_than_passing_silently(self) -> None:
        self.write(self.PROMPT,
                   "---\nstatus: resolved\nverify:\n  - rm -rf /\n---\n")
        self.assertEqual(self.run_check(), 1)

    def test_status_with_no_verify_is_reported(self) -> None:
        self.write(self.PROMPT, "---\nstatus: resolved\n---\n")
        self.assertEqual(self.run_check(), 1)

    def test_missing_verify_is_baseline_eligible_but_a_failure_is_not(self) -> None:
        """The split that keeps the baseline from becoming an escape hatch:
        an unchecked claim can be accepted, a contradicted one never can."""
        self.write(self.PROMPT, "---\nstatus: resolved\n---\n")
        _, soft = crc.collect_all(self.dir)
        self.assertTrue(any(f.fingerprint.startswith("C-missing:") for f in soft))

        self.write(self.PROMPT,
                   "---\nstatus: resolved\nverify:\n  - path_exists:scripts/nope.py\n---\n")
        hard, _ = crc.collect_all(self.dir)
        self.assertTrue(any(f.check == "C" for f in hard))


class TestCiSuiteCoverage(TreeCase):
    """Check D."""

    def test_wired_suite_passes(self) -> None:
        self.assertEqual(self.run_check(), 0)

    def test_unwired_suite_fails(self) -> None:
        (self.dir / "scripts" / "test_orphan.py").write_text(
            "def test_x():\n    pass\n", encoding="utf-8")
        self.assertEqual(self.run_check(), 1)

    def test_exempt_suite_is_allowed(self) -> None:
        name = next(iter(crc.CI_EXEMPT_SUITES))
        (self.dir / "scripts" / name).write_text("def test_x():\n    pass\n",
                                                 encoding="utf-8")
        self.assertEqual(self.run_check(), 0)

    def test_every_exemption_states_a_reason(self) -> None:
        for name, reason in crc.CI_EXEMPT_SUITES.items():
            self.assertTrue(reason.strip(), f"{name} is exempt with no reason")


class TestGateHonesty(TreeCase):
    """Check E."""

    def _add_non_enforcing_script(self, step_name: str) -> None:
        (self.dir / "scripts" / "reporter.py").write_text(
            "ENFORCE = False\n", encoding="utf-8")
        (self.dir / ".github" / "workflows" / "ci.yml").write_text(
            "jobs:\n  test:\n    steps:\n"
            "      - name: test_widget.py\n        run: python3 scripts/test_widget.py\n"
            f"      - name: {step_name}\n        run: python3 scripts/reporter.py\n",
            encoding="utf-8")

    def test_gate_named_as_a_gate_that_cannot_fail_is_flagged(self) -> None:
        self._add_non_enforcing_script("reporter.py (fails on missing docs)")
        self.assertEqual(self.run_check(), 1)

    def test_honest_non_blocking_name_passes(self) -> None:
        self._add_non_enforcing_script("reporter.py (reports missing docs; non-blocking)")
        self.assertEqual(self.run_check(), 0)

    def test_suite_step_for_the_same_script_is_not_flagged(self) -> None:
        """`test_reporter.py` contains `reporter.py`. A unit-test step makes
        no enforcement claim, and flagging it was a real bug in this check."""
        (self.dir / "scripts" / "reporter.py").write_text("ENFORCE = False\n",
                                                          encoding="utf-8")
        (self.dir / "scripts" / "test_reporter.py").write_text(
            "def test_x():\n    pass\n", encoding="utf-8")
        (self.dir / ".github" / "workflows" / "ci.yml").write_text(
            "jobs:\n  test:\n    steps:\n"
            "      - name: test_widget.py\n        run: python3 scripts/test_widget.py\n"
            "      - name: test_reporter.py\n        run: python3 scripts/test_reporter.py\n"
            "      - name: reporter.py (non-blocking)\n        run: python3 scripts/reporter.py\n",
            encoding="utf-8")
        self.assertEqual(self.run_check(), 0)


class TestBaseline(TreeCase):
    def test_baseline_absorbs_an_existing_finding_but_not_a_new_one(self) -> None:
        self.write("README.md", "See `scripts/nope.py`.\n")
        baseline = self.dir / "baseline.json"
        crc.main(["--root", str(self.dir), "--baseline", str(baseline), "--update"])
        self.assertEqual(
            crc.main(["--root", str(self.dir), "--baseline", str(baseline)]), 0)

        self.write("README.md", "See `scripts/nope.py` and `scripts/also_nope.py`.\n")
        self.assertEqual(
            crc.main(["--root", str(self.dir), "--baseline", str(baseline)]), 1)

    def test_exact_checks_are_never_baselined(self) -> None:
        """A/D/E and a contradicted verify: predicate must stay fatal even
        immediately after --update, or the ratchet becomes an off switch."""
        (self.dir / "scripts" / "test_orphan.py").write_text(
            "def test_x():\n    pass\n", encoding="utf-8")
        baseline = self.dir / "baseline.json"
        code = crc.main(["--root", str(self.dir), "--baseline", str(baseline),
                         "--update"])
        self.assertEqual(code, 1)
        self.assertEqual(
            crc.main(["--root", str(self.dir), "--baseline", str(baseline)]), 1)

    def test_schema_version_mismatch_is_rejected(self) -> None:
        baseline = self.dir / "baseline.json"
        baseline.write_text(json.dumps({"schema_version": 99, "accepted": []}),
                            encoding="utf-8")
        self.assertEqual(
            crc.main(["--root", str(self.dir), "--baseline", str(baseline)]), 2)

    def test_fingerprint_survives_the_claim_moving_line(self) -> None:
        self.write("README.md", "See `scripts/nope.py`.\n")
        before = crc.check_references(self.dir, ["README.md"])[0].fingerprint
        self.write("README.md", "\n\n\n\nSee `scripts/nope.py`.\n")
        after = crc.check_references(self.dir, ["README.md"])[0].fingerprint
        self.assertEqual(before, after)


class TestBacktest(unittest.TestCase):
    """Against the real tree, reconstructing defects this repo actually had.

    A checker that passes its own unit tests but would have missed every
    historical instance is mis-aimed, and that is not visible from synthetic
    fixtures. Backtesting caught exactly that: check B originally exempted
    fenced blocks, which made the launcher incident below invisible.
    """

    def _flag_count(self, rel: str, mutate) -> int:
        path = REPO_ROOT / rel
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(mutate(original), encoding="utf-8")
            _, soft = crc.collect_all(REPO_ROOT)
            return len([f for f in soft if f.path == rel])
        finally:
            path.write_text(original, encoding="utf-8")

    def test_launcher_pointing_at_missing_prompts_is_caught(self) -> None:
        """The renumbering incident: 12-review-session-launcher.md told fresh
        sessions to read two prompt files where "neither exists". Its payload
        is one fenced block of bare, un-backticked paths -- both properties
        that an earlier draft of this checker skipped."""
        rel = "claude/steering-prompts/12-review-session-launcher.md"
        found = self._flag_count(rel, lambda t: t
                                 .replace("10-review-persona-and-standards.md",
                                          "08-review-persona-and-standards.md")
                                 .replace("11-context-traversal-protocol.md",
                                          "09-context-traversal-protocol.md"))
        self.assertGreaterEqual(found, 2, "the launcher incident is not caught")

    def test_current_launcher_is_clean(self) -> None:
        rel = "claude/steering-prompts/12-review-session-launcher.md"
        self.assertEqual(self._flag_count(rel, lambda t: t), 0)

    def test_current_state_doc_citing_a_deleted_script_is_caught(self) -> None:
        """CONSTRAINTS.md cited verify_llms_docs.py after 2f82971 deleted it.
        The real commit added the tombstone in the same change, so the stale
        state was never committed -- this reconstructs it without one."""
        found = self._flag_count(
            "CONSTRAINTS.md",
            lambda t: t + "\n\nThe checker `scripts/verify_llms_docs.py` runs in CI.\n")
        self.assertGreaterEqual(found, 1)


class TestRealRepo(unittest.TestCase):
    """Against the actual tree. These are the assertions that would notice
    the checker having quietly stopped looking at anything."""

    def test_real_repo_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "check_repo_claims.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0,
                         f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")

    def test_every_steering_prompt_with_a_status_has_predicates(self) -> None:
        """Scoped to the steering-prompt corpus, which is what this test's
        name has always claimed. It previously asserted over *all* missing
        findings, which was the same thing while prompts were the only
        corpus; CONSTRAINTS.md joining made the assertion wider than the
        name. Those claims are genuinely unfalsifiable today and ride the
        baseline -- that is the finding, not a reason to weaken this."""
        _, soft = crc.collect_all(REPO_ROOT)
        unchecked = [f.path for f in soft
                     if f.fingerprint.startswith("C-missing:")
                     and f.path.startswith("claude/steering-prompts/")]
        self.assertEqual(unchecked, [], f"prompts with an unchecked status: {unchecked}")

    def test_constraints_claims_are_actually_collected(self) -> None:
        """Non-vacuity for the corpus registry. Scoping the test above means
        an empty CONSTRAINTS.md extractor would no longer fail anything, so
        this asserts the corpus is really being read. CONSTRAINTS.md is the
        repo's densest claim store; if this ever reads zero, the extractor
        broke rather than the file becoming clean."""
        claims = [c for c in crc.collect_claims(REPO_ROOT) if c.corpus == "constraints"]
        self.assertGreater(len(claims), 10,
                           "CONSTRAINTS.md bracket-tag extraction returned almost nothing")
        self.assertTrue(any(c.status == "Resolved" for c in claims),
                        f"no [Resolved] claim found; statuses seen: "
                        f"{sorted({c.status for c in claims})}")

    def test_bracket_tags_inside_fenced_blocks_are_not_claims(self) -> None:
        """A tag shown as an example in a code fence documents the syntax; it
        does not assert anything. Counting it would make every doc that
        explains the convention look like it carries claims."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONSTRAINTS.md").write_text(
                "**[Resolved]** a real claim.\n\n"
                "```\n**[Resolved]** an example in a fence.\n```\n",
                encoding="utf-8")
            claims = crc.extract_bracket_tag_claims(root, root / "CONSTRAINTS.md")
            self.assertEqual(len(claims), 1, [c.status for c in claims])

    def test_an_inline_verify_comment_opts_a_claim_in(self) -> None:
        """Read-only adoption: a CONSTRAINTS.md entry joins the checked set by
        carrying its own predicates in an HTML comment, which renders as
        nothing. No migration of the file is required."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONSTRAINTS.md").write_text(
                "**[Resolved]** ships a thing. <!-- verify: path_exists:real.txt -->\n\n"
                "**[Flagged]** unchecked entry.\n",
                encoding="utf-8")
            (root / "real.txt").write_text("x", encoding="utf-8")
            claims = crc.extract_bracket_tag_claims(root, root / "CONSTRAINTS.md")
            self.assertEqual(claims[0].predicates, ("path_exists:real.txt",))
            self.assertEqual(claims[1].predicates, ())

    def test_a_long_status_tag_is_not_silently_dropped(self) -> None:
        """Regression: the first extractor capped the tag at 60 characters,
        which silently omitted three real CONSTRAINTS.md entries -- the long
        '[New info — ...]' corrections, i.e. exactly the claims that record a
        previous claim going wrong. Undercounting inflates the checked ratio,
        so the omission would have made the numbers look better than reality."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            long_tag = ("**[New info — the wording above ran ahead of the code, "
                        "corrected 2026-07-24]** body text.\n")
            (root / "CONSTRAINTS.md").write_text(long_tag, encoding="utf-8")
            claims = crc.extract_bracket_tag_claims(root, root / "CONSTRAINTS.md")
            self.assertEqual(len(claims), 1, "long status tag was dropped")
            self.assertTrue(claims[0].status.startswith("New info"), claims[0].status)

    def test_a_tag_does_not_match_across_a_newline(self) -> None:
        """The bound that replaced the length cap. Without it an unterminated
        `**[` would swallow the rest of the document as one giant status."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONSTRAINTS.md").write_text(
                "**[Unterminated tag\nspanning lines]** and more.\n", encoding="utf-8")
            self.assertEqual(
                crc.extract_bracket_tag_claims(root, root / "CONSTRAINTS.md"), [])

    def test_predicates_attach_to_the_claim_that_declares_them(self) -> None:
        """A verify: comment belongs to the tag above it, not to every tag in
        the file -- otherwise one opted-in entry would silently mark the whole
        document as checked."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONSTRAINTS.md").write_text(
                "**[Flagged]** first, unchecked.\n\n"
                "**[Resolved]** second. <!-- verify: path_absent:gone.txt -->\n",
                encoding="utf-8")
            claims = crc.extract_bracket_tag_claims(root, root / "CONSTRAINTS.md")
            self.assertEqual(claims[0].predicates, ())
            self.assertEqual(claims[1].predicates, ("path_absent:gone.txt",))

    def test_the_checker_actually_inspects_files(self) -> None:
        """Non-vacuity against the real tree: if tracked_markdown() ever
        returned nothing, every markdown check would report clean forever."""
        self.assertGreater(len(crc.tracked_markdown(REPO_ROOT)), 20)

    def test_every_derivation_key_is_computable(self) -> None:
        for key, fn in crc.DERIVATIONS.items():
            with self.subTest(key=key):
                value = fn(REPO_ROOT)
                self.assertTrue(value.isdigit() and int(value) > 0,
                                f"{key} produced {value!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
