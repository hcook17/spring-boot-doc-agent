"""Shared constants and helpers for Stage-0 gap_probe rate views."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from doc_engine._compat import StrEnum


class CoveringPreconditionError(RuntimeError):
    """Raised when gap_probe cannot verify S1 covering before scoring S2."""


class ScoringEnv(StrEnum):
    """Closed scoring environments for R_lin (and delta_r contrast)."""

    CALLABLE = "callable"
    POOLED = "pooled"


class RateKey(StrEnum):
    """Closed R_* schema keys owned by the rate registry."""

    SYM = "R_sym"
    COLL = "R_coll"
    JOIN = "R_join"
    LIN = "R_lin"
    CODE_DEP = "R_code_dep"
    ABSENCE = "R_absence"
    RECALL = "R_recall"


GAP_PROBE_SCHEMA_VERSION = 3

# Fixed uncertainty weights (policy) — do not tune per narrative.
WEIGHT_COLLISION = 0.30
WEIGHT_JOIN = 0.25
WEIGHT_LINEAGE = 0.30
WEIGHT_CODE_DEP = 0.15

# Public aliases — StrEnum members are str, so wire format stays unchanged.
SCORING_ENV_CALLABLE = ScoringEnv.CALLABLE
SCORING_ENV_POOLED = ScoringEnv.POOLED

# Deployment / outbound match text → family for R_code|dep.
_DEP_FAMILY_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("redis", re.compile(r"redis", re.I)),
    ("actuator", re.compile(r"actuator", re.I)),
    ("feign", re.compile(r"feign|openfeign", re.I)),
    ("aws_secrets", re.compile(r"secretsmanager|aws.secrets", re.I)),
    ("messaging", re.compile(r"kafka|rabbit|amqp|jms", re.I)),
)

_CODE_BUCKET_BY_FAMILY: Dict[str, Tuple[str, ...]] = {
    "redis": ("observability", "configuration", "outbound_clients"),
    "actuator": ("observability", "configuration"),
    "feign": ("outbound_clients",),
    "aws_secrets": ("configuration", "security"),
    "messaging": ("messaging",),
}


def _rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return numerator / denominator


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_facts_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _maps_to(facts: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [fact for fact in facts if fact.get("predicate") == "MAPS_TO"]


def _rate_block(numerator: int, denominator: int, **extra: Any) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "numerator": numerator,
        "denominator": denominator,
        "callable_denominator": denominator,
        "rate": _rate(numerator, denominator),
    }
    block.update(extra)
    return block
