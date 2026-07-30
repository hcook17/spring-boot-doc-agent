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
    # Slice 2 — fail closed on shape before trusting certified: true.
    from pydantic import ValidationError

    from doc_engine.pipeline.compliance import CertificationReport

    try:
        CertificationReport.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"{path} failed certification schema: {exc}") from exc
    return data


def verify_certification(
    path: Path,
    *,
    allow_mock: bool = False,
) -> tuple[bool, str]:
    """Return (ok, message). ok is True only when certified is true.

    By default ``generative_executor`` of ``none`` or ``mock`` is rejected so a
    stale deterministic/mock certificate cannot pass as a live adoption gate.
    Pass ``allow_mock=True`` (CLI ``--allow-mock``) for local mock-profile runs.
    """
    try:
        data = load_certification(path)
    except (ValueError, json.JSONDecodeError) as exc:
        return False, f"error: {exc}"

    executor = data.get("generative_executor", "none")
    if executor in ("none", "mock") and not allow_mock:
        return False, (
            f"error: generative_executor={executor!r} is not accepted "
            f"(use --allow-mock for mock/none certificates, or re-run "
            f"`doc-engine pipeline gates` to write generative_executor=live)"
        )

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
        description=(
            "Exit 0 only when certification.json exists, reports certified: true, "
            "and generative_executor is live (or --allow-mock)."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="certification.json",
        help="path to certification.json (default: certification.json)",
    )
    parser.add_argument(
        "--allow-mock",
        action="store_true",
        help="accept generative_executor none/mock (local mock-profile runs)",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    ok, message = verify_certification(path, allow_mock=args.allow_mock)
    if ok:
        print(message)
        return 0
    print(message, file=sys.stderr)
    return 1 if path.is_file() else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
