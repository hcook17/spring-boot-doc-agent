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
import re
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


class TestAgentSearchTooling(TreeCase):
    """Check F. Each test names the one property it defends, and every one
    is run in both directions -- the arrangement that passes and the single
    mutation that must turn it red."""

    SCOPED = ["Bash(ast-grep run:*)"]
    DENIES = ["Bash(grep:*)", "Bash(rg:*)"]

    def agent(self, name: str, tools: str) -> None:
        folder = self.dir / "agents"
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(
            f"---\nname: {name[:-3]}\ndescription: d\ntools: {tools}\n---\n\nBody.\n",
            encoding="utf-8")

    def settings(self, allow: list, deny: list) -> None:
        folder = self.dir / ".claude"
        folder.mkdir(exist_ok=True)
        (folder / "settings.json").write_text(
            json.dumps({"permissions": {"allow": allow, "deny": deny}}),
            encoding="utf-8")

    def test_structural_only_agent_passes(self) -> None:
        self.agent("writer.md", "Read, Glob, Write")
        self.assertEqual(self.run_check(), 0)

    def test_an_agent_declaring_grep_fails(self) -> None:
        self.agent("writer.md", "Read, Grep, Glob, Write")
        self.assertEqual(self.run_check(), 1)

    def test_scoped_bash_grant_passes(self) -> None:
        self.agent("writer.md", "Read, Glob, Write, Bash")
        self.settings(self.SCOPED, self.DENIES)
        self.assertEqual(self.run_check(), 0)

    def test_bash_without_a_scoped_allowlist_entry_fails(self) -> None:
        """A subagent's tools: field cannot scope Bash, so settings.json is
        the only thing standing between `Bash` and a general shell."""
        self.agent("writer.md", "Read, Glob, Write, Bash")
        self.settings(["Bash(git status:*)"], self.DENIES)
        self.assertEqual(self.run_check(), 1)

    def test_bash_without_text_search_denies_fails(self) -> None:
        """Removing the Grep tool buys nothing if the same agent can shell
        out to grep instead."""
        self.agent("writer.md", "Read, Glob, Write, Bash")
        self.settings(self.SCOPED, [])
        self.assertEqual(self.run_check(), 1)

    def test_a_dot_claude_agent_is_checked_too(self) -> None:
        folder = self.dir / ".claude" / "agents"
        folder.mkdir(parents=True)
        (folder / "local.md").write_text(
            "---\nname: local\ndescription: d\ntools: Read, Grep\n---\n\nBody.\n",
            encoding="utf-8")
        self.assertEqual(self.run_check(), 1)

    def test_grep_in_prose_is_not_a_violation(self) -> None:
        """The check reads the frontmatter tools: field, not the body. An
        agent may legitimately mention the word while describing input it
        was handed -- gap-analyzer.md does exactly that."""
        self.agent("writer.md", "Read, Glob, Write")
        (self.dir / "agents" / "writer.md").write_text(
            "---\nname: writer\ndescription: d\ntools: Read, Glob, Write\n---\n\n"
            "You are given the TODO/FIXME grep hits from Stage 0.\n",
            encoding="utf-8")
        self.assertEqual(self.run_check(), 0)


class TestNotContainsPredicate(TreeCase):
    def test_not_contains_both_directions(self) -> None:
        self.write("claude/steering-prompts/02-y-research-prompt.md",
                   "---\nstatus: resolved\n"
                   "verify:\n  - not_contains:scripts/widget.py:Grep\n---\n\nBody.\n")
        self.assertEqual(self.run_check(), 0)
        (self.dir / "scripts" / "widget.py").write_text(
            "def do_a_thing():\n    return Grep\n", encoding="utf-8")
        self.assertEqual(self.run_check(), 1)

    def test_not_contains_on_a_missing_file_fails(self) -> None:
        """Vacuous truth would turn a rename into a silent pass -- the exact
        direction prompt 06's status went wrong in."""
        self.write("claude/steering-prompts/02-y-research-prompt.md",
                   "---\nstatus: resolved\n"
                   "verify:\n  - not_contains:scripts/gone.py:Grep\n---\n\nBody.\n")
        self.assertEqual(self.run_check(), 1)


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


