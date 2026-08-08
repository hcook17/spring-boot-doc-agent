#!/usr/bin/env python3
"""Regen Stage-0 artifacts for the canonical real-repo lane.

Usage:
    DOC_ENGINE_REAL_REPO=/path/to/local-spring-tree \\
        python scripts/ci/regen_real_repo_artifacts.py

    # Optional override for output root (default: local-runs/real-repo-latest)
    DOC_ENGINE_REAL_ARTIFACTS_DIR=local-runs/real-repo-latest \\
        python scripts/ci/regen_real_repo_artifacts.py

Writes spring_signals.json, facts.jsonl (via the scan tool), and
covering_proof.json under a gitignored directory. Never commit the output.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from doc_engine.paths import repo_root
from doc_engine.real_fixture import (
    DEFAULT_ARTIFACTS_REL,
    ENV_REAL_ARTIFACTS,
    ENV_REAL_REPO,
    real_artifacts_dir,
    require_real_repo,
)

REPO_ROOT = repo_root()

_ALLOWED_SCANNERS = frozenset({"filesystem", "ast-grep", "codeql"})


def _validated_scanners_arg(raw: str) -> str:
    """Reject scanner tokens outside the Stage-0 allowlist before OS argv handoff."""
    tokens = [t.strip() for t in str(raw).split(",") if t.strip()]
    if not tokens:
        raise ValueError("scanners list is empty")
    bad = sorted({token for token in tokens if token not in _ALLOWED_SCANNERS})
    if bad:
        raise ValueError(
            f"unknown scanner(s) {bad}; allowed: {', '.join(sorted(_ALLOWED_SCANNERS))}"
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ",".join(ordered)


def _validated_repo_path(repo: Path) -> Path:
    resolved = repo.resolve()
    if not resolved.is_dir():
        raise ValueError(f"repo is not a directory: {resolved}")
    return resolved


def _validated_out_path(out_root: Path) -> Path:
    resolved = out_root if out_root.is_absolute() else (REPO_ROOT / out_root)
    resolved = resolved.resolve()
    # Contain under repo root or absolute path the operator already chose.
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _scan_command(repo: Path, signals_out: Path, scanners: str) -> list[str]:
    # Fixed module argv — only allowlisted scanners and resolved paths.
    return [
        sys.executable,
        "-m",
        "doc_engine.tools.spring_signal_scan",
        str(repo),
        "--out",
        str(signals_out),
        "--scanners",
        scanners,
    ]


def _run_spring_signal_scan(repo: Path, signals_out: Path, scanners: str) -> int:
    cmd = _scan_command(repo, signals_out, scanners)
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    print(f"regen: scanning {repo} -> {signals_out.parent}")
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, check=False, shell=False)
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Artifact root (default: ${ENV_REAL_ARTIFACTS} or {DEFAULT_ARTIFACTS_REL})",
    )
    parser.add_argument(
        "--scanners",
        default="filesystem,ast-grep",
        help="Scanner list passed to spring_signal_scan (default: filesystem,ast-grep)",
    )
    args = parser.parse_args(argv)

    try:
        scanners = _validated_scanners_arg(args.scanners)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        repo = _validated_repo_path(require_real_repo())
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_root = args.out
    if out_root is None:
        out_root = real_artifacts_dir(prefer_default=True)
    assert out_root is not None
    out_root = _validated_out_path(out_root)
    signals_out = out_root / "spring_signals.json"

    rc = _run_spring_signal_scan(repo, signals_out, scanners)
    if rc != 0:
        print("error: spring_signal_scan failed", file=sys.stderr)
        return rc

    facts = out_root / "facts.jsonl"
    covering = out_root / "covering_proof.json"
    missing = [p.name for p in (signals_out, facts, covering) if not p.is_file()]
    if missing:
        print(f"error: scan finished but missing artifacts: {missing}", file=sys.stderr)
        return 1
    print(f"regen: ok — set {ENV_REAL_ARTIFACTS}={out_root}")
    print(f"regen: also set {ENV_REAL_REPO}={repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
