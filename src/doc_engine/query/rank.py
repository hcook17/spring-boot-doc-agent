"""Deterministic ranking + token-budget trim for context packets.

Ranking formula (E1-S2 — falsifiable)::

    score = 0.50 * token_overlap(request, path∪text)
          + 0.30 * bucket_priority(bucket)
          + 0.20 * contested_boost

Token proxy: ``chars // 4`` (same heuristic family as partition_repo).
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, MutableMapping, Sequence

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")

_BUCKET_PRIORITY: dict[str, float] = {
    "security": 1.0,
    "api_surface": 0.9,
    "route-trace": 0.9,
    "routes": 0.9,
    "persistence": 0.8,
    "entity": 0.8,
    "facts": 0.7,
    "dependents": 0.6,
    "redaction": 1.0,
    "references": 0.3,
}


def tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def bucket_priority(bucket: str | None) -> float:
    if not bucket:
        return 0.4
    return _BUCKET_PRIORITY.get(bucket, 0.4)


def token_overlap(a: set[str], b: set[str]) -> float:
    if not a:
        return 0.0
    return len(a & b) / max(1, len(a))


def score_item(
    *,
    request: str,
    path: str | None,
    text: str | None,
    bucket: str | None,
    contested: bool,
) -> float:
    req = tokenize(request)
    blob = tokenize(f"{path or ''} {text or ''}")
    contested_boost = 1.0 if contested else 0.0
    return (
        0.50 * token_overlap(req, blob)
        + 0.30 * bucket_priority(bucket)
        + 0.20 * contested_boost
    )


def estimate_tokens(obj: Any) -> int:
    """Chars/4 proxy. For context items, ignore bulky ``payload`` (DDIA budget)."""
    if isinstance(obj, Mapping) and (
        "provider" in obj or "score" in obj or "path" in obj
    ):
        slim = {
            k: obj.get(k)
            for k in (
                "provider",
                "path",
                "line",
                "match",
                "bucket",
                "reason",
                "score",
                "freshness",
            )
        }
        raw = json.dumps(slim, ensure_ascii=False, default=str)
    else:
        raw = json.dumps(obj, ensure_ascii=False, default=str)
    return max(0, len(raw) // 4)


def trim_to_budget(
    items: Sequence[Mapping[str, Any]],
    budget_tokens: int,
) -> tuple[list[dict[str, Any]], bool, int]:
    """Keep highest-score items until budget exhausted.

    Returns (kept, truncated, tokens_used).
    If the top item alone exceeds the budget, keep it and mark truncated
    (agents still get one lead); ``tokens_used`` reports the item cost.
    """
    budget = max(0, int(budget_tokens))
    ordered = sorted(
        (dict(i) for i in items),
        key=lambda i: (
            -float(i.get("score") or 0.0),
            str(i.get("path") or ""),
            str(i.get("provider") or ""),
        ),
    )
    kept: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for item in ordered:
        cost = estimate_tokens(item)
        if used + cost > budget:
            if not kept:
                kept.append(item)
                used = cost
                truncated = True
            else:
                truncated = True
            break
        kept.append(item)
        used += cost
    if len(kept) < len(ordered):
        truncated = True
    return kept, truncated, used