class TestUnchangedSince(unittest.TestCase):
    """The stability predicate. It does not assert a claim is true -- nothing
    here can judge that -- it asserts nobody has re-read the claim since the
    thing it describes moved."""

    SUBJECT = 'def f(x):\n    """Docs."""\n    return x + 1\n'

    def _repo(self, tmp):
        root = Path(tmp)
        (root / "scripts").mkdir()
        (root / "scripts" / "sub.py").write_text(self.SUBJECT, encoding="utf-8")
        return root

    def _pred(self, root, level="t2", digest=None):
        if digest is None:
            digest = crc._ast_signature.signature(root / "scripts/sub.py", level).split(":")[1]
        return f"unchanged_since:scripts/sub.py:{level}:{digest}"

    def test_a_matching_signature_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            self.assertTrue(crc.evaluate_predicate(root, self._pred(root))[0])

    def test_never_affirmed_is_reported_differently_from_changed(self):
        """These are different problems with different fixes -- one needs a
        stamp, the other needs a human to re-read a claim. Collapsing them
        into one message would train people to run --affirm reflexively,
        which defeats the predicate."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            _, unaffirmed = crc.evaluate_predicate(root, self._pred(root, digest=""))
            _, changed = crc.evaluate_predicate(root, self._pred(root, digest="0" * 64))
            self.assertIn("never been affirmed", unaffirmed)
            self.assertIn("changed since", changed)
            self.assertNotEqual(unaffirmed, changed)

    def test_an_unknown_level_fails_rather_than_falling_back(self):
        """Falling back to a different relation would compare two
        incomparable digests and report the answer confidently."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            passed, why = crc.evaluate_predicate(root, self._pred(root, level="t9",
                                                                 digest="0" * 64))
            self.assertFalse(passed)
            self.assertIn("unknown signature level", why)

    def test_a_missing_subject_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            passed, why = crc.evaluate_predicate(
                root, "unchanged_since:scripts/gone.py:t2:" + "0" * 64)
            self.assertFalse(passed)
            self.assertIn("does not exist", why)

    def test_a_malformed_predicate_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            self.assertFalse(crc.evaluate_predicate(
                root, "unchanged_since:scripts/sub.py")[0])

    def test_reformatting_the_subject_does_not_trip_t2(self):
        """The end-to-end form of the property that decides adoption. If this
        fails, `ruff format` breaks every claim in the repo at once."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            predicate = self._pred(root)
            (root / "scripts" / "sub.py").write_text(
                'def f(x):\n    """Docs."""\n    return x+1\n', encoding="utf-8")
            self.assertTrue(crc.evaluate_predicate(root, predicate)[0])

    def test_a_docstring_edit_does_not_trip_t2_but_does_trip_t1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            t2_pred = self._pred(root, "t2")
            t1_pred = self._pred(root, "t1")
            (root / "scripts" / "sub.py").write_text(
                'def f(x):\n    """Different prose."""\n    return x + 1\n', encoding="utf-8")
            self.assertTrue(crc.evaluate_predicate(root, t2_pred)[0])
            self.assertFalse(crc.evaluate_predicate(root, t1_pred)[0])

    def test_a_behaviour_change_trips_t2(self):
        """Non-vacuity: a predicate that never fails detects nothing, and
        every other test in this class would still pass."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            predicate = self._pred(root)
            (root / "scripts" / "sub.py").write_text(
                'def f(x):\n    """Docs."""\n    return x + 2\n', encoding="utf-8")
            self.assertFalse(crc.evaluate_predicate(root, predicate)[0])


