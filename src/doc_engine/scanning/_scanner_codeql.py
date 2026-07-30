#!/usr/bin/env python3
"""CodeQL scanner backend."""

import glob
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from doc_engine.core.context import ScanContext
from doc_engine.scanning._paths import codeql_pack_dir
from doc_engine.scanning._scanner_base import ScannerBackend
from doc_engine.scanning.java_extract import (
    extract_entity,
    extract_repository,
    first_line_match,
    normalize_repo_path,
    read_source_lines,
    to_snake_case,
)
from doc_engine.scanning.support._codeql_runner import CodeQLError, scan_with_codeql


class CodeQLBackend(ScannerBackend):
    """Scanner backend that extracts Java structural signals via CodeQL."""

    @property
    def name(self) -> str:
        return "codeql"

    def version_hash(self) -> str:
        h = hashlib.sha256()
        paths = [
            str(Path(__file__).resolve()),
            str(Path(__file__).resolve().parent / "support" / "_codeql_runner.py"),
        ]
        pack_dir = codeql_pack_dir()
        if pack_dir.is_dir():
            for ql in sorted(glob.glob(str(pack_dir / "*.ql"))):
                paths.append(ql)
        for p in sorted(paths):
            try:
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
            except OSError:
                pass
        return h.hexdigest()[:16]

    def scan(
        self,
        repo_path: str,
        build_command: Optional[str] = None,
        db_path: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        repo_path = os.path.abspath(repo_path)
        scan_context: Optional[ScanContext] = kwargs.get("scan_context")

        if build_command is None:
            raise CodeQLError(
                "CodeQL backend requires a build command. "
                "Pass --build-command or use detect_build_command()."
            )

        rows = scan_with_codeql(
            Path(repo_path),
            build_command,
            pack_dir=codeql_pack_dir(),
            db_path=Path(db_path) if db_path else None,
            keep_database=True,
            scanner_version=self.version_hash(),
            scan_context=scan_context,
        )

        java_rels: Optional[set] = None
        if scan_context is not None:
            java_rels = {entry.rel_path for entry in scan_context.java_files}

        evidence: Dict[str, List[Dict[str, Any]]] = {}
        entity_candidates: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            rel = normalize_repo_path(repo_path, row.get("file", ""))
            if java_rels is not None and rel not in java_rels:
                continue
            row["file"] = rel
            rule_id = row.get("rule_id", "")
            line = row.get("line", 1)
            max_lines = 40 if rule_id in {"persistence__entity", "persistence__repository"} else 10
            match_text = read_source_lines(repo_path, rel, line, max_lines=max_lines)
            bucket, _, _ = rule_id.partition("__")

            if rule_id == "persistence__entity":
                header = read_source_lines(repo_path, rel, 1, max_lines=40)
                extracted = extract_entity(rel, match_text, package_source=header or None)
                if extracted is None:
                    class_name = row.get("class_name")
                    if not class_name:
                        continue
                    map_entry = {
                        "file": rel,
                        "table": to_snake_case(class_name),
                        "table_name_source": "inferred-default-naming",
                        "fqcn": class_name,
                    }
                else:
                    class_name, map_entry = extracted

                codeql_table = row.get("table_name")
                if codeql_table:
                    preserved_pkg = map_entry.get("package")
                    preserved_fqcn = map_entry.get("fqcn")
                    map_entry = {
                        "file": rel,
                        "table": codeql_table,
                        "table_name_source": "explicit",
                        "fqcn": preserved_fqcn or class_name,
                    }
                    if preserved_pkg is not None:
                        map_entry["package"] = preserved_pkg
                elif extracted is None:
                    map_entry = {
                        "file": rel,
                        "table": to_snake_case(class_name),
                        "table_name_source": "inferred-default-naming",
                        "fqcn": class_name,
                    }

                map_entry["rule_id"] = rule_id
                map_entry["match"] = first_line_match(match_text)
                entity_candidates.setdefault(class_name, []).append(map_entry)
                evidence.setdefault("persistence", []).append({
                    "file": rel,
                    "line": row.get("line"),
                    "match": first_line_match(match_text),
                    "rule_id": rule_id,
                    "class_name": class_name,
                })
                continue

            entry: Dict[str, Any] = {
                "file": rel,
                "line": row.get("line"),
                "match": first_line_match(match_text),
                "rule_id": rule_id,
            }
            if rule_id == "raw_queries__query":
                query_kind = row.get("query_kind", "jpql")
                query_text = row.get("query_text") or row.get("query")
                entry["query_kind"] = query_kind
                if query_text:
                    entry["query"] = query_text
            elif rule_id == "persistence__repository":
                entry.update(extract_repository(match_text))
                if not entry.get("entity") and row.get("entity_name"):
                    entry["entity"] = row.get("entity_name")

            evidence.setdefault(bucket, []).append(entry)

        for bucket in evidence.values():
            bucket.sort(key=lambda e: (e["file"], e.get("line", 0)))

        return {"evidence": evidence, "entity_table_map_candidates": entity_candidates}
