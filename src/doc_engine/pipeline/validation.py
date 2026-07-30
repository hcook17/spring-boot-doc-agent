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
