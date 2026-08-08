"""GitHub Issues handoff (dry-run by default)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from stf.schemas.tasks import TasksDocument


def issues_from_tasks(tasks: TasksDocument) -> list[dict[str, Any]]:
    issues = []
    for t in tasks.tasks:
        if t.id == "T0":
            continue
        body = (
            f"**Goal:** {t.goal}\n\n"
            f"**Acceptance:** {t.acceptance}\n\n"
            f"**Verify:** `{t.verify}`\n\n"
            f"**Source SPEC:** `{tasks.source_spec}`\n"
            f"**Target:** `{tasks.target}`\n"
        )
        issues.append(
            {
                "title": f"[STF {tasks.target}] {t.id} — {t.title}",
                "body": body,
                "labels": ["stf", tasks.target],
            }
        )
    return issues


def _gh_issue_cmd(issue: dict[str, Any], repo: str | None) -> list[str]:
    cmd = ["gh", "issue", "create", "--title", issue["title"], "--body", issue["body"]]
    if repo:
        cmd.extend(["--repo", repo])
    for lab in issue.get("labels") or []:
        cmd.extend(["--label", lab])
    return cmd


def _create_gh_issue(issue: dict[str, Any], repo: str | None) -> dict[str, Any]:
    proc = subprocess.run(
        _gh_issue_cmd(issue, repo), capture_output=True, text=True, check=False
    )
    return {
        "title": issue["title"],
        "rc": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def handoff_gh(
    tasks: TasksDocument,
    *,
    dry_run: bool = True,
    repo: str | None = None,
) -> list[dict[str, Any]]:
    issues = issues_from_tasks(tasks)
    if dry_run:
        return [{"dry_run": True, **i} for i in issues]
    return [_create_gh_issue(issue, repo) for issue in issues]


def write_handoff_checklist(path: Path, tasks: TasksDocument) -> Path:
    issues = issues_from_tasks(tasks)
    lines = ["# STF handoff checklist", "", f"Target: `{tasks.target}`", ""]
    for i in issues:
        lines.append(f"- [ ] {i['title']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
