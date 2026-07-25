#!/usr/bin/env python3
"""Proves every ast-grep rule can actually fire, and ratchets real-corpus hits.

Usage:
    python3 scripts/rule_coverage.py                    # non-vacuity gate (CI)
    python3 scripts/rule_coverage.py <repo>             # corpus backtest
    python3 scripts/rule_coverage.py <repo> --update    # rewrite the baseline

Two modes, because they answer two different questions and only one of them
can run in CI.

**Non-vacuity** (no argument) runs the rule set against scripts/rule_fixtures/,
a committed corpus small enough to live in the repo, and fails if any rule
matches nothing. This is the invariant that was missing. Measured against a
real 615-file Spring service, 10 of 23 rules fired and 13 returned zero -- and
nothing in the repo could distinguish "this codebase has no Kafka" from "this
rule is broken". A rule that cannot fire on a fixture written to trigger it is
broken, unambiguously, and that is decidable here with no external corpus.

**Backtest** (with a path) reports per-rule hit counts against a real
repository and compares them to scripts/rule_coverage_baseline.json. It exists
because the fixture corpus proves a rule *can* fire, never that it fires on
code anyone actually wrote. The baseline is committed and the comparison is a
ratchet: a rule that used to find things and now finds none is a regression,
which is the shape check_code_quality.py already uses. Real corpora are large
and usually gitignored, so this mode is run on a dev machine and its result --
not the corpus -- is what CI sees.

The split matters. Putting the corpus in CI was never an option (the one used
to derive the current baseline is ~101MB and untracked), and a check that
cannot run is worth nothing, which is how this repo ended up with four
checkers wired to nothing at all.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spring_signal_scan  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
RULE_FILE = SCRIPT_DIR / "spring_ast_grep_rules.yml"
FIXTURE_DIR = SCRIPT_DIR / "rule_fixtures"
BASELINE_FILE = SCRIPT_DIR / "rule_coverage_baseline.json"
SCHEMA_VERSION = 1

# `id:` at column 0 of a document in the rule file. Anchored so an `id:` nested
# inside a rule body can never be mistaken for a rule name.
RULE_ID_RE = re.compile(r"^id:\s*([a-z0-9_]+__[a-z0-9_]+)\s*$", re.MULTILINE)

# Rules that legitimately cannot be exercised by a fixture, each with the
# reason. Same shape as check_repo_claims.py's CI_EXEMPT_SUITES: an exemption
# must say why, or it is indistinguishable from an oversight.
FIXTURE_EXEMPT: Dict[str, str] = {}


def rule_ids(rule_file: Path = RULE_FILE) -> List[str]:
    return RULE_ID_RE.findall(rule_file.read_text(encoding="utf-8"))


def hit_counts(target: Path) -> collections.Counter[str]:
    """Per-rule match counts, via the same runner the real scanner uses so
    this cannot drift from what the pipeline actually sees."""
    binary = spring_signal_scan.find_ast_grep()
    matches = spring_signal_scan.run_ast_grep(binary, str(target))
    counts: collections.Counter[str] = collections.Counter()
    for match in matches:
        rule = match.get("ruleId")
        if rule:
            counts[rule] += 1
    return counts


def check_non_vacuity() -> List[str]:
    """Every rule must match something in the fixture corpus."""
    if not FIXTURE_DIR.is_dir():
        return [f"fixture corpus {FIXTURE_DIR.name}/ is missing; "
                f"the non-vacuity gate has nothing to run against"]
    counts = hit_counts(FIXTURE_DIR)
    problems = []
    for rule in rule_ids():
        if rule in FIXTURE_EXEMPT:
            continue
        if counts.get(rule, 0) == 0:
            problems.append(
                f"{rule} matched nothing in {FIXTURE_DIR.name}/. Either the "
                f"rule is broken, or the fixture that should trigger it is "
                f"missing. A rule nobody can make fire is not coverage.")
    for rule, reason in FIXTURE_EXEMPT.items():
        if not reason.strip():
            problems.append(f"{rule} is fixture-exempt with no stated reason")
    return problems


def load_baseline() -> Optional[Dict[str, object]]:
    if not BASELINE_FILE.is_file():
        return None
    return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))


def write_baseline(target: Path, counts: collections.Counter[str]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "$comment": (
            "Per-rule hit counts from a real corpus, measured on a dev machine "
            "because the corpus is too large to track. The gate is a ratchet: "
            "a rule that used to fire and now fires zero times is a "
            "regression. Rising counts are always fine and do not need a "
            "re-measure. Regenerate with: "
            "python3 scripts/rule_coverage.py <repo> --update"
        ),
        "corpus": target.name,
        "counts": dict(sorted(counts.items())),
    }
    BASELINE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def check_ratchet(counts: collections.Counter[str]) -> List[str]:
    baseline = load_baseline()
    if baseline is None:
        return []
    if baseline.get("schema_version") != SCHEMA_VERSION:
        return [f"baseline schema_version {baseline.get('schema_version')!r} "
                f"!= {SCHEMA_VERSION}; regenerate it with --update"]
    recorded = baseline.get("counts", {})
    if not isinstance(recorded, dict):
        return ["baseline 'counts' is not an object; regenerate it with --update"]
    problems = []
    for rule, was in sorted(recorded.items()):
        now = counts.get(rule, 0)
        if was > 0 and now == 0:
            problems.append(
                f"{rule} fired {was} time(s) in the baseline and zero now. "
                f"Either the rule regressed or the corpus changed; if the "
                f"corpus changed, re-measure with --update.")
    return problems


def report(counts: collections.Counter[str], label: str) -> None:
    every = rule_ids()
    fired = [r for r in every if counts.get(r, 0)]
    print(f"{label}: {len(fired)}/{len(every)} rules fired")
    for rule in every:
        count = counts.get(rule, 0)
        marker = "     " if count else "  <-- "
        print(f"  {count:7d}  {rule}{marker}{'no hits' if not count else ''}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", nargs="?",
                        help="target repository for the corpus backtest; "
                             "omit to run the fixture non-vacuity gate")
    parser.add_argument("--update", action="store_true",
                        help="rewrite the baseline from this run")
    args = parser.parse_args(argv)

    try:
        if args.repo is None:
            problems = check_non_vacuity()
            if not problems:
                report(hit_counts(FIXTURE_DIR), "fixture non-vacuity")
                print("OK: every rule fires on the fixture corpus.")
                return 0
        else:
            target = Path(args.repo)
            if not target.is_dir():
                print(f"error: {target} is not a directory", file=sys.stderr)
                return 2
            counts = hit_counts(target)
            report(counts, f"corpus {target.name}")
            if args.update:
                write_baseline(target, counts)
                print(f"wrote {BASELINE_FILE.name}")
                return 0
            problems = check_ratchet(counts)
            if not problems:
                print("OK: no rule regressed against the baseline.")
                return 0
    except spring_signal_scan.AstGrepNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"rule-coverage check failed ({len(problems)} issue(s)):", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
