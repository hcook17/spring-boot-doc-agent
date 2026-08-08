#!/usr/bin/env python3
"""

Run with: python -m doc_engine.tools.build_cross_group_edges

build_cross_group_edges.py — resolve cross-group file relationships once,
deterministically, instead of broadcasting the whole reference table to
every Stage-1 subagent and asking each to infer them.

THE PROBLEM THIS REPLACES
Stage 1 used to hand every file-summarizer dispatch the *entire* repo-wide
`references` bucket, because a group's own file list gives it no visibility
outside itself. Each dispatch then re-derived cross-group relationships by
string-matching its files' imports against that table — a join, executed by
a language model, once per group, with the whole right-hand side in context.

Two things are wrong with that, and the second matters more:

  Cost. Broadcasting is g*|R| rows. Group count g = ceil(T/M) grows with
  repo size, and |R| grows with repo size, so the shipped volume is
  quadratic. Measured on a 109-file sample repo: 1030 rows shipped, 14
  actually load-bearing.

  Kind. It is mechanical work done probabilistically. The relation is
  exactly computable from `package`/`import` lines; nothing about it needs
  inference. Computed here it becomes a fact with file:line provenance
  (taggable [Evidenced — ...]) rather than an LLM guess that the tag
  grammar cannot honestly label.

This is a broadcast join replaced by a partitioned one: build a package
index once (hash join, build side = declarations), probe it with imports,
then emit each group only the arcs on its own boundary.

THREE THINGS THAT ARE EASY TO GET WRONG, ALL HANDLED HERE

1. The grouping is a COVER, not a partition — partition_repo.py overlaps
   adjacent groups by ~10% of tokens, so a file can belong to two groups.
   An arc is therefore cut iff NO group contains both endpoints
   (memb(u) & memb(v) == empty), not "owner(u) != owner(v)". A single
   file->group map is ill-defined here and silently wrong.

2. Resolve imports to a TYPE, not a package. `import com.x.Foo` names a
   type; keying the join on the package fans out to every file in it,
   making the join many-to-many with output proportional to package size.
   Keying on (package, type-stem) is a functional lookup — one arc.
   Measured on the same sample: package-keyed 61 arcs, type-keyed 14.

3. Same-package relationships are an EQUIVALENCE relation, so each package
   induces a clique. Materializing cross-group pairs costs O(sum |P|^2) and
   would dominate everything else — on the sample, 111 pairs against 14
   import arcs. So they are emitted as adjacency (per group: the package's
   files that live outside it), never as an edge list.

WHERE THE ECONOMY COMES FROM, AND WHEN IT STOPS
The cut stays small because partition_repo.py walks the tree depth-first
and, in Java, packages ARE directories — so same-package files land
contiguously and the densest arc class is intra-group by construction.
That is a property of Java's source layout, not of the partitioner, which
optimizes token budget and makes no cut guarantee at all. Expect this to
degrade for languages where namespace and directory are independent.

SCOPE
Import/package text only, which is what `references` records. It does not
resolve interface-mediated injection (an @Autowired interface type needs
matching implementers, which an import graph cannot show), and wildcard
imports remain irreducibly many-to-many. Both are marked in the output
rather than hidden — see `confidence` on each edge.

Run with:
    python -m doc_engine.tools.build_cross_group_edges groups.json spring_signals.json \
        --out cross_group_edges.json
"""

import argparse
import collections
import json
import re
import sys
from typing import Dict, List, Set, Tuple

SCHEMA_VERSION = 1

PACKAGE_RE = re.compile(r"^package\s+([\w.]+)\s*;")
IMPORT_RE = re.compile(r"^import\s+(static\s+)?([\w.*]+)\s*;")


