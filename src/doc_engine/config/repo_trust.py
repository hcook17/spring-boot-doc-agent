"""Trust policy for target-repo ``.doc-engine.yml``.

Customer Spring trees are untrusted by default: a hostile
``.doc-engine.yml`` must not supply CodeQL ``build_command`` / ``db_path``,
enable CodeQL via ``scanners``, or weaken ``compliance_profile`` below the
operator floor. Pass ``--trust-repo-config`` only when the operator intends
to honor that file's security-sensitive keys.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from doc_engine.config.settings import Settings
from doc_engine.pipeline.compliance import ComplianceProfile


class RepoConfigTrust(StrEnum):
    UNTRUSTED = "untrusted"
    TRUSTED = "trusted"


def trust_from_flag(trust_repo_config: bool) -> RepoConfigTrust:
    return RepoConfigTrust.TRUSTED if trust_repo_config else RepoConfigTrust.UNTRUSTED


def sanitize_repo_settings(
    settings: Optional[Settings],
    trust: RepoConfigTrust,
) -> Optional[Settings]:
    """Return settings filtered for the given trust level.

    UNTRUSTED keeps non-executing keys (``sql_dialect``, ``respect_gitignore``,
    ``doc_taxonomy``) and floors ``compliance_profile`` to ``certified``.
    Sensitive keys are cleared so only CLI/operator overrides can reintroduce them.
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
        extra=dict(settings.extra or {}),
    )
