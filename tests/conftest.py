"""Shared paths and sys.path setup for the test suite."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
SRC_DIR = REPO_ROOT / "src"
FIXTURE_DIR = SCRIPTS_DIR / "test_fixtures" / "spring_signals"
FIXTURE_SNAPSHOT_PATH = SCRIPTS_DIR / "test_fixtures" / "spring_signals_fixture_expected.json"

for path in (str(SRC_DIR), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)
