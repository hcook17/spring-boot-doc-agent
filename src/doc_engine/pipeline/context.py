"""Pipeline orchestration — stage graph, context, and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class StageKind(str, Enum):
    DETERMINISTIC = "deterministic"
    GENERATIVE = "generative"


# run_manifest.py stage names (SKILL.md concurrency contract).
STAGE_SIGNAL_SCAN = "signal_scan"
STAGE_PARTITION = "partition"
STAGE_FILE_SUMMARIZE = "file_summarize"
STAGE_ARCHITECT = "architect"
STAGE_GAP_INTERVIEW = "gap_analysis_interview"
STAGE_DOC_WRITER = "doc_writer"

MANIFEST_STAGES = frozenset({
    STAGE_SIGNAL_SCAN,
    STAGE_PARTITION,
    STAGE_FILE_SUMMARIZE,
    STAGE_ARCHITECT,
    STAGE_GAP_INTERVIEW,
    STAGE_DOC_WRITER,
})


@dataclass
class StageSpec:
    name: str
    kind: StageKind
    manifest_stage: str | None = None
    """Manifest stage name for start-stage/end-stage bookkeeping."""
    fanout: int | None = None
    outputs: tuple[str, ...] = ()
    """Artifact filenames produced (for boundary validation)."""
    argv_builder: Callable[[PipelineContext], list[str]] | None = None
    """Build subprocess argv for deterministic stages."""
    generative_key: str | None = None
    """Key passed to StageExecutor for generative stages."""
    agent_names: tuple[str, ...] = ()
    """Claude/Cursor agent ids for live generative adapters (empty for deterministic)."""
    requires_human_interview: bool = False
    """True when the stage includes live Q&A in the orchestrating thread."""
    input_artifacts: tuple[str, ...] = ()
    """Artifact filenames this stage consumes (documentation / adapter wiring)."""


@dataclass
class StageResult:
    success: bool
    detail: str = ""
    error: str | None = None


@dataclass
class PipelineContext:
    repo_path: Path
    out_dir: Path
    manifest_path: Path
    docs_dir: Path
    python: str
    today: str
    respect_gitignore: bool = False
    max_tokens: int = 120000
    # Populated as the run progresses (write-once between stages).
    signals_path: Path | None = None
    groups_path: Path | None = None
    edges_path: Path | None = None
    preflight_path: Path | None = None
    signals: dict[str, Any] | None = None
    groups: dict[str, Any] | None = None
    edges: dict[str, Any] | None = None
    pool: dict[str, list] | None = None
    todos: list[dict[str, Any]] = field(default_factory=list)
    existing_readme: str | None = None
    log: Callable[[str], None] = print

    def artifact_path(self, filename: str) -> Path:
        return self.out_dir / filename
