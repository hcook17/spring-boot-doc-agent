#!/usr/bin/env python3
"""Regenerate the fixture snapshot used by SPRING_SIGNAL_USE_SNAPSHOT=1.

This runs a full CodeQL scan of scripts/test_fixtures/spring_signals/ and
writes the result to scripts/test_fixtures/spring_signals_fixture_expected.json.
Commit the updated JSON when the scanner code or queries change and the
snapshot's scanner_version no longer matches the current version.
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(SCRIPT_DIR, "test_fixtures", "spring_signals")
SNAPSHOT_PATH = os.path.join(FIXTURE_DIR, "..", "spring_signals_fixture_expected.json")
sys.path.insert(0, SCRIPT_DIR)

import spring_signal_scan


def main() -> int:
    build_command = (
        os.path.join(FIXTURE_DIR, "gradlew.bat" if os.name == "nt" else "gradlew")
        + " --no-daemon clean compileJava compileTestJava"
    )
    result = spring_signal_scan.scan(FIXTURE_DIR, build_command=build_command)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"wrote {SNAPSHOT_PATH}")
    print(f"  schema_version: {result.get('schema_version')}")
    print(f"  scanner_version: {result.get('scanner_version')}")
    print(f"  files_scanned: {result.get('files_scanned')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
