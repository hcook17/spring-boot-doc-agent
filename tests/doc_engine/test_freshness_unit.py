"""Unit coverage for query freshness policies.

Policies return wire-string labels (``live`` / ``fresh_indexed`` / ``stale`` /
``unknown``). ``FreshnessLabel`` is an internal StrEnum used by the
implementation; these tests assert the public string contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_engine.core.walk import compute_file_signature
from doc_engine.query.freshness import (
    DriftReportFreshness,
    SignatureFreshness,
    UnknownFreshnessWhenNoRepo,
    label_item_path,
    stale_paths_from_drift_report,
)
from doc_engine.query.load import QueryError


def test_unknown_policy_and_empty_rel() -> None:
    policy = UnknownFreshnessWhenNoRepo()
    assert policy.freshness_for(None) == "unknown"
    assert policy.freshness_for("") == "unknown"


def test_signature_freshness_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    tracked = repo / "a.java"
    tracked.write_text("class A {}", encoding="utf-8")
    nosig = repo / "nosig.java"
    nosig.write_text("class N {}", encoding="utf-8")
    digest = compute_file_signature(str(tracked))

    policy = SignatureFreshness(
        repo_root=repo,
        signatures={"a.java": digest, "missing.java": "deadbeef"},
        live_paths={"live.java"},
    )
    assert policy.freshness_for(None) == "unknown"
    assert policy.freshness_for("live.java") == "live"
    assert policy.freshness_for("a.java") == "fresh_indexed"
    assert policy.freshness_for("missing.java") == "stale"
    assert policy.freshness_for("nosig.java") == "unknown"

    def boom(_path: str) -> str:
        raise OSError("io")

    monkeypatch.setattr(
        "doc_engine.query.freshness.compute_file_signature",
        boom,
    )
    assert policy.freshness_for("a.java") == "unknown"

    monkeypatch.setattr(
        "doc_engine.query.freshness.is_path_inside_root",
        lambda *_args, **_kwargs: False,
    )
    assert policy.freshness_for("a.java") == "unknown"


def test_drift_overlay_and_label_item_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.java").write_text("x", encoding="utf-8")
    digest = compute_file_signature(str(repo / "a.java"))
    inner = SignatureFreshness(repo_root=repo, signatures={"a.java": digest})
    policy = DriftReportFreshness(stale_paths={"a.java"}, inner=inner)
    assert policy.freshness_for("a.java") == "stale"
    assert label_item_path(policy, "a.java") == "stale"

    missing = object()
    with pytest.raises(QueryError, match="missing freshness_for"):
        label_item_path(missing, "a.java")

    class BadPolicy:
        def freshness_for(self, rel_path: str | None) -> str:
            return "weird"

    bad = BadPolicy()
    with pytest.raises(QueryError, match="illegal freshness"):
        label_item_path(bad, "a.java")


def test_stale_paths_from_drift_report() -> None:
    paths = stale_paths_from_drift_report(
        {
            "changed_files": ["a.java", {"file": "b.java"}],
            "stale_files": ["c.java"],
            "files": {
                "d.java": {"status": "changed"},
                "e.java": {"status": "ok"},
                "f.java": {"status": "drifted"},
            },
        }
    )
    assert paths == {"a.java", "b.java", "c.java", "d.java", "f.java"}
