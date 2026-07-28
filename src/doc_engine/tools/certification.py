"""Certification gate — exit non-zero when certification.json is missing or not certified."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_certification(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"certification file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def verify_certification(path: Path) -> tuple[bool, str]:
    """Return (ok, message). ok is True only when certified is true."""
    try:
        data = load_certification(path)
    except (ValueError, json.JSONDecodeError) as exc:
        return False, f"error: {exc}"

    if data.get("certified") is True:
        return True, f"OK: certified ({path})"

    failures = data.get("failures") or []
    profile = data.get("compliance_profile", "unknown")
    return False, (
        f"error: not certified (profile={profile}, failures={failures})"
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Exit 0 only when certification.json exists and reports certified: true."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="certification.json",
        help="path to certification.json (default: certification.json)",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    ok, message = verify_certification(path)
    if ok:
        print(message)
        return 0
    print(message, file=sys.stderr)
    return 1 if path.is_file() else 2
