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

# Package module paths for deterministic Stage 0 (portable; no scripts/ tree).
MOD_RUN_MANIFEST = "doc_engine.tools.run_manifest"
MOD_SIGNAL_SCAN = "doc_engine.tools.spring_signal_scan"
MOD_GAP_PROBE = "doc_engine.tools.gap_probe"
MOD_PARTITION = "doc_engine.tools.partition_repo"
MOD_CROSS_GROUP = "doc_engine.tools.build_cross_group_edges"
MOD_CAPACITY = "doc_engine.tools.capacity_preflight"


def _scan_flags(ctx: PipelineContext) -> list[str]:
    return ["--respect-gitignore"] if ctx.respect_gitignore else []


def _py_mod(ctx: PipelineContext, module: str, *args: str) -> list[str]:
    """Build argv for `python -m doc_engine.tools.<module> …`."""
    return [ctx.python, "-m", module, *args]


def build_stage_specs() -> list[StageSpec]:
    """Executable stage graph — maps 1:1 to SKILL.md stage names.

    Deterministic stages invoke package entrypoints (`python -m doc_engine.tools…`),
    not monorepo ``scripts/`` paths, so a wheel install without ``scripts/`` works.
    """
    return [
        StageSpec(
            name="init_manifest",
            kind=StageKind.DETERMINISTIC,
            argv_builder=lambda ctx: _py_mod(
                ctx,
                MOD_RUN_MANIFEST,
                "init",
                str(ctx.repo_path),
                "--out",
                str(ctx.manifest_path),
            ),
        ),
        StageSpec(
            name="signal_scan",
            kind=StageKind.DETERMINISTIC,
            manifest_stage=STAGE_SIGNAL_SCAN,
            outputs=(
                ARTIFACT_FILENAMES["spring_signals"],
                ARTIFACT_FILENAMES["facts"],
                "covering_proof.json",
            ),
            argv_builder=lambda ctx: _py_mod(
                ctx,
                MOD_SIGNAL_SCAN,
                str(ctx.repo_path),
                "--out",
                str(ctx.signals_path or ctx.artifact_path("spring_signals.json")),
            )
            + _scan_flags(ctx),
        ),
        StageSpec(
            name="gap_probe",
            kind=StageKind.DETERMINISTIC,
            outputs=("gap_report/gap_report.json",),
            argv_builder=lambda ctx: _py_mod(
                ctx,
                MOD_GAP_PROBE,
                "--signals",
                str(ctx.signals_path or ctx.artifact_path("spring_signals.json")),
                "--facts",
                str(ctx.artifact_path("facts.jsonl")),
                "--covering",
                str(ctx.artifact_path("covering_proof.json")),
                "--out",
                str(ctx.out_dir / "gap_report"),
            ),
        ),
        StageSpec(
            name="partition",
            kind=StageKind.DETERMINISTIC,
            manifest_stage=STAGE_PARTITION,
            outputs=(ARTIFACT_FILENAMES["groups"],),
            argv_builder=lambda ctx: _py_mod(
                ctx,
                MOD_PARTITION,
                str(ctx.repo_path),
                "--max-tokens",
                str(ctx.max_tokens),
                "--out",
                str(ctx.groups_path or ctx.artifact_path("groups.json")),
            )
            + _scan_flags(ctx),
        ),
        StageSpec(
            name="cross_group_edges",
            kind=StageKind.DETERMINISTIC,
            outputs=(ARTIFACT_FILENAMES["cross_group_edges"],),
            argv_builder=lambda ctx: _py_mod(
                ctx,
                MOD_CROSS_GROUP,
                str(ctx.groups_path or ctx.artifact_path("groups.json")),
                str(ctx.signals_path or ctx.artifact_path("spring_signals.json")),
                "--out",
                str(ctx.edges_path or ctx.artifact_path("cross_group_edges.json")),
            ),
        ),
        StageSpec(
            name="capacity_preflight",
            kind=StageKind.DETERMINISTIC,
            outputs=(ARTIFACT_FILENAMES["capacity_preflight_report"],),
            argv_builder=lambda ctx: _py_mod(
                ctx,
                MOD_CAPACITY,
                str(ctx.repo_path),
                "--groups-file",
                str(ctx.groups_path or ctx.artifact_path("groups.json")),
                "--signals-file",
                str(ctx.signals_path or ctx.artifact_path("spring_signals.json")),
                "--max-tokens",
                str(ctx.max_tokens),
                "--out",
                str(ctx.preflight_path or ctx.artifact_path("capacity_preflight_report.json")),
            ),
        ),
        StageSpec(
            name="file_summarize",
            kind=StageKind.GENERATIVE,
            manifest_stage=STAGE_FILE_SUMMARIZE,
            outputs=(ARTIFACT_FILENAMES["summaries"],),
            generative_key="file_summarize",
            agent_names=("file-summarizer",),
            input_artifacts=(
                ARTIFACT_FILENAMES["spring_signals"],
                ARTIFACT_FILENAMES["groups"],
                "cross_group_edges.json",
            ),
        ),
        StageSpec(
            name="architect",
            kind=StageKind.GENERATIVE,
            manifest_stage=STAGE_ARCHITECT,
            generative_key="architect",
            agent_names=("architect-segment", "architect-merge"),
            input_artifacts=(
                ARTIFACT_FILENAMES["summaries"],
                ARTIFACT_FILENAMES["groups"],
            ),
        ),
        StageSpec(
            name="gap_analysis_interview",
            kind=StageKind.GENERATIVE,
            manifest_stage=STAGE_GAP_INTERVIEW,
            outputs=(ARTIFACT_FILENAMES["interview_answers"],),
            generative_key="gap_analysis_interview",
            agent_names=("gap-analyzer", "software-architect-and-testing"),
            requires_human_interview=True,
            input_artifacts=(
                ARTIFACT_FILENAMES["summaries"],
                ARTIFACT_FILENAMES["spring_signals"],
                ARTIFACT_FILENAMES["facts"],
            ),
        ),
        StageSpec(
            name="doc_writer",
            kind=StageKind.GENERATIVE,
            manifest_stage=STAGE_DOC_WRITER,
            generative_key="doc_writer",
            agent_names=("doc-writer",),
            input_artifacts=(
                ARTIFACT_FILENAMES["summaries"],
                ARTIFACT_FILENAMES["interview_answers"],
                ARTIFACT_FILENAMES["spring_signals"],
                ARTIFACT_FILENAMES["facts"],
            ),
        ),
    ]


