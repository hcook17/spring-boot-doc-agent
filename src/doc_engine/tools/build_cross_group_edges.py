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
        path = row.get("file")
        text = (row.get("match") or "").strip()
        if not path:
            continue
        m = PACKAGE_RE.match(text)
        if m:
            pkg = m.group(1)
            decl_files[pkg].add(path)
            stem = path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
            stem_index[(pkg, stem)] = path
            continue
        m = IMPORT_RE.match(text)
        if m:
            imports[path].append((m.group(2), bool(m.group(1))))

    return decl_files, stem_index, imports


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
        pkg = qualified[:-2]
        targets = sorted(decl_files.get(pkg, ()))
        return targets, ("package-fanout" if targets else "unresolved")

    name = qualified
    while "." in name:
        pkg, stem = name.rsplit(".", 1)
        hit = stem_index.get((pkg, stem))
        if hit is not None:
            return [hit], "exact"
        if pkg in decl_files:
            return sorted(decl_files[pkg]), "package-fanout"
        name = pkg  # shorten and retry: static member / nested class
    return [], "unresolved"


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


def build_report(groups_data: dict, signals_data: dict) -> dict:
    groups = groups_data["groups"]
    references = signals_data.get("evidence", {}).get("references", [])
    decl_files, stem_index, imports = parse_references(references)
    memb = build_membership(groups)
    group_ids = [g["id"] for g in groups]
    files_of = {g["id"]: set(g["files"]) for g in groups}

    per_group = {
        gid: {"outbound": [], "inbound": [], "same_package_outside": []}
        for gid in group_ids
    }

    seen = set()
    counts = collections.Counter()
    for src, entries in imports.items():
        for qualified, is_static in entries:
            targets, confidence = resolve_targets(qualified, decl_files, stem_index)
            if confidence == "unresolved":
                counts["unresolved_imports"] += 1
                continue
            for dst in targets:
                if dst == src or not is_cut(memb, src, dst):
                    continue
                key = (src, dst, qualified)
                if key in seen:
                    continue
                seen.add(key)
                counts["cut_arcs"] += 1
                counts[f"confidence_{confidence}"] += 1
                edge = {
                    "from": src, "to": dst, "via": qualified,
                    "confidence": confidence, "static_import": is_static,
                }
                for gid in memb.get(src, ()):
                    per_group[gid]["outbound"].append(edge)
                for gid in memb.get(dst, ()):
                    per_group[gid]["inbound"].append(edge)

    # Same-package neighbours as ADJACENCY, never a materialized clique:
    # a package with k files spanning two groups has O(k^2) cross pairs but
    # only O(k) members to name.
    for pkg, members in sorted(decl_files.items()):
        if len(members) < 2:
            continue
        for gid in group_ids:
            inside = sorted(members & files_of[gid])
            outside = sorted(f for f in members if gid not in memb.get(f, set()))
            if inside and outside:
                per_group[gid]["same_package_outside"].append(
                    {"package": pkg, "files_in_group": inside, "files_outside_group": outside}
                )
                counts["same_package_adjacency_rows"] += len(outside)

    broadcast_rows = len(references) * len(groups)
    shipped_rows = (
        sum(len(v["outbound"]) + len(v["inbound"]) for v in per_group.values())
        + counts["same_package_adjacency_rows"]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "repo_path": groups_data.get("repo_path"),
        "num_groups": len(groups),
        "references_rows": len(references),
        "stats": {
            "broadcast_rows_avoided": broadcast_rows,
            "rows_shipped": shipped_rows,
            "reduction_factor": round(broadcast_rows / shipped_rows, 1) if shipped_rows else None,
            **dict(counts),
        },
        "groups": {str(gid): per_group[gid] for gid in group_ids},
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
