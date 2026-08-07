"""Validate pipeline artifact files against Pydantic boundary objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from doc_engine.pipeline.artifacts import (
    ARTIFACT_FILENAMES,
    ARTIFACT_MODELS,
    JSONL_ARTIFACTS,
)


class ArtifactValidationError(Exception):
    """Raised when an artifact fails schema validation."""

    def __init__(self, artifact: str, path: Path, error: BaseException | str):
        self.artifact = artifact
        self.path = path
        self.error = error
        super().__init__(f"{artifact} validation failed for {path}: {error}")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl_objects(path: Path, *, artifact: str = "facts") -> list[Any]:
    """Load a JSON Lines file as a list of decoded objects (skip blank lines)."""
    rows: list[Any] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ArtifactValidationError(
                    artifact,
                    path,
                    f"invalid JSON on line {lineno}: {exc.msg}",
                ) from exc
    return rows


def validate_artifact_data(artifact: str, data: Any) -> BaseModel:
    if artifact not in ARTIFACT_MODELS:
        raise KeyError(f"unknown artifact {artifact!r}; expected one of {sorted(ARTIFACT_MODELS)}")
    model = ARTIFACT_MODELS[artifact]
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ArtifactValidationError(artifact, Path("<data>"), exc) from exc


def validate_artifact_file(artifact: str, path: Path) -> BaseModel:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if artifact in JSONL_ARTIFACTS:
        data = load_jsonl_objects(path, artifact=artifact)
    else:
        data = load_json(path)
    model = ARTIFACT_MODELS[artifact]
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ArtifactValidationError(artifact, path, exc) from exc


def validate_artifacts_in_dir(directory: Path) -> list[tuple[str, Path]]:
    """Validate every known artifact present in directory. Returns validated pairs."""
    directory = directory.resolve()
    validated: list[tuple[str, Path]] = []
    for artifact, filename in ARTIFACT_FILENAMES.items():
        path = directory / filename
        if path.is_file():
            validate_artifact_file(artifact, path)
            validated.append((artifact, path))
    return validated


def missing_required_artifacts(
    directory: Path,
    required: list[str],
) -> list[str]:
    """Return required artifact names whose files are absent under directory."""
    directory = directory.resolve()
    missing: list[str] = []
    for name in required:
        if name not in ARTIFACT_FILENAMES:
            raise KeyError(
                f"unknown artifact {name!r}; expected one of {sorted(ARTIFACT_FILENAMES)}"
            )
        path = directory / ARTIFACT_FILENAMES[name]
        if not path.is_file():
            missing.append(name)
    return missing


# Sidecar filenames written next to spring_signals.json by Stage 0 (not all
# are ARTIFACT_FILENAMES keys — covering_proof is proof-of-S1, not a DTO yet).
_STAGE0_SIDECARS = (
    ARTIFACT_FILENAMES["facts"],
    "covering_proof.json",
)

_GAP_REPORT_REL = Path("gap_report") / "gap_report.json"


def require_stage0_siblings(directory: Path) -> None:
    """Fail closed when spring_signals.json is present without Stage-0 sidecars.

    Path A certification consumes facts + covering_proof; a signals-only dump
    must not validate as a complete Stage-0 boundary.
    """
    directory = directory.resolve()
    signals = directory / ARTIFACT_FILENAMES["spring_signals"]
    if not signals.is_file():
        return
    for filename in _STAGE0_SIDECARS:
        path = directory / filename
        if not path.is_file():
            raise ArtifactValidationError(
                "spring_signals",
                signals,
                f"missing Stage-0 sibling {filename!r} (required next to spring_signals.json)",
            )


def require_gap_probe_artifact(directory: Path) -> None:
    """Fail closed when spring_signals.json is present without a verified gap_report.

    Existence alone is insufficient: planted ``{}`` or ``s1_covering.verified=false``
    must not green ``validate --all``.
    """
    from doc_engine.scanning.gap_probe import GAP_PROBE_SCHEMA_VERSION

    directory = directory.resolve()
    signals = directory / ARTIFACT_FILENAMES["spring_signals"]
    if not signals.is_file():
        return
    path = directory / _GAP_REPORT_REL
    if not path.is_file():
        raise ArtifactValidationError(
            "spring_signals",
            signals,
            f"missing gap probe report at {_GAP_REPORT_REL.as_posix()}",
        )
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        raise ArtifactValidationError("gap_report", path, exc) from exc
    if not isinstance(data, dict):
        raise ArtifactValidationError("gap_report", path, "root must be a JSON object")
    if data.get("schema_version") != GAP_PROBE_SCHEMA_VERSION:
        raise ArtifactValidationError(
            "gap_report",
            path,
            f"schema_version={data.get('schema_version')!r} "
            f"(expected {GAP_PROBE_SCHEMA_VERSION})",
        )
    covering = data.get("s1_covering")
    if not isinstance(covering, dict) or covering.get("verified") is not True:
        raise ArtifactValidationError(
            "gap_report",
            path,
            "s1_covering.verified must be true",
        )
    if "uncertainty" not in data or not isinstance(data.get("uncertainty"), dict):
        raise ArtifactValidationError(
            "gap_report",
            path,
            "uncertainty object required",
        )
