"""Tests for pipeline artifact Pydantic schemas."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from doc_engine.pipeline.artifacts import (
    ARTIFACT_FILENAMES,
    GroupsArtifact,
    InterviewAnswersArtifact,
    SpringSignalsArtifact,
    SummariesArtifact,
)
from doc_engine.pipeline.validation import (
    ArtifactValidationError,
    validate_artifact_file,
    validate_artifacts_in_dir,
)

from tests.conftest import FIXTURE_SNAPSHOT_PATH, REPO_ROOT


@pytest.fixture
def spring_signals_path():
    return FIXTURE_SNAPSHOT_PATH


def test_spring_signals_fixture_validates(spring_signals_path):
    model = validate_artifact_file("spring_signals", spring_signals_path)
    assert isinstance(model, SpringSignalsArtifact)
    assert model.schema_version >= 2


def test_spring_signals_rejects_low_schema_version(spring_signals_path):
    data = json.loads(spring_signals_path.read_text(encoding="utf-8"))
    data["schema_version"] = 1
    with pytest.raises((ValidationError, ArtifactValidationError)):
        SpringSignalsArtifact.model_validate(data)


def test_groups_minimal_valid():
    artifact = GroupsArtifact.model_validate({
        "repo_path": "/repo",
        "max_tokens_per_group": 120000,
        "overlap": 0.1,
        "total_files_considered": 2,
        "total_files_skipped": 0,
        "skipped": [],
        "num_groups": 1,
        "groups": [{"id": 0, "files": ["src/Main.java"], "est_tokens": 100}],
    })
    assert artifact.num_groups == 1


def test_summaries_valid_entry():
    SummariesArtifact.model_validate([{
        "file": "Invoice.java",
        "cluster": [],
        "summary": "Handles invoices.",
        "relationships": [],
        "cross_group_relationships": [],
        "group_function": "billing",
        "spring_role": "entity",
        "evidence": [{"line": 10, "what": "entity mapping"}],
    }])


def test_summaries_invalid_spring_role():
    with pytest.raises(ValidationError):
        SummariesArtifact.model_validate([{
            "file": "X.java",
            "cluster": [],
            "summary": "s",
            "relationships": [],
            "cross_group_relationships": [],
            "group_function": "",
            "spring_role": "invalid",
            "evidence": [],
        }])


def test_interview_answers_from_ocs_fixture():
    path = REPO_ROOT / "ocs-api-service-develop" / "interview_answers.json"
    if not path.is_file():
        pytest.skip("ocs-api-service-develop/interview_answers.json not present")
    model = validate_artifact_file("interview_answers", path)
    assert isinstance(model, InterviewAnswersArtifact)
    assert len(model.root) > 0


def test_validate_artifacts_in_dir_empty(tmp_path):
    assert validate_artifacts_in_dir(tmp_path) == []


def test_artifact_filenames_cover_models():
    assert set(ARTIFACT_FILENAMES) == {"spring_signals", "groups", "summaries", "interview_answers"}
