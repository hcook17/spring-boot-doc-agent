#!/usr/bin/env python3
"""ast-grep scanner backend — fail-closed extraction + covering receipts."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from doc_engine.core.context import FileEntry, ScanContext
from doc_engine.core.excludes import load_gitignore_spec
from doc_engine.scanning._paths import ast_grep_rules_path
from doc_engine.scanning._scanner_base import ScannerBackend
from doc_engine.scanning.covering import (
    COVERING_RECEIPT_KEY,
    build_receipt,
    java_scope_paths,
    subset_root,
)
from doc_engine.scanning.java_extract import (
    extract_entity,
    extract_query_from_astgrep_args,
    extract_repository,
    first_line_match,
    read_source_lines,
)

RULE_FILE = ast_grep_rules_path()

# Windows CreateProcess fails with WinError 206 when hundreds of absolute paths
# are passed as separate argv entries. Chunking preserves ScanContext inventory.
_PATH_LIST_CHAR_LIMIT = 7000 if sys.platform == "win32" else 2 ** 31

_EVIDENCE_BUCKETS = {
    "api_surface", "outbound_clients", "messaging", "persistence",
    "raw_queries", "security", "configuration", "error_handling",
    "observability", "deployment", "testing", "references",
}


def _argv_char_len(parts: List[str]) -> int:
    return sum(len(part) + 1 for part in parts)


def _flush_path_chunk(
    chunks: List[List[str]],
    current: List[str],
) -> List[str]:
    """Append *current* to *chunks* and return a fresh empty chunk list."""
    chunks.append(current)
    return []


def _append_path_within_budget(
    path: str,
    budget: int,
    chunks: List[List[str]],
    current: List[str],
    current_len: int,
) -> tuple[List[str], int]:
    """Add one path to the active chunk, flushing when the budget would break."""
    cost = len(path) + 1
    if current and current_len + cost > budget:
        current = _flush_path_chunk(chunks, current)
        current_len = 0
    current.append(path)
    current_len += cost
    if current_len > budget and len(current) == 1:
        current = _flush_path_chunk(chunks, current)
        current_len = 0
    return current, current_len


def chunk_paths_for_argv(
    base_argv: List[str],
    paths: List[str],
    limit: int,
) -> List[List[str]]:
    """Partition ``paths`` so each ``base_argv + chunk`` stays within ``limit`` chars."""
    if not paths:
        return []
    budget = max(limit - _argv_char_len(base_argv), 1)
    chunks: List[List[str]] = []
    current: List[str] = []
    current_len = 0
    for path in paths:
        current, current_len = _append_path_within_budget(
            path, budget, chunks, current, current_len
        )
    if current:
        chunks.append(current)
    return chunks


def _is_windows_cmdline_too_long(exc: OSError) -> bool:
    return getattr(exc, "winerror", None) == 206


def _astgrep_errors():
    from doc_engine.scanning.spring import AstGrepError, AstGrepNotFoundError
    return AstGrepError, AstGrepNotFoundError


def inventory_root_empty() -> str:
    from doc_engine.scanning.covering import inventory_root
    return inventory_root({})


def _parse_ast_grep_stdout(stdout: str) -> List[Dict[str, Any]]:
    """Parse compact JSON stdout from one ast-grep invocation."""
    AstGrepError, _ = _astgrep_errors()
    try:
        return json.loads(stdout) if stdout.strip() else []
    except json.JSONDecodeError as exc:
        raise AstGrepError(f"ast-grep output is not valid JSON: {exc}") from exc


def _enrich_query_entry(entry: Dict[str, Any], match: Dict[str, Any]) -> None:
    """Attach query_kind / query text extracted from ast-grep metaVariables."""
    multi_args = match.get("metaVariables", {}).get("multi", {}).get("ARGS", [])
    query_kind, query_text = extract_query_from_astgrep_args(multi_args)
    entry["query_kind"] = query_kind
    if query_text is not None:
        entry["query"] = query_text


class AstGrepBackend(ScannerBackend):
    """Scanner backend that extracts Java structural signals via ast-grep."""

    @property
    def name(self) -> str:
        return "ast-grep"

    def version_hash(self) -> str:
        digest = hashlib.sha256()
        paths = [
            str(Path(__file__).resolve()),
            str(RULE_FILE),
        ]
        for path in sorted(paths):
            try:
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(chunk)
            except OSError:
                pass
        return digest.hexdigest()[:16]

    def _find_ast_grep(self) -> Optional[str]:
        return shutil.which("ast-grep")

    def _scan_base_argv(self, ast_grep_path: str) -> List[str]:
        return [
            ast_grep_path, "scan",
            "--rule", str(RULE_FILE),
            "--json=compact",
            "--no-ignore", "hidden",
            "--no-ignore", "dot",
            "--no-ignore", "vcs",
            "--no-ignore", "parent",
            "--no-ignore", "global",
            "--no-ignore", "exclude",
        ]

    def _require_ast_grep_ready(self) -> str:
        """Return the ast-grep binary path or raise a NotFound error."""
        _, AstGrepNotFoundError = _astgrep_errors()
        ast_grep_path = self._find_ast_grep()
        if ast_grep_path is None:
            raise AstGrepNotFoundError(
                "ast-grep binary is not on PATH. "
                "Install ast-grep to enable this backend."
            )
        if not RULE_FILE.is_file():
            raise AstGrepNotFoundError(f"ast-grep rule file not found: {RULE_FILE}")
        return ast_grep_path

    def _invoke_ast_grep(self, cmd: List[str]) -> List[Dict[str, Any]]:
        """Run one ast-grep argv; raise on any process/JSON failure (fail-closed)."""
        AstGrepError, _ = _astgrep_errors()
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            if _is_windows_cmdline_too_long(exc):
                raise
            raise AstGrepError(f"ast-grep failed to start: {exc}") from exc
        if proc.returncode != 0:
            raise AstGrepError(
                f"ast-grep exited with status {proc.returncode}: "
                f"{(proc.stderr or '').strip()}"
            )
        return _parse_ast_grep_stdout(proc.stdout)

    def _bisect_oversized_chunk(
        self,
        base_argv: List[str],
        chunk: List[str],
        char_limit: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Bisect a WinError-206 chunk; return (matches, additional_bisects)."""
        AstGrepError, _ = _astgrep_errors()
        if len(chunk) == 1:
            raise AstGrepError(
                "single Java path exceeds CreateProcess argv limit; "
                f"incomplete inventory: {chunk[0]}"
            )
        mid = len(chunk) // 2
        print(
            "warning: CreateProcess WinError 206 on a path batch "
            f"({len(chunk)} files); bisecting and retrying",
            file=sys.stderr,
        )
        left, _left_batches, left_bisects = self._invoke_ast_grep_chunked(
            base_argv, chunk[:mid], limit=char_limit,
        )
        right, _right_batches, right_bisects = self._invoke_ast_grep_chunked(
            base_argv, chunk[mid:], limit=char_limit,
        )
        return left + right, 1 + left_bisects + right_bisects

    def _scan_one_chunk(
        self,
        base_argv: List[str],
        chunk: List[str],
        char_limit: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Scan one argv chunk; bisect on WinError 206. Returns (matches, bisects)."""
        try:
            return self._invoke_ast_grep(base_argv + chunk), 0
        except OSError as exc:
            if not _is_windows_cmdline_too_long(exc):
                raise
            return self._bisect_oversized_chunk(base_argv, chunk, char_limit)

    def _invoke_ast_grep_chunked(
        self,
        base_argv: List[str],
        paths: List[str],
        *,
        limit: Optional[int] = None,
    ) -> tuple[List[Dict[str, Any]], int, int]:
        """Scan paths in argv chunks. Returns (matches, batch_count, bisects)."""
        char_limit = _PATH_LIST_CHAR_LIMIT if limit is None else limit
        chunks = chunk_paths_for_argv(base_argv, paths, char_limit)
        if len(chunks) > 1:
            print(
                "warning: Java path list exceeds this platform's command-line "
                f"budget ({len(paths)} files); scanning in {len(chunks)} "
                "ast-grep batches to preserve ScanContext inventory",
                file=sys.stderr,
            )
        matches: List[Dict[str, Any]] = []
        bisects = 0
        for chunk in chunks:
            chunk_matches, chunk_bisects = self._scan_one_chunk(
                base_argv, chunk, char_limit
            )
            matches.extend(chunk_matches)
            bisects += chunk_bisects
        return matches, len(chunks), bisects

    def _covering_receipt(
        self,
        *,
        expected_root: str,
        acked_root: str,
        covered_count: int,
        batches: int,
        error: Optional[str] = None,
        winerror_206_bisects: int = 0,
    ) -> Dict[str, Any]:
        """Build a covering receipt and raise when status is failed."""
        AstGrepError, _ = _astgrep_errors()
        status = "complete" if acked_root == expected_root else "failed"
        if status == "failed" and error is None:
            error = "acked java subset does not match ScanContext inventory"
        receipt = build_receipt(
            scanner=self.name,
            version_hash=self.version_hash(),
            scope="java",
            expected_subset_root=expected_root,
            acked_subset_root=acked_root,
            status=status,
            covered_count=covered_count,
            batches=batches,
            winerror_206_bisects=winerror_206_bisects,
            error=error if status == "failed" else None,
        )
        if status == "failed":
            raise AstGrepError(error or "ast-grep covering receipt failed")
        return receipt

    def _empty_java_inventory_result(
        self,
        *,
        sigs: Dict[str, str],
        expected_root: str,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Covering result when ScanContext supplies an empty java_files list."""
        acked_root = subset_root(sigs, []) if sigs else expected_root
        error = (
            None
            if acked_root == expected_root
            else "empty java_files inventory does not cover ScanContext java signatures"
        )
        receipt = self._covering_receipt(
            expected_root=expected_root,
            acked_root=acked_root,
            covered_count=0,
            batches=0,
            error=error,
        )
        return [], receipt

    def _scan_java_inventory(
        self,
        base_argv: List[str],
        java_files: List[FileEntry],
        *,
        sigs: Dict[str, str],
        expected_root: str,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Scan an explicit java_files inventory and prove covering."""
        paths = [entry.full_path for entry in java_files]
        acked_rels = [entry.rel_path for entry in java_files]
        matches, batches, bisects = self._invoke_ast_grep_chunked(base_argv, paths)
        acked_root = subset_root(sigs, acked_rels) if sigs else expected_root
        receipt = self._covering_receipt(
            expected_root=expected_root,
            acked_root=acked_root,
            covered_count=len(acked_rels),
            batches=batches,
            winerror_206_bisects=bisects,
        )
        return matches, receipt

    def _run_ast_grep(
        self,
        repo_path: str,
        java_files: Optional[List[FileEntry]] = None,
        *,
        file_signatures: Optional[Dict[str, str]] = None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        AstGrepError, _ = _astgrep_errors()
        base_argv = self._scan_base_argv(self._require_ast_grep_ready())
        sigs = file_signatures or {}
        expected_paths = java_scope_paths(sigs) if sigs else []
        expected_root = (
            subset_root(sigs, expected_paths) if sigs else inventory_root_empty()
        )

        if java_files is None:
            # No inventory — cannot prove covering; do not widen to repo-root scan.
            raise AstGrepError(
                "java_files inventory not supplied; repo-root scan cannot prove covering"
            )
        if not java_files:
            return self._empty_java_inventory_result(
                sigs=sigs, expected_root=expected_root
            )
        return self._scan_java_inventory(
            base_argv, java_files, sigs=sigs, expected_root=expected_root
        )

    def _record_entity_match(
        self,
        *,
        repo_path: str,
        rel: str,
        line: int,
        text: str,
        match_str: str,
        rule_id: str,
        evidence: Dict[str, List[Dict[str, Any]]],
        entity_table_map_candidates: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        """Record one persistence__entity match into evidence + map candidates."""
        AstGrepError, _ = _astgrep_errors()
        header = read_source_lines(repo_path, rel, 1, max_lines=40)
        extracted = extract_entity(rel, text, package_source=header or None)
        if extracted is None:
            raise AstGrepError(
                f"persistence__entity match at {rel}:{line} failed extract_entity "
                "(annotation-induced extract failure — STRUCTURAL)"
            )
        class_name, map_entry = extracted
        map_entry["rule_id"] = rule_id
        map_entry["match"] = match_str
        entity_table_map_candidates.setdefault(class_name, []).append(map_entry)
        evidence.setdefault("persistence", []).append({
            "file": rel, "line": line, "match": match_str,
            "rule_id": rule_id, "class_name": class_name,
        })

    def _record_bucket_match(
        self,
        *,
        match: Dict[str, Any],
        rel: str,
        line: int,
        text: str,
        match_str: str,
        rule_id: str,
        evidence: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        """Record a non-entity rule hit into its evidence bucket."""
        AstGrepError, _ = _astgrep_errors()
        bucket, _, _ = rule_id.partition("__")
        if bucket not in _EVIDENCE_BUCKETS:
            raise AstGrepError(
                f"ast-grep rule id '{rule_id}' has no matching evidence bucket"
            )
        entry: Dict[str, Any] = {
            "file": rel, "line": line, "match": match_str, "rule_id": rule_id
        }
        if rule_id == "raw_queries__query":
            _enrich_query_entry(entry, match)
        elif rule_id == "persistence__repository":
            entry.update(extract_repository(text))
        evidence.setdefault(bucket, []).append(entry)

    def _ingest_ast_grep_match(
        self,
        *,
        match: Dict[str, Any],
        repo_path: str,
        gitignore_spec: Any,
        evidence: Dict[str, List[Dict[str, Any]]],
        entity_table_map_candidates: Dict[str, List[Dict[str, Any]]],
        seen: set,
    ) -> None:
        """Filter, dedupe, and record one ast-grep match into evidence maps."""
        file_path = match.get("file", "")
        rel = os.path.relpath(file_path, repo_path).replace(os.sep, "/")
        if gitignore_spec is not None and gitignore_spec.match_file(rel):
            return
        line = match.get("range", {}).get("start", {}).get("line", 0) + 1
        text = match.get("text", "")
        rule_id = match.get("ruleId", "")
        match_str = first_line_match(text)
        dedup_key = (rel, line, rule_id)
        if dedup_key in seen:
            return
        seen.add(dedup_key)
        if rule_id == "persistence__entity":
            self._record_entity_match(
                repo_path=repo_path,
                rel=rel,
                line=line,
                text=text,
                match_str=match_str,
                rule_id=rule_id,
                evidence=evidence,
                entity_table_map_candidates=entity_table_map_candidates,
            )
            return
        self._record_bucket_match(
            match=match,
            rel=rel,
            line=line,
            text=text,
            match_str=match_str,
            rule_id=rule_id,
            evidence=evidence,
        )

    def scan(
        self,
        repo_path: str,
        sql_dialect: str = "ansi",
        respect_gitignore: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        repo_path = os.path.abspath(repo_path)
        scan_context: Optional[ScanContext] = kwargs.get("scan_context")
        java_files = scan_context.java_files if scan_context is not None else None
        file_signatures = (
            dict(scan_context.file_signatures) if scan_context is not None else {}
        )
        matches, receipt = self._run_ast_grep(
            repo_path,
            java_files=java_files,
            file_signatures=file_signatures,
        )
        gitignore_spec = load_gitignore_spec(repo_path) if respect_gitignore else None

        evidence: Dict[str, List[Dict[str, Any]]] = {}
        entity_table_map_candidates: Dict[str, List[Dict[str, Any]]] = {}
        seen: set = set()

        for match in matches:
            self._ingest_ast_grep_match(
                match=match,
                repo_path=repo_path,
                gitignore_spec=gitignore_spec,
                evidence=evidence,
                entity_table_map_candidates=entity_table_map_candidates,
                seen=seen,
            )

        for bucket in evidence.values():
            bucket.sort(key=lambda entry: (entry["file"], entry.get("line", 0)))

        return {
            "evidence": evidence,
            "entity_table_map_candidates": entity_table_map_candidates,
            COVERING_RECEIPT_KEY: receipt,
        }
