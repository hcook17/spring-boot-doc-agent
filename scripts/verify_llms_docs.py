#!/usr/bin/env python3
"""
verify_llms_docs.py — mechanical re-verification of claude/llms/pr-*.md's
own deterministic-verification commands.

WHY THIS EXISTS
claude/llms/pr-1.md through pr-N.md each pair a PR summary with literal
git/gh commands, hand-verified correct against the commit they're pinned to
at write-time (see claude/llms/README.md). Nothing re-runs those commands as
main moves — a later rename, a squash-merged PR whose docs never got
repinned, or a stale "state: OPEN" left over after the PR actually merged
(this exact thing happened to pr-8.md; see claude/session-log.md) can drift
silently, with no signal to a reader that a heuristic has gone stale. This
is the same failure shape spring_drift_check.py exists to catch for a
*target* repo's generated docs, applied reflexively to this repo's own
PR-verification docs (CONSTRAINTS.md's "Integration gaps" item 4).

WHAT "MECHANICAL" MEANS HERE, CONCRETELY
This is not a shell parser. It recognizes exactly two authored command
shapes, both already established across pr-1.md..pr-8.md:

  1. A plain one-liner — `git show <ref>[:<path>] | grep ...`, `git log
     --follow ...`, `git diff <a> <b> ...`, `gh pr view N --json ...` — run
     verbatim through bash and judged by exit status (with one narrow
     override: an "Expect: ... no output / empty output ..." line means
     empty stdout is the actual pass condition, since a `grep` with no
     match exits non-zero on purpose in that case).

  2. The `git worktree add <path> <sha> && cd <path> && <rest>; cd - &&
     git worktree remove <path>` compound shape used for "existing test
     suite still passes" claims. This one is NOT run as one shell string:
     the trailing `; cd - && git worktree remove` means bash's own exit
     status reflects the *cleanup* command, not `<rest>` — silently
     masking a real test failure. Same problem again if `<rest>` ends in
     `| tail -N`: `tail` always exits 0, discarding pytest/unittest's own
     status. So this shape is decomposed into three explicit steps (add,
     run `<rest>` under `bash -o pipefail` so a failure deep in a pipe
     still propagates, remove-in-finally) instead of trusting the
     documented one-liner's own exit code.

Anything that doesn't match one of those two shapes — or a `gh` command
when the `gh` binary isn't on PATH — is skipped with an explicit
"not auto-verified: <reason>" line and does NOT fail the run. Silently
ignoring an unparseable command would be worse than saying so out loud.

WHAT THIS DELIBERATELY DOES NOT DO
It does not semantically diff real command output against each free-text
"Expect: ..." line (e.g. "5 files, 52 insertions, 29 deletions") — that
line is prose written for a human, not a machine-checkable spec, and
attempting to parse it would be exactly the over-engineering
01-testability-research-prompt.md's own "mechanical wherever possible,
don't over-engineer" precedent warns against. A command that still runs
clean but now returns *different* matching output than documented would
not be caught by this script; that residual gap is a stated scope
boundary, not an oversight.

REQUIRES: full git history (a shallow `actions/checkout` will make most
`git show <old-sha>:path` commands fail with "invalid object name" even
though nothing is actually wrong — see .github/workflows/ci.yml's
`fetch-depth: 0`). `gh` commands additionally need GH_TOKEN in the
environment to authenticate non-interactively; if `gh` isn't on PATH at
all, those commands are skipped rather than failing the run.

Run with:
    python3 scripts/verify_llms_docs.py
"""

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_LLMS_DIR = REPO_ROOT / "claude" / "llms"

CLAIM_RE = re.compile(r"^(\d+)\.\s+\*\*Claim:")
BACKTICK_RE = re.compile(r"`([^`]+)`")
COMMAND_PREFIX_RE = re.compile(r"^(git|gh)\s")
NO_OUTPUT_EXPECTED_RE = re.compile(r"no output|empty output", re.IGNORECASE)
HARD_ERROR_RE = re.compile(r"fatal:|^usage:", re.IGNORECASE | re.MULTILINE)

# Matches the `git worktree add <path> <sha> && cd <path> && <rest>;
# cd - && git worktree remove <path>` shape used by every "existing suite(s)
# still pass" claim across pr-1.md..pr-8.md.
WORKTREE_RE = re.compile(
    r"^git worktree add (?P<path>\S+) (?P<sha>\S+) && cd (?P=path) && "
    r"(?P<rest>.+?); cd - && git worktree remove (?P=path)$"
)


@dataclass
class Command:
    pr_file: str
    claim_num: int
    seq: int
    text: str
    expect_text: Optional[str]


def find_pr_docs(llms_dir: Path) -> List[Path]:
    def pr_number(p: Path) -> int:
        m = re.search(r"pr-(\d+)\.md$", p.name)
        return int(m.group(1)) if m else 0

    return sorted(llms_dir.glob("pr-*.md"), key=pr_number)


def parse_commands(path: Path) -> List[Command]:
    lines = path.read_text(encoding="utf-8").splitlines()

    start = next(
        (i for i, l in enumerate(lines) if l.strip() == "## Deterministic verification"),
        None,
    )
    if start is None:
        return []
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )

    commands: List[Command] = []
    claim_num = 0
    seq_in_claim = 0
    pending: Optional[str] = None  # command text awaiting its "Expect:" line

    def finalize(expect_text: Optional[str]) -> None:
        nonlocal pending, seq_in_claim
        if pending is not None:
            seq_in_claim += 1
            commands.append(Command(path.name, claim_num, seq_in_claim, pending, expect_text))
            pending = None

    for line in lines[start + 1 : end]:
        stripped = line.strip()

        claim_match = CLAIM_RE.match(stripped)
        if claim_match:
            finalize(None)  # a claim with no trailing Expect: line for its last command
            claim_num = int(claim_match.group(1))
            seq_in_claim = 0
            continue

        if stripped.startswith("Expect:"):
            finalize(stripped)
            continue

        for span in BACKTICK_RE.findall(line):
            candidate = span.strip()
            if COMMAND_PREFIX_RE.match(candidate):
                finalize(None)  # previous command never got an explicit Expect: line
                pending = candidate

    finalize(None)
    return commands


