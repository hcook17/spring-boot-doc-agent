#!/usr/bin/env python3
"""Ratchet complexipy offender count (must not rise; lower after remediations).

Usage:
    python3 scripts/ci/check_complexipy_ratchet.py
    python3 scripts/ci/check_complexipy_ratchet.py --update

The hard gate remains ``complexipy --max-complexity-allowed=5 --failed`` on
``src/doc_engine`` + ``src/stf`` (see ``run_quality_gates.py``). This script
additionally fails when the *count* of functions above that ceiling rises vs
``scripts/ratchets/complexipy_baseline.json``. Ratchet the baseline downward
after each remediation batch; never raise it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from doc_engine.paths import repo_root

REPO_ROOT = repo_root()
PACKAGE_ROOTS = ("src/doc_engine", "src/stf")
COMPLEXITY_MAX = 5
DEFAULT_BASELINE = REPO_ROOT / "scripts" / "ratchets" / "complexipy_baseline.json"
SCHEMA_VERSION = 1


def _require_complexipy() -> str:
    resolved = shutil.which("complexipy")
    if resolved:
        return resolved
    sibling = Path(sys.executable).resolve().parent
    for candidate in (
        sibling / "complexipy",
        sibling / "complexipy.exe",
        sibling / "Scripts" / "complexipy",
        sibling / "Scripts" / "complexipy.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    print("error: complexipy is not on PATH", file=sys.stderr)
    raise SystemExit(2)


def count_offenders() -> int:
    """Return how many functions exceed COMPLEXITY_MAX under package roots."""
    complexipy = _require_complexipy()
    completed = subprocess.run(
        [
            complexipy,
            *PACKAGE_ROOTS,
            f"--max-complexity-allowed={COMPLEXITY_MAX}",
            "--failed",
            "--plain",
            "--color=no",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    count = 0
    for line in (completed.stdout or "").splitlines():
        parts = line.strip().rsplit(None, 1)
        if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) > COMPLEXITY_MAX:
            count += 1
    return count


def load_baseline(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        print(
            f"error: baseline schema_version {data.get('schema_version')!r} "
            f"!= {SCHEMA_VERSION}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return data


def write_baseline(path: Path, offender_count: int) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "max_complexity_allowed": COMPLEXITY_MAX,
        "package_roots": list(PACKAGE_ROOTS),
        "offender_count": offender_count,
        "note": (
            "Whole-repo complexipy ≤5 is the hard gate in run_quality_gates.py. "
            "This baseline additionally ratchets the interim offender count "
            "downward only — never raise it. Remeasure with: python3 scripts/ci/"
            "check_complexipy_ratchet.py --update"
        ),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="committed baseline JSON path",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite baseline from the current offender count",
    )
    args = parser.parse_args(argv)

    current = count_offenders()
    if args.update:
        write_baseline(args.baseline, current)
        print(f"baseline written: {args.baseline} (offender_count={current})")
        return 0

    if not args.baseline.is_file():
        print(
            f"error: no baseline at {args.baseline}; create one with --update",
            file=sys.stderr,
        )
        return 2

    baseline = load_baseline(args.baseline)
    ceiling = int(baseline["offender_count"])
    print(
        f"complexipy ratchet: offenders={current} baseline_ceiling={ceiling} "
        f"(max_complexity={COMPLEXITY_MAX})"
    )
    if current > ceiling:
        print(
            f"error: complexipy offender count rose {ceiling} -> {current}; "
            f"refactor or do not raise the baseline",
            file=sys.stderr,
        )
        return 1
    if current < ceiling:
        print(
            f"note: offender count dropped {ceiling} -> {current}; "
            f"re-baseline with --update to ratchet downward"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
