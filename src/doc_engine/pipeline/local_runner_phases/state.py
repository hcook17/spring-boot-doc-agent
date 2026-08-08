"""Mutable run-state shared across local_runner phase modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from doc_engine.pipeline.compliance import ComplianceProfile
from doc_engine.pipeline.context import PipelineContext, StageSpec
from doc_engine.pipeline.executor import MockStageExecutor
from doc_engine.pipeline.local_runner_phases.support import Log, Runner


@dataclass
class LocalRunState:
    """Paths, profile, and runners for one local pipeline invocation."""

    args: Any
    repo_path: str
    out_dir: str
    docs_dir: str
    today: str
    profile: ComplianceProfile
    allow_mock: bool
    skip_signal_scan: bool
    strict_citations_effective: bool
    log: Log
    runner: Runner
    py: str
    manifest: str
    signals_path: str
    preflight_path: str
    until_stage: Optional[str] = None
    pipeline_ctx: Optional[PipelineContext] = None
    mock_executor: Optional[MockStageExecutor] = None
    selected_specs: List[StageSpec] = field(default_factory=list)
    deterministic_specs: List[StageSpec] = field(default_factory=list)
    generative_specs: List[StageSpec] = field(default_factory=list)
