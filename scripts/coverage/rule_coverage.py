#!/usr/bin/env python3
"""Proves every CodeQL query/sub-kind can actually fire, and ratchets real-corpus hits.

Usage:
    python3 scripts/coverage/rule_coverage.py                    # non-vacuity gate (CI)
    python3 scripts/coverage/rule_coverage.py <repo>             # corpus backtest
    python3 scripts/coverage/rule_coverage.py <repo> --update  # rewrite the baseline

Two modes, because they answer two different questions and only one of them
can run hermetically in CI.

**Non-vacuity** (no argument) runs the query pack against
scripts/fixtures/spring_signals/, a committed corpus small enough to live
in the repo, and fails if any rule_id matches nothing. This is the invariant
that was missing. With the old ast-grep layer, 10 of 23 rules fired on a real
production Spring service and 13 returned zero, and nothing in the repo could
distinguish "this codebase has no Kafka" from "this rule is broken". A rule
that cannot fire on a fixture written to trigger it is broken, unambiguously,
and that is decidable here with no external corpus.

**Backtest** (with a path) reports per-rule-id hit counts against a real
repository and compares them to scripts/coverage/rule_coverage_baseline.json. It exists
because the fixture corpus proves a rule *can* fire, never that it fires on
code anyone actually wrote. The baseline is committed; CI witnesses its
``schema_version`` stamp and pack-owned keys (tests/coverage/test_rule_coverage.py)
but does **not** run the external corpus. The comparison is a ratchet: a rule
that used to find things and now finds none is a regression, which is the
shape check_code_quality.py already uses. Real corpora are large and usually
gitignored, so this mode is run on a dev machine and only the baseline file
is committed — absence of a baseline key means not yet measured, not proven
zero. Missing / corrupt / schema-stale baselines fail closed.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from doc_engine.paths import codeql_pack_dir, scripts_dir
from doc_engine.tools import spring_signal_scan

SCRIPT_DIR = Path(__file__).resolve().parent
PACK_DIR = codeql_pack_dir()
FIXTURE_DIR = scripts_dir() / "fixtures" / "spring_signals"
BASELINE_FILE = SCRIPT_DIR / "rule_coverage_baseline.json"
SCHEMA_VERSION = 2

# Rule ids appear in two CodeQL spellings inside .ql files:
#   rule_id = "bucket__kind"
#   "bucket__kind" as rule_id
# Missing the `as` form silently under-counts the pack (RawQueries.ql).
RULE_ID_EQ_RE = re.compile(r'rule_id\s*=\s*"([a-z0-9_]+__[a-z0-9_]+)"')
RULE_ID_AS_RE = re.compile(r'"([a-z0-9_]+__[a-z0-9_]+)"\s+as\s+rule_id')
# Back-compat alias used by older tests / callers.
RULE_ID_RE = RULE_ID_EQ_RE


def _extract_rule_ids(text: str) -> List[str]:
    """All rule_id literals from one .ql (or fixture) body, both spellings."""
    return RULE_ID_EQ_RE.findall(text) + RULE_ID_AS_RE.findall(text)


# Rules that legitimately cannot be exercised by the fixture, each with the
# reason. An exemption must say why, or it is indistinguishable from an oversight.
FIXTURE_EXEMPT: Dict[str, str] = {}


def rule_ids(rule_file: Optional[Path] = None) -> List[str]:
    """Return every unique rule_id declared in the CodeQL query pack.

    The optional rule_file argument is kept for backward compatibility with
    tests that previously passed a YAML file to the ast-grep version.
    """
    ids: List[str] = []
    if rule_file is not None:
        sources = [rule_file]
    else:
        sources = sorted(PACK_DIR.glob("*.ql"))
    for ql in sources:
        ids.extend(_extract_rule_ids(ql.read_text(encoding="utf-8")))
    # Deduplicate while preserving the order they appear in the pack.
    seen = set()
    unique: List[str] = []
    for rid in ids:
        if rid not in seen:
            seen.add(rid)
            unique.append(rid)
    return unique


def hit_counts(target: Path) -> collections.Counter[str]:
    """Per-rule-id match counts, via the same scanner the pipeline uses so
    this cannot drift from what Stage 0 actually sees.

    CI uses filesystem+ast-grep (no CodeQL CLI on the runner). The CodeQL pack
    and ast-grep rules share the same rule_id vocabulary, so non-vacuity still
    proves every declared id can fire on the fixture corpus.
    """
    result = spring_signal_scan.scan(
        str(target),
        scanners=["filesystem", "ast-grep"],
    )
    counts: collections.Counter[str] = collections.Counter()
    for entries in result["evidence"].values():
        for entry in entries:
            rule = entry.get("rule_id")
            if rule:
                counts[rule] += 1
    return counts


def check_non_vacuity() -> List[str]:
    """Every rule must match something in the fixture corpus."""
    if not FIXTURE_DIR.is_dir():
        return [f"fixture corpus {FIXTURE_DIR.name}/ is missing; "
                f"the non-vacuity gate has nothing to run against"]
    ids = rule_ids()
    if not ids:
        return ["CodeQL pack yielded no rule_id values; empty denominator "
                "is not coverage (vacuous pass refused)"]
    counts = hit_counts(FIXTURE_DIR)
    problems = []
    for rule in ids:
        if rule in FIXTURE_EXEMPT:
            continue
        if counts.get(rule, 0) == 0:
            problems.append(
                f"{rule} matched nothing in {FIXTURE_DIR.name}/. Either the "
                f"query is broken, or the fixture that should trigger it is "
                f"missing. A rule nobody can make fire is not coverage.")
    for rule, reason in FIXTURE_EXEMPT.items():
        if not reason.strip():
            problems.append(f"{rule} is fixture-exempt with no stated reason")
    return problems


def _load_baseline_payload() -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    """Return (payload, error). Missing / corrupt baselines are errors."""
    if not BASELINE_FILE.is_file():
        return None, (
            f"baseline {BASELINE_FILE.name} is missing; SoR absent is not OK "
            f"— measure a corpus with --update or restore the committed file"
        )
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, (
            f"baseline {BASELINE_FILE.name} is not valid JSON ({exc.msg}); "
            f"regenerate it with --update"
        )
    if not isinstance(data, dict):
        return None, (
            f"baseline {BASELINE_FILE.name} root is not an object; "
            f"regenerate it with --update"
        )
    return data, None


def load_baseline() -> Optional[Dict[str, object]]:
    """Load the committed baseline object, or None if missing/corrupt.

    Prefer ``check_ratchet`` for fail-closed messages; this helper remains for
    callers that only need the payload when present.
    """
    data, _err = _load_baseline_payload()
    return data


def write_baseline(target: Path, counts: collections.Counter[str]) -> None:
    pack = set(rule_ids())
    # Only pack-owned keys enter the SoR. Scanner hits can include filesystem
    # filename tags (deployment__*) and must not reintroduce "orphans" that
    # the committed-schema witness then rejects.
    pack_counts = {k: int(v) for k, v in sorted(counts.items()) if k in pack}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "$comment": (
            "Per-rule-id hit counts from a real corpus, measured on a dev "
            "machine because the corpus is too large to track. schema_version "
            f"{SCHEMA_VERSION}: CI witnesses this stamp + pack-owned keys "
            "(hermetic); it does not run the external corpus. The gate is a "
            "ratchet: a rule that used to fire and now fires zero times is a "
            "regression. Rising counts are always fine. Absence of a pack id "
            "from counts means not yet measured, not proven zero. Regenerate "
            "with: python3 scripts/coverage/rule_coverage.py <repo> --update"
        ),
        "corpus": target.name,
        "counts": pack_counts,
    }
    BASELINE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def check_ratchet(counts: collections.Counter[str]) -> List[str]:
    baseline, err = _load_baseline_payload()
    if err is not None:
        return [err]
    assert baseline is not None
    if baseline.get("schema_version") != SCHEMA_VERSION:
        return [f"baseline schema_version {baseline.get('schema_version')!r} "
                f"!= {SCHEMA_VERSION}; regenerate it with --update"]
    if "counts" not in baseline:
        return ["baseline is missing 'counts'; regenerate it with --update"]
    recorded = baseline.get("counts")
    if not isinstance(recorded, dict):
        return ["baseline 'counts' is not an object; regenerate it with --update"]
    problems = []
    for rule, was in sorted(recorded.items()):
        now = counts.get(rule, 0)
        if was > 0 and now == 0:
            problems.append(
                f"{rule} fired {was} time(s) in the baseline and zero now. "
                f"Either the query regressed or the corpus changed; if the "
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
    except spring_signal_scan.CodeQLScannerError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"rule-coverage check failed ({len(problems)} issue(s)):", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