class TestAffirm(unittest.TestCase):
    """--affirm is what makes the predicate usable. Without it a claim can
    only be re-affirmed by hand-computing a digest, and an unusable check is
    an ignored one."""

    def _repo(self, tmp, doc_body):
        root = Path(tmp)
        (root / "scripts").mkdir()
        (root / "scripts" / "sub.py").write_text(
            'def f(x):\n    """Docs."""\n    return x + 1\n', encoding="utf-8")
        (root / "CONSTRAINTS.md").write_text(doc_body, encoding="utf-8")
        return root

    def test_affirm_round_trip(self):
        """affirm -> clean; mutate -> fails; affirm -> clean. The operational
        loop, which is what decides whether anyone adopts this."""
        body = ("**[Resolved]** a claim. "
                "<!-- verify: unchanged_since:scripts/sub.py:t2: -->\n")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp, body)

            def claim_passes():
                claims = crc.extract_bracket_tag_claims(root, root / "CONSTRAINTS.md")
                return crc.evaluate_predicate(root, claims[0].predicates[0])[0]

            self.assertFalse(claim_passes(), "unaffirmed claim should not pass")
            self.assertEqual(crc.apply_affirm(root, ["CONSTRAINTS.md"]), ["CONSTRAINTS.md"])
            self.assertTrue(claim_passes(), "affirm did not stamp a usable digest")

            (root / "scripts" / "sub.py").write_text(
                'def f(x):\n    """Docs."""\n    return x + 99\n', encoding="utf-8")
            self.assertFalse(claim_passes(), "a behaviour change should trip it")

            crc.apply_affirm(root, ["CONSTRAINTS.md"])
            self.assertTrue(claim_passes(), "re-affirming did not clear it")

    def test_affirm_does_not_rewrite_inside_a_code_fence(self):
        """A fenced example documents the syntax. Rewriting the sample in
        CLAUDE.md that explains this feature would be a small, funny
        disaster -- the same guard apply_fix already carries."""
        body = ("```\n"
                "<!-- verify: unchanged_since:scripts/sub.py:t2: -->\n"
                "```\n")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp, body)
            self.assertEqual(crc.apply_affirm(root, ["CONSTRAINTS.md"]), [])
            self.assertIn("unchanged_since:scripts/sub.py:t2: -->",
                          (root / "CONSTRAINTS.md").read_text(encoding="utf-8"))

    def test_affirm_leaves_an_unknown_level_alone(self):
        """It must keep failing the check rather than being rewritten to
        something plausible -- silently repairing a claim nobody can evaluate
        is the same class of bug as a gate that cannot fail."""
        body = "**[Resolved]** x. <!-- verify: unchanged_since:scripts/sub.py:t9: -->\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp, body)
            self.assertEqual(crc.apply_affirm(root, ["CONSTRAINTS.md"]), [])

    def test_affirm_leaves_a_missing_subject_alone(self):
        body = "**[Resolved]** x. <!-- verify: unchanged_since:scripts/gone.py:t2: -->\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp, body)
            self.assertEqual(crc.apply_affirm(root, ["CONSTRAINTS.md"]), [])


class TestPredicateRegistry(unittest.TestCase):
    """The registry replaced a startswith() chain that duplicated the prefix
    list. These defend the properties that restructure either preserves or
    newly makes possible to break."""

    def test_an_unknown_predicate_is_rejected(self):
        """The closed-vocabulary guarantee, asserted rather than assumed. A
        document may select among keys this file defines; it can never supply
        behaviour. That is the exact inverse of the deleted
        verify_llms_docs.py, where the document supplied the command."""
        passed, why = crc.evaluate_predicate(REPO_ROOT, "exec_shell:rm -rf /")
        self.assertFalse(passed)
        self.assertIn("unknown predicate", why)

    def test_no_predicate_prefix_is_a_prefix_of_another(self):
        """The invariant the registry creates a need for. Dispatch is
        first-match, which is unambiguous today only because no prefix
        shadows another. Add `path_exists_recursive:` and it would silently
        route to `path_exists:` with the rest of the string as its operand --
        wrong, and quiet. Currently true; this makes it stay true."""
        prefixes = list(crc.PREDICATE_HANDLERS)
        shadowed = [(a, b) for a in prefixes for b in prefixes
                    if a != b and b.startswith(a)]
        self.assertEqual(shadowed, [], f"prefix shadowing would misroute: {shadowed}")

    def test_every_registered_handler_is_reachable(self):
        """A handler in the dict that no predicate can select is dead code
        that looks live.

        Reachability is the whole property; the verdict is each handler's own
        business. The first version of this test also asserted the result was
        False, which is wrong: `path_absent:__no_such_thing__` correctly
        returns True, because the path really is absent. Asserting a verdict
        here was testing the handlers rather than the dispatch."""
        for prefix in crc.PREDICATE_HANDLERS:
            _, why = crc.evaluate_predicate(REPO_ROOT, f"{prefix}__no_such_thing__")
            self.assertNotIn("unknown predicate", why,
                             f"{prefix} fell through to the unknown-predicate branch")

    def test_the_reference_alternation_is_derived_from_the_prefix_list(self):
        """These were two literal tuples of the same eight strings. Deriving
        one from the other is what stops them drifting; this fails if someone
        re-inlines the list."""
        for prefix in crc.OWN_PATH_PREFIXES:
            self.assertIn(re.escape(prefix), crc._OWN_PREFIX_ALT)


