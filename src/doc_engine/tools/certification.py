"""Certification gate — exit non-zero when certification.json is missing or not certified.

Usage:
    python -m doc_engine.tools.certification [path] [--allow-mock]
"""

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


def _stage_gate_records(data: dict[str, Any]):
    from doc_engine.pipeline.compliance import GateRecord, StageRecord

    stages = [StageRecord.model_validate(row) for row in data.get("stages") or []]
    gates = [GateRecord.model_validate(row) for row in data.get("gates") or []]
    return stages, gates


def _refold_certification(
    data: dict[str, Any],
    *,
    allow_mock: bool,
):
    """Recompute certified/failures from stamped stage/gate facts."""
    from doc_engine.pipeline.compliance import (
        ComplianceProfile,
        build_certification_report,
    )

    profile = ComplianceProfile(data["compliance_profile"])
    stages, gates = _stage_gate_records(data)
    executor = data.get("generative_executor", "none")
    return build_certification_report(
        profile,
        str(data.get("repo_path") or ""),
        str(data.get("out_dir") or ""),
        stages,
        gates,
        generative_executor=executor,
        allow_mock=allow_mock,
    )


def _incoherent_stamp_error(stamped_certified, stamped_failures) -> str | None:
    if stamped_certified is True and stamped_failures:
        return (
            "error: certified=true with non-empty failures "
            f"(incoherent stamp; failures={stamped_failures})"
        )
    return None


def _refold_mismatch_error(stamped_certified, stamped_failures, refold) -> str | None:
    if stamped_certified != refold.certified:
        return (
            f"error: certified bit {stamped_certified!r} ≠ refold "
            f"{refold.certified!r} (refold_failures={refold.failures})"
        )
    if sorted(stamped_failures) != sorted(refold.failures):
        return (
            "error: failures list ≠ refold "
            f"(stamped={stamped_failures}, refold={refold.failures})"
        )
    return None


def _executor_policy_error(executor: str, allow_mock: bool) -> str | None:
    if executor in ("none", "mock") and not allow_mock:
        return (
            f"error: generative_executor={executor!r} is not accepted "
            f"(use --allow-mock for mock/none certificates, or re-run "
            f"`doc-engine pipeline gates` to write generative_executor=live)"
        )
    return None


def _verify_loaded(
    path: Path,
    data: dict[str, Any],
    *,
    allow_mock: bool,
) -> tuple[bool, str]:
    stamped_certified = data.get("certified")
    stamped_failures = list(data.get("failures") or [])
    incoherent = _incoherent_stamp_error(stamped_certified, stamped_failures)
    if incoherent is not None:
        return False, incoherent

    refold = _refold_certification(data, allow_mock=allow_mock)
    mismatch = _refold_mismatch_error(stamped_certified, stamped_failures, refold)
    if mismatch is not None:
        return False, mismatch

    policy = _executor_policy_error(
        data.get("generative_executor", "none"),
        allow_mock,
    )
    if policy is not None:
        return False, policy

    if stamped_certified is True:
        return True, f"OK: certified ({path})"

    profile = data.get("compliance_profile", "unknown")
    return False, (
        f"error: not certified (profile={profile}, failures={stamped_failures})"
    )


def verify_certification(
    path: Path,
    *,
    allow_mock: bool = False,
) -> tuple[bool, str]:
    """Return (ok, message). ok is True only when certified is true.

    Refolds ``build_certification_report`` from stamped stage/gate rows and
    rejects bit≠refold or ``certified ∧ failures ≠ ∅``. By default
    ``generative_executor`` of ``none`` or ``mock`` is rejected so a stale
    deterministic/mock certificate cannot pass as a live adoption gate.
    Pass ``allow_mock=True`` (CLI ``--allow-mock``) for local mock-profile runs.
    """
    try:
        data = load_certification(path)
    except (ValueError, json.JSONDecodeError) as exc:
        return False, f"error: {exc}"
    return _verify_loaded(path, data, allow_mock=allow_mock)


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
