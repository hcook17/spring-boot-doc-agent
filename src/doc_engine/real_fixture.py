"""Resolve the canonical local real-Spring fixture for merge-readiness tests.

Usage (operator machine)::

    export DOC_ENGINE_REAL_REPO=/path/to/local-spring-tree
    export DOC_ENGINE_REAL_ARTIFACTS_DIR=local-runs/real-repo-latest  # optional

Or write one absolute path line to the gitignored file
``local-runs/real-repo.path`` (same resolution order: env wins).

Legacy env names (``GAP_PROBE_OCS_*``, ``DRIFT_OCS_*``,
``PARTITION_REPO_REAL_FIXTURE_DIR``) are aliases when the canonical vars are
unset. Never commit a client checkout path or denylist token into tracked files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from doc_engine.paths import repo_root

# Canonical
ENV_REAL_REPO = "DOC_ENGINE_REAL_REPO"
ENV_REAL_ARTIFACTS = "DOC_ENGINE_REAL_ARTIFACTS_DIR"
ENV_LIVE_SCAN = "DOC_ENGINE_REAL_LIVE_SCAN"

# Legacy aliases (compat with existing opt-in suite docs)
_LEGACY_REPO_VARS = (
    "GAP_PROBE_OCS_REPO",
    "DRIFT_OCS_REPO",
    "PARTITION_REPO_REAL_FIXTURE_DIR",
    "KITCHEN_SINK_REPO",
)
_LEGACY_ARTIFACTS_VARS = (
    "GAP_PROBE_OCS_ARTIFACTS_DIR",
    "DRIFT_OCS_ARTIFACTS_DIR",
)
_LEGACY_LIVE_VARS = (
    "GAP_PROBE_OCS_LIVE_SCAN",
    "DRIFT_OCS_LIVE_SCAN",
)

DEFAULT_ARTIFACTS_REL = Path("local-runs") / "real-repo-latest"
# Gitignored pointer file — one absolute path per line; first non-empty, non-#
# line wins. Lets operators avoid exporting env vars every shell.
REAL_REPO_PATH_FILE = Path("local-runs") / "real-repo.path"

# Paths that trigger the pre_pr real_repo hard lane.
REAL_REPO_PATH_PREFIXES: tuple[str, ...] = (
    "src/doc_engine/scanning/",
    "src/doc_engine/tools/spring_signal_scan.py",
    "src/doc_engine/tools/spring_drift_check.py",
    "src/doc_engine/tools/gap_probe.py",
    "src/doc_engine/tools/partition_repo.py",
    "src/doc_engine/tools/query_artifacts.py",
    "src/doc_engine/query/",
    "src/doc_engine/real_fixture.py",
    "scripts/ci/regen_real_repo_artifacts.py",
    "scripts/coverage/real_repo_gap_baseline.json",
    "scripts/fixtures/gap_probe_shapes/",
    "tests/doc_engine/test_gap_probe",
    "tests/doc_engine/test_covering",
    "tests/doc_engine/test_partition_repo",
    "tests/doc_engine/test_scan_context_wiring",
    "tests/doc_engine/test_spring_signal_scan",
    "tests/doc_engine/test_spring_drift_check",
    "tests/doc_engine/test_drift_report",
    "tests/doc_engine/test_etl_adversarial.py",
    "tests/doc_engine/test_query_artifacts.py",
    "tests/doc_engine/test_query_ocs_real_world.py",
    "tests/doc_engine/test_context_packet.py",
)


def _truthy(raw: Optional[str]) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes"}


def _first_env(*names: str) -> Optional[str]:
    for name in names:
        val = os.environ.get(name)
        if val is not None and val.strip():
            return val.strip()
    return None


def _first_content_line(text: str) -> Optional[str]:
    """First non-empty, non-comment line (BOM-tolerant)."""
    for line in text.splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if not stripped or stripped.startswith("#"):
            continue
        return stripped
    return None


def _read_path_file() -> Optional[Path]:
    """Return path from ``local-runs/real-repo.path`` when present and non-empty."""
    path_file = repo_root() / REAL_REPO_PATH_FILE
    if not path_file.is_file():
        return None
    try:
        text = path_file.read_text(encoding="utf-8")
    except OSError:
        return None
    line = _first_content_line(text)
    return Path(line) if line else None


def real_repo_path() -> Optional[Path]:
    """Return the local Spring tree path, or None if unset.

    Resolution order: ``DOC_ENGINE_REAL_REPO`` → legacy env aliases →
    ``local-runs/real-repo.path``.
    """
    raw = _first_env(ENV_REAL_REPO, *_LEGACY_REPO_VARS)
    if raw is not None:
        return Path(raw)
    return _read_path_file()


def require_real_repo() -> Path:
    """Return an existing real-repo directory or raise ``FileNotFoundError``."""
    path = real_repo_path()
    if path is None:
        raise FileNotFoundError(
            f"{ENV_REAL_REPO} is unset (no legacy alias, no {REAL_REPO_PATH_FILE}). "
            "Point it at a local Spring Boot tree for the real-repo lane."
        )
    if not path.is_dir():
        raise FileNotFoundError(f"{ENV_REAL_REPO} is not a directory: {path}")
    return path


def real_artifacts_dir(*, prefer_default: bool = False) -> Optional[Path]:
    """Resolve Stage-0 artifact root (signals/facts/covering).

    When ``prefer_default`` is True and no env is set, return the conventional
    ``local-runs/real-repo-latest`` path under the plugin root (may not exist).
    """
    raw = _first_env(ENV_REAL_ARTIFACTS, *_LEGACY_ARTIFACTS_VARS)
    root = repo_root()
    if raw is None:
        if prefer_default:
            return root / DEFAULT_ARTIFACTS_REL
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    return p


def live_scan_enabled() -> bool:
    """True when a live Stage-0 re-scan of the real repo is requested."""
    if _truthy(os.environ.get(ENV_LIVE_SCAN)):
        return True
    return any(_truthy(os.environ.get(name)) for name in _LEGACY_LIVE_VARS)


def _normalize_changed_path(raw: str) -> str:
    norm = raw.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def _path_matches_prefix(norm: str, prefix: str) -> bool:
    return norm == prefix.rstrip("/") or norm.startswith(prefix)


def _path_matches_any_prefix(norm: str, prefixes: Iterable[str]) -> bool:
    return any(_path_matches_prefix(norm, prefix) for prefix in prefixes)


def _any_path_matches_prefixes(
    paths: list[str] | tuple[str, ...],
    prefixes: Iterable[str],
) -> bool:
    return any(
        _path_matches_any_prefix(_normalize_changed_path(raw), prefixes)
        for raw in paths
    )


def stage0_paths_require_real_repo(paths: list[str] | tuple[str, ...]) -> bool:
    """True when any changed path should force the pre_pr real_repo lane."""
    return _any_path_matches_prefixes(paths, REAL_REPO_PATH_PREFIXES)


# Generative / pipeline-stage paths that require PIPELINE_ARTIFACTS_DIR under --full.
GENERATIVE_PATH_PREFIXES: tuple[str, ...] = (
    "src/doc_engine/pipeline/",
    "tests/doc_engine/test_pipeline_stages.py",
    "skills/semantic-pipeline-eval/",
)


def generative_paths_require_artifacts(paths: list[str] | tuple[str, ...]) -> bool:
    """True when --full should require PIPELINE_ARTIFACTS_DIR for real artifact bite."""
    return _any_path_matches_prefixes(paths, GENERATIVE_PATH_PREFIXES)
