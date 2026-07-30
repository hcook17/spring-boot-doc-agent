#!/usr/bin/env python3
"""Parse every GitHub Actions workflow with yaml.safe_load.

Closes the failure class from PR #57: an unquoted colon in a step `name:`
made Actions reject the whole workflow file before any job ran. Presence of
PyYAML is a requirements-dev pin; this script fails closed if it is missing.

Run with:
    python3 scripts/ci/check_workflow_yaml.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs requirements-dev
    print(
        "error: PyYAML is required (pin in requirements-dev.txt)",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

from doc_engine.paths import repo_root

REPO_ROOT = repo_root()
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def check_workflows(workflows_dir: Path = WORKFLOWS) -> list[str]:
    """Return human-readable errors; empty list means all workflows parse."""
    errors: list[str] = []
    if not workflows_dir.is_dir():
        return [f"missing workflows directory: {workflows_dir}"]
    paths = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    if not paths:
        return [f"no workflow files under {workflows_dir}"]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            docs = list(yaml.safe_load_all(text))
        except yaml.YAMLError as exc:
            try:
                label = str(path.relative_to(REPO_ROOT))
            except ValueError:
                label = path.name
            errors.append(f"{label}: {exc}")
            continue
        if not any(doc is not None for doc in docs):
            try:
                label = str(path.relative_to(REPO_ROOT))
            except ValueError:
                label = path.name
            errors.append(f"{label}: empty document")
    return errors


def main() -> int:
    errors = check_workflows()
    if errors:
        print("workflow YAML check failed:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print(f"OK: {len(list(WORKFLOWS.glob('*.yml')) + list(WORKFLOWS.glob('*.yaml')))} workflow(s) parse")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