class TestMirrorDebt(unittest.TestCase):
    """Prompts 00-06 have a canonical copy in the Claude project; editing one
    creates an obligation no CLI session can discharge. This turns that
    obligation from a paragraph someone has to read into a counted number."""

    def _repo(self, tmp):
        root = Path(tmp)
        prompts = root / "claude" / "steering-prompts"
        prompts.mkdir(parents=True)
        for name in ["00-a.md", "01-b.md", "06-c.md", "07-not-mirrored.md",
                     "13-also-not.md"]:
            (prompts / name).write_text(f"# {name}\n", encoding="utf-8")
        return root

    def test_an_unrecorded_prompt_counts_as_debt(self):
        """Absent state must not read as clean. A checker whose default is
        'everything is fine' reports best when it knows least."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            self.assertEqual(len(crc.mirror_debt(root)), 3)

    def test_recording_clears_the_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            crc.write_mirror_state(root)
            self.assertEqual(crc.mirror_debt(root), [])

    def test_editing_a_mirrored_prompt_reopens_its_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            crc.write_mirror_state(root)
            edited = root / "claude" / "steering-prompts" / "01-b.md"
            edited.write_text("# 01-b.md\n\nstatus changed\n", encoding="utf-8")
            self.assertEqual(crc.mirror_debt(root),
                             ["claude/steering-prompts/01-b.md"])

    def test_prompts_above_06_are_not_tracked(self):
        """07+ were authored in this repo and exist nowhere else, so they
        carry no mirror obligation. Counting them would inflate the debt with
        work nobody owes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            crc.write_mirror_state(root)
            (root / "claude" / "steering-prompts" / "07-not-mirrored.md").write_text(
                "# heavily edited\n", encoding="utf-8")
            self.assertEqual(crc.mirror_debt(root), [])

    def test_affirming_claims_does_not_clear_mirror_debt(self):
        """The hazard this design exists to avoid. Affirming means "I re-read
        this claim"; mirroring means "I copied this file to the project."
        Sharing one verb would let a routine --affirm silently clear real
        mirror debt, making the number lowest exactly when someone had been
        most casual."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            crc.write_mirror_state(root)
            prompt = root / "claude" / "steering-prompts" / "01-b.md"
            prompt.write_text("# 01-b.md\n\nedited\n", encoding="utf-8")
            self.assertEqual(len(crc.mirror_debt(root)), 1)

            crc.apply_affirm(root, ["claude/steering-prompts/01-b.md"])
            self.assertEqual(len(crc.mirror_debt(root)), 1,
                             "--affirm must not clear mirror debt")

    def test_the_state_file_says_what_it_cannot_prove(self):
        """It records debt, not sync -- nothing here can see the project copy.
        A reader who mistakes it for proof of sync would trust it exactly
        where it is weakest."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            crc.write_mirror_state(root)
            payload = json.loads((root / crc.MIRROR_STATE).read_text(encoding="utf-8"))
            self.assertIn("cannot see the project", payload["$comment"])


class TestRealRepo(unittest.TestCase):
    """Against the actual tree. These are the assertions that would notice
    the checker having quietly stopped looking at anything."""

    def test_real_repo_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "check_repo_claims.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0,
                         f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")

    def test_no_real_agent_declares_grep(self) -> None:
        """The backtest for check F. The fixture tests prove the check can
        fire; this proves it is aimed at the real tree, where all five agents
        declared `tools: Read, Grep, Glob, Write` before this change."""
        agents = crc._agent_definitions(REPO_ROOT)
        self.assertTrue(agents, "no agent definitions found — check F is aimed at nothing")
        for path in agents:
            self.assertNotIn("Grep", crc._declared_tools(path), f"{path.name} declares Grep")

    def test_real_bash_agents_are_scoped_by_settings(self) -> None:
        """Every agent granted Bash must be narrowed by the committed
        allowlist, since its own frontmatter cannot express the scope."""
        settings = json.loads(
            (REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        permissions = settings.get("permissions", {})
        bash_agents = [p.name for p in crc._agent_definitions(REPO_ROOT)
                       if "Bash" in crc._declared_tools(p)]
        if bash_agents:
            self.assertTrue(
                any(e.startswith(crc.SCOPED_BASH_PREFIX)
                    for e in permissions.get("allow", [])),
                f"{bash_agents} declare Bash with no scoped allow entry")
            for required in crc.TEXT_SEARCH_DENIES:
                self.assertIn(required, permissions.get("deny", []))

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
