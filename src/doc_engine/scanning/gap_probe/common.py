"""Shared constants and helpers for Stage-0 gap_probe rate views."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


class CoveringPreconditionError(RuntimeError):
    """Raised when gap_probe cannot verify S1 covering before scoring S2."""

GAP_PROBE_SCHEMA_VERSION = 3

# Fixed uncertainty weights (policy) — do not tune per narrative.
WEIGHT_COLLISION = 0.30
WEIGHT_JOIN = 0.25
WEIGHT_LINEAGE = 0.30
WEIGHT_CODE_DEP = 0.15

SCORING_ENV_CALLABLE = "callable"
SCORING_ENV_POOLED = "pooled"

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


def _rate(num: int, den: int) -> Optional[float]:
    if den <= 0:
        return None
    return num / den


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
    return [f for f in facts if f.get("predicate") == "MAPS_TO"]


def _rate_block(num: int, den: int, **extra: Any) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "numerator": num,
        "denominator": den,
        "callable_denominator": den,
        "rate": _rate(num, den),
    }
    block.update(extra)
    return block
