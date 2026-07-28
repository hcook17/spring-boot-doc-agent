"""Shared paths and sys.path setup for the test suite."""

from doc_engine.paths import repo_root, scripts_dir
from doc_engine.tools._bootstrap import ensure_scripts_importable

REPO_ROOT = repo_root()
SCRIPTS_DIR = scripts_dir()
SRC_DIR = REPO_ROOT / "src"
FIXTURE_DIR = SCRIPTS_DIR / "test_fixtures" / "spring_signals"
FIXTURE_SNAPSHOT_PATH = SCRIPTS_DIR / "test_fixtures" / "spring_signals_fixture_expected.json"

ensure_scripts_importable()
