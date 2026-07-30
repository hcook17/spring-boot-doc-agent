#!/usr/bin/env python3
"""PreToolUse hook: refuse a commit that skipped the hardening this repo requires.

Reads a hook payload on stdin; denies `git commit` when a fast, mechanical
precondition fails, and names the skill to load when it does.

WHY THIS EXISTS

Every control in this repo that depends on someone remembering has eventually
been forgotten, and the record says so: prompt 06's status was flagged three
times before anyone edited it, CONSTRAINTS.md cited a deleted script in two
places at once, and this file's own author -- in the session that added the
mutation harness -- shipped a complexity regression, propagated a measured
number that was wrong, and wrote three assertions that were false within
minutes of being written.

The response this repo prescribes for a repeat failure is not another note. It
is an enforced control. So the checks below run at the moment of commit rather
than when someone thinks to run them.

WHAT IT CHECKS, AND WHY ONLY THESE

Speed is a correctness property here: a gate slow enough to resent is a gate
people route around. The full suite takes about two minutes, so it is NOT run.
These four are all fast, and each maps to a failure this repo has actually had:

  1. a staged scripts/*.py with no tests/test_*.py sibling  -- code added untested
  2. a staged test_*.py outside pyproject testpaths         -- wrapper revival
  3. check_repo_claims.py                             -- a claim nothing reads back
  4. check_code_quality.py                            -- a silent complexity ratchet break

FAIL OPEN ON ERROR, CLOSED ON A FINDING

An internal error here must not wedge the session: if this hook cannot do its
job it gets out of the way, and the CI-side gates still stand. A real finding
is different -- that is the thing it exists to stop.

Usage: wired from .claude/settings.json; not run by hand.
       echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}' \\
           | python3 hooks/require_hardened_tests.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parents[3]

from doc_engine.paths import scripts_meta_path_entries  # noqa: E402

for _entry in scripts_meta_path_entries():
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import suite_layout  # noqa: E402

SKILL = "directional-tests"

# Modules that are libraries or entry points for which a dedicated suite is not
# the convention here. Each needs a reason, the same shape as
# check_repo_claims.CI_EXEMPT_SUITES.
TEST_EXEMPT = {
    "drift_match_normalizers.py": "re-derived by test_drift_normalization.py",
    "java_perturbations.py": "test infrastructure itself",
    "prompt_contracts.py": "exercised by test_prompt_contracts.py",
    "regenerate_fixture_snapshot.py": "operator helper; exercised manually / CI snapshot step",
    "generate_signal_mermaid.py": "operator helper for fixture visualization",
}

COMMIT_RE = re.compile(r"(^|[;&|]\s*)git\s+(-C\s+\S+\s+)?commit\b")


def is_commit(command: str) -> bool:
    return bool(COMMIT_RE.search(command))


def staged_files() -> List[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--cached", "--name-only"],
        capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if line.strip()]


def staged_deletions() -> Set[str]:
    """Paths staged for deletion only — those do not need a sibling test suite."""
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--cached", "--diff-filter=D",
         "--name-only"],
        capture_output=True, text=True)
    return {line for line in result.stdout.splitlines() if line.strip()}


def missing_test_suites(staged: List[str],
                        deletions: Optional[Set[str]] = None) -> List[str]:
    problems = []
    deleted = deletions if deletions is not None else set()
    for rel in staged:
        if rel in deleted:
            continue
        path = Path(rel)
        # Path.name is only the final segment, so "hooks" here also covers
        # .claude/hooks/foo.py -- no separate case needed for the nested
        # form. check_pipe_exit_code.py shipped from .claude/hooks/ with no
        # test and no test suite named it, because this guard used to read
        # `!= "scripts"` and neither hook directory was in it.
        hook_parents = {"ci", "ratchets", "coverage", "fixtures", "hooks"}
        rel_parts = path.parts
        under_scripts = len(rel_parts) >= 2 and rel_parts[0] == "scripts"
        is_adapter_hook = (
            len(rel_parts) >= 3
            and rel_parts[0] == "adapters"
            and rel_parts[1] == "claude"
            and rel_parts[2] == "hooks"
        )
        if (
            path.parent.name not in hook_parents
            and not under_scripts
            and not is_adapter_hook
        ) or path.suffix != ".py":
            continue
        if path.name.startswith("test_") or path.name in TEST_EXEMPT:
            continue
        if suite_layout.suite_file_for_module(REPO_ROOT, path.name) is not None:
            continue
        roots = ", ".join(suite_layout.suite_roots(REPO_ROOT))
        problems.append(
            f"{rel} has no test_{path.name} under pyproject testpaths "
            f"({roots}). Add one, or add the module to TEST_EXEMPT in this "
            f"hook with a reason.")
    return problems


def unwired_suites(staged: List[str],
                   deletions: Optional[Set[str]] = None) -> List[str]:
    """Flag staged test modules outside pyproject testpaths (wrapper revival)."""
    deleted = deletions if deletions is not None else set()
    roots = set(suite_layout.suite_roots(REPO_ROOT))
    problems: List[str] = []
    for rel in staged:
        if rel in deleted:
            continue
        path = Path(rel)
        name = path.name
        if not name.startswith("test_") or path.suffix != ".py":
            continue
        if path.parts and path.parts[0] in roots:
            continue
        problems.append(
            f"{rel} is outside pyproject testpaths {sorted(roots)}; "
            f"pytest discovery will not collect it. Do not revive "
            f"scripts/test_*.py wrappers.")
    return problems


def failing_gates() -> List[str]:
    problems = []
    for rel in ("scripts/ci/check_repo_claims.py", "scripts/ci/check_code_quality.py"):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / rel)],
            capture_output=True, text=True, cwd=str(REPO_ROOT))
        if result.returncode != 0:
            tail = (result.stdout + result.stderr).strip().splitlines()
            problems.append(f"{rel} exits {result.returncode}: "
                            + " / ".join(tail[:3]))
    return problems


def findings() -> List[str]:
    staged = staged_files()
    if not staged:
        return []
    deleted = staged_deletions()
    return (missing_test_suites(staged, deletions=deleted)
            + unwired_suites(staged, deletions=deleted)
            + failing_gates())


def build_reason(problems: List[str]) -> str:
    return (
        "Commit blocked: this change has not cleared the hardening gates.\n\n"
        + "\n".join(f"  - {p}" for p in problems)
        + f"\n\nLoad the `{SKILL}` skill and follow it before committing. It "
        f"covers what these checks are for: a gate that cannot be shown to "
        f"fail is not a gate, assert exit codes rather than internal lists, "
        f"and prefer an invariant to a re-run-and-diff probe.\n"
        "Then re-run the gate that failed. Do not weaken the check to pass it "
        "-- if a ratchet caught a regression, fix the regression; raising the "
        "ceiling hides the growth this repo added the ratchet to see."
    )


def main(argv: List[str]) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
            return 0
        command = str(payload.get("tool_input", {}).get("command", ""))
        if not is_commit(command):
            return 0
        problems = findings()
    except Exception:  # noqa: BLE001 - fail open, never wedge the session
        return 0
    if not problems:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": build_reason(problems),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
