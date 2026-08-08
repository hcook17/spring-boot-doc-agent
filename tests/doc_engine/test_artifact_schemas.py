"""Tests for pipeline artifact Pydantic schemas."""

import json

import pytest
from pydantic import ValidationError

from doc_engine.pipeline.artifacts import (
    ARTIFACT_FILENAMES,
    ARTIFACT_MODELS,
    FACTS_LEDGER_SCHEMA_VERSION,
    Fact,
    FactsArtifact,
    GroupsArtifact,
    InterviewAnswersArtifact,
    SpringSignalsArtifact,
    SummariesArtifact,
    export_json_schemas,
)
from doc_engine.pipeline.validation import (
    ArtifactValidationError,
    validate_artifact_file,
    validate_artifacts_in_dir,
)

from tests.conftest import FIXTURE_SNAPSHOT_PATH, REPO_ROOT
from tests.doc_engine.cert_helpers import ok_stages_for


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


def test_interview_answers_from_local_target_repo():
    """Optional live artifact: put interview_answers.json under gitignored target-repo/."""
    path = REPO_ROOT / "target-repo" / "interview_answers.json"
    if not path.is_file():
        pytest.skip("target-repo/interview_answers.json not present")
    model = validate_artifact_file("interview_answers", path)
    assert isinstance(model, InterviewAnswersArtifact)
    assert len(model.root) > 0


def test_validate_artifacts_in_dir_empty(tmp_path):
    assert validate_artifacts_in_dir(tmp_path) == []


def test_validate_artifacts_require_missing_fails(tmp_path):
    from doc_engine.tools import validate_artifacts as va

    code = va.main(["--all", str(tmp_path), "--require", "spring_signals"])
    assert code == 1


def test_validate_artifacts_require_present_passes(tmp_path):
    from doc_engine.scanning.gap_probe import run_gap_probe
    from doc_engine.scanning.stage0_siblings import materialize_stage0_siblings
    from doc_engine.tools import validate_artifacts as va
    from tests.conftest import FIXTURE_SNAPSHOT_PATH
    import shutil

    dest = tmp_path / "spring_signals.json"
    shutil.copy(FIXTURE_SNAPSHOT_PATH, dest)
    # --all fail-closes without Stage-0 siblings + verified gap_report.
    materialize_stage0_siblings(dest, tmp_path)
    run_gap_probe(
        dest,
        tmp_path / "facts.jsonl",
        tmp_path / "gap_report",
        covering_path=tmp_path / "covering_proof.json",
    )
    code = va.main(["--all", str(tmp_path), "--require", "spring_signals"])
    assert code == 0
def test_artifact_filenames_cover_models():
    assert set(ARTIFACT_FILENAMES) == set(ARTIFACT_MODELS)
    assert set(ARTIFACT_FILENAMES) == {
        "spring_signals", "groups", "summaries", "interview_answers", "facts",
        "certification", "cross_group_edges", "gap_questions", "architecture_testing_review",
        "drift_report", "capacity_preflight_report",
    }


def test_fact_closed_world_rejects_unknown_key():
    with pytest.raises(ValidationError):
        Fact.model_validate({
            "predicate": "MAPS_TO",
            "subject": "User",
            "object": "users",
            "qualifiers": {},
            "file": "User.java",
            "line": 1,
            "rule_id": None,
            "scanner": "ast-grep",
            "extra_column": "nope",
        })


def test_fact_rejects_line_below_one():
    with pytest.raises(ValidationError):
        Fact.model_validate({
            "predicate": "EVIDENCE",
            "subject": "A.java",
            "object": "@Entity",
            "qualifiers": {},
            "file": "A.java",
            "line": 0,
            "rule_id": None,
            "scanner": None,
        })


def test_facts_jsonl_file_validates(tmp_path):
    from doc_engine.scanning.facts import facts_from_signals, write_facts_jsonl

    signals = {
        "scanners": ["ast-grep"],
        "evidence": {
            "entities": [{
                "file": "A.java",
                "line": 3,
                "match": "@Entity",
                "rule_id": "persistence__entity",
            }]
        },
        "entity_table_map": {
            "A": {"file": "A.java", "table": "a", "table_name_source": "default"}
        },
    }
    path = tmp_path / "facts.jsonl"
    write_facts_jsonl(path, facts_from_signals(signals))
    model = validate_artifact_file("facts", path)
    assert isinstance(model, FactsArtifact)
    assert len(model.root) >= 2


def test_facts_jsonl_rejects_invalid_line(tmp_path):
    path = tmp_path / "facts.jsonl"
    path.write_text('{"predicate":"X","subject":"s"}\nnot-json\n', encoding="utf-8")
    with pytest.raises(ArtifactValidationError, match="invalid JSON on line 2"):
        validate_artifact_file("facts", path)


def test_facts_schema_export_marks_jsonl_encoding():
    schema = export_json_schemas()["facts"]
    assert schema["x-doc-engine-schema-version"] == FACTS_LEDGER_SCHEMA_VERSION
    assert schema["x-doc-engine-encoding"] == "jsonl"
    exported = json.loads(
        (REPO_ROOT / "scripts" / "schemas" / "facts.schema.json").read_text(encoding="utf-8")
    )
    assert exported["x-doc-engine-encoding"] == "jsonl"


def test_certification_schema_file_and_round_trip(tmp_path):
    from doc_engine.pipeline.compliance import (
        ComplianceProfile,
        GateRecord,
        StageRecord,
        build_certification_report,
        write_certification_json,
    )

    report = build_certification_report(
        ComplianceProfile.DETERMINISTIC_ONLY,
        repo_path="/repo",
        out_dir=str(tmp_path),
        stages=ok_stages_for(ComplianceProfile.DETERMINISTIC_ONLY),
        gates=[GateRecord(id="validate_artifacts_all", label="all", status="ok")],
    )
    path = write_certification_json(tmp_path, report)
    model = validate_artifact_file("certification", path)
    assert model.certified is True
    assert model.completeness_claim == "fold_of_recorded_rows"
    assert (REPO_ROOT / "scripts" / "schemas" / "certification.schema.json").is_file()


def test_cross_group_edges_minimal_validates():
    from doc_engine.pipeline.artifacts import CrossGroupEdgesArtifact

    CrossGroupEdgesArtifact.model_validate({
        "schema_version": 1,
        "num_groups": 1,
        "references_rows": 0,
        "stats": {},
        "groups": {"0": {"outbound": [], "inbound": [], "same_package_outside": []}},
    })


def test_gap_questions_rejects_unknown_blocks_file():
    from doc_engine.pipeline.artifacts import GapQuestionsArtifact

    with pytest.raises(ValidationError):
        GapQuestionsArtifact.model_validate([{
            "blocks_file": "not_a_doc",
            "topic": "t",
            "question": "q",
            "evidence": "A.java:1",
        }])


def test_architecture_testing_review_validates_array():
    from doc_engine.pipeline.artifacts import ArchitectureTestingReviewArtifact

    ArchitectureTestingReviewArtifact.model_validate([{
        "lens": "ddia",
        "concept": "c",
        "claim": "x",
        "evidence": [{"line": 1, "what": "w"}],
        "severity": "informational",
        "external_research": None,
    }])
