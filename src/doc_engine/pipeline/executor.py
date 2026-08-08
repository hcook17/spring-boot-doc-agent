"""StageExecutor port and subprocess/mock implementations."""

from __future__ import annotations

import subprocess
from typing import Callable, Protocol

from doc_engine.core.timeouts import tool_timeout_seconds
from doc_engine.pipeline.context import PipelineContext, StageResult


class StageExecutor(Protocol):
    """Clean Architecture port for generative (LLM) pipeline stages."""

    def run_generative(self, stage_key: str, context: PipelineContext) -> StageResult:
        ...


class SubprocessStageRunner:
    """Runs deterministic stages as subprocesses (CI-safe, no LLM runtime)."""

    def run(self, argv: list[str], context: PipelineContext, cwd: str | None = None) -> StageResult:
        printable = " ".join(argv)
        context.log(f"  $ {printable}")
        timeout = tool_timeout_seconds()
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            context.log(f"  !! could not execute: {exc}")
            return StageResult(success=False, error=str(exc))
        except subprocess.TimeoutExpired as exc:
            context.log(f"  !! timed out after {timeout}s: {exc}")
            return StageResult(
                success=False,
                detail=f"timeout {timeout}s",
                error="subprocess timed out",
            )

        body = (proc.stdout or "") + (proc.stderr or "")
        for line in body.rstrip("\n").splitlines():
            context.log(f"  | {line}")
        context.log(f"  -> exit {proc.returncode}")

        if proc.returncode == 0:
            return StageResult(success=True, detail=f"exit {proc.returncode}")
        return StageResult(success=False, detail=f"exit {proc.returncode}", error="subprocess failed")


class MockStageExecutor:
    """Generative stage executor for local runs — no LLM, shape-faithful mocks."""

    def __init__(
        self,
        handlers: dict[str, Callable[[PipelineContext], str]] | None = None,
    ):
        self._handlers = handlers or {}

    def run_generative(self, stage_key: str, context: PipelineContext) -> StageResult:
        handler = self._handlers.get(stage_key)
        if handler is None:
            return StageResult(
                success=False,
                error=f"no mock handler registered for generative stage {stage_key!r}",
            )
        try:
            detail = handler(context) or ""
            return StageResult(success=True, detail=detail)
        except Exception as exc:
            return StageResult(success=False, error=repr(exc))


class HttpLLMStageExecutor:
    """Stub adapter — implement when a named non-Claude customer integration exists.

    Do not embed API keys or provider SDKs in doc_engine until a concrete
    integration is specified. See doc_engine/pipeline/README.md and adapters.md.
    """

    def run_generative(self, stage_key: str, context: PipelineContext) -> StageResult:
        return StageResult(
            success=False,
            error=(
                "HttpLLMStageExecutor is not implemented — use Claude Code (SKILL.md) "
                "or MockStageExecutor for local runs"
            ),
        )