def _type_stem_from_path(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _index_package_declaration(
    path: str,
    package_name: str,
    decl_files: Dict[str, Set[str]],
    stem_index: Dict[Tuple[str, str], str],
) -> None:
    decl_files[package_name].add(path)
    stem_index[(package_name, _type_stem_from_path(path))] = path


def _ingest_reference_row(
    row: dict,
    decl_files: Dict[str, Set[str]],
    stem_index: Dict[Tuple[str, str], str],
    imports: Dict[str, List[Tuple[str, bool]]],
) -> None:
    path = row.get("file")
    text = (row.get("match") or "").strip()
    if not path:
        return
    package_match = PACKAGE_RE.match(text)
    if package_match:
        _index_package_declaration(
            path, package_match.group(1), decl_files, stem_index
        )
        return
    import_match = IMPORT_RE.match(text)
    if import_match:
        imports[path].append(
            (import_match.group(2), bool(import_match.group(1)))
        )


def parse_references(references: List[dict]):
    """Split the `references` bucket into the two indexes the join needs.

    Returns (decl_files, stem_index, imports):
      decl_files[package]        -> set of files declaring it
      stem_index[(package, Type)]-> the file whose name is Type.java
      imports[file]              -> list of (qualified_name, is_static)
    """
    decl_files: Dict[str, Set[str]] = collections.defaultdict(set)
    stem_index: Dict[Tuple[str, str], str] = {}
    imports: Dict[str, List[Tuple[str, bool]]] = collections.defaultdict(list)
    for row in references:
        _ingest_reference_row(row, decl_files, stem_index, imports)
    return decl_files, stem_index, imports


def _resolve_wildcard_import(qualified: str, decl_files) -> Tuple[List[str], str]:
    package_name = qualified[:-2]
    targets = sorted(decl_files.get(package_name, ()))
    return targets, ("package-fanout" if targets else "unresolved")


def _resolve_type_import(qualified: str, decl_files, stem_index) -> Tuple[List[str], str]:
    name = qualified
    while "." in name:
        package_name, stem = name.rsplit(".", 1)
        hit = stem_index.get((package_name, stem))
        if hit is not None:
            return [hit], "exact"
        if package_name in decl_files:
            return sorted(decl_files[package_name]), "package-fanout"
        name = package_name  # shorten and retry: static member / nested class
    return [], "unresolved"


def resolve_targets(qualified: str, decl_files, stem_index) -> Tuple[List[str], str]:
    """Resolve one imported qualified name to the file(s) that declare it.

    Returns (target_files, confidence) where confidence is one of:
      "exact"           — resolved to a single declaring file by type name
      "package-fanout"  — resolved only to a package; every file in it is a
                          candidate (wildcard imports, or a type whose file
                          name doesn't match the type name)
      "unresolved"      — nothing in this repo declares it (third-party)

    Static-member and nested-class imports are handled by shortening the
    name one component at a time: `import static com.x.Foo.BAR` first tries
    (com.x.Foo, BAR), fails, then tries (com.x, Foo) and resolves. Without
    this loop those imports resolve to nothing and vanish silently, which is
    the single easiest way to under-report the cut.
    """
    if qualified.endswith(".*"):
        return _resolve_wildcard_import(qualified, decl_files)
    return _resolve_type_import(qualified, decl_files, stem_index)


def build_membership(groups: List[dict]) -> Dict[str, Set[int]]:
    """file -> set of group ids. A set, not a scalar: the grouping is a
    cover with ~10% overlap, so a file can legitimately belong to two."""
    memb: Dict[str, Set[int]] = collections.defaultdict(set)
    for group in groups:
        for path in group["files"]:
            memb[path].add(group["id"])
    return memb


def is_cut(memb: Dict[str, Set[int]], u: str, v: str) -> bool:
    """True iff no single group contains both endpoints — the correct
    predicate for a cover. `owner(u) != owner(v)` is not well defined."""
    return not (memb.get(u, set()) & memb.get(v, set()))


def _empty_per_group_buckets(group_ids: List[int]) -> Dict[int, dict]:
    return {
        group_id: {"outbound": [], "inbound": [], "same_package_outside": []}
        for group_id in group_ids
    }


def _append_cut_edge(
    per_group: Dict[int, dict],
    memb: Dict[str, Set[int]],
    edge: dict,
) -> None:
    for group_id in memb.get(edge["from"], ()):
        per_group[group_id]["outbound"].append(edge)
    for group_id in memb.get(edge["to"], ()):
        per_group[group_id]["inbound"].append(edge)


def _maybe_emit_cut_arc(
    source_path: str,
    destination_path: str,
    qualified: str,
    confidence: str,
    is_static: bool,
    memb: Dict[str, Set[int]],
    per_group: Dict[int, dict],
    seen: Set[Tuple[str, str, str]],
    counts: collections.Counter,
) -> None:
    if destination_path == source_path or not is_cut(memb, source_path, destination_path):
        return
    edge_key = (source_path, destination_path, qualified)
    if edge_key in seen:
        return
    seen.add(edge_key)
    counts["cut_arcs"] += 1
    counts[f"confidence_{confidence}"] += 1
    edge = {
        "from": source_path,
        "to": destination_path,
        "via": qualified,
        "confidence": confidence,
        "static_import": is_static,
    }
    _append_cut_edge(per_group, memb, edge)


def _emit_targets_for_import(
    source_path: str,
    qualified: str,
    is_static: bool,
    decl_files,
    stem_index,
    memb: Dict[str, Set[int]],
    per_group: Dict[int, dict],
    seen: Set[Tuple[str, str, str]],
    counts: collections.Counter,
) -> None:
    targets, confidence = resolve_targets(qualified, decl_files, stem_index)
    if confidence == "unresolved":
        counts["unresolved_imports"] += 1
        return
    for destination_path in targets:
        _maybe_emit_cut_arc(
            source_path,
            destination_path,
            qualified,
            confidence,
            is_static,
            memb,
            per_group,
            seen,
            counts,
        )


def _record_resolved_import_arcs(
    imports: Dict[str, List[Tuple[str, bool]]],
    decl_files,
    stem_index,
    memb: Dict[str, Set[int]],
    per_group: Dict[int, dict],
    counts: collections.Counter,
) -> None:
    """Emit cut import arcs into per-group outbound/inbound buckets."""
    seen: Set[Tuple[str, str, str]] = set()
    for source_path, entries in imports.items():
        for qualified, is_static in entries:
            _emit_targets_for_import(
                source_path,
                qualified,
                is_static,
                decl_files,
                stem_index,
                memb,
                per_group,
                seen,
                counts,
            )


def _adjacency_outside_group(
    members: Set[str],
    group_id: int,
    files_of: Dict[int, Set[str]],
    memb: Dict[str, Set[int]],
) -> Tuple[List[str], List[str]]:
    inside = sorted(members & files_of[group_id])
    outside = sorted(
        path for path in members if group_id not in memb.get(path, set())
    )
    return inside, outside


def _record_package_group_adjacency(
    package_name: str,
    members: Set[str],
    group_id: int,
    files_of: Dict[int, Set[str]],
    memb: Dict[str, Set[int]],
    per_group: Dict[int, dict],
    counts: collections.Counter,
) -> None:
    inside, outside = _adjacency_outside_group(members, group_id, files_of, memb)
    if not inside or not outside:
        return
    per_group[group_id]["same_package_outside"].append(
        {
            "package": package_name,
            "files_in_group": inside,
            "files_outside_group": outside,
        }
    )
    counts["same_package_adjacency_rows"] += len(outside)


def _record_same_package_adjacency(
    decl_files: Dict[str, Set[str]],
    group_ids: List[int],
    files_of: Dict[int, Set[str]],
    memb: Dict[str, Set[int]],
    per_group: Dict[int, dict],
    counts: collections.Counter,
) -> None:
    """Same-package neighbours as adjacency, never a materialized clique."""
    for package_name, members in sorted(decl_files.items()):
        if len(members) < 2:
            continue
        for group_id in group_ids:
            _record_package_group_adjacency(
                package_name, members, group_id, files_of, memb, per_group, counts
            )


def _shipping_stats(
    references: List[dict],
    groups: List[dict],
    per_group: Dict[int, dict],
    counts: collections.Counter,
) -> dict:
    broadcast_rows = len(references) * len(groups)
    shipped_rows = (
        sum(
            len(bucket["outbound"]) + len(bucket["inbound"])
            for bucket in per_group.values()
        )
        + counts["same_package_adjacency_rows"]
    )
    reduction_factor = (
        round(broadcast_rows / shipped_rows, 1) if shipped_rows else None
    )
    return {
        "broadcast_rows_avoided": broadcast_rows,
        "rows_shipped": shipped_rows,
        "reduction_factor": reduction_factor,
        **dict(counts),
    }


def build_report(groups_data: dict, signals_data: dict) -> dict:
    groups = groups_data["groups"]
    references = signals_data.get("evidence", {}).get("references", [])
    decl_files, stem_index, imports = parse_references(references)
    memb = build_membership(groups)
    group_ids = [group["id"] for group in groups]
    files_of = {group["id"]: set(group["files"]) for group in groups}
    per_group = _empty_per_group_buckets(group_ids)
    counts: collections.Counter = collections.Counter()

    _record_resolved_import_arcs(
        imports, decl_files, stem_index, memb, per_group, counts
    )
    _record_same_package_adjacency(
        decl_files, group_ids, files_of, memb, per_group, counts
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "repo_path": groups_data.get("repo_path"),
        "num_groups": len(groups),
        "references_rows": len(references),
        "stats": _shipping_stats(references, groups, per_group, counts),
        "groups": {str(group_id): per_group[group_id] for group_id in group_ids},
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("groups_file", help="groups.json from partition_repo.py")
    ap.add_argument("signals_file", help="spring_signals.json from spring_signal_scan.py")
    ap.add_argument("--out", default="cross_group_edges.json")
    args = ap.parse_args()

    try:
        groups_data = json.load(open(args.groups_file, encoding="utf-8"))
        signals_data = json.load(open(args.signals_file, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    report = build_report(groups_data, signals_data)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)

    s = report["stats"]
    print(
        f"Wrote {args.out}. {report['num_groups']} groups, "
        f"{s.get('cut_arcs', 0)} cut arcs "
        f"(exact={s.get('confidence_exact', 0)}, fanout={s.get('confidence_package-fanout', 0)}), "
        f"{s.get('same_package_adjacency_rows', 0)} same-package adjacency rows. "
        f"{s['rows_shipped']} rows shipped vs {s['broadcast_rows_avoided']} broadcast"
        # reduction_factor is None when nothing was shipped (a single-group
        # repo has no cut by definition), and interpolating that printed
        # "Nonex reduction". The JSON was always correct; only this line lied.
        + (f" ({s['reduction_factor']}x reduction)." if s.get("reduction_factor") else ".")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
