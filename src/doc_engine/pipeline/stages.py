"""Ordered stage graph for the document-spring-repo pipeline."""

from __future__ import annotations

from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES
from doc_engine.pipeline.context import (
    STAGE_ARCHITECT,
    STAGE_DOC_WRITER,
    STAGE_FILE_SUMMARIZE,
    STAGE_GAP_INTERVIEW,
    STAGE_PARTITION,
    STAGE_SIGNAL_SCAN,
    PipelineContext,
    StageKind,
    StageSpec,
)


def _scan_flags(ctx: PipelineContext) -> list[str]:
    return ["--respect-gitignore"] if ctx.respect_gitignore else []


def build_stage_specs() -> list[StageSpec]:
    """Executable stage graph — maps 1:1 to SKILL.md stage names."""
    return [
        StageSpec(
            name="init_manifest",
            kind=StageKind.DETERMINISTIC,
            argv_builder=lambda ctx: [
                ctx.python,
                str(ctx.script("run_manifest.py")),
                "init",
                str(ctx.repo_path),
                "--out",
                str(ctx.manifest_path),
            ],
        ),
        StageSpec(
            name="signal_scan",
            kind=StageKind.DETERMINISTIC,
            manifest_stage=STAGE_SIGNAL_SCAN,
            outputs=(ARTIFACT_FILENAMES["spring_signals"],),
            argv_builder=lambda ctx: [
                ctx.python,
                str(ctx.script("spring_signal_scan.py")),
                str(ctx.repo_path),
                "--out",
                str(ctx.signals_path or ctx.artifact_path("spring_signals.json")),
            ] + _scan_flags(ctx),
        ),
        StageSpec(
            name="partition",
            kind=StageKind.DETERMINISTIC,
            manifest_stage=STAGE_PARTITION,
            outputs=(ARTIFACT_FILENAMES["groups"],),
            argv_builder=lambda ctx: [
                ctx.python,
                str(ctx.script("partition_repo.py")),
                str(ctx.repo_path),
                "--max-tokens",
                str(ctx.max_tokens),
                "--out",
                str(ctx.groups_path or ctx.artifact_path("groups.json")),
            ] + _scan_flags(ctx),
        ),
        StageSpec(
            name="cross_group_edges",
            kind=StageKind.DETERMINISTIC,
            outputs=("cross_group_edges.json",),
            argv_builder=lambda ctx: [
                ctx.python,
                str(ctx.script("build_cross_group_edges.py")),
                str(ctx.groups_path or ctx.artifact_path("groups.json")),
                str(ctx.signals_path or ctx.artifact_path("spring_signals.json")),
                "--out",
                str(ctx.edges_path or ctx.artifact_path("cross_group_edges.json")),
            ],
        ),
        StageSpec(
            name="capacity_preflight",
            kind=StageKind.DETERMINISTIC,
            argv_builder=lambda ctx: [
                ctx.python,
                str(ctx.script("capacity_preflight.py")),
                str(ctx.repo_path),
                "--groups-file",
                str(ctx.groups_path or ctx.artifact_path("groups.json")),
                "--signals-file",
                str(ctx.signals_path or ctx.artifact_path("spring_signals.json")),
                "--max-tokens",
                str(ctx.max_tokens),
                "--out",
                str(ctx.preflight_path or ctx.artifact_path("capacity_preflight_report.json")),
            ],
        ),
        StageSpec(
            name="file_summarize",
            kind=StageKind.GENERATIVE,
            manifest_stage=STAGE_FILE_SUMMARIZE,
            outputs=(ARTIFACT_FILENAMES["summaries"],),
            generative_key="file_summarize",
        ),
        StageSpec(
            name="architect",
            kind=StageKind.GENERATIVE,
            manifest_stage=STAGE_ARCHITECT,
            generative_key="architect",
        ),
        StageSpec(
            name="gap_analysis_interview",
            kind=StageKind.GENERATIVE,
            manifest_stage=STAGE_GAP_INTERVIEW,
            outputs=(ARTIFACT_FILENAMES["interview_answers"],),
            generative_key="gap_analysis_interview",
        ),
        StageSpec(
            name="doc_writer",
            kind=StageKind.GENERATIVE,
            manifest_stage=STAGE_DOC_WRITER,
            generative_key="doc_writer",
        ),
    ]


def manifest_fanout(spec: StageSpec, context: PipelineContext) -> int | None:
    if spec.manifest_stage == STAGE_FILE_SUMMARIZE and context.groups:
        return context.groups.get("num_groups")
    if spec.manifest_stage == STAGE_ARCHITECT and context.groups:
        return context.groups.get("num_groups", 0) + 1
    if spec.manifest_stage == STAGE_GAP_INTERVIEW:
        return 1
    if spec.manifest_stage == STAGE_DOC_WRITER:
        return 14
    return None
