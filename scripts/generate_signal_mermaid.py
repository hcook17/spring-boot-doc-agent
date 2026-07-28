#!/usr/bin/env python3
"""Generate Mermaid diagrams from a spring_signals.json file.

Produces two diagrams:
1. erDiagram — from entity_table_map, plus persistence relations if they can
   be parsed from the match text.
2. flowchart TD — from evidence.* grouped by rule_id, showing signal counts per
   bucket and rule.

Usage:
    python3 scripts/generate_signal_mermaid.py <spring_signals.json> [out.md]
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional


def _load_signals(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sanitize_mermaid_id(name: str) -> str:
    """Mermaid IDs must be alphanumeric + underscore; collapse the rest."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _extract_relation_type(match: str) -> Optional[str]:
    """Best-effort extraction of @OneToMany / @ManyToOne / @OneToOne / @ManyToMany."""
    m = re.search(r"@(\w+)\s*\(", match)
    if not m:
        return None
    ann = m.group(1)
    if ann in {"OneToMany", "ManyToOne", "OneToOne", "ManyToMany"}:
        return ann
    return None


def _extract_target_entity(match: str) -> Optional[str]:
    """Try to find a target entity in a generic type like List<TargetEntity>."""
    m = re.search(r"(?:List|Set|Collection|Map)<\s*([A-Z][A-Za-z0-9_]*)\s*>", match)
    if m:
        return m.group(1)
    # Fallback: first capitalized word after the annotation that looks like a class.
    m = re.search(r"@\w+\([^)]*\)\s*(?:\n\s+)?(?:private\s+)?(?:\w+\s+)?([A-Z][A-Za-z0-9_]+)", match)
    if m:
        return m.group(1)
    return None


def _extract_mapped_by(match: str) -> Optional[str]:
    m = re.search(r'mappedBy\s*=\s*"([^"]+)"', match)
    if m:
        return m.group(1)
    return None


def _entity_name_from_path(file_path: str) -> Optional[str]:
    """Derive a simple class name from a Java file path."""
    base = os.path.basename(file_path)
    if base.endswith(".java"):
        return base[:-5]
    return None


def generate_er_diagram(data: Dict) -> str:
    """Build an erDiagram from entity_table_map + persistence relation rows."""
    entity_map = data.get("entity_table_map", {})
    evidence = data.get("evidence", {})
    persistence_rows = evidence.get("persistence", [])

    lines = ["erDiagram"]

    # Entities
    for class_name in sorted(entity_map.keys()):
        entry = entity_map[class_name]
        table = entry.get("table", class_name)
        source = entry.get("table_name_source", "")
        node_id = _sanitize_mermaid_id(class_name)
        lines.append(f"    {node_id} {{")
        lines.append(f"        string table \"{table}\"")
        if source:
            lines.append(f"        string source \"{source}\"")
        lines.append("    }")

    # Relations: parse from persistence__relation rows. We need the owning entity,
    # which we infer from the file path.
    seen_rels = set()
    for row in persistence_rows:
        if row.get("rule_id") != "persistence__relation":
            continue
        match = row.get("match", "")
        rel_type = _extract_relation_type(match)
        if not rel_type:
            continue
        source_class = _entity_name_from_path(row.get("file", ""))
        target_class = _extract_target_entity(match)
        if not source_class or not target_class:
            continue
        if source_class not in entity_map or target_class not in entity_map:
            continue
        mapped_by = _extract_mapped_by(match)
        # Deduplicate a little: source-target-type is enough for a sketch.
        key = (source_class, target_class, rel_type)
        if key in seen_rels:
            continue
        seen_rels.add(key)
        sid = _sanitize_mermaid_id(source_class)
        tid = _sanitize_mermaid_id(target_class)
        label = rel_type
        if mapped_by:
            label += f' mappedBy="{mapped_by}"'
        cardinality = {
            "OneToMany": "1 : many",
            "ManyToOne": "many : 1",
            "OneToOne": "1 : 1",
            "ManyToMany": "many : many",
        }.get(rel_type, rel_type)
        lines.append(f'    {sid} {cardinality} {tid} : "{label}"')

    return "\n".join(lines) + "\n"


def generate_flow_graph(data: Dict) -> str:
    """Build a flowchart TD from evidence grouped by rule_id."""
    evidence = data.get("evidence", {})

    # Count per rule_id across all buckets.
    counts: Counter[str] = Counter()
    bucket_counts: Dict[str, Counter[str]] = {}
    for bucket, rows in evidence.items():
        bucket_counts[bucket] = Counter()
        for row in rows:
            rid = row.get("rule_id")
            if rid:
                counts[rid] += 1
                bucket_counts[bucket][rid] += 1

    lines = ["flowchart TD"]
    lines.append("    Sources[Java / Gradle / properties sources]")
    lines.append("    Sources --> spring_signal_scan")
    lines.append("    spring_signal_scan --> Buckets[evidence buckets]")

    for bucket in sorted(bucket_counts.keys()):
        rules = bucket_counts[bucket]
        if not rules:
            continue
        subgraph_id = _sanitize_mermaid_id(bucket)
        lines.append(f"    subgraph {subgraph_id} [{bucket}]")
        for rid in sorted(rules.keys()):
            node_id = _sanitize_mermaid_id(rid)
            lines.append(f'        {node_id}("{rid}: {rules[rid]}")')
        lines.append("    end")
        lines.append(f"    Buckets --> {subgraph_id}")

    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python3 scripts/generate_signal_mermaid.py <spring_signals.json> [out.md]", file=sys.stderr)
        return 1

    signals_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    data = _load_signals(signals_path)
    repo_path = data.get("repo_path", "unknown")
    schema_version = data.get("schema_version", "unknown")
    files_scanned = data.get("files_scanned", {})

    output_lines = [
        "# Auto-generated signal diagrams",
        "",
        f"- **repo**: `{repo_path}`",
        f"- **schema_version**: {schema_version}",
        f"- **files_scanned**: {files_scanned}",
        "",
        "## ER diagram",
        "",
        "```mermaid",
    ]
    output_lines.extend(generate_er_diagram(data).splitlines())
    output_lines.extend([
        "```",
        "",
        "## Signal flow graph",
        "",
        "```mermaid",
    ])
    output_lines.extend(generate_flow_graph(data).splitlines())
    output_lines.append("```")
    output_lines.append("")

    text = "\n".join(output_lines)

    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(f"wrote {out_path}")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
