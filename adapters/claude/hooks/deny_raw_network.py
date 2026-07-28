#!/usr/bin/env python3
"""PreToolUse hook: agents reach the network only through the WebFetch tool,
never a raw shell command.

Mirrors deny_text_search.py's structure and tokenizing (command-word
extraction on shell segments, heredoc bodies treated as data, env-assignment
and wrapper skipping) rather than re-deriving it -- imported from that module
directly, since its heredoc-stripping already fixed a real bug (prose in a
heredoc tokenized as a command) that a fresh copy could silently lose. New
here: `git clone` is a two-word check (command word "git" AND second word
"clone"), not a bare "git" block, since git status/diff/log/ls-files must
keep working (they're allowed in .claude/settings.json).

Usage: wired from hooks/hooks.json; not run by hand.
       echo '{"tool_name":"Bash","tool_input":{"command":"curl https://x"}}' \
         | python3 hooks/deny_raw_network.py
"""
from __future__ import annotations

import json
import sys

from deny_text_search import ENV_ASSIGN_RE, SEGMENT_SPLIT_RE, WRAPPERS, strip_heredocs

# Command words that reach the network directly. `git` is deliberately not
# listed bare -- see the module docstring.
NETWORK_TOOLS = frozenset({"curl", "wget"})

NETWORK_REASON = (
    "Blocked: this project reaches the network only through the WebFetch "
    "tool, never a raw shell command. curl/wget/git clone bypass WebFetch's "
    "tiering/citation discipline (arXiv id resolves and says what's "
    "claimed, GitHub star/push-activity signal, deepwiki.com "
    "orientation-only Tier C) -- see agents/software-architect-and-"
    "testing.md's 'External research' section. Use the WebFetch tool "
    "instead."
)


def command_word_pairs(command: str) -> list:
    """The first two real words of each shell segment, skipping env
    assignments and wrappers -- same tokenizing as deny_text_search's
    command_words(), extended to keep a second word for the git-clone case."""
    pairs = []
    for segment in SEGMENT_SPLIT_RE.split(strip_heredocs(command)):
        words = []
        for token in segment.strip().split():
            bare = token.strip("\"'`")
            if ENV_ASSIGN_RE.match(bare) or bare in WRAPPERS:
                continue
            words.append(bare.replace("\\", "/").rsplit("/", 1)[-1])
            if len(words) == 2:
                break
        if words:
            pairs.append(tuple(words))
    return pairs


def uses_raw_network(command: str) -> bool:
    for words in command_word_pairs(command):
        first = words[0]
        if first in NETWORK_TOOLS:
            return True
        if first == "git" and len(words) > 1 and words[1] == "clone":
            return True
    return False


def decide(payload: dict) -> dict:
    tool = payload.get("tool_name", "")
    if tool == "Bash":
        command = str(payload.get("tool_input", {}).get("command", ""))
        if uses_raw_network(command):
            return {"deny": True, "reason": NETWORK_REASON}
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
