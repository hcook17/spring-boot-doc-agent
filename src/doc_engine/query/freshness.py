"""Freshness policies — label currency without a second store."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from doc_engine._compat import StrEnum
from doc_engine.core.walk import compute_file_signature, is_path_inside_root
from doc_engine.query.load import QueryError


class FreshnessLabel(StrEnum):
    LIVE = "live"
    FRESH_INDEXED = "fresh_indexed"
    STALE = "stale"
    UNKNOWN = "unknown"


class UnknownFreshnessWhenNoRepo:
    """Honest default when no repo path is supplied — never invent fresh_indexed."""

    def freshness_for(self, rel_path: str | None = None) -> str:
        _ = rel_path
        return FreshnessLabel.UNKNOWN


# Historical name kept as alias so call sites and docs remain greppable.
AssumeIndexed = UnknownFreshnessWhenNoRepo


class SignatureFreshness:
    """Compare on-disk hashes to spring_signals.file_signatures."""

    def __init__(
        self,
        *,
        repo_root: Path,
        signatures: Mapping[str, str],
        live_paths: set[str] | None = None,
    ) -> None:
        self._root = repo_root.resolve()
        self._sigs = {
            str(path).replace("\\", "/"): str(digest)
            for path, digest in signatures.items()
        }
        self._live = {path.replace("\\", "/") for path in (live_paths or set())}

    def freshness_for(self, rel_path: str | None) -> str:
        if not rel_path:
            return FreshnessLabel.UNKNOWN
        rel = rel_path.replace("\\", "/")
        if rel in self._live:
            return FreshnessLabel.LIVE
        return self._compare_on_disk(rel)

    def _compare_on_disk(self, rel: str) -> str:
        full = (self._root / rel).resolve()
        if not is_path_inside_root(str(full), str(self._root)):
            return FreshnessLabel.UNKNOWN
        if not full.is_file():
            return FreshnessLabel.STALE
        expected = self._sigs.get(rel)
        if expected is None:
            return FreshnessLabel.UNKNOWN
        try:
            actual = compute_file_signature(str(full))
        except OSError:
            return FreshnessLabel.UNKNOWN
        return (
            FreshnessLabel.FRESH_INDEXED
            if actual == expected
            else FreshnessLabel.STALE
        )


class DriftReportFreshness:
    """Mark paths listed as changed/stale in a prior drift_report.json."""

    def __init__(self, *, stale_paths: set[str], inner: SignatureFreshness | AssumeIndexed) -> None:
        self._stale = {path.replace("\\", "/") for path in stale_paths}
        self._inner = inner

    def freshness_for(self, rel_path: str | None) -> str:
        if rel_path and rel_path.replace("\\", "/") in self._stale:
            return FreshnessLabel.STALE
        return self._inner.freshness_for(rel_path)


def label_item_path(policy: object, rel_path: str | None) -> str:
    fn = getattr(policy, "freshness_for", None)
    if not callable(fn):
        raise QueryError("freshness policy missing freshness_for")
    label = fn(rel_path)
    # ``x in SomeEnum`` raises TypeError for non-members on 3.10/3.11 (fixed in 3.12).
    # Validate via constructor so str values and StrEnum members both work.
    try:
        return FreshnessLabel(label)
    except ValueError as exc:
        raise QueryError(f"illegal freshness label: {label!r}") from exc


def _add_list_paths(val: list[Any], out: set[str]) -> None:
    for item in val:
        if isinstance(item, str):
            out.add(item.replace("\\", "/"))
        elif isinstance(item, Mapping) and item.get("file"):
            out.add(str(item["file"]).replace("\\", "/"))


def stale_paths_from_drift_report(report: Mapping) -> set[str]:
    """Best-effort extract of changed file paths from drift_report shape."""
    out: set[str] = set()
    for key in ("changed_files", "stale_files", "drifted_files"):
        val = report.get(key)
        if isinstance(val, list):
            _add_list_paths(val, out)
    files = report.get("files")
    if isinstance(files, Mapping):
        for path, meta in files.items():
            if isinstance(meta, Mapping) and meta.get("status") in ("changed", "stale", "drifted"):
                out.add(str(path).replace("\\", "/"))
    return out
