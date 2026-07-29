#!/usr/bin/env python3
"""
check_llms_coverage.py — fails when a merged PR has no claude/llms/pr-N.md,
or when a pr-N.md's frontmatter `state:` says OPEN for a PR that's actually
merged.

WHY THIS EXISTS
claude/llms/pr-*.md creation has always been a manual, judgment-heavy step
(see claude/llms/README.md) — nothing forced it to happen, so it silently
didn't: PRs #9-12, #14, and #15 all merged with no corresponding pr-N.md,
and pr-13.md's frontmatter was left saying `state: OPEN` after PR #13 itself
merged. verify_llms_docs.py re-verifies commands inside files that already
exist; it has no way to notice a file that was never written, or a stale
frontmatter field, at all. This script is the completeness check that closes
that gap — mechanical coverage, not content quality (a pr-N.md that exists
but is thin or wrong is still out of scope here, same boundary
verify_llms_docs.py draws around its own "Expect:" prose).

GRACE WINDOW FOR THE MOST-RECENTLY-MERGED PR
A PR that adds a missing pr-N.md is itself a newly-merged PR with no pr-N.md
of its own — a PR cannot document its own merge commit before that commit
exists. Enforcing zero-gap coverage literally would mean every single PR
forever needs an immediate, separate follow-up PR whose only content is
documenting the PR before it (this happened for real, twice: PR #16 then
PR #17). To break that regress, the single most-recently-merged PR (by
`mergedAt`, not PR number — GitHub PR numbers are assigned at creation and
don't strictly track merge order) is exempt from both checks below. This
bounds the real requirement to "covered before the *next* PR merges" rather
than "covered before this PR's own CI run finishes," which is impossible.
See claude/llms/README.md for the companion convention (write a PR's own
pr-N.md in the same PR, pinned to its head commit) that makes this
exemption rarely even necessary in practice.

REQUIRES: `gh` on PATH with GH_TOKEN in the environment to list merged PRs
non-interactively (same requirement verify_llms_docs.py's `gh pr view` calls
already have — see .github/workflows/ci.yml).

Run with:
    python3 scripts/check_llms_coverage.py
"""

# Always advisory (2026-07-29 principal gate redesign). Detection remains
# useful for humans/agents reading CI logs; failing the build on the current
# "most-recently-merged exempt" heuristic was theater (ENFORCE=False for
# months). Either delete this step later or redesign the exemption — do not
# reintroduce a latent hard gate behind a toggle.

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_LLMS_DIR = REPO_ROOT / "claude" / "llms"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def get_merged_prs() -> List[dict]:
    proc = subprocess.run(
        ["gh", "pr", "list", "--state", "merged", "--json", "number,title,mergedAt", "--limit", "200"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh pr list failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def most_recently_merged(merged_prs: List[dict]) -> Optional[int]:
    """Returns the PR number with the latest `mergedAt`, or None if empty.
    `mergedAt` is zero-padded ISO 8601 (e.g. "2026-07-24T03:38:08Z"), so
    plain string comparison sorts correctly without needing datetime parsing."""
    if not merged_prs:
        return None
    return max(merged_prs, key=lambda pr: pr["mergedAt"])["number"]


def parse_frontmatter(path: Path) -> Dict[str, str]:
    match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def existing_docs(llms_dir: Path) -> Dict[int, Path]:
    docs = {}
    for path in llms_dir.glob("pr-*.md"):
        m = re.match(r"pr-(\d+)\.md$", path.name)
        if m:
            docs[int(m.group(1))] = path
    return docs


def check_coverage(merged_prs: List[dict], llms_dir: Path) -> List[str]:
    """Pure-ish (only touches disk to read existing docs) so it's unit-testable
    without a live gh call. Returns a list of human-readable issue strings;
    empty means clean. The single most-recently-merged PR is exempt from
    both checks — see the module docstring's "GRACE WINDOW" section."""
    docs = existing_docs(llms_dir)
    issues = []
    exempt_number = most_recently_merged(merged_prs)

    for pr in merged_prs:
        number = pr["number"]
        if number == exempt_number:
            continue
        title = pr.get("title", "")
        doc = docs.get(number)
        if doc is None:
            issues.append(f"PR #{number} ({title!r}) is merged but claude/llms/pr-{number}.md is missing")
            continue
        state = parse_frontmatter(doc).get("state", "").upper()
        if state and state != "MERGED":
            issues.append(
                f"claude/llms/pr-{number}.md frontmatter says `state: {state}` "
                f"but PR #{number} is actually merged"
            )

    return issues


def exit_code(issues: List[str]) -> int:
    """Always advisory: findings never fail the build."""
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llms-dir", default=str(DEFAULT_LLMS_DIR),
                     help="directory containing pr-*.md files (default: claude/llms next to this repo)")
    args = ap.parse_args()

    llms_dir = Path(args.llms_dir)
    if not llms_dir.is_dir():
        print(f"error: {llms_dir} is not a directory", file=sys.stderr)
        return 1

    try:
        merged_prs = get_merged_prs()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    issues = check_coverage(merged_prs, llms_dir)
    exempt_number = most_recently_merged(merged_prs)

    if not issues:
        grace_note = f" (PR #{exempt_number} exempt as the most-recently-merged, per the grace window)" if exempt_number else ""
        print(f"OK: all {len(merged_prs)} merged PR(s) have an up-to-date claude/llms/pr-N.md{grace_note}.")
        return 0

    print(f"claude/llms/ coverage check found issues (advisory; never fails CI) "
          f"({len(issues)} issue(s)):", file=sys.stderr)
    for issue in issues:
        print(f"  - {issue}", file=sys.stderr)
    return exit_code(issues)


if __name__ == "__main__":
    sys.exit(main())
