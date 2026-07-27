#!/usr/bin/env python3
"""Proves every semgrep rule can actually fire, and ratchets real-corpus hits.

Usage:
    python3 scripts/semgrep_rule_coverage.py                 # non-vacuity gate (CI)
    python3 scripts/semgrep_rule_coverage.py <repo>           # corpus backtest
    python3 scripts/semgrep_rule_coverage.py <repo> --update  # rewrite the baseline

Same two-mode split as rule_coverage.py (the ast-grep analog), for the same
reason: **non-vacuity** (no argument) runs scripts/spring_semgrep_rules.yml
against the committed scripts/semgrep_rule_fixtures/ corpus and fails if any
rule matches nothing -- a rule nobody can make fire is not coverage, whether
the tool behind it is ast-grep or semgrep. **Backtest** (with a path) reports
hit counts against a real repository and ratchets against
scripts/semgrep_rule_coverage_baseline.json; it is a dev-machine-only step,
same as rule_coverage.py's, since a real corpus is too large to commit.

A REAL QUIRK THIS MODULE WORKS AROUND
semgrep's JSON `check_id` is not the bare rule id from the YAML when a rule
file is passed by local path (as opposed to a registry ref like `p/java`):
it prefixes the id with a dotted form of the config file's containing
directory, and that prefix's *length* depends on the current working
directory semgrep was invoked from (confirmed empirically: the same rule,
same file, produced `scripts.<id>` when invoked from the repo root and
`C.Users.<...long absolute path...>.scripts.<id>` when invoked from an
unrelated cwd with an absolute --config path). Matching by exact equality
against the raw YAML id would therefore be cwd-dependent and silently break.
Every rule id in spring_semgrep_rules.yml uses `__` (double underscore,
never a literal `.`), so `check_id.rsplit(".", 1)[-1]` reliably recovers the
bare id regardless of that prefix. See claude/tool-quirks.md.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
RULE_FILE = SCRIPT_DIR / "spring_semgrep_rules.yml"
FIXTURE_DIR = SCRIPT_DIR / "semgrep_rule_fixtures"
BASELINE_FILE = SCRIPT_DIR / "semgrep_rule_coverage_baseline.json"
SCHEMA_VERSION = 1

# `- id: <bucket>__<subkind>` as a YAML list item under `rules:`. Anchored to
# the `- id:` shape (not bare `id:`) since this file is a single-document
# `rules:` list, not spring_ast_grep_rules.yml's multi-document `---` shape.
RULE_ID_RE = re.compile(r"^\s*-\s*id:\s*([a-z0-9_]+__[a-z0-9_]+)\s*$", re.MULTILINE)

# Same shape as rule_coverage.py's FIXTURE_EXEMPT: a rule that legitimately
# cannot be exercised by a fixture, with a stated reason. Empty today -- every
# rule below must fire on the committed corpus.
FIXTURE_EXEMPT: Dict[str, str] = {}


class SemgrepError(RuntimeError):
    """Base for every way invoking semgrep can fail short of a real match."""


class SemgrepNotFoundError(SemgrepError):
    pass


def find_semgrep() -> str:
    binary = shutil.which("semgrep")
    if not binary:
        raise SemgrepNotFoundError(
            "error: the 'semgrep' binary is not on PATH. Install it with "
            "`pip install -r requirements.txt` (pins the version this repo "
            "expects) or `pip install semgrep`.")
    return binary


def rule_ids(rule_file: Path = RULE_FILE) -> List[str]:
    return RULE_ID_RE.findall(rule_file.read_text(encoding="utf-8"))


def _normalize_check_id(check_id: str) -> str:
    """Strip semgrep's cwd-dependent path prefix; see the module docstring."""
    return check_id.rsplit(".", 1)[-1]


def run_semgrep(binary: str, rule_file: Path, target: Path) -> List[dict]:
    try:
        proc = subprocess.run(
            [binary, "scan", "--config", str(rule_file), "--json", str(target)],
            capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError as exc:
        raise SemgrepError(f"error: failed to invoke semgrep: {exc}") from exc
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SemgrepError(
            f"error: semgrep did not produce parseable JSON (exit "
            f"{proc.returncode}): {exc}\nstderr: {proc.stderr[-2000:]}") from exc
    return payload.get("results", [])


def hit_counts(target: Path) -> collections.Counter[str]:
    """Per-rule match counts, via the same runner CI actually invokes, so
    this cannot drift from what a real scan sees."""
    binary = find_semgrep()
    matches = run_semgrep(binary, RULE_FILE, target)
    counts: collections.Counter[str] = collections.Counter()
    for match in matches:
        check_id = match.get("check_id")
        if check_id:
            counts[_normalize_check_id(check_id)] += 1
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
            "python3 scripts/semgrep_rule_coverage.py <repo> --update"
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
    except SemgrepError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"rule-coverage check failed ({len(problems)} issue(s)):", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
