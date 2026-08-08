"""Atomic store + Magentic ledger + 2+N validation tokens."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from stf.schemas.spec import SpecDocument
from stf.schemas.tasks import LedgerState, TasksDocument


class SpecStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def spec_json_path(self) -> Path:
        return self.root / "SPEC.json"

    def spec_md_path(self) -> Path:
        return self.root / "SPEC.md"

    def write_spec(self, spec: SpecDocument) -> None:
        self._atomic_write(self.spec_json_path(), spec.model_dump_json(indent=2))
        self._atomic_write(self.spec_md_path(), spec.to_markdown())

    def load_spec(self) -> SpecDocument:
        return SpecDocument.model_validate_json(self.spec_json_path().read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)


class TasksStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def tasks_json_path(self) -> Path:
        return self.root / "TASKS.json"

    def write_tasks(self, tasks: TasksDocument) -> None:
        SpecStore._atomic_write(self.tasks_json_path(), tasks.model_dump_json(indent=2))

    def load_tasks(self) -> TasksDocument:
        return TasksDocument.model_validate_json(self.tasks_json_path().read_text(encoding="utf-8"))

    def set_ledger(self, state: LedgerState, *, resume_wave: int | None = None) -> TasksDocument:
        tasks = self.load_tasks()
        tasks.ledger = state
        if resume_wave is not None:
            tasks.resume_wave = resume_wave
        self.write_tasks(tasks)
        return tasks

    def issue_validation_token(self) -> str:
        """Reviewer (human/CI) issues token — Implement cannot self-approve."""
        tasks = self.load_tasks()
        token = secrets.token_urlsafe(16)
        tasks.validation_token = token
        self.write_tasks(tasks)
        return token

    def mark_done(self, *, validation_token: str) -> TasksDocument:
        tasks = self.load_tasks()
        if not tasks.validation_token or tasks.validation_token != validation_token:
            raise PermissionError(
                "2+N SoD: DONE requires Reviewer validation_token (cannot self-approve)"
            )
        tasks.ledger = LedgerState.DONE
        tasks.validation_token = None
        self.write_tasks(tasks)
        return tasks

    def checkpoint(self) -> dict:
        """In-house LangGraph-style checkpoint snapshot."""
        tasks = self.load_tasks()
        return {
            "ledger": tasks.ledger.value,
            "resume_wave": tasks.resume_wave,
            "open_blockers": [b.id for b in tasks.open_blockers()],
            "task_status": {t.id: t.status for t in tasks.tasks},
        }


def write_change_pack(
    root: Path,
    *,
    added: list[str],
    modified: list[str],
    removed: list[str],
) -> Path:
    """OpenSpec-style delta change pack for review remediation."""
    change = Path(root) / "change"
    change.mkdir(parents=True, exist_ok=True)
    text = "# Change delta (OpenSpec-style)\n\n"
    text += "## ADDED Requirements\n\n" + "\n".join(f"- {x}" for x in added) + "\n\n"
    text += "## MODIFIED Requirements\n\n" + "\n".join(f"- {x}" for x in modified) + "\n\n"
    text += "## REMOVED Requirements\n\n" + "\n".join(f"- {x}" for x in removed) + "\n"
    (change / "delta.md").write_text(text, encoding="utf-8")
    (change / "delta.json").write_text(
        json.dumps({"added": added, "modified": modified, "removed": removed}, indent=2),
        encoding="utf-8",
    )
    return change
