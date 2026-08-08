"""Import dependents — reuse build_cross_group_edges join helpers."""

from __future__ import annotations

from typing import Any, Mapping

from doc_engine.tools.build_cross_group_edges import parse_references, resolve_targets


def _normalize_want_file(target_file: str | None) -> str | None:
    return target_file.replace("\\", "/") if target_file else None


def _matches_want_file(src: str, dst: str, want_file: str | None) -> bool:
    if not want_file:
        return True
    src_n = src.replace("\\", "/")
    dst_n = dst.replace("\\", "/")
    return dst_n == want_file or src_n == want_file


def _matches_want_type(qualified: str, want_type: str | None) -> bool:
    if not want_type:
        return True
    stem = qualified.rstrip(".*").rsplit(".", 1)[-1]
    return stem == want_type or want_type in qualified


def _passes_target_filters(
    src: str,
    dst: str,
    qualified: str,
    want_file: str | None,
    want_type: str | None,
) -> bool:
    if dst == src:
        return False
    return _matches_want_file(src, dst, want_file) and _matches_want_type(
        qualified, want_type
    )


def _arc_direction(src: str, dst: str, want_file: str | None) -> str:
    if want_file and src.replace("\\", "/") == want_file:
        return "outbound"
    if want_file and dst.replace("\\", "/") == want_file:
        return "inbound"
    return "outbound"


def _append_import_arc(
    rows: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    *,
    src: str,
    dst: str,
    qualified: str,
    confidence: str,
    is_static: bool,
    want_file: str | None,
) -> None:
    key = (src, dst, qualified)
    if key in seen:
        return
    seen.add(key)
    rows.append(
        {
            "from": src,
            "to": dst,
            "via": qualified,
            "confidence": confidence,
            "static_import": bool(is_static),
            "direction": _arc_direction(src, dst, want_file),
        }
    )


def _append_resolved_targets(
    rows: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    *,
    src: str,
    qualified: str,
    is_static: bool,
    targets: Any,
    confidence: str,
    want_file: str | None,
    want_type: str | None,
) -> None:
    for dst in targets:
        if not _passes_target_filters(src, dst, qualified, want_file, want_type):
            continue
        _append_import_arc(
            rows,
            seen,
            src=src,
            dst=dst,
            qualified=qualified,
            confidence=confidence,
            is_static=is_static,
            want_file=want_file,
        )


def _collect_arcs_for_source(
    rows: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    *,
    src: str,
    entries: Any,
    decl_files: Any,
    stem_index: Any,
    want_file: str | None,
    want_type: str | None,
) -> None:
    for qualified, is_static in entries:
        targets, confidence = resolve_targets(qualified, decl_files, stem_index)
        if confidence == "unresolved":
            continue
        _append_resolved_targets(
            rows,
            seen,
            src=src,
            qualified=qualified,
            is_static=is_static,
            targets=targets,
            confidence=confidence,
            want_file=want_file,
            want_type=want_type,
        )


def _from_references(
    signals: Mapping[str, Any],
    *,
    target_file: str | None,
    target_type: str | None,
) -> list[dict[str, Any]]:
    references = (signals.get("evidence") or {}).get("references") or []
    if not isinstance(references, list):
        return []
    decl_files, stem_index, imports = parse_references(references)
    want_file = _normalize_want_file(target_file)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for src, entries in imports.items():
        _collect_arcs_for_source(
            rows,
            seen,
            src=src,
            entries=entries,
            decl_files=decl_files,
            stem_index=stem_index,
            want_file=want_file,
            want_type=target_type,
        )
    return rows


def query_dependents(
    signals: Mapping[str, Any],
    *,
    target_file: str | None = None,
    target_type: str | None = None,
    edges: Mapping[str, Any] | None = None,
    group_id: str | int | None = None,
) -> list[dict[str, Any]]:
    """Return inbound/outbound import arcs.

    Hard stops (documented): import/package text only — no @Autowired
    interface→implementer resolution; wildcards may be ``package-fanout``.

    When ``edges`` + ``group_id`` are set, return that group's cut arcs only
    (filtered by target if provided). Otherwise compute whole-repo arcs from
    ``evidence.references``.
    """
    if edges is not None and group_id is not None:
        return _from_edges(edges, group_id, target_file=target_file)
    return _from_references(
        signals, target_file=target_file, target_type=target_type
    )


def _lookup_mapping_entry(mapping: Any, gid: str) -> Mapping[str, Any] | None:
    if isinstance(mapping, Mapping) and gid in mapping:
        entry = mapping[gid]
        if isinstance(entry, Mapping):
            return entry
    return None


def _resolve_group_entry(
    edges: Mapping[str, Any], group_id: str | int
) -> Mapping[str, Any] | None:
    groups = edges.get("groups") or edges.get("per_group") or edges
    gid = str(group_id)
    return _lookup_mapping_entry(groups, gid) or _lookup_mapping_entry(edges, gid)


def _arc_matches_want(arc: Mapping[str, Any], want: str | None) -> bool:
    if not want:
        return True
    fr = str(arc.get("from") or "").replace("\\", "/")
    to = str(arc.get("to") or "").replace("\\", "/")
    return fr == want or to == want


def _normalize_direction_arc(
    raw: Mapping[str, Any], direction: str, want: str | None
) -> dict[str, Any] | None:
    arc = dict(raw)
    arc["direction"] = direction
    if not _arc_matches_want(arc, want):
        return None
    return arc


def _maybe_direction_arc(
    raw: Any, direction: str, want: str | None
) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    return _normalize_direction_arc(raw, direction, want)


def _arcs_for_direction(
    entry: Mapping[str, Any], direction: str, want: str | None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in entry.get(direction) or []:
        arc = _maybe_direction_arc(raw, direction, want)
        if arc is not None:
            rows.append(arc)
    return rows


def _from_edges(
    edges: Mapping[str, Any],
    group_id: str | int,
    *,
    target_file: str | None,
) -> list[dict[str, Any]]:
    entry = _resolve_group_entry(edges, group_id)
    if entry is None:
        return []
    want = _normalize_want_file(target_file)
    rows: list[dict[str, Any]] = []
    for direction in ("outbound", "inbound"):
        rows.extend(_arcs_for_direction(entry, direction, want))
    return rows
