"""Repository path helpers for the scanning package."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_RESOURCES_DIR = Path(__file__).resolve().parent / "resources"
_AST_GREP_RULES = _RESOURCES_DIR / "spring_ast_grep_rules.yml"
_CODEQL_PACK_DIR = _REPO_ROOT / "codeql" / "spring-signals"


def repo_root() -> Path:
    return _REPO_ROOT


def scripts_dir() -> Path:
    return _SCRIPTS_DIR


def ast_grep_rules_path() -> Path:
    return _AST_GREP_RULES


def codeql_pack_dir() -> Path:
    return _CODEQL_PACK_DIR
