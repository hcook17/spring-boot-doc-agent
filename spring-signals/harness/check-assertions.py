#!/usr/bin/env python3
"""Check query row counts against expectations.

Reads two files from an expectations directory (default: the directory
containing this script):
  expected-empty.txt   one query name per line (blank/comment lines ignored)
  expected-min.txt     one 'query rule_id min_count' triple per line

Exits non-zero if any expectation is violated.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        ln.strip()
        for ln in path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def count_rows(query: str, out: Path) -> int:
    csv_path = out / f"{query}.csv"
    if not csv_path.exists():
        return -1
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def count_by_rule_id(query: str, rule_id: str, out: Path) -> int:
    csv_path = out / f"{query}.csv"
    if not csv_path.exists():
        return -1
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return sum(1 for row in csv.DictReader(fh) if row.get("rule_id") == rule_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--expected-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="directory containing expected-empty.txt and expected-min.txt",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "out",
        help="directory containing the generated query CSVs",
    )
    args = ap.parse_args(argv)

    failed = 0

    for ln in load_lines(args.expected_dir / "expected-empty.txt"):
        parts = ln.split()
        if len(parts) != 2:
            print(f"BAD empty expectation line: {ln}")
            failed += 1
            continue
        query, expected = parts
        expected_count = int(expected)
        actual = count_rows(query, args.out_dir)
        if actual == -1:
            print(f"MISS {query} (no {args.out_dir / query}.csv)")
            failed += 1
        elif actual != expected_count:
            print(f"FAIL {query} = {actual} (expected {expected_count})")
            failed += 1
        else:
            print(f"OK   {query} = {expected_count}")

    for ln in load_lines(args.expected_dir / "expected-min.txt"):
        parts = ln.split()
        if len(parts) != 3:
            print(f"BAD expectation line: {ln}")
            failed += 1
            continue
        query, rule_id, expected = parts
        expected_count = int(expected)
        actual = count_by_rule_id(query, rule_id, args.out_dir)
        if actual == -1:
            print(f"MISS {query} {rule_id} (no CSV)")
            failed += 1
        elif actual < expected_count:
            print(f"FAIL {query} {rule_id} = {actual} (expected >= {expected_count})")
            failed += 1
        else:
            print(f"OK   {query} {rule_id} = {actual} (expected >= {expected_count})")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