def is_worktree_shaped(cmd_text: str) -> bool:
    return "worktree add" in cmd_text or "worktree remove" in cmd_text


def evaluate(returncode: int, stdout: str, stderr: str, expect_text: Optional[str]) -> bool:
    hard_error = bool(HARD_ERROR_RE.search(stderr or "")) or returncode == 127
    if hard_error:
        return False
    if expect_text and NO_OUTPUT_EXPECTED_RE.search(expect_text):
        return stdout.strip() == ""
    return returncode == 0


def run_bash(cmd_text: str, cwd: Path, timeout: int):
    return subprocess.run(
        ["bash", "-o", "pipefail", "-c", cmd_text],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def cleanup_worktree(path: str, cwd: Path) -> None:
    subprocess.run(
        ["bash", "-c", f'git worktree remove --force "{path}" 2>/dev/null; rm -rf "{path}"'],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def run_simple(cmd: Command, cwd: Path) -> "Result":
    if cmd.text.startswith("gh ") and shutil.which("gh") is None:
        return Result(cmd, "SKIP", "not auto-verified: gh CLI not found on PATH")
    try:
        proc = run_bash(cmd.text, cwd, timeout=120)
    except subprocess.TimeoutExpired:
        return Result(cmd, "FAIL", "timed out after 120s")
    ok = evaluate(proc.returncode, proc.stdout, proc.stderr, cmd.expect_text)
    detail = "" if ok else f"exit={proc.returncode} stderr={proc.stderr.strip()[:300]!r}"
    return Result(cmd, "PASS" if ok else "FAIL", detail)


def run_worktree(cmd: Command, cwd: Path) -> "Result":
    match = WORKTREE_RE.match(cmd.text)
    if not match:
        return Result(
            cmd,
            "SKIP",
            "not auto-verified: worktree-shaped command didn't match the expected "
            "add/cd/run/remove pattern; skipped rather than risk an unsafe side effect",
        )
    path, sha, rest = match.group("path"), match.group("sha"), match.group("rest")

    cleanup_worktree(path, cwd)
    try:
        # Run `add` through the same bash that runs `rest` and the cleanup
        # below, not a raw git.exe subprocess — on Windows, native git and
        # Git Bash resolve a bare "/tmp/..." path to two different real
        # directories, so mixing the two here would create the worktree in
        # one place and try to remove it from another.
        add_proc = run_bash(f'git worktree add "{path}" "{sha}"', cwd, timeout=60)
        if add_proc.returncode != 0:
            return Result(cmd, "FAIL", f"git worktree add failed: {add_proc.stderr.strip()[:300]!r}")

        try:
            # `cd` inside the same bash -c invocation that runs `rest`,
            # rather than pointing Python's own subprocess `cwd=` at `path`
            # directly — a bare "/tmp/..." string is a path bash's own MSYS
            # runtime translates (see the `add` step above), not one
            # CreateProcess/os.chdir can resolve natively on Windows.
            run_proc = run_bash(f'cd "{path}" && {rest}', cwd, timeout=300)
        except subprocess.TimeoutExpired:
            return Result(cmd, "FAIL", "timed out after 300s")
        ok = evaluate(run_proc.returncode, run_proc.stdout, run_proc.stderr, cmd.expect_text)
        detail = "" if ok else f"exit={run_proc.returncode} stderr={run_proc.stderr.strip()[:300]!r}"
        return Result(cmd, "PASS" if ok else "FAIL", detail)
    finally:
        cleanup_worktree(path, cwd)


@dataclass
class Result:
    command: Command
    status: str  # PASS | FAIL | SKIP
    detail: str


def run_command(cmd: Command, cwd: Path) -> Result:
    if is_worktree_shaped(cmd.text):
        return run_worktree(cmd, cwd)
    return run_simple(cmd, cwd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llms-dir", default=str(DEFAULT_LLMS_DIR),
                     help="directory containing pr-*.md files (default: claude/llms next to this repo)")
    args = ap.parse_args()

    if shutil.which("bash") is None:
        print("error: bash not found on PATH — cannot re-run any documented command", file=sys.stderr)
        return 1

    llms_dir = Path(args.llms_dir)
    docs = find_pr_docs(llms_dir)
    if not docs:
        print(f"error: no pr-*.md files found under {llms_dir}", file=sys.stderr)
        return 1

    subprocess.run(["git", "worktree", "prune"], cwd=str(REPO_ROOT), capture_output=True, text=True)

    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for doc in docs:
        commands = parse_commands(doc)
        print(f"== {doc.name} ({len(commands)} command(s)) ==")
        if not commands:
            print("  (no '## Deterministic verification' commands found)")
            continue
        for cmd in commands:
            result = run_command(cmd, REPO_ROOT)
            counts[result.status] += 1
            label = f"claim {cmd.claim_num}.{cmd.seq}"
            print(f"  [{result.status}] {label}: {cmd.text}")
            if result.detail:
                print(f"         {result.detail}")

    total = sum(counts.values())
    print(
        f"\n{counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped "
        f"out of {total} commands across {len(docs)} file(s)."
    )
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