def generative_choreography() -> list[dict[str, object]]:
    """Machine-readable generative stage map (SoT for adapter skills).

    Skills must cite this via ``build_stage_specs()`` / profiles / ``--until``,
    not maintain a second stage list in prose.
    """
    rows: list[dict[str, object]] = []
    for spec in build_stage_specs():
        if spec.kind != StageKind.GENERATIVE:
            continue
        rows.append(
            {
                "name": spec.name,
                "generative_key": spec.generative_key,
                "agents": list(spec.agent_names),
                "requires_human_interview": spec.requires_human_interview,
                "inputs": list(spec.input_artifacts),
                "outputs": list(spec.outputs),
            }
        )
    return rows


def _fanout_from_groups(spec: StageSpec, context: PipelineContext) -> int | None:
    if not context.groups:
        return None
    if spec.manifest_stage == STAGE_FILE_SUMMARIZE:
        return context.groups.get("num_groups")
    if spec.manifest_stage == STAGE_ARCHITECT:
        return context.groups.get("num_groups", 0) + 1
    return None


def manifest_fanout(spec: StageSpec, context: PipelineContext) -> int | None:
    grouped = _fanout_from_groups(spec, context)
    if grouped is not None:
        return grouped
    if spec.manifest_stage == STAGE_GAP_INTERVIEW:
        return 1
    if spec.manifest_stage == STAGE_DOC_WRITER:
        return 14
    return None
