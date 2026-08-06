"""One-shot mutation driver for check_assertions.py.

Applies each named mutant to the engine in place, runs the test suite,
verifies the mutant is killed, and restores the pristine source. Run from the
repo root:  python tests/spring_signals/mutation_driver.py
Exits 0 only if every mutant dies.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE = REPO_ROOT / "spring-signals" / "harness" / "check_assertions.py"

MUTANTS = [
    (
        "M1 AtLeast >= -> >",
        "ok = result.rows >= exp.value",
        "ok = result.rows > exp.value",
    ),
    (
        "M2 AssertedExact == -> >=",
        "class AssertedExact:\n    def evaluate(self, exp: Expectation, result: QueryResult) -> Outcome:\n"
        "        ok = result.rows == exp.value",
        "class AssertedExact:\n    def evaluate(self, exp: Expectation, result: QueryResult) -> Outcome:\n"
        "        ok = result.rows >= exp.value",
    ),
    (
        "M3 AssertedExact == -> <=",
        "class AssertedExact:\n    def evaluate(self, exp: Expectation, result: QueryResult) -> Outcome:\n"
        "        ok = result.rows == exp.value",
        "class AssertedExact:\n    def evaluate(self, exp: Expectation, result: QueryResult) -> Outcome:\n"
        "        ok = result.rows <= exp.value",
    ),
    (
        "M4 missing CSV returns 0 rows",
        '        raise DataError(f"missing CSV for {query}: {csv_path} (absence is not zero rows)")',
        "        return QueryResult(query=query, rows=0, records=())",
    ),
    (
        "M5 IDENT_RE weakened",
        'IDENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")',
        'IDENT_RE = re.compile(r".*")',
    ),
    (
        "M6 containment check removed",
        "    if resolved != parent and parent not in resolved.parents:",
        "    if False:",
    ),
    (
        "M7 signal match on rule_id only",
        '            rec.get("rule_id") == pin["rule_id"]\n'
        '            and rec.get("symbol") == pin["symbol"]\n'
        '            and rec.get("signal") == pin["signal"]',
        '            rec.get("rule_id") == pin["rule_id"]',
    ),
    (
        "M8 unexpected-CSV check removed",
        "    check_unexpected_csvs(out_dir, spec)",
        "    pass  # mutant: unexpected CSVs tolerated",
    ),
    (
        "M9 rule_minimums counts all rows",
        '            rows = sum(1 for rec in result.records if rec.get("rule_id") == rule_id)',
        "            rows = result.rows",
    ),
    (
        "M10 rule_minimums >= -> >",
        "                    rows >= minimum,",
        "                    rows > minimum,",
    ),
]


def main() -> int:
    pristine = ENGINE.read_text(encoding="utf-8")
    survivors = []
    try:
        for name, old, new in MUTANTS:
            if old not in pristine:
                print(f"ANCHOR MISSING for {name}; driver is stale")
                return 2
            ENGINE.write_text(pristine.replace(old, new, 1), encoding="utf-8")
            run = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/spring_signals/", "-q", "-x"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            status = "KILLED" if run.returncode != 0 else "SURVIVED"
            print(f"{status}: {name}")
            if run.returncode == 0:
                survivors.append(name)
    finally:
        ENGINE.write_text(pristine, encoding="utf-8")
    if survivors:
        print(f"\n{len(survivors)} mutant(s) survived: {survivors}")
        return 1
    print(f"\nAll {len(MUTANTS)} mutants killed; engine restored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
