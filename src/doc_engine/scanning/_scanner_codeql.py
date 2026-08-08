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
from doc_engine.scanning.covering import COVERING_RECEIPT_KEY
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

    @staticmethod
    def _version_hash_paths() -> List[str]:
        self_file = Path(__file__).resolve()
        paths = [
            str(self_file),
            str(self_file.parent / "support" / "_codeql_runner.py"),
        ]
        pack_dir = codeql_pack_dir()
        if pack_dir.is_dir():
            paths.extend(sorted(glob.glob(str(pack_dir / "*.ql"))))
        return paths

    @staticmethod
    def _update_digest_from_path(digest: Any, path: str) -> None:
        try:
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
        except OSError:
            return

    def version_hash(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self._version_hash_paths()):
            self._update_digest_from_path(digest, path)
        return digest.hexdigest()[:16]

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

        evidence, entity_candidates = self._bucket_codeql_rows(
            repo_path=repo_path,
            rows=rows,
            scan_context=scan_context,
        )
        receipt = self._covering_receipt_for_scan(scan_context)
        return {
            "evidence": evidence,
            "entity_table_map_candidates": entity_candidates,
            COVERING_RECEIPT_KEY: receipt,
        }

    def _bucket_codeql_rows(
        self,
        *,
        repo_path: str,
        rows: List[Dict[str, Any]],
        scan_context: Optional[ScanContext],
    ) -> tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        java_rels: Optional[set] = None
        if scan_context is not None:
            java_rels = {entry.rel_path for entry in scan_context.java_files}

        evidence: Dict[str, List[Dict[str, Any]]] = {}
        entity_candidates: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            self._ingest_codeql_row(
                repo_path=repo_path,
                row=row,
                java_rels=java_rels,
                evidence=evidence,
                entity_candidates=entity_candidates,
            )
        for bucket_rows in evidence.values():
            bucket_rows.sort(key=lambda item: (item["file"], item.get("line", 0)))
        return evidence, entity_candidates

    def _ingest_codeql_row(
        self,
        *,
        repo_path: str,
        row: Dict[str, Any],
        java_rels: Optional[set],
        evidence: Dict[str, List[Dict[str, Any]]],
        entity_candidates: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        rel = normalize_repo_path(repo_path, row.get("file", ""))
        if java_rels is not None and rel not in java_rels:
            return
        row["file"] = rel
        rule_id = row.get("rule_id", "")
        line = row.get("line", 1)
        max_lines = 40 if rule_id in {"persistence__entity", "persistence__repository"} else 10
        match_text = read_source_lines(repo_path, rel, line, max_lines=max_lines)
        bucket, _, _ = rule_id.partition("__")

        if rule_id == "persistence__entity":
            self._ingest_entity_row(
                repo_path=repo_path,
                rel=rel,
                row=row,
                match_text=match_text,
                rule_id=rule_id,
                entity_candidates=entity_candidates,
                evidence=evidence,
            )
            return

        entry = self._evidence_entry_from_codeql_row(
            rel=rel,
            row=row,
            match_text=match_text,
            rule_id=rule_id,
        )
        evidence.setdefault(bucket, []).append(entry)

    @staticmethod
    def _acked_java_paths(
        scan_context: Optional[ScanContext],
        expected_paths: List[str],
    ) -> List[str]:
        if scan_context is None:
            return expected_paths
        return sorted({entry.rel_path for entry in scan_context.java_files})

    def _covering_receipt_for_scan(
        self,
        scan_context: Optional[ScanContext],
    ) -> Dict[str, Any]:
        from doc_engine.scanning.covering import (
            build_receipt,
            java_scope_paths,
            subset_root,
        )

        sigs = dict(scan_context.file_signatures) if scan_context is not None else {}
        expected_paths = java_scope_paths(sigs)
        expected_root = subset_root(sigs, expected_paths)
        acked = self._acked_java_paths(scan_context, expected_paths)
        acked_root = subset_root(sigs, acked)
        status = "complete" if acked_root == expected_root else "failed"
        receipt = build_receipt(
            scanner=self.name,
            version_hash=self.version_hash(),
            scope="java",
            expected_subset_root=expected_root,
            acked_subset_root=acked_root,
            status=status,
            covered_count=len(acked),
            batches=1,
            error=None if status == "complete" else "codeql acked java subset mismatch",
        )
        if status == "failed":
            raise CodeQLError(receipt["error"] or "codeql covering receipt failed")
        return receipt

    @staticmethod
    def _inferred_entity_map_entry(rel: str, class_name: str) -> Dict[str, Any]:
        return {
            "file": rel,
            "table": to_snake_case(class_name),
            "table_name_source": "inferred-default-naming",
            "fqcn": class_name,
        }

    @staticmethod
    def _explicit_table_map_entry(
        *,
        rel: str,
        class_name: str,
        codeql_table: str,
        map_entry: Dict[str, Any],
    ) -> Dict[str, Any]:
        preserved_package = map_entry.get("package")
        preserved_fqcn = map_entry.get("fqcn")
        out = {
            "file": rel,
            "table": codeql_table,
            "table_name_source": "explicit",
            "fqcn": preserved_fqcn or class_name,
        }
        if preserved_package is not None:
            out["package"] = preserved_package
        return out

    @staticmethod
    def _base_entity_map_entry(
        *,
        rel: str,
        class_name: str,
        extracted: Optional[tuple],
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        if extracted is None:
            if not class_name:
                return None
            return class_name, CodeQLBackend._inferred_entity_map_entry(rel, class_name)
        return extracted

    @staticmethod
    def _entity_map_entry(
        *,
        rel: str,
        class_name: str,
        match_text: str,
        rule_id: str,
        extracted: Optional[tuple],
        codeql_table: Optional[str],
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        """Build (class_name, map_entry) for a persistence__entity CodeQL row.

        SoR: CodeQL result row. Derived: entity_table_map candidate entry.
        """
        built = CodeQLBackend._base_entity_map_entry(
            rel=rel, class_name=class_name, extracted=extracted,
        )
        if built is None:
            return None
        class_name, map_entry = built
        if codeql_table:
            map_entry = CodeQLBackend._explicit_table_map_entry(
                rel=rel,
                class_name=class_name,
                codeql_table=codeql_table,
                map_entry=map_entry,
            )
        elif extracted is None:
            map_entry = CodeQLBackend._inferred_entity_map_entry(rel, class_name)

        map_entry["rule_id"] = rule_id
        map_entry["match"] = first_line_match(match_text)
        return class_name, map_entry

    def _ingest_entity_row(
        self,
        *,
        repo_path: str,
        rel: str,
        row: Dict[str, Any],
        match_text: str,
        rule_id: str,
        entity_candidates: Dict[str, List[Dict[str, Any]]],
        evidence: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        """Record entity_table_map candidate + persistence evidence for one entity hit.

        SoR: CodeQL entity row. Derived: map candidate + evidence bucket entry.
        """
        header = read_source_lines(repo_path, rel, 1, max_lines=40)
        extracted = extract_entity(rel, match_text, package_source=header or None)
        class_name = row.get("class_name") if extracted is None else None
        built = self._entity_map_entry(
            rel=rel,
            class_name=class_name or "",
            match_text=match_text,
            rule_id=rule_id,
            extracted=extracted,
            codeql_table=row.get("table_name"),
        )
        if built is None:
            return
        class_name, map_entry = built
        entity_candidates.setdefault(class_name, []).append(map_entry)
        evidence.setdefault("persistence", []).append({
            "file": rel,
            "line": row.get("line"),
            "match": first_line_match(match_text),
            "rule_id": rule_id,
            "class_name": class_name,
        })

    @staticmethod
    def _apply_raw_query_fields(entry: Dict[str, Any], row: Dict[str, Any]) -> None:
        query_kind = row.get("query_kind", "jpql")
        query_text = row.get("query_text") or row.get("query")
        entry["query_kind"] = query_kind
        if query_text:
            entry["query"] = query_text

    @staticmethod
    def _apply_repository_fields(
        entry: Dict[str, Any],
        row: Dict[str, Any],
        match_text: str,
    ) -> None:
        entry.update(extract_repository(match_text))
        if not entry.get("entity") and row.get("entity_name"):
            entry["entity"] = row.get("entity_name")

    @staticmethod
    def _evidence_entry_from_codeql_row(
        *,
        rel: str,
        row: Dict[str, Any],
        match_text: str,
        rule_id: str,
    ) -> Dict[str, Any]:
        """Build a non-entity evidence entry from one CodeQL result row.

        SoR: CodeQL result row. Derived: evidence-map entry (not entity map).
        """
        entry: Dict[str, Any] = {
            "file": rel,
            "line": row.get("line"),
            "match": first_line_match(match_text),
            "rule_id": rule_id,
        }
        if rule_id == "raw_queries__query":
            CodeQLBackend._apply_raw_query_fields(entry, row)
        elif rule_id == "persistence__repository":
            CodeQLBackend._apply_repository_fields(entry, row, match_text)
        return entry
