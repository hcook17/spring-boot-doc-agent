"""Trust policy for target-repo ``.doc-engine.yml`` and CodeQL build mode.

Customer Spring trees are untrusted by default. Two independent gates:

1. **Config trust** (``RepoConfigTrust`` / ``--trust-repo-config``) — whether
   security-sensitive keys from the target's ``.doc-engine.yml`` are honored.
2. **CodeQL build** (``--allow-codeql-build``) — whether ``codeql database
   create --command`` may run against the tree. Allowlisting build-tool names
   cannot make that safe; the control is refusing the build unless the operator
   explicitly opts in (first-party tree or sandboxed host).
"""

from __future__ import annotations

from typing import Optional

from doc_engine._compat import StrEnum
from doc_engine.config.settings import Settings
from doc_engine.pipeline.compliance import ComplianceProfile


class RepoConfigTrust(StrEnum):
    UNTRUSTED = "untrusted"
    TRUSTED = "trusted"


class CodeQLBuildPolicy(StrEnum):
    """Whether CodeQL may execute a build command inside the target tree."""

    REFUSED = "refused"
    ALLOWED = "allowed"


def trust_from_flag(trust_repo_config: bool) -> RepoConfigTrust:
    return RepoConfigTrust.TRUSTED if trust_repo_config else RepoConfigTrust.UNTRUSTED


def codeql_build_policy_from_flag(allow_codeql_build: bool) -> CodeQLBuildPolicy:
    return CodeQLBuildPolicy.ALLOWED if allow_codeql_build else CodeQLBuildPolicy.REFUSED


def require_codeql_build_allowed(
    scanner_names: list[str],
    policy: CodeQLBuildPolicy,
) -> None:
    """Raise if CodeQL is selected while build mode is refused."""
    if "codeql" not in scanner_names:
        return
    if policy is CodeQLBuildPolicy.ALLOWED:
        return
    raise PermissionError(
        "CodeQL build mode is refused for untrusted target trees: "
        "`codeql database create --command` executes the build inside "
        "--source-root (attacker-controlled gradlew/pom/build.gradle). "
        "Pass --allow-codeql-build only for first-party repos or a sandboxed host."
    )


def sanitize_repo_settings(
    settings: Optional[Settings],
    trust: RepoConfigTrust,
) -> Optional[Settings]:
    """Return settings filtered for the given trust level.

    UNTRUSTED keeps non-executing keys (``sql_dialect``, ``respect_gitignore``,
    ``doc_taxonomy``), ignores YAML ``compliance_profile`` (always certified
    floor here), clears ``extra``, and strips build_command / db_path / scanners.
    """
    if settings is None:
        return None
    if trust == RepoConfigTrust.TRUSTED:
        return settings

    defaults = Settings()
    return Settings(
        scanners=list(defaults.scanners),
        sql_dialect=settings.sql_dialect,
        respect_gitignore=settings.respect_gitignore,
        build_command=None,
        db_path=None,
        doc_taxonomy=settings.doc_taxonomy,
        compliance_profile=ComplianceProfile.CERTIFIED,
        extra={},
    )
