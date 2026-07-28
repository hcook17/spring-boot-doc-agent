#!/usr/bin/env python3
"""Regenerate the fixture snapshot used by SPRING_SIGNAL_USE_SNAPSHOT=1.

This runs the configured scanner set against scripts/test_fixtures/spring_signals/
and writes the result to scripts/test_fixtures/spring_signals_fixture_expected.json.
Commit the updated JSON when the scanner code or rules change and the snapshot's
scanner_version no longer matches the current version.
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(SCRIPT_DIR, "test_fixtures", "spring_signals")
SNAPSHOT_PATH = os.path.join(FIXTURE_DIR, "..", "spring_signals_fixture_expected.json")
sys.path.insert(0, SCRIPT_DIR)

import spring_signal_scan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--scanners",
        default="filesystem,ast-grep",
        help="Comma-separated scanner names to use for the snapshot. Default: filesystem,ast-grep",
    )
    args = ap.parse_args()

    scanners = [s.strip() for s in args.scanners.split(",") if s.strip()]
    result = spring_signal_scan.scan(FIXTURE_DIR, scanners=scanners)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"wrote {SNAPSHOT_PATH}")
    print(f"  schema_version: {result.get('schema_version')}")
    print(f"  scanner_version: {result.get('scanner_version')}")
    print(f"  files_scanned: {result.get('files_scanned')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
