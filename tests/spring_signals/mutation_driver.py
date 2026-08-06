"""One-shot mutation driver for spring-signals/harness/check-assertions.py.

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
ENGINE = REPO_ROOT / "spring-signals" / "harness" / "check-assertions.py"

MUTANTS = [
    (
        "M1 minimums >= -> >",
        'rep.verdict(got >= want, name, got, f">= {want}")',
        'rep.verdict(got > want, name, got, f">= {want}")',
    ),
    (
        "M2 exact == -> >=",
        "rep.verdict(got == want, name, got, str(want))",
        "rep.verdict(got >= want, name, got, str(want))",
    ),
    (
        "M3 exact == -> <=",
        "rep.verdict(got == want, name, got, str(want))",
        "rep.verdict(got <= want, name, got, str(want))",
    ),
    (
        "M4 missing CSV returns 0 rows",
        "    if not path.exists():\n        return -1, Counter()",
        "    if not path.exists():\n        return 0, Counter()",
    ),
    (
        "M5 IDENT_RE weakened",
        'IDENT_RE = re.compile(r"^[A-Za-z]\\w*$", re.ASCII)',
        'IDENT_RE = re.compile(r".*")',
    ),
    (
        "M6 record containment removed",
        "    if not spec_path.is_relative_to(harness_dir):",
        "    if False:",
    ),
    (
        "M7 signals compared as sets",
        "        rep.verdict(actual.get(rule, []) == want_sorted,",
        "        rep.verdict(set(actual.get(rule, [])) == set(want_sorted),",
    ),
    (
        "M8 stale-CSV check removed",
        "    check_no_stale_csvs(out_dir, spec)",
        "    pass  # mutant: stale CSVs tolerated",
    ),
    (
        "M9 record shadows asserted",
        "        for key in list(entry):\n"
        "            if key in asserted.get(query, {}):\n"
        "                del entry[key]",
        "        pass  # mutant: asserted keys shadowed by recorded ones",
    ),
    (
        "M10 record merges instead of replaces",
        '    spec["snapshot"] = build_recorded_block(out_dir, asserted)',
        '    spec.setdefault("snapshot", {}).update(build_recorded_block(out_dir, asserted))',
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
