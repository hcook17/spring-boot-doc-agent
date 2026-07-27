#!/usr/bin/env python3
"""PreToolUse(Bash) hook: block commands that read a build/test tool's exit code through a pipe.

WHY THIS EXISTS
---------------
This exact mistake produced two false "green" reports in one session on this project:

    gradle stage0Oracle --console=plain | tail -30
    echo "GRADLE_EXIT=$?"

`$?` after a pipeline is the *last* command's exit status -- `tail`'s, not Gradle's. Both
failed runs printed "GRADLE_EXIT=0" because `tail` always exits 0. The failure was only caught
later by noticing the log file was empty, which is not a check anyone should have to remember
to perform by hand.

WHAT THIS DETECTS
-----------------
A pipeline whose head looks like a build/test/verification tool, ending in a filter
(`tail`/`head`/`grep`/`wc`/`sed -n`/...) that discards the head's exit status, with no
recognized escape hatch present anywhere in the command (`PIPESTATUS`, `set -o pipefail`).

WHAT IT DOES NOT TRY TO DO
---------------------------
This is a heuristic over the command string, not a shell parser. It will have false positives
(an `npm ls | grep foo` a user genuinely doesn't care about the exit code for) and false
negatives (anything creative enough to dodge the regex). That asymmetry is deliberate: a false
positive costs one corrected command; a false negative is silent, which is the failure mode this
guards against. When blocked, the model can immediately switch to the safe pattern (redirect to
a file, capture $? on the actual command, then read the file) and retry -- this does not require
a human in the loop.

HEREDOC BODIES ARE DATA, NOT COMMANDS
--------------------------------------
This hook blocked its own author writing this exact docstring's *earlier* draft into
claude/tool-quirks.md via `cat >> file <<'QUIRK' ... QUIRK`: the heredoc body quoted the phrase
"gradle ... | tail" as prose describing the bug, and an unstripped regex read that quotation as
a live command. hooks/deny_text_search.py already hit and fixed the identical mistake for a
different matcher ("Treating text as executable is the same category of mistake that got
verify_llms_docs.py deleted"). Heredoc bodies are stripped before matching for the same reason.
"""

import json
import re
import sys

# Heredoc bodies are prose/data, not commands, and must not be matched against. Mirrors
# hooks/deny_text_search.py's HEREDOC_RE exactly, for the same reason stated there.
HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
    re.DOTALL | re.MULTILINE,
)


def strip_heredocs(command: str) -> str:
    return HEREDOC_RE.sub("<<HEREDOC", command)

BUILD_TOOL_RE = re.compile(
    r"\b(gradle\w*|\.\/gradlew|mvn\w*|\.\/mvnw|npm|yarn|pnpm|pytest|"
    r"python3?\s+-m\s+unittest|cargo|go\s+test|"
    r"dotnet(?:\.exe)?\s+(?:test|build)|make|msbuild)\b",
    re.IGNORECASE,
)

# The tail end of a pipeline that swallows the head's real exit status.
MASKING_FILTER_RE = re.compile(
    r"\|\s*(tail|head|grep|egrep|fgrep|wc|sed\s+-n|awk)\b",
    re.IGNORECASE,
)

ESCAPE_HATCH_RE = re.compile(r"PIPESTATUS|pipefail", re.IGNORECASE)


def is_risky(command: str) -> bool:
    if not command:
        return False
    command = strip_heredocs(command)
    if ESCAPE_HATCH_RE.search(command):
        return False
    if not MASKING_FILTER_RE.search(command):
        return False
    return bool(BUILD_TOOL_RE.search(command))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")

    if not is_risky(command):
        return 0

    reason = (
        "This command pipes a build/test tool's output into a filter "
        "(tail/head/grep/wc/sed) that discards the tool's own exit status. "
        "`$?` after a pipe is the LAST command's exit code, not the tool's -- this produced "
        "two false 'green' reports in this exact project because `tail` always exits 0. "
        "Use one of: (1) redirect to a file and check the tool's own exit code directly: "
        "`cmd > log.txt 2>&1; RC=$?; tail -n 40 log.txt` "
        "(2) `set -o pipefail` before the pipeline, or "
        "(3) read `${PIPESTATUS[0]}` instead of `$?`."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
