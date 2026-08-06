#!/usr/bin/env python3
"""Principal-engineer local pre-PR / pre-push gate orchestrator.

Usage:
    python3 scripts/ci/pre_pr.py              # same as --auto
    python3 scripts/ci/pre_pr.py --auto
    python3 scripts/ci/pre_pr.py --fast
    python3 scripts/ci/pre_pr.py --full
    python3 scripts/ci/pre_pr.py --actions-outage [--status-url URL]

Cannot intercept `gh pr create`. Wire via `.githooks/pre-push` so push
(the usual step before opening a PR) fails closed. CI remains the
merge-time second line.

`--actions-outage` is CI parity when GitHub Actions is unavailable: full
suites plus CodeQL invariants/compile/runtime and doc-engine certification
verify (--allow-mock). Requires codeql + java + bash on PATH; see
scripts/ci/setup_codeql.sh and scripts/README.md ("Actions outage").

Escape hatch (logged): PRE_PR_SKIP=1 and PRE_PR_SKIP_REASON='…'
(min 8 chars). Skip without a reason exits non-zero. Skip is refused
under --actions-outage (outage mode replaces Actions, not local gates).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from doc_engine.paths import repo_root

REPO_ROOT = repo_root()
RECEIPT_PATH = REPO_ROOT / ".git" / "pre-pr-receipt.json"
BYPASS_LOG = REPO_ROOT / ".git" / "pre-pr-bypass.log"
# schema 2 adds attestation + github_status_note for actions-outage receipts.
RECEIPT_SCHEMA_VERSION = 2

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

SETUP_CODEQL_HINT = (
    "Install the pinned CodeQL CLI (bash scripts/ci/setup_codeql.sh) and "
    "ensure java (17+) and bash are on PATH. See scripts/README.md "
    "('Actions outage')."
)


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
    attestation: Optional[str] = None
    github_status_note: Optional[str] = None


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
    for tool in ("ruff", "ast-grep", "semgrep", "codeql", "java"):
        if tool == "ruff":
            proc = _run([sys.executable, "-m", "ruff", "--version"])
            versions[tool] = (proc.stdout or proc.stderr or "").strip() or f"exit={proc.returncode}"
            continue
        binary = shutil.which(tool)
        if not binary:
            versions[tool] = "missing"
            continue
        if tool == "java":
            proc = _run([binary, "-version"])
        else:
            proc = _run([binary, "--version"])
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


def require_outage_toolchain() -> int:
    """Fail closed if CodeQL / Java / bash are missing (actions-outage mode)."""
    missing: List[str] = []
    if not shutil.which("codeql"):
        missing.append("codeql")
    if not (shutil.which("java") or shutil.which("javac")):
        missing.append("java")
    if not (shutil.which("bash") or shutil.which("bash.exe")):
        missing.append("bash")
    if missing:
        print(
            f"error: --actions-outage requires toolchain on PATH; missing: "
            f"{', '.join(missing)}. {SETUP_CODEQL_HINT}",
            file=sys.stderr,
        )
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


def _py_script(*rel: str, extra_args: Optional[Sequence[str]] = None) -> SuiteFn:
    path = REPO_ROOT.joinpath(*rel)
    extras = list(extra_args or ())

    def run() -> int:
        proc = _run([sys.executable, str(path), *extras])
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


def _doc_engine_cmd(*args: str) -> List[str]:
    if shutil.which("doc-engine") is not None:
        return ["doc-engine", *args]
    return [sys.executable, "-m", "doc_engine.cli", *args]


def _stage0_full() -> int:
    """Portable Stage-0 + artifact validate (CI mirror; --full only)."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = _doc_engine_cmd(
            "pipeline",
            "run",
            "scripts/fixtures/spring_signals",
            "--out-dir",
            tmp,
            "--compliance-profile",
            "deterministic_only",
            "--skip-drift",
        )
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


def _codeql_invariants() -> int:
    return _py_script("spring-signals", "harness", "check-invariants.py")()


def _codeql_compile_and_ql_tests() -> int:
    codeql = shutil.which("codeql")
    if not codeql:
        print(f"error: codeql not on PATH. {SETUP_CODEQL_HINT}", file=sys.stderr)
        return 1
    codeql_root = REPO_ROOT / "spring-signals" / "codeql"
    steps = [
        [codeql, "pack", "install", "packs/java-signals-lib"],
        [codeql, "pack", "install", "packs/spring-signals"],
        [codeql, "pack", "install", "packs/spring-signals/test"],
        [
            codeql,
            "query",
            "compile",
            "--check-only",
            "--threads=0",
            "packs/spring-signals",
        ],
        [
            codeql,
            "test",
            "run",
            "--threads=0",
            "packs/spring-signals/test",
        ],
    ]
    # compile glob: CI uses packs/spring-signals/*.ql — pass the directory;
    # CodeQL accepts a directory of queries. Prefer explicit *.ql via shell-free
    # expansion:
    ql_files = sorted((codeql_root / "packs" / "spring-signals").glob("*.ql"))
    if not ql_files:
        print("error: no packs/spring-signals/*.ql found", file=sys.stderr)
        return 1
    steps[3] = [
        codeql,
        "query",
        "compile",
        "--check-only",
        "--threads=0",
        *[str(p.relative_to(codeql_root)) for p in ql_files],
    ]
    for cmd in steps:
        proc = _run(cmd, cwd=codeql_root)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            return proc.returncode
    return 0


