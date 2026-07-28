#!/usr/bin/env python3
"""PreToolUse hook: agents search structurally (ast-grep), not textually.

Reads a hook payload on stdin and emits a PreToolUse decision on stdout. Two
tools are in scope:

  Grep  -- always denied. It is ripgrep under a friendlier name.
  Bash  -- denied only when the command actually *invokes* a text searcher.

The Bash case is the one worth being careful about, because `ast-grep`
contains the substring `grep`. A naive `"grep" in command` test blocks the
exact tool this hook exists to mandate, which would be a self-defeating gate
of precisely the kind this repo keeps writing tests against. Matching is
therefore done on the command word of each shell segment, not on substrings.

Denial is advisory in the sense that it explains the alternative: a hook that
only says "no" trains the reader to work around it.

Usage: wired from hooks/hooks.json; not run by hand.
       echo '{"tool_name":"Grep"}' | python3 hooks/deny_text_search.py
"""
from __future__ import annotations

import json
import re
import sys

# Command words that mean "search text". `ast-grep` and `sg` are deliberately
# absent: they are the sanctioned tools.
TEXT_SEARCHERS = frozenset({"grep", "egrep", "fgrep", "rg", "ripgrep", "ack", "ag"})

# Shell segment separators. A command word can begin a line, or follow any of
# these -- `foo | grep x` hides the invocation behind a pipe.
SEGMENT_SPLIT_RE = re.compile(r"(?:\|\||&&|[;|&\n()])")

# Heredoc bodies are DATA, not commands, and must be removed before any of the
# tokenizing below runs. This hook blocked its own author writing a session-log
# entry that quoted a steering prompt: the quoted line began with the word
# "grep", a newline counts as a segment separator, and prose became a command.
# Treating text as executable is the same category of mistake that got
# verify_llms_docs.py deleted, so it is worth fixing properly rather than by
# loosening the matcher.
HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
    re.DOTALL | re.MULTILINE)


def strip_heredocs(command: str) -> str:
    return HEREDOC_RE.sub("<<HEREDOC", command)

# Leading environment assignments (`FOO=bar grep x`) and `sudo`/`command`/`time`
# wrappers precede the real command word.
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
WRAPPERS = frozenset({"sudo", "command", "time", "nice", "env", "xargs", "then", "do", "!"})

GREP_REASON = (
    "Blocked: this project searches code structurally, not textually. "
    "Use ast-grep instead:  ast-grep run -l <lang> -p '<pattern>' <path>\n"
    "Two things that have produced wrong answers here:\n"
    "  1. A marker annotation and an argument-bearing one are disjoint node "
    "shapes. `-p '@Column'` returns ZERO on a file full of `@Column(name=...)`. "
    "Try both `@Name` and `@Name($$$)`.\n"
    "  2. A zero result means UNPROVEN, not absent -- ast-grep exits 0 when a "
    "valid pattern matches nothing. Never turn a silent zero into a claim that "
    "something is not there.\n"
    "Text search matches inside strings and comments, which is how a citation "
    "ends up anchored to a line that does not support the claim."
)


def command_words(command: str) -> list:
    """The first real word of each shell segment, skipping env assignments
    and wrappers. Substring matching is not used anywhere here."""
    words = []
    for segment in SEGMENT_SPLIT_RE.split(strip_heredocs(command)):
        for token in segment.strip().split():
            bare = token.strip("\"'`")
            if ENV_ASSIGN_RE.match(bare) or bare in WRAPPERS:
                continue
            # Strip any path prefix: /usr/bin/grep and grep are the same call.
            words.append(bare.replace("\\", "/").rsplit("/", 1)[-1])
            break
    return words


def uses_text_search(command: str) -> bool:
    return any(word in TEXT_SEARCHERS for word in command_words(command))


def decide(payload: dict) -> dict:
    tool = payload.get("tool_name", "")
    if tool == "Grep":
        return {"deny": True, "reason": GREP_REASON}
    if tool == "Bash":
        command = str(payload.get("tool_input", {}).get("command", ""))
        if uses_text_search(command):
            return {"deny": True, "reason": GREP_REASON}
    return {"deny": False, "reason": ""}


def main(argv: list) -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        # A hook that cannot parse its input must not block work: failing open
        # here is the difference between a broken gate and a broken session.
        return 0
    verdict = decide(payload if isinstance(payload, dict) else {})
    if not verdict["deny"]:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": verdict["reason"],
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
