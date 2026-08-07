"""Tests for untrusted target-repo .doc-engine.yml policy."""

from argparse import Namespace

from doc_engine.config.loader import merge_config
from doc_engine.config.repo_trust import (
    RepoConfigTrust,
    sanitize_repo_settings,
    trust_from_flag,
)
from doc_engine.config.settings import Settings
from doc_engine.pipeline.compliance import ComplianceProfile, resolve_compliance_profile


def test_trust_from_flag():
    assert trust_from_flag(False) is RepoConfigTrust.UNTRUSTED
    assert trust_from_flag(True) is RepoConfigTrust.TRUSTED


def test_untrusted_strips_build_command_db_path_and_scanners():
    hostile = Settings(
        scanners=["filesystem", "codeql"],
        build_command="bash -c echo pwned",
        db_path="/tmp/evil.db",
        sql_dialect="postgres",
        compliance_profile=ComplianceProfile.SCAN_ONLY,
    )
    cleaned = sanitize_repo_settings(hostile, RepoConfigTrust.UNTRUSTED)
    assert cleaned is not None
    assert cleaned.build_command is None
    assert cleaned.db_path is None
    assert cleaned.scanners == ["filesystem", "ast-grep"]
    assert cleaned.sql_dialect == "postgres"
    assert cleaned.compliance_profile == ComplianceProfile.CERTIFIED


def test_trusted_preserves_hostile_keys():
    hostile = Settings(
        scanners=["filesystem", "codeql"],
        build_command="gradlew clean compileJava",
        compliance_profile=ComplianceProfile.SCAN_ONLY,
    )
    kept = sanitize_repo_settings(hostile, RepoConfigTrust.TRUSTED)
    assert kept is hostile
    assert kept.build_command == "gradlew clean compileJava"
    assert kept.compliance_profile == ComplianceProfile.SCAN_ONLY


def test_untrusted_yaml_cannot_weaken_profile_without_cli():
    cleaned = sanitize_repo_settings(
        Settings(compliance_profile=ComplianceProfile.SCAN_ONLY),
        RepoConfigTrust.UNTRUSTED,
    )
    profile = resolve_compliance_profile(
        cleaned,
        Namespace(compliance_profile=None, deterministic_only=False),
    )
    assert profile == ComplianceProfile.CERTIFIED


def test_cli_profile_override_still_wins():
    cleaned = sanitize_repo_settings(
        Settings(compliance_profile=ComplianceProfile.CERTIFIED),
        RepoConfigTrust.UNTRUSTED,
    )
    profile = resolve_compliance_profile(
        cleaned,
        Namespace(compliance_profile="scan_only", deterministic_only=False),
    )
    assert profile == ComplianceProfile.SCAN_ONLY


def test_operator_build_command_override_after_sanitize():
    cleaned = sanitize_repo_settings(
        Settings(build_command="bash -c echo no"),
        RepoConfigTrust.UNTRUSTED,
    )
    merged = merge_config(cleaned or Settings(), {"build_command": "gradlew clean compileJava"})
    assert merged.build_command == "gradlew clean compileJava"
