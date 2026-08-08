"""Post-generative gate suite for live adapter runs (A+C hybrid).

After Claude/Cursor agents write docs into a run directory, call:

    doc-engine pipeline gates --out-dir <run> --target-repo <repo> --docs-dir <docs>

Deterministic Stage 0 still comes from ``doc-engine pipeline run``.

On every invocation this module **rewrites** ``certification.json`` as a
derived view: ``generative_executor: "live"``, gate audit from this run, and
stage facts via ``stages_for_live_certification`` (deterministic prior rows +
``generative_external`` — not a LWW merge of mock generative history).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from doc_engine.config.loader import load_repo_config
from doc_engine.pipeline import gates
from doc_engine.pipeline.compliance import (
    CERTIFIED_GATE_IDS,
    ComplianceProfile,
    GateRecord,
    StageRecord,
    build_certification_report,
    citations_are_strict,
    resolve_compliance_profile,
    stages_for_live_certification,
    write_certification_json,
)

MOD_CHECK_PIPELINE = "doc_engine.tools.check_pipeline_output"
MOD_CITATION = "doc_engine.tools.citation_coverage"
MOD_SECRETS = "doc_engine.tools.check_no_secrets_leaked"

# Live path does not re-run the pytest suite; record it as optional skip so
# profile_gate_ids still list it without vacuous missing failures.
_LIVE_SKIPPED_GATE = "test_pipeline_stages"


def _load_prior_stages(out_dir: str) -> list[StageRecord]:
    path = Path(out_dir) / "certification.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return _stage_records_from_raw(data.get("stages") or [])


def _stage_records_from_raw(stages: list) -> list[StageRecord]:
    """Validate prior certification stage rows; skip malformed entries."""
    records: list[StageRecord] = []
    for raw in stages:
        try:
            records.append(StageRecord.model_validate(raw))
        except Exception:  # noqa: BLE001 — skip malformed prior rows
            continue
    return records


def _write_live_certification(
    *,
    out_dir: str,
    repo_path: str,
    gate_records: list[GateRecord],
) -> Path:
    """Derive live certification.json (executor=live) from gate facts + prior stages."""
    by_id = {gate.id: gate for gate in gate_records}
    if _LIVE_SKIPPED_GATE not in by_id:
        gate_records.append(
            GateRecord(
                id=_LIVE_SKIPPED_GATE,
                label="pytest test_pipeline_stages (not run on live gates path)",
                status="skipped",
                required=False,
                detail="live gates path does not invoke pytest",
            )
        )
    stages = stages_for_live_certification(_load_prior_stages(out_dir))
    report = build_certification_report(
        ComplianceProfile.CERTIFIED,
        repo_path,
        out_dir,
        stages,
        gate_records,
        generative_executor="live",
    )
    path = write_certification_json(out_dir, report)
    print(
        f"certification: certified={report.certified} "
        f"generative_executor=live -> {path}"
    )
    return path


def _record_gate_result(
    gate_records: list[GateRecord],
    failures: list[str],
    gate_id: str,
    label: str,
    code: int,
    body: str = "",
) -> None:
    """Append one GateRecord and print OK/FAIL with optional body preview."""
    if code == 0:
        print(f"OK    {label}")
        gate_records.append(
            GateRecord(id=gate_id, label=label, status="ok", detail="")
        )
        return
    failures.append(label)
    print(f"FAIL  {label}", file=sys.stderr)
    stripped = body.strip()
    if stripped:
        for line in stripped.splitlines()[:40]:
            print(f"  | {line}", file=sys.stderr)
    detail = stripped.splitlines()[0][:200] if stripped else f"exit {code}"
    gate_records.append(
        GateRecord(id=gate_id, label=label, status="fail", detail=detail)
    )


def _resolve_live_profile(
    repo_path: str,
    compliance_profile: str | None,
    strict_citations: bool,
) -> tuple[ComplianceProfile, bool]:
    """Load repo config and resolve profile + effective citation strictness."""
    from argparse import Namespace

    from doc_engine.config.repo_trust import sanitize_repo_settings, trust_from_flag

    repo_config = load_repo_config(repo_path)
    # Live gates inherit the same untrusted default; operators who already
    # chose a weaker profile via --compliance-profile keep that explicit choice.
    repo_config = sanitize_repo_settings(repo_config, trust_from_flag(False))
    profile = resolve_compliance_profile(
        repo_config,
        Namespace(
            compliance_profile=compliance_profile,
            deterministic_only=False,
        ),
    )
    strict = citations_are_strict(profile, force_strict=strict_citations)
    return profile, strict


def _run_certified_mechanical_gates(
    *,
    out_dir: str,
    repo_path: str,
    docs_dir: str,
    strict_citations_effective: bool,
    no_write_check: bool,
    gate_records: list[GateRecord],
    failures: list[str],
) -> None:
    """Execute the certified-profile mechanical gates and record results."""
    py = sys.executable

    def check(gate_id: str, label: str, code: int, body: str = "") -> None:
        _record_gate_result(gate_records, failures, gate_id, label, code, body)

    code = gates.run_validate_all_artifacts(out_dir)
    check("validate_artifacts_all", "validate_artifacts --all", code)

    code, body = gates.run_pipeline_validators(out_dir, repo_path)
    check("pipeline_validators", "pipeline_validators", code, body)

    gate_argv = [py, "-m", MOD_CHECK_PIPELINE, docs_dir, "--target-repo", repo_path]
    if no_write_check:
        gate_argv.append("--no-write-check")
    code, body = gates.run_subprocess_gate(gate_argv)
    check("check_pipeline_output", "check_pipeline_output", code, body)

    cc_argv = [py, "-m", MOD_CITATION, docs_dir, "--target-repo", repo_path]
    if strict_citations_effective:
        cc_argv.append("--strict")
    code, body = gates.run_subprocess_gate(cc_argv)
    check("citation_coverage", "citation_coverage", code, body)

    secrets_argv = [
        py,
        "-m",
        MOD_SECRETS,
        os.path.join(out_dir, "summaries.json"),
        docs_dir,
    ]
    code, body = gates.run_subprocess_gate(secrets_argv)
    check("check_no_secrets_leaked", "check_no_secrets_leaked", code, body)


def _fail_missing_live_gates(
    gate_records: list[GateRecord],
    failures: list[str],
) -> None:
    """Record FAIL rows for any certified gate id this path did not execute."""
    live_required = CERTIFIED_GATE_IDS - {_LIVE_SKIPPED_GATE}
    recorded = {gate.id for gate in gate_records}
    missing = sorted(live_required - recorded)
    if not missing:
        return
    print(
        f"error: live gates did not record required gate id(s): {missing}",
        file=sys.stderr,
    )
    for gate_id in missing:
        gate_records.append(
            GateRecord(
                id=gate_id,
                label=gate_id,
                status="fail",
                detail="not executed",
            )
        )
        failures.append(gate_id)


def run_live_gates(
    *,
    out_dir: str,
    repo_path: str,
    docs_dir: str,
    compliance_profile: str | None = None,
    strict_citations: bool = False,
    no_write_check: bool = False,
) -> int:
    """Run certified-profile mechanical gates against an existing run directory.

    Always rewrites ``certification.json`` with ``generative_executor: "live"``.
    Citation strictness follows ``citations_are_strict`` (certified ⇒ strict),
    matching ``local_runner``.
    Returns 0 when every required live gate passes; non-zero otherwise.
    """
    out_dir = os.path.abspath(out_dir)
    repo_path = os.path.abspath(repo_path)
    docs_dir = os.path.abspath(docs_dir)

    _profile, strict_citations_effective = _resolve_live_profile(
        repo_path, compliance_profile, strict_citations
    )
    failures: list[str] = []
    gate_records: list[GateRecord] = []

    _run_certified_mechanical_gates(
        out_dir=out_dir,
        repo_path=repo_path,
        docs_dir=docs_dir,
        strict_citations_effective=strict_citations_effective,
        no_write_check=no_write_check,
        gate_records=gate_records,
        failures=failures,
    )
    _fail_missing_live_gates(gate_records, failures)
    _write_live_certification(
        out_dir=out_dir,
        repo_path=repo_path,
        gate_records=gate_records,
    )

    if failures:
        print(f"error: {len(failures)} gate(s) failed", file=sys.stderr)
        return 1
    print("All live gates passed.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Run mechanical gates on an existing pipeline run directory "
                    "(after live generative stages).",
    )
    ap.add_argument("--out-dir", required=True, help="run artifact directory")
    ap.add_argument("--target-repo", required=True, help="target Spring Boot repo")
    ap.add_argument(
        "--docs-dir",
        default=None,
        help="docs directory (default: <out-dir>/docs)",
    )
    ap.add_argument(
        "--compliance-profile",
        choices=[p.value for p in ComplianceProfile],
        default=None,
        help="compliance profile (default: certified, or .doc-engine.yml on "
             "target-repo). certified enables --strict on citation_coverage.",
    )
    ap.add_argument(
        "--strict-citations",
        action="store_true",
        help="force --strict on citation_coverage even when profile is not certified",
    )
    ap.add_argument(
        "--no-write-check",
        action="store_true",
        help="pass --no-write-check to check_pipeline_output "
             "(docs written outside the target repo)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    docs_dir = args.docs_dir or os.path.join(args.out_dir, "docs")
    return run_live_gates(
        out_dir=args.out_dir,
        repo_path=args.target_repo,
        docs_dir=docs_dir,
        compliance_profile=args.compliance_profile,
        strict_citations=args.strict_citations,
        no_write_check=args.no_write_check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
