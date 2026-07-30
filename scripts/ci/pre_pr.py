#!/usr/bin/env python3
"""Principal-engineer local pre-PR / pre-push gate orchestrator.

Usage:
    python3 scripts/ci/pre_pr.py              # same as --auto
    python3 scripts/ci/pre_pr.py --auto
    python3 scripts/ci/pre_pr.py --fast
    python3 scripts/ci/pre_pr.py --full

Cannot intercept `gh pr create`. Wire via `.githooks/pre-push` so push
(the usual step before opening a PR) fails closed. CI remains the
merge-time second line.

Escape hatch (logged): PRE_PR_SKIP=1 and PRE_PR_SKIP_REASON='…'
(min 8 chars). Skip without a reason exits non-zero.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from doc_engine.paths import repo_root

REPO_ROOT = repo_root()
RECEIPT_PATH = REPO_ROOT / ".git" / "pre-pr-receipt.json"
BYPASS_LOG = REPO_ROOT / ".git" / "pre-pr-bypass.log"
RECEIPT_SCHEMA_VERSION = 1

CODE_PATH_PREFIXES = (
    "scripts/",
    "src/",
    "tests/",
    ".github/",
    "adapters/",
    "hooks/",
    ".claude/",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    ".ruff.toml",
)

SuiteFn = Callable[[], int]


@dataclass
class SuiteResult:
    name: str
    status: str  # pass | fail | skip | advisory
    duration_ms: int
    kind: str  # hard | advisory
    detail: str = ""


@dataclass
class Receipt:
    schema_version: int
    git_sha: str
    mode: str
    suites: List[SuiteResult] = field(default_factory=list)
    tool_versions: dict = field(default_factory=dict)
    overall: str = "fail"
    bypass: Optional[dict] = None


def _run(cmd: Sequence[str], *, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def _git_sha() -> str:
    proc = _run(["git", "rev-parse", "HEAD"])
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _tool_versions() -> dict:
    versions: dict = {"python": sys.version.split()[0]}
    for tool in ("ruff", "ast-grep", "semgrep"):
        binary = shutil.which(tool) if tool != "ruff" else None
        if tool == "ruff":
            proc = _run([sys.executable, "-m", "ruff", "--version"])
        elif binary:
            proc = _run([binary, "--version"])
        else:
            versions[tool] = "missing"
            continue
        versions[tool] = (proc.stdout or proc.stderr or "").strip() or f"exit={proc.returncode}"
    return versions


def classify_path_risk(paths: Sequence[str]) -> str:
    """Return 'fast' for docs-only changes, else 'standard' (CI hard suites).

    Empty path list (unknown diff) is treated as standard — fail closed on risk.
    Does not select '--full' (Stage-0 + advisory); that is an explicit flag only.
    """
    if not paths:
        return "standard"
    for raw in paths:
        norm = raw.replace("\\", "/")
        while norm.startswith("./"):
            norm = norm[2:]
        if any(norm == p.rstrip("/") or norm.startswith(p) for p in CODE_PATH_PREFIXES):
            return "standard"
    return "fast"


def changed_files_vs_main() -> List[str]:
    """Best-effort list of files changed vs origin/main or main merge-base."""
    for base in ("origin/main", "main"):
        proc = _run(["git", "diff", "--name-only", f"{base}...HEAD"])
        if proc.returncode == 0 and proc.stdout.strip():
            return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        proc = _run(["git", "merge-base", base, "HEAD"])
        if proc.returncode != 0:
            continue
        mb = proc.stdout.strip()
        proc = _run(["git", "diff", "--name-only", f"{mb}...HEAD"])
        if proc.returncode == 0:
            return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    # Uncommitted + untracked as last resort for local-only work.
    staged = _run(["git", "diff", "--name-only", "HEAD"])
    paths = [ln.strip() for ln in staged.stdout.splitlines() if ln.strip()]
    return paths


def check_bypass() -> Optional[dict]:
    """Return bypass dict if skip is authorized; raise SystemExit on bad skip."""
    if os.environ.get("PRE_PR_SKIP", "").strip() not in ("1", "true", "TRUE", "yes"):
        return None
    reason = os.environ.get("PRE_PR_SKIP_REASON", "").strip()
    if len(reason) < 8:
        print(
            "error: PRE_PR_SKIP set but PRE_PR_SKIP_REASON missing or too short "
            "(need >= 8 characters).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sha": _git_sha(),
        "reason": reason,
    }
    print(
        f"WARNING: pre_pr bypassed — reason={reason!r}",
        file=sys.stderr,
    )
    try:
        BYPASS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with BYPASS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError as exc:
        print(f"warning: could not append bypass log: {exc}", file=sys.stderr)
    return entry


def _pin_from_requirements(pkg: str) -> Optional[Tuple[str, str]]:
    req = REPO_ROOT / "requirements.txt"
    text = req.read_text(encoding="utf-8")
    match = re.search(
        rf"^{re.escape(pkg)}~=(\d+)\.(\d+)\.",
        text,
        re.M,
    )
    if not match:
        return None
    return match.group(1), match.group(2)


def tool_doctor() -> int:
    """Fail if ast-grep / semgrep on PATH disagree with requirements.txt pins."""
    errors: List[str] = []
    for pkg, binary_name in (("ast-grep-cli", "ast-grep"), ("semgrep", "semgrep")):
        pin = _pin_from_requirements(pkg)
        if pin is None:
            errors.append(f"requirements.txt does not pin {pkg}")
            continue
        binary = shutil.which(binary_name)
        if not binary:
            errors.append(f"{binary_name} is not on PATH")
            continue
        out = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        got = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
        if not got:
            errors.append(f"could not parse a version from {out!r}")
            continue
        want, have = pin, (got.group(1), got.group(2))
        print(f"doctor: {binary_name} pin={'.'.join(want)}.x  resolved={out}  at {binary}")
        if want != have:
            errors.append(
                f"{binary_name} on PATH is {out}, but requirements.txt pins "
                f"{'.'.join(want)}.x"
            )
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


def _suite(name: str, kind: str, fn: SuiteFn) -> SuiteResult:
    started = time.perf_counter()
    code = fn()
    ms = int((time.perf_counter() - started) * 1000)
    if kind == "advisory":
        status = "advisory" if code == 0 else "advisory"
        # Advisory never fails the gate; still record non-zero as detail.
        return SuiteResult(name, status, ms, kind, detail=f"exit={code}")
    status = "pass" if code == 0 else "fail"
    return SuiteResult(name, status, ms, kind, detail=f"exit={code}")


def _py_script(*rel: str) -> SuiteFn:
    path = REPO_ROOT.joinpath(*rel)

    def run() -> int:
        proc = _run([sys.executable, str(path)])
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode

    return run


def _ruff() -> int:
    proc = _run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "scripts/", "src/doc_engine/"]
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


def _pytest() -> int:
    proc = _run([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"])
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


def _stage0_full() -> int:
    """Portable Stage-0 + artifact validate (CI mirror; --full only)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "doc-engine",
            "pipeline",
            "run",
            "scripts/fixtures/spring_signals",
            "--out-dir",
            tmp,
            "--compliance-profile",
            "deterministic_only",
            "--skip-drift",
        ]
        if shutil.which("doc-engine") is None:
            cmd = [sys.executable, "-m", "doc_engine.cli", *cmd[1:]]
        proc = _run(cmd)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            return proc.returncode
        val = _run(
            [sys.executable, "-m", "doc_engine.tools.validate_artifacts", "--all", tmp]
        )
        sys.stdout.write(val.stdout)
        sys.stderr.write(val.stderr)
        if val.returncode != 0:
            return val.returncode
        if not (Path(tmp) / "certification.json").is_file():
            print("error: certification.json missing after Stage 0", file=sys.stderr)
            return 1
    return 0


