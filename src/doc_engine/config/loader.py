"""Repository-level configuration file loading."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from doc_engine.config.settings import Settings
from doc_engine.core.walk import is_path_inside_root

_CONFIG_NAMES = (".doc-engine.yml", ".doc-engine.yaml", ".doc-engine.json")


def find_repo_config(repo_path: str) -> Optional[Path]:
    """Return the config path if it exists *and* resolves inside the repo root."""
    root = Path(repo_path).resolve()
    for name in _CONFIG_NAMES:
        candidate = root / name
        if not candidate.is_file():
            continue
        if not is_path_inside_root(str(candidate), str(root)):
            continue
        return candidate
    return None


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        raise RuntimeError(
            f"PyYAML is required to read {path.name}. Install with: pip install pyyaml"
        ) from None
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _load_config_dict(path: Path) -> Any:
    if path.suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return _load_yaml(path)


def _coerce_scanners(raw: Any) -> Any:
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return raw


def _extra_mapping(raw: Dict[str, Any]) -> Dict[str, Any]:
    extra = raw.get("extra", {})
    return extra if isinstance(extra, dict) else {}


def _settings_from_raw(raw: Dict[str, Any]) -> Settings:
    scanners = _coerce_scanners(raw.get("scanners"))
    return Settings(
        scanners=scanners if scanners else Settings().scanners,
        sql_dialect=raw.get("sql_dialect", "ansi"),
        respect_gitignore=bool(raw.get("respect_gitignore", False)),
        build_command=raw.get("build_command"),
        db_path=raw.get("db_path"),
        doc_taxonomy=raw.get("doc_taxonomy"),
        compliance_profile=raw.get("compliance_profile", "certified"),
        extra=_extra_mapping(raw),
    )


def load_repo_config(repo_path: str) -> Optional[Settings]:
    path = find_repo_config(repo_path)
    if path is None:
        return None

    raw = _load_config_dict(path)
    if not isinstance(raw, dict):
        return None
    return _settings_from_raw(raw)


def merge_config(base: Settings, overrides: Dict[str, Any]) -> Settings:
    data = base.model_dump()
    for key, value in overrides.items():
        if value is not None and key in data:
            data[key] = value
    return Settings(**data)
