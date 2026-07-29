"""Post-generative gate suite for live adapter runs (A+C hybrid).

After Claude/Cursor agents write docs into a run directory, call:

    doc-engine pipeline gates --out-dir <run> --target-repo <repo> --docs-dir <docs>

Deterministic Stage 0 still comes from ``doc-engine pipeline run``.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence

from doc_engine.paths import scripts_dir
from doc_engine.pipeline import gates


def run_live_gates(
    *,
    out_dir: str,
    repo_path: str,
    docs_dir: str,
    strict_citations: bool = False,
    no_write_check: bool = False,
) -> int:
    """Run certified-profile mechanical gates against an existing run directory.

    Returns 0 when every required gate passes; non-zero otherwise.
    """
    out_dir = os.path.abspath(out_dir)
    repo_path = os.path.abspath(repo_path)
    docs_dir = os.path.abspath(docs_dir)
    py = sys.executable
    script = scripts_dir()

    failures: list[str] = []

    def _check(label: str, code: int, body: str = "") -> None:
        if code != 0:
            failures.append(label)
            print(f"FAIL  {label}", file=sys.stderr)
            if body.strip():
                for line in body.strip().splitlines()[:40]:
                    print(f"  | {line}", file=sys.stderr)
        else:
            print(f"OK    {label}")

    code = gates.run_validate_all_artifacts(out_dir)
    _check("validate_artifacts --all", code)

    code, body = gates.run_pipeline_validators(out_dir, repo_path)
    _check("pipeline_validators", code, body)

    gate_argv = [
        py,
        str(script / "check_pipeline_output.py"),
        docs_dir,
        "--target-repo",
        repo_path,
    ]
    if no_write_check:
        gate_argv.append("--no-write-check")
    code, body = gates.run_subprocess_gate(gate_argv)
    _check("check_pipeline_output", code, body)

    cc_argv = [
        py,
        str(script / "citation_coverage.py"),
        docs_dir,
        "--target-repo",
        repo_path,
    ]
    if strict_citations:
        cc_argv.append("--strict")
    code, body = gates.run_subprocess_gate(cc_argv)
    _check("citation_coverage", code, body)

    secrets_argv = [
        py,
        str(script / "check_no_secrets_leaked.py"),
        os.path.join(out_dir, "summaries.json"),
        docs_dir,
    ]
    code, body = gates.run_subprocess_gate(secrets_argv)
    _check("check_no_secrets_leaked", code, body)

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