def build_suites(mode: str) -> List[Tuple[str, str, SuiteFn]]:
    hard: List[Tuple[str, str, SuiteFn]] = [
        ("check_workflow_yaml", "hard", _py_script("scripts", "ci", "check_workflow_yaml.py")),
        ("tool_doctor", "hard", tool_doctor),
        ("ruff", "hard", _ruff),
    ]
    if mode == "fast":
        hard.append(
            ("check_repo_claims", "hard", _py_script("scripts", "ci", "check_repo_claims.py"))
        )
        return hard

    # standard (path-risk default) and full share CI hard suites
    hard.extend(
        [
            (
                "check_code_quality",
                "hard",
                _py_script("scripts", "ci", "check_code_quality.py"),
            ),
            (
                "check_repo_claims",
                "hard",
                _py_script("scripts", "ci", "check_repo_claims.py"),
            ),
            (
                "rule_coverage",
                "hard",
                _py_script("scripts", "coverage", "rule_coverage.py"),
            ),
            (
                "semgrep_rule_coverage",
                "hard",
                _py_script("scripts", "coverage", "semgrep_rule_coverage.py"),
            ),
            ("pytest", "hard", _pytest),
        ]
    )
    if mode == "full":
        hard.append(("stage0_portable", "hard", _stage0_full))
        hard.append(
            (
                "mutate_advisory",
                "advisory",
                _py_script("scripts", "ratchets", "mutate.py"),
            )
        )

        def claims_metrics() -> int:
            proc = _run(
                [sys.executable, str(REPO_ROOT / "scripts" / "ci" / "check_repo_claims.py"),
                 "--metrics"]
            )
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            return 0  # metrics never fail

        hard.append(("claims_metrics", "advisory", claims_metrics))
    return hard


