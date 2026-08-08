#!/usr/bin/env python3
"""Hard in-repo quality gates (coverage / duplication / complexity / cycles).

Usage:
    python3 scripts/ci/run_quality_gates.py --compare-ref origin/main
    python3 scripts/ci/run_quality_gates.py --compare-ref HEAD~1 \\
        --coverage-xml coverage.xml

Same command on Mac, Windows, and Linux (CI uses this entry point too).
Requires: ``pip install -r requirements-dev.txt && pip install -e .`` and
``npm ci`` (pins jscpd; see CONTRIBUTING.md "Quality gates (all OS)").

Exit codes:
    0  all hard gates passed
    1  one or more hard gates failed
    2  usage / missing prerequisite
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from gate_tools import JSCPD_VERSION, REPO_ROOT, jscpd_command, python_module_command

PACKAGE_ROOTS = ("src/doc_engine", "src/stf")
NEW_CODE_COVERAGE_FLOOR = 98.7
COMPLEXITY_MAX = 5
DUPLICATION_MAX_PERCENT = 3


def _run(command: list[str], *, label: str) -> int:
    """Run *command* as an argv list (no shell); return the process exit code."""
    print(f"\n=== {label} ===", flush=True)
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return int(completed.returncode)


def resolve_compare_ref(explicit: str | None) -> str:
    """Return the git ref used as the new-code baseline."""
    if explicit:
        return explicit
    print("error: --compare-ref is required", file=sys.stderr)
    raise SystemExit(2)


def changed_python_under_packages(compare_ref: str) -> list[str]:
    """List ACMR Python paths under package roots vs *compare_ref*."""
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{compare_ref}...HEAD",
            "--",
            *PACKAGE_ROOTS,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print(completed.stderr, file=sys.stderr)
        print("error: git diff for changed Python files failed", file=sys.stderr)
        raise SystemExit(2)
    paths = []
    for line in completed.stdout.splitlines():
        path = line.strip()
        if path.endswith(".py") and Path(REPO_ROOT, path).is_file():
            paths.append(path)
    return paths


def gate_new_code_coverage(compare_ref: str, coverage_xml: Path) -> int:
    """Fail when covered lines on the diff are below NEW_CODE_COVERAGE_FLOOR."""
    if not coverage_xml.is_file():
        print(f"error: missing coverage report: {coverage_xml}", file=sys.stderr)
        return 2
    coverage_xml = coverage_xml if coverage_xml.is_absolute() else REPO_ROOT / coverage_xml
    return _run(
        python_module_command(
            "diff_cover.diff_cover_tool",
            str(coverage_xml),
            f"--compare-branch={compare_ref}",
            f"--fail-under={NEW_CODE_COVERAGE_FLOOR}",
            "--include=src/doc_engine/*",
            "--include=src/stf/*",
        ),
        label=f"diff-cover new-code coverage >= {NEW_CODE_COVERAGE_FLOOR}%",
    )


def gate_duplication(compare_ref: str) -> int:
    """Fail when jscpd duplication among changed package files exceeds 3%."""
    changed = changed_python_under_packages(compare_ref)
    if not changed:
        print(
            "\n=== jscpd duplication <= 3% ===\n"
            "No changed Python under src/doc_engine or src/stf; skipping.",
            flush=True,
        )
        return 0
    if len(changed) == 1:
        print(
            "\n=== jscpd duplication <= 3% ===\n"
            f"Single changed file ({changed[0]}); intra-diff duplication N/A - pass.",
            flush=True,
        )
        return 0
    return _run(
        jscpd_command(
            f"--threshold={DUPLICATION_MAX_PERCENT}",
            "--min-lines=5",
            "--format=python",
            *changed,
        ),
        label=(
            f"jscpd@{JSCPD_VERSION} duplication <= {DUPLICATION_MAX_PERCENT}% "
            "(changed files; local node_modules)"
        ),
    )


def gate_cognitive_complexity() -> int:
    """Fail when the count of >COMPLEXITY_MAX functions rises vs baseline.

    Policy target remains <=COMPLEXITY_MAX per function. While
    ``scripts/ratchets/complexipy_baseline.json`` still lists offenders,
    whole-repo ``complexipy --failed`` cannot green CI — the ratchet is the
    hard gate. When the baseline reaches 0, ``--failed`` becomes free.
    """
    return _run(
        [sys.executable, "scripts/ci/check_complexipy_ratchet.py"],
        label=(
            f"complexipy offender-count ratchet "
            f"(must not rise; target <={COMPLEXITY_MAX}/fn)"
        ),
    )


def gate_import_cycles() -> int:
    """Fail when tach finds circular imports among configured modules."""
    return _run(
        python_module_command("tach", "check"),
        label="tach forbid circular dependencies",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the quality-gate runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare-ref",
        required=True,
        help="Git ref for new-code baseline (PR base SHA, origin/main, HEAD~1).",
    )
    parser.add_argument(
        "--coverage-xml",
        type=Path,
        default=REPO_ROOT / "coverage.xml",
        help="Cobertura XML from pytest-cov (default: ./coverage.xml).",
    )
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Skip diff-cover (local debug only).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run every hard gate; return the worst non-zero exit code."""
    args = parse_args(argv)
    compare_ref = resolve_compare_ref(args.compare_ref)
    results: list[tuple[str, int]] = []

    if not args.skip_coverage:
        results.append(
            ("new-code-coverage", gate_new_code_coverage(compare_ref, args.coverage_xml))
        )
    results.append(("duplication", gate_duplication(compare_ref)))
    results.append(("cognitive-complexity", gate_cognitive_complexity()))
    results.append(("import-cycles", gate_import_cycles()))

    print("\n=== quality-gates summary ===", flush=True)
    for name, code in results:
        status = "PASS" if code == 0 else f"FAIL (exit {code})"
        print(f"- {name}: {status}", flush=True)
    # Prefer exit 1 for gate failure; preserve 2 for missing prerequisites.
    if any(code == 2 for _, code in results):
        return 2
    if any(code != 0 for _, code in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
