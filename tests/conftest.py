"""Shared paths for the test suite.

Inserts ``scripts/`` on ``sys.path`` so historical ``import run_manifest``-style
tests resolve thin shims that re-export ``doc_engine.tools.*``.
"""

from __future__ import annotations

import sys

from doc_engine.paths import repo_root, scripts_dir

REPO_ROOT = repo_root()
SCRIPTS_DIR = scripts_dir()
SRC_DIR = REPO_ROOT / "src"
FIXTURE_DIR = SCRIPTS_DIR / "test_fixtures" / "spring_signals"
FIXTURE_SNAPSHOT_PATH = SCRIPTS_DIR / "test_fixtures" / "spring_signals_fixture_expected.json"

_scripts = str(SCRIPTS_DIR)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