def _find_bash() -> Optional[str]:
    return shutil.which("bash") or shutil.which("bash.exe")


def _codeql_fixture_runtime() -> int:
    bash = _find_bash()
    if not bash:
        print(f"error: bash not on PATH. {SETUP_CODEQL_HINT}", file=sys.stderr)
        return 1
    script = REPO_ROOT / "spring-signals" / "harness" / "create-test-db.sh"
    proc = _run([bash, str(script)], cwd=script.parent)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


def _certify_profile(profile: str, *, allow_mock_run: bool) -> SuiteFn:
    def run() -> int:
        with tempfile.TemporaryDirectory() as tmp:
            cmd = _doc_engine_cmd(
                "pipeline",
                "run",
                "scripts/fixtures/spring_signals",
                "--out-dir",
                tmp,
                "--compliance-profile",
                profile,
            )
            if allow_mock_run:
                cmd.append("--allow-mock")
            proc = _run(cmd)
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            if proc.returncode != 0:
                return proc.returncode
            cert = str(Path(tmp) / "certification.json")
            verify = _run(
                _doc_engine_cmd("certification", "verify", "--allow-mock", cert)
            )
            sys.stdout.write(verify.stdout)
            sys.stderr.write(verify.stderr)
            return verify.returncode

    return run


def _append_full_extras(hard: List[Tuple[str, str, SuiteFn]]) -> None:
    hard.append(("stage0_portable", "hard", _stage0_full))
    hard.append(
        (
            "mutate_advisory",
            "advisory",
            _py_script("scripts", "ratchets", "mutate.py"),
        )
    )
    mutation_driver = REPO_ROOT / "tests" / "spring_signals" / "mutation_driver.py"
    if mutation_driver.is_file():
        hard.append(
            (
                "mutation_driver_advisory",
                "advisory",
                _py_script("tests", "spring_signals", "mutation_driver.py"),
            )
        )

    def claims_metrics() -> int:
        proc = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "ci" / "check_repo_claims.py"),
                "--metrics",
            ]
        )
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return 0  # metrics never fail

    hard.append(("claims_metrics", "advisory", claims_metrics))


def _append_outage_lanes(hard: List[Tuple[str, str, SuiteFn]]) -> None:
    hard.append(("codeql_invariants", "hard", _codeql_invariants))
    hard.append(("codeql_compile_and_ql_tests", "hard", _codeql_compile_and_ql_tests))
    hard.append(("codeql_fixture_runtime", "hard", _codeql_fixture_runtime))
    hard.append(
        ("certify_scan_only", "hard", _certify_profile("scan_only", allow_mock_run=False))
    )
    hard.append(
        ("certify_certified", "hard", _certify_profile("certified", allow_mock_run=True))
    )


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
        hard.append(
            (
                "check_no_client_identifiers",
                "hard",
                _py_script(
                    "scripts",
                    "ci",
                    "check_no_client_identifiers.py",
                    extra_args=["--tracked-tree"],
                ),
            )
        )
        return hard

    # standard (path-risk default), full, and actions_outage share CI hard suites
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
                "check_no_client_identifiers",
                "hard",
                _py_script(
                    "scripts",
                    "ci",
                    "check_no_client_identifiers.py",
                    extra_args=["--tracked-tree"],
                ),
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
    if mode in ("full", "actions_outage"):
        _append_full_extras(hard)
    if mode == "actions_outage":
        _append_outage_lanes(hard)
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
        "attestation": receipt.attestation,
        "github_status_note": receipt.github_status_note,
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
    if getattr(args, "actions_outage", False):
        return "actions_outage"
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
    mode_g.add_argument(
        "--actions-outage",
        action="store_true",
        help=(
            "CI parity while GitHub Actions is down: --full plus CodeQL "
            "invariants/compile/runtime and certification verify (--allow-mock)"
        ),
    )
    parser.add_argument(
        "--status-url",
        default="",
        help="optional GitHub Status / incident URL recorded on the receipt",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    mode = resolve_mode(args)
    status_note = (args.status_url or "").strip() or None

    if mode == "actions_outage":
        if os.environ.get("PRE_PR_SKIP", "").strip() in ("1", "true", "TRUE", "yes"):
            print(
                "error: PRE_PR_SKIP is refused under --actions-outage "
                "(outage mode replaces Actions, not local gates).",
                file=sys.stderr,
            )
            return 2
        if require_outage_toolchain() != 0:
            return 1

    bypass = check_bypass()
    receipt = Receipt(
        schema_version=RECEIPT_SCHEMA_VERSION,
        git_sha=_git_sha(),
        mode=mode,
        tool_versions=_tool_versions(),
        bypass=bypass,
        attestation="actions_outage" if mode == "actions_outage" else None,
        github_status_note=status_note if mode == "actions_outage" else None,
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
