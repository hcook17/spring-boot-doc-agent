"""Shared paths for the test suite.

Inserts ``scripts/{ci,ratchets,coverage,fixtures}`` on ``sys.path`` so **meta**
modules resolve (``_ast_signature``, ``drift_match_normalizers``,
``java_perturbations``, ``prompt_contracts``, ``check_*``, ``mutate``, …).
Product tools are imported via ``doc_engine.tools`` / ``doc_engine.scanning``
package paths — not via this path insert.
"""

from __future__ import annotations

import sys

from doc_engine.paths import repo_root, scripts_dir, scripts_meta_path_entries

REPO_ROOT = repo_root()
SCRIPTS_DIR = scripts_dir()
SRC_DIR = REPO_ROOT / "src"
FIXTURE_DIR = SCRIPTS_DIR / "fixtures" / "spring_signals"
FIXTURE_SNAPSHOT_PATH = SCRIPTS_DIR / "fixtures" / "spring_signals_fixture_expected.json"

for _entry in scripts_meta_path_entries():
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