def write_receipt(receipt: Receipt) -> None:
    payload = {
        "schema_version": receipt.schema_version,
        "git_sha": receipt.git_sha,
        "mode": receipt.mode,
        "suites": [asdict(s) for s in receipt.suites],
        "tool_versions": receipt.tool_versions,
        "overall": receipt.overall,
        "bypass": receipt.bypass,
    }
    try:
        RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"warning: could not write receipt: {exc}", file=sys.stderr)


def print_summary(results: Sequence[SuiteResult]) -> None:
    print("\n=== pre_pr summary ===")
    for r in results:
        print(f"  {r.status:8} {r.kind:8} {r.duration_ms:6}ms  {r.name}  {r.detail}")


def resolve_mode(args: argparse.Namespace) -> str:
    if args.fast:
        return "fast"
    if args.full:
        return "full"
    if args.auto or not (args.fast or args.full):
        risk = classify_path_risk(changed_files_vs_main())
        print(f"pre_pr: --auto path-risk => {risk}")
        return risk
    return "full"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode_g = parser.add_mutually_exclusive_group()
    mode_g.add_argument(
        "--auto",
        action="store_true",
        help="path-risk routing (default when no mode flag)",
    )
    mode_g.add_argument("--fast", action="store_true", help="tier 0 + claims only")
    mode_g.add_argument(
        "--full",
        action="store_true",
        help="all hard suites + Stage-0 + advisory mutate/metrics",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    bypass = check_bypass()
    mode = resolve_mode(args)
    receipt = Receipt(
        schema_version=RECEIPT_SCHEMA_VERSION,
        git_sha=_git_sha(),
        mode=mode,
        tool_versions=_tool_versions(),
        bypass=bypass,
    )
    if bypass is not None:
        receipt.overall = "bypassed"
        write_receipt(receipt)
        print_summary(receipt.suites)
        print(f"receipt: {RECEIPT_PATH}")
        return 0

    results: List[SuiteResult] = []
    failed = False
    for name, kind, fn in build_suites(mode):
        print(f"\n--- {name} ({kind}) ---")
        result = _suite(name, kind, fn)
        results.append(result)
        if kind == "hard" and result.status == "fail":
            failed = True
            break

    receipt.suites = results
    receipt.overall = "fail" if failed else "pass"
    write_receipt(receipt)
    print_summary(results)
    print(f"receipt: {RECEIPT_PATH} overall={receipt.overall}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
