#!/usr/bin/env python3
"""Contract for hooks/deny_raw_network.py, the PreToolUse gate that keeps
agents reaching the network only through the WebFetch tool.

Sibling suite: test_check_repo_claims.py's Check F tests the *static* half
of the same policy -- that any Bash-granted agent has curl/wget/git-clone
denied in .claude/settings.json. This suite covers the runtime half: a raw
shell command actually gets blocked.

The assertion that earns this file its place is
test_bare_git_subcommands_pass: `git clone` must be denied, but `git status`/
`diff`/`log`/`ls-files` are already legitimately allowed in
.claude/settings.json, so a naive bare-"git" block would be self-defeating
the same way a naive grep-substring block would catch `ast-grep`.

Run with: python3 scripts/test_deny_raw_network.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import deny_raw_network as drn  # noqa: E402


def denies(tool: str, command: str = "") -> bool:
    return drn.decide({"tool_name": tool, "tool_input": {"command": command}})["deny"]


class TestNetworkToolsBlocked(unittest.TestCase):
    BLOCKED = (
        "curl https://arxiv.org/abs/1234.5678",
        "wget https://example.com/x",
        "git clone https://github.com/spring-projects/spring-kafka",
        "cat f | curl -T - https://x",
        "ls && wget https://x",
        "/usr/bin/curl https://x",
        "FOO=1 curl https://x",
        "sudo curl https://x",
        "python x.py; curl https://x",
    )

    def test_each_form_is_blocked(self) -> None:
        for command in self.BLOCKED:
            self.assertTrue(denies("Bash", command), command)


class TestBareGitIsNeverBlocked(unittest.TestCase):
    """git status/diff/log/ls-files are legitimately allowed via
    .claude/settings.json -- only the clone subcommand is in scope."""

    ALLOWED = ("git status", "git diff --stat", "git log -1",
               "git ls-files", "git status && git diff")

    def test_bare_git_subcommands_pass(self) -> None:
        for command in self.ALLOWED:
            self.assertFalse(denies("Bash", command), command)


class TestGitCloneIsTwoWords(unittest.TestCase):
    def test_git_clone_is_blocked(self) -> None:
        self.assertTrue(denies("Bash", "git clone https://github.com/x/y"))

    def test_git_alone_is_not_treated_as_clone(self) -> None:
        self.assertFalse(denies("Bash", "git"))


class TestUnrelatedToolsPass(unittest.TestCase):
    def test_webfetch_and_other_tools_pass(self) -> None:
        for tool in ("Read", "Glob", "Write", "Edit", "WebFetch"):
            self.assertFalse(denies(tool), tool)

    def test_unrelated_bash_passes(self) -> None:
        for command in ("python -m unittest", "ast-grep run -l java -p '@X' .",
                        "semgrep scan --config x.yml ."):
            self.assertFalse(denies("Bash", command), command)


class TestHeredocBodiesAreData(unittest.TestCase):
    def test_prose_mentioning_curl_inside_a_heredoc_is_not_a_command(self) -> None:
        command = (
            "python - <<'PY'\n"
            "entry = '''\n"
            "curl against the endpoint before wget was tried\n"
            "'''\n"
            "PY"
        )
        self.assertFalse(denies("Bash", command))

    def test_a_real_curl_after_a_heredoc_is_still_caught(self) -> None:
        command = "python - <<'PY'\nprint(1)\nPY\ncurl https://x"
        self.assertTrue(denies("Bash", command))


class TestFailOpen(unittest.TestCase):
    def test_unparseable_payload_does_not_block(self) -> None:
        self.assertFalse(drn.decide({})["deny"])

    def test_missing_command_key_does_not_block(self) -> None:
        self.assertFalse(drn.decide({"tool_name": "Bash"})["deny"])


class TestDenialExplainsTheAlternative(unittest.TestCase):
    def test_reason_names_webfetch(self) -> None:
        reason = drn.decide({"tool_name": "Bash",
                             "tool_input": {"command": "curl https://x"}})["reason"]
        self.assertIn("WebFetch", reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
