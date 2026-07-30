"""Shared paths for the test suite.

Inserts ``scripts/`` on ``sys.path`` so **meta** modules resolve
(``_ast_signature``, ``drift_match_normalizers``, ``java_perturbations``,
``prompt_contracts``). Product tools are imported via ``doc_engine.tools`` /
``doc_engine.scanning`` package paths — not via this path insert.
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
