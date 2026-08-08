#!/usr/bin/env python3
"""gap_probe — AET Stage-0 gap measurement (rates with denominators).

See claude/research/aet-measurement-2026-07-30.md.

Usage:
    python -m doc_engine.tools.gap_probe \\
        --signals spring_signals.json --facts facts.jsonl --out gap_report/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from doc_engine.scanning.gap_probe import (
    GAP_PROBE_SCHEMA_VERSION,
    CoveringPreconditionError,
    run_gap_probe,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure Stage-0 residual uncertainty "
            "(AET: rates, scoring-env delta, truncation)."
        ),
    )
    parser.add_argument("--signals", required=True, type=Path, help="Path to spring_signals.json")
    parser.add_argument("--facts", required=True, type=Path, help="Path to facts.jsonl")
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output directory for gap_report.json + gap_failures.jsonl",
    )
    parser.add_argument(
        "--covering",
        type=Path,
        default=None,
        help="Path to covering_proof.json (default: sibling of --signals).",
    )
    parser.add_argument(
        "--failure-budget",
        type=int,
        default=None,
        help="Pi_B: keep at most B sorted failure rows (default: keep all).",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Reserved for future oracle / walk strata (ignored; dep/code use evidence bags only).",
    )
    return parser


def _validate_input_paths(args: argparse.Namespace) -> int | None:
    if args.repo is not None:
        print(
            "warning: --repo is reserved and ignored in "
            f"GAP_PROBE_SCHEMA_VERSION={GAP_PROBE_SCHEMA_VERSION}",
            file=sys.stderr,
        )
    if not args.signals.is_file():
        print(f"error: signals not found: {args.signals}", file=sys.stderr)
        return 2
    if not args.facts.is_file():
        print(f"error: facts not found: {args.facts}", file=sys.stderr)
        return 2
    return None


def _print_gap_summary(report: dict, out_dir: Path) -> None:
    rates = report.get("rates") or {}
    trunc = ((report.get("measurement") or {}).get("truncation")) or {}
    delta = ((report.get("measurement") or {}).get("delta_r_scoring_env")) or {}
    print(
        json.dumps(
            {
                "event": "gap_probe",
                "schema_version": GAP_PROBE_SCHEMA_VERSION,
                "out": str(out_dir.resolve()),
                "U": (report.get("uncertainty") or {}).get("U"),
                "R_sym": (rates.get("R_sym") or {}).get("rate"),
                "R_coll": (rates.get("R_coll") or {}).get("rate"),
                "R_join": (rates.get("R_join") or {}).get("rate"),
                "R_lin_mean": (rates.get("R_lin") or {}).get("mean_rate"),
                "R_code_dep": (rates.get("R_code_dep") or {}).get("rate"),
                "L": trunc.get("L"),
                "delta_R_lin_mean": delta.get("R_lin_mean"),
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    resolved = out_dir.resolve()
    print(f"Wrote {resolved / 'gap_report.json'} and {resolved / 'gap_failures.jsonl'}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    path_error = _validate_input_paths(args)
    if path_error is not None:
        return path_error
    try:
        report = run_gap_probe(
            args.signals.resolve(),
            args.facts.resolve(),
            args.out.resolve(),
            failure_budget=args.failure_budget,
            covering_path=args.covering.resolve() if args.covering else None,
        )
    except CoveringPreconditionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    _print_gap_summary(report, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
