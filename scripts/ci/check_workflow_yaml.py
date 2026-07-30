#!/usr/bin/env python3
"""Parse every GitHub Actions workflow with yaml.safe_load.

Closes the failure class from PR #57: an unquoted colon in a step `name:`
made Actions reject the whole workflow file before any job ran. Presence of
PyYAML is a requirements-dev pin; this script fails closed if it is missing.

Also applies a zero-dep actionsec-inspired severity ramp: critical/high
findings (script injection from untrusted contexts, write-all, missing
permissions, pull_request_target+checkout) hard-fail. Medium unpinned
`actions/*@vN` tags print as advisory only until a SHA-pin migration.

Run with:
    python3 scripts/ci/check_workflow_yaml.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

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

# Untrusted event payloads in run: (not workflow_dispatch inputs).
_UNTRUSTED_EXPR = re.compile(
    r"\$\{\{\s*github\.event\.(?:pull_request|issue|comment|review|"
    r"discussion|head_commit)\.(?:title|body|head_ref|ref|message|"
    r"user\.login)",
    re.I,
)
_USES_LINE = re.compile(
    r"^\s*-?\s*uses:\s*(?P<action>[^\s#]+)",
    re.M,
)
_SHA_REF = re.compile(r"@[0-9a-f]{40}(\b|$)", re.I)
_DIGEST_REF = re.compile(r"@sha256:[0-9a-f]{64}$", re.I)


@dataclass(frozen=True)
class SecurityFinding:
    path: str
    severity: str  # critical | high | medium | low
    rule: str
    message: str
    line: int = 0


def _label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def check_workflows(workflows_dir: Path = WORKFLOWS) -> list[str]:
    """Return human-readable parse errors; empty list means all workflows parse."""
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
            errors.append(f"{_label(path)}: {exc}")
            continue
        if not any(doc is not None for doc in docs):
            errors.append(f"{_label(path)}: empty document")
    return errors


def _line_no(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def scan_workflow_security(path: Path, text: str) -> List[SecurityFinding]:
    """Line-oriented security pass; does not require a YAML tree for all rules."""
    findings: List[SecurityFinding] = []
    label = _label(path)
    lines = text.splitlines()

    # Missing top-level permissions: (low in actionsec; we treat as high for gate).
    if not re.search(r"(?m)^permissions\s*:", text):
        findings.append(
            SecurityFinding(
                label,
                "high",
                "missing-permissions",
                "no top-level permissions: block — workflow inherits default token scope",
            )
        )

    if re.search(r"(?m)^\s*permissions\s*:\s*write-all\s*$", text):
        findings.append(
            SecurityFinding(
                label,
                "high",
                "broad-permissions",
                "permissions: write-all grants full read/write — scope it down",
            )
        )

    # pull_request_target + checkout of PR head (critical).
    if re.search(r"(?m)^\s*pull_request_target\s*:", text) or re.search(
        r"(?m)^\s*-\s*pull_request_target\b", text
    ):
        if re.search(r"(?m)^\s*uses:\s*actions/checkout@", text):
            findings.append(
                SecurityFinding(
                    label,
                    "critical",
                    "pull-request-target-checkout",
                    "pull_request_target with actions/checkout — untrusted code may run "
                    "with a privileged token",
                )
            )

    for match in _UNTRUSTED_EXPR.finditer(text):
        findings.append(
            SecurityFinding(
                label,
                "critical",
                "script-injection",
                "untrusted github.event.* interpolated into workflow text — pass via env:",
                line=_line_no(text, match.start()),
            )
        )

    # Also catch classic ${{ github.event.pull_request.title }} inside run blocks
    # when the regex above is too narrow: scan run: multiline regions lightly.
    for i, line in enumerate(lines, start=1):
        if "${{" in line and "github.event." in line and "inputs." not in line:
            if _UNTRUSTED_EXPR.search(line):
                continue  # already recorded
            if re.search(
                r"github\.event\.(?:pull_request|issue|comment|review|discussion|"
                r"head_commit)\.",
                line,
            ):
                findings.append(
                    SecurityFinding(
                        label,
                        "critical",
                        "script-injection",
                        f"untrusted expression in workflow line: {line.strip()[:80]}",
                        line=i,
                    )
                )

    for match in _USES_LINE.finditer(text):
        action = match.group("action").strip().strip("'\"")
        if action.startswith("./") or action.startswith(".\\"):
            continue
        if "@" not in action:
            findings.append(
                SecurityFinding(
                    label,
                    "high",
                    "unpinned-action",
                    f"{action} has no ref — pin to a full commit SHA",
                    line=_line_no(text, match.start()),
                )
            )
            continue
        ref = action.split("@", 1)[1]
        if _SHA_REF.search("@" + ref) or _DIGEST_REF.search("@" + ref):
            continue
        owner_action = action.split("@", 1)[0]
        is_github_owned = owner_action.startswith("actions/") or owner_action.startswith(
            "github/"
        )
        severity = "medium" if is_github_owned else "high"
        findings.append(
            SecurityFinding(
                label,
                severity,
                "unpinned-action",
                f"{action} uses a mutable tag/branch — pin to a full commit SHA",
                line=_line_no(text, match.start()),
            )
        )

    return findings


def collect_security_findings(
    workflows_dir: Path = WORKFLOWS,
) -> Tuple[List[SecurityFinding], List[SecurityFinding]]:
    """Return (hard_fail_findings, advisory_findings)."""
    hard: List[SecurityFinding] = []
    advisory: List[SecurityFinding] = []
    if not workflows_dir.is_dir():
        return hard, advisory
    paths = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for finding in scan_workflow_security(path, text):
            if finding.severity in ("critical", "high"):
                hard.append(finding)
            else:
                advisory.append(finding)
    return hard, advisory


def format_finding(finding: SecurityFinding) -> str:
    loc = f":{finding.line}" if finding.line else ""
    return (
        f"{finding.path}{loc} [{finding.severity}/{finding.rule}] {finding.message}"
    )


def main() -> int:
    errors = check_workflows()
    if errors:
        print("workflow YAML check failed:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    hard, advisory = collect_security_findings()
    for finding in advisory:
        print(f"advisory: {format_finding(finding)}")
    if hard:
        print("workflow security check failed (critical/high):", file=sys.stderr)
        for finding in hard:
            print(f"  {format_finding(finding)}", file=sys.stderr)
        return 1

    n = len(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml")))
    print(
        f"OK: {n} workflow(s) parse; "
        f"{len(advisory)} medium/low advisory finding(s); 0 critical/high"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
