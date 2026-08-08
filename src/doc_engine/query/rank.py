"""Deterministic ranking + honest token-budget trim for context packets.

Token proxy (Option A ADR): ``chars // 4`` over the **full JSON of emitted
items** (payload replaced by ``row_ref`` before costing).
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

_TOKEN_RE = re.compile(r"\w+", re.ASCII)

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

DEFAULT_NESTED_LIST_CAP = 50


def extract_lowercase_tokens_from_text(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


# Backward-compatible alias
tokenize = extract_lowercase_tokens_from_text


def lookup_bucket_priority_score(bucket: str | None) -> float:
    if not bucket:
        return 0.4
    return _BUCKET_PRIORITY.get(bucket, 0.4)


bucket_priority = lookup_bucket_priority_score


def measure_token_overlap_ratio(request_tokens: set[str], item_tokens: set[str]) -> float:
    if not request_tokens:
        return 0.0
    return len(request_tokens & item_tokens) / max(1, len(request_tokens))


token_overlap = measure_token_overlap_ratio


def score_context_item_for_request(
    *,
    request: str,
    path: str | None,
    text: str | None,
    bucket: str | None,
    contested: bool,
) -> float:
    request_tokens = extract_lowercase_tokens_from_text(request)
    item_tokens = extract_lowercase_tokens_from_text(f"{path or ''} {text or ''}")
    contested_boost = 1.0 if contested else 0.0
    return (
        0.50 * measure_token_overlap_ratio(request_tokens, item_tokens)
        + 0.30 * lookup_bucket_priority_score(bucket)
        + 0.20 * contested_boost
    )


score_item = score_context_item_for_request


def estimate_tokens_from_serialized_json(obj: Any) -> int:
    """Chars/4 proxy over full JSON of what agents actually receive."""
    raw = json.dumps(obj, ensure_ascii=False, default=str)
    return max(0, len(raw) // 4)


estimate_tokens = estimate_tokens_from_serialized_json


def split_budget_into_primary_finding_and_risk_shares(budget: int) -> tuple[int, int, int]:
    """Partition tokens so shares always sum to ``budget`` (never overshoot)."""
    total = max(0, int(budget))
    if total == 0:
        return 0, 0, 0
    primary = (total * 7) // 10
    finding = (total * 2) // 10
    risk = total - primary - finding
    return primary, finding, risk


partition_budget = split_budget_into_primary_finding_and_risk_shares


def truncate_nested_lists_that_exceed_cap(
    obj: Any,
    *,
    max_list_length: int = DEFAULT_NESTED_LIST_CAP,
) -> tuple[Any, bool]:
    """Return (possibly capped object, did_truncate). Caps guards/candidates/etc."""
    state = {"truncated": False}
    return _walk_nested(obj, max_list_length, state), bool(state["truncated"])


def _walk_nested(node: Any, max_list_length: int, state: dict[str, bool]) -> Any:
    if isinstance(node, list):
        return _walk_nested_list(node, max_list_length, state)
    if isinstance(node, Mapping):
        return _walk_nested_mapping(node, max_list_length, state)
    return node


def _walk_nested_list(
    node: list[Any], max_list_length: int, state: dict[str, bool]
) -> list[Any]:
    if len(node) > max_list_length:
        state["truncated"] = True
    return [_walk_nested(item, max_list_length, state) for item in node[:max_list_length]]


def _map_value_capped(
    value: Any, max_list_length: int, state: dict[str, bool]
) -> Any:
    if isinstance(value, list) and len(value) > max_list_length:
        state["truncated"] = True
        return [_walk_nested(item, max_list_length, state) for item in value[:max_list_length]]
    return _walk_nested(value, max_list_length, state)


def _walk_nested_mapping(
    node: Mapping[str, Any], max_list_length: int, state: dict[str, bool]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in node.items():
        out[key] = _map_value_capped(value, max_list_length, state)
    return out


apply_nested_cap = truncate_nested_lists_that_exceed_cap  # returns tuple; see wrap below


def apply_nested_cap_value(obj: Any, *, max_list: int = DEFAULT_NESTED_LIST_CAP) -> Any:
    capped, _ = truncate_nested_lists_that_exceed_cap(obj, max_list_length=max_list)
    return capped


def replace_bulky_payload_with_row_ref_pointer(item: Mapping[str, Any]) -> dict[str, Any]:
    """Option A emission shape: drop payload body; keep expandable row_ref."""
    emission: dict[str, Any] = {
        "provider": item.get("provider"),
        "path": item.get("path"),
        "line": item.get("line"),
        "match": item.get("match"),
        "bucket": item.get("bucket"),
        "reason": item.get("reason"),
        "score": item.get("score"),
        "row_ref": {
            "path": item.get("path"),
            "line": item.get("line"),
            "provider": item.get("provider"),
            "bucket": item.get("bucket"),
        },
    }
    if "freshness" in item:
        emission["freshness"] = item.get("freshness")
    if "contested" in item:
        emission["contested"] = item.get("contested")
    payload = item.get("payload")
    if isinstance(payload, Mapping):
        capped_payload, nested_truncated = truncate_nested_lists_that_exceed_cap(payload)
        if nested_truncated:
            emission["nested_truncated"] = True
            # keep only capped nested lists under row_ref for traceability
            for key in ("guards", "candidates"):
                if key in capped_payload:
                    emission["row_ref"][key] = capped_payload[key]
    return {key: value for key, value in emission.items() if value is not None}


to_emission_item = replace_bulky_payload_with_row_ref_pointer


def sort_items_highest_score_first(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(i) for i in items),
        key=lambda i: (
            -float(i.get("score") or 0.0),
            str(i.get("path") or ""),
            str(i.get("provider") or ""),
        ),
    )


def keep_highest_scoring_items_within_token_budget(
    items: Sequence[Mapping[str, Any]],
    budget_tokens: int,
) -> tuple[list[dict[str, Any]], bool, int]:
    """Trim to budget using emission-shaped costs. Returns (kept, truncated, tokens_used)."""
    budget = max(0, int(budget_tokens))
    ordered = sort_items_highest_score_first(items)
    kept: list[dict[str, Any]] = []
    tokens_used = 0
    truncated = False
    for item in ordered:
        emission = replace_bulky_payload_with_row_ref_pointer(item)
        cost = estimate_tokens_from_serialized_json(emission)
        if tokens_used + cost > budget:
            if not kept and budget > 0:
                kept.append(emission)
                tokens_used = cost
                truncated = True
            else:
                truncated = True
            break
        kept.append(emission)
        tokens_used += cost
    if len(kept) < len(ordered):
        truncated = True
    return kept, truncated, tokens_used


trim_to_budget = keep_highest_scoring_items_within_token_budget
