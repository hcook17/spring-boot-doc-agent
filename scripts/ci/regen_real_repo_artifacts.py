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
        repo = require_real_repo()
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_root = args.out
    if out_root is None:
        out_root = real_artifacts_dir(prefer_default=True)
    assert out_root is not None
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root
    out_root.mkdir(parents=True, exist_ok=True)
    signals_out = out_root / "spring_signals.json"

    cmd = [
        sys.executable,
        "-m",
        "doc_engine.tools.spring_signal_scan",
        str(repo),
        "--out",
        str(signals_out),
        "--scanners",
        args.scanners,
    ]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    print(f"regen: scanning {repo} -> {out_root}")
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, check=False)
    if proc.returncode != 0:
        print("error: spring_signal_scan failed", file=sys.stderr)
        return proc.returncode

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
