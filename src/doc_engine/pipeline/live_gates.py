"""Post-generative gate suite for live adapter runs (A+C hybrid).

After Claude/Cursor agents write docs into a run directory, call:

    doc-engine pipeline gates --out-dir <run> --target-repo <repo> --docs-dir <docs>

Deterministic Stage 0 still comes from ``doc-engine pipeline run``.

On every invocation this module **rewrites** ``certification.json`` with
``generative_executor: "live"`` and the gate audit that just ran, so
``doc-engine certification verify`` reflects live mechanical results (not a
stale mock/none certificate).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from doc_engine.pipeline import gates
from doc_engine.pipeline.compliance import (
    CERTIFIED_GATE_IDS,
    ComplianceProfile,
    GateRecord,
    StageRecord,
    build_certification_report,
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
    stages = data.get("stages") or []
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
    """Merge live gate results into certification.json (executor=live)."""
    # Ensure every CERTIFIED profile gate id is represented.
    by_id = {g.id: g for g in gate_records}
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
    report = build_certification_report(
        ComplianceProfile.CERTIFIED,
        repo_path,
        out_dir,
        _load_prior_stages(out_dir),
        gate_records,
        generative_executor="live",
    )
    path = write_certification_json(out_dir, report)
    print(
        f"certification: certified={report.certified} "
        f"generative_executor=live -> {path}"
    )
    return path


def run_live_gates(
    *,
    out_dir: str,
    repo_path: str,
    docs_dir: str,
    strict_citations: bool = False,
    no_write_check: bool = False,
) -> int:
    """Run certified-profile mechanical gates against an existing run directory.

    Always rewrites ``certification.json`` with ``generative_executor: "live"``.
    Returns 0 when every required live gate passes; non-zero otherwise.
    """
    out_dir = os.path.abspath(out_dir)
    repo_path = os.path.abspath(repo_path)
    docs_dir = os.path.abspath(docs_dir)
    py = sys.executable

    failures: list[str] = []
    gate_records: list[GateRecord] = []

    def _check(gate_id: str, label: str, code: int, body: str = "") -> None:
        status = "ok" if code == 0 else "fail"
        detail = ""
        if code != 0:
            failures.append(label)
            print(f"FAIL  {label}", file=sys.stderr)
            if body.strip():
                for line in body.strip().splitlines()[:40]:
                    print(f"  | {line}", file=sys.stderr)
            detail = body.strip().splitlines()[0][:200] if body.strip() else f"exit {code}"
        else:
            print(f"OK    {label}")
        gate_records.append(
            GateRecord(id=gate_id, label=label, status=status, detail=detail)
        )

    code = gates.run_validate_all_artifacts(out_dir)
    _check("validate_artifacts_all", "validate_artifacts --all", code)

    code, body = gates.run_pipeline_validators(out_dir, repo_path)
    _check("pipeline_validators", "pipeline_validators", code, body)

    gate_argv = [
        py,
        "-m",
        MOD_CHECK_PIPELINE,
        docs_dir,
        "--target-repo",
        repo_path,
    ]
    if no_write_check:
        gate_argv.append("--no-write-check")
    code, body = gates.run_subprocess_gate(gate_argv)
    _check("check_pipeline_output", "check_pipeline_output", code, body)

    cc_argv = [
        py,
        "-m",
        MOD_CITATION,
        docs_dir,
        "--target-repo",
        repo_path,
    ]
    if strict_citations:
        cc_argv.append("--strict")
    code, body = gates.run_subprocess_gate(cc_argv)
    _check("citation_coverage", "citation_coverage", code, body)

    secrets_argv = [
        py,
        "-m",
        MOD_SECRETS,
        os.path.join(out_dir, "summaries.json"),
        docs_dir,
    ]
    code, body = gates.run_subprocess_gate(secrets_argv)
    _check("check_no_secrets_leaked", "check_no_secrets_leaked", code, body)

    # Assert we covered every live-required id (all CERTIFIED except pytest skip).
    live_required = CERTIFIED_GATE_IDS - {_LIVE_SKIPPED_GATE}
    recorded = {g.id for g in gate_records}
    missing = sorted(live_required - recorded)
    if missing:
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
        "--strict-citations",
        action="store_true",
        help="make citation_coverage findings fail the gate",
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
        strict_citations=args.strict_citations,
        no_write_check=args.no_write_check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
