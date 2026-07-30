#!/usr/bin/env python3
"""Contract for hooks/require_hardened_tests.py, the commit-time gate.

The property defended: **a commit that skipped the hardening is refused, and
everything else is left alone.** Both halves matter equally. A hook that
denies too much gets disabled within a day, and a disabled hook enforces
nothing -- so `PassesThroughTest` is as load-bearing as `DeniesTest`.

Not covered by sibling suites. test_deny_text_search.py covers the other
PreToolUse hook, which decides on a tool name and a command word; this one
inspects git state and runs other checkers, so its failure modes are
different: a wrong answer here blocks work rather than permitting a bad
search.

The deliberate design choice this suite pins is FAIL OPEN ON ERROR. If the
hook cannot do its job it must get out of the way, because the CI-side gates
still stand and a session wedged by its own tooling is worse than a commit
that reaches a checker one step later.

Run with: pytest tests/test_require_hardened_tests.py -v
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

sys.path.insert(0, str(REPO_ROOT / "adapters" / "claude" / "hooks"))

import require_hardened_tests as gate  # noqa: E402


def decide(command: str, tool: str = "Bash") -> str:
    """Run the hook end to end and return whatever it printed."""
    payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}})
    captured = io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
         mock.patch.object(sys, "stdout", captured):
        gate.main([])
    return captured.getvalue()


class CommitDetectionTest(unittest.TestCase):
    def test_recognises_a_commit(self) -> None:
        for command in ("git commit -m x", "git commit", "git -C /r commit -m x",
                        "ls && git commit -m x", "make && git commit --amend"):
            self.assertTrue(gate.is_commit(command), command)

    def test_does_not_fire_on_other_git_commands(self) -> None:
        for command in ("git status", "git add -A", "git log --oneline",
                        "git diff --cached"):
            self.assertFalse(gate.is_commit(command), command)

    def test_does_not_fire_on_a_word_containing_commit(self) -> None:
        """`git commitish` or a path named commit must not trip it. The
        boundary is what keeps this from denying unrelated work."""
        self.assertFalse(gate.is_commit("git show commitish"))
        self.assertFalse(gate.is_commit("cat notes/commit-message.txt"))


class MissingTestSuiteTest(unittest.TestCase):
    def test_a_deleted_script_does_not_require_a_suite(self) -> None:
        """Staging a deletion of scripts/foo.py must not demand test_foo.py —
        the module is leaving the tree, not landing untested."""
        self.assertEqual(
            gate.missing_test_suites(
                ["scripts/definitely_gone_module.py"],
                deletions={"scripts/definitely_gone_module.py"}),
            [])

    def test_a_new_script_without_a_suite_is_reported(self) -> None:
        problems = gate.missing_test_suites(["scripts/brand_new_thing.py"])
        self.assertEqual(len(problems), 1)
        self.assertIn("test_brand_new_thing.py", problems[0])

    def test_a_script_with_tests_dir_suite_passes(self) -> None:
        """CI SoT is tests/; a scripts/ module is covered by tests/test_*.py."""
        self.assertEqual(
            gate.missing_test_suites(["scripts/ci/check_repo_claims.py"]), [])

    def test_a_test_file_is_not_itself_required_to_have_a_test(self) -> None:
        self.assertEqual(gate.missing_test_suites(["scripts/test_anything.py"]), [])

    def test_an_exempt_module_is_allowed(self) -> None:
        self.assertEqual(gate.missing_test_suites(["scripts/ci/prompt_contracts.py"]), [])

    def test_every_exemption_states_a_reason(self) -> None:
        """An exemption without a reason is indistinguishable from an
        oversight -- the same rule CI_EXEMPT_SUITES carries."""
        for name, reason in gate.TEST_EXEMPT.items():
            self.assertGreater(len(reason.strip()), 15, name)

    def test_a_hook_without_a_suite_is_reported(self) -> None:
        """check_pipe_exit_code.py shipped from .claude/hooks/ with no test
        and nothing caught it: this guard used to check only scripts/, so a
        hook living anywhere else was invisible to it. hooks/ and the nested
        .claude/hooks/ form must both be covered now."""
        problems = gate.missing_test_suites(
            ["adapters/claude/hooks/brand_new_hook.py"])
        self.assertEqual(len(problems), 1)
        self.assertIn("test_brand_new_hook.py", problems[0])

    def test_a_nested_claude_hooks_file_without_a_suite_is_reported(self) -> None:
        problems = gate.missing_test_suites([".claude/hooks/brand_new_hook.py"])
        self.assertEqual(len(problems), 1)
        self.assertIn("test_brand_new_hook.py", problems[0])

    def test_a_hook_with_a_suite_passes(self) -> None:
        self.assertEqual(
            gate.missing_test_suites(
                ["adapters/claude/hooks/deny_text_search.py"]), [])
        self.assertEqual(
            gate.missing_test_suites(
                [".claude/hooks/check_pipe_exit_code.py"]), [])

    def test_files_outside_scripts_and_hooks_are_ignored(self) -> None:
        self.assertEqual(gate.missing_test_suites(["CLAUDE.md"]), [])


class UnwiredSuiteTest(unittest.TestCase):
    def test_scripts_test_wrapper_revival_is_reported(self) -> None:
        problems = gate.unwired_suites(["scripts/test_not_in_ci_at_all.py"])
        self.assertEqual(len(problems), 1)
        self.assertIn("outside pyproject testpaths", problems[0])

    def test_a_suite_under_tests_passes(self) -> None:
        self.assertEqual(gate.unwired_suites(["tests/test_set_delta.py"]), [])


class PassesThroughTest(unittest.TestCase):
    """A hook that denies too much gets disabled, and a disabled hook enforces
    nothing. These are the cases that keep it tolerable."""

    def test_a_non_bash_tool_is_untouched(self) -> None:
        self.assertEqual(decide("anything", tool="Read"), "")

    def test_a_non_commit_command_is_untouched(self) -> None:
        self.assertEqual(decide("python -m unittest"), "")

    def test_the_current_clean_tree_is_allowed(self) -> None:
        """Against the real repo. If this ever denies on a clean tree, the
        hook is broken in the direction that stops all work."""
        self.assertEqual(decide("git commit -m 'x'"), "")


class DeniesTest(unittest.TestCase):
    def test_a_finding_produces_a_deny_decision(self) -> None:
        with mock.patch.object(gate, "findings", return_value=["something broke"]):
            output = decide("git commit -m x")
        payload = json.loads(output)["hookSpecificOutput"]
        self.assertEqual(payload["permissionDecision"], "deny")
        self.assertIn("something broke", payload["permissionDecisionReason"])

    def test_the_reason_names_the_skill_to_load(self) -> None:
        """A gate that only says no teaches people to route around it."""
        reason = gate.build_reason(["x"])
        self.assertIn(gate.SKILL, reason)

    def test_the_reason_forbids_weakening_the_check(self) -> None:
        """The obvious way to satisfy a ratchet is to raise its ceiling, which
        hides exactly what the ratchet was added to see."""
        reason = gate.build_reason(["x"]).lower()
        self.assertIn("do not weaken", reason)


class FailOpenTest(unittest.TestCase):
    def test_unparseable_input_does_not_block(self) -> None:
        captured = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO("not json")), \
             mock.patch.object(sys, "stdout", captured):
            self.assertEqual(gate.main([]), 0)
        self.assertEqual(captured.getvalue(), "")

    def test_an_internal_error_does_not_block(self) -> None:
        with mock.patch.object(gate, "findings", side_effect=RuntimeError("boom")):
            self.assertEqual(decide("git commit -m x"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
