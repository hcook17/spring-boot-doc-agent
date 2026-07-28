#!/usr/bin/env python3
"""ast-grep scanner backend."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from doc_engine.core.context import FileEntry, ScanContext
from doc_engine.core.excludes import DEFAULT_EXCLUDED_DIRS, load_gitignore_spec
from doc_engine.scanning._paths import ast_grep_rules_path
from doc_engine.scanning._scanner_base import ScannerBackend
from doc_engine.scanning.java_extract import (
    extract_entity,
    extract_query_from_astgrep_args,
    extract_repository,
    first_line_match,
)

RULE_FILE = ast_grep_rules_path()

# Windows CreateProcess fails with WinError 206 when hundreds of absolute paths
# are passed as separate argv entries (common on large Java repos).
_PATH_LIST_CHAR_LIMIT = 7000 if sys.platform == "win32" else 2 ** 31


class AstGrepBackend(ScannerBackend):
    """Scanner backend that extracts Java structural signals via ast-grep."""

    @property
    def name(self) -> str:
        return "ast-grep"

    def version_hash(self) -> str:
        h = hashlib.sha256()
        paths = [
            str(Path(__file__).resolve()),
            str(RULE_FILE),
        ]
        for p in sorted(paths):
            try:
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
            except OSError:
                pass
        return h.hexdigest()[:16]

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

    def _repo_root_scan_argv(self, ast_grep_path: str, repo_path: str) -> List[str]:
        cmd = self._scan_base_argv(ast_grep_path)
        for d in sorted(DEFAULT_EXCLUDED_DIRS):
            cmd += ["--globs", f"!**/{d}/**"]
        cmd.append(repo_path)
        return cmd

    def _path_list_too_long(self, base_argv: List[str], paths: List[str]) -> bool:
        total = sum(len(part) + 1 for part in base_argv)
        total += sum(len(path) + 1 for path in paths)
        return total > _PATH_LIST_CHAR_LIMIT

    def _run_ast_grep(
        self,
        repo_path: str,
        java_files: Optional[List[FileEntry]] = None,
    ) -> List[Dict[str, Any]]:
        ast_grep_path = self._find_ast_grep()
        if ast_grep_path is None:
            print(
                "warning: ast-grep backend skipped — binary not on PATH. "
                "Install ast-grep to enable this backend.",
                file=sys.stderr,
            )
            return []
        if not RULE_FILE.is_file():
            print(f"warning: ast-grep rule file not found: {RULE_FILE}", file=sys.stderr)
            return []

        base_argv = self._scan_base_argv(ast_grep_path)
        if java_files is not None:
            if not java_files:
                return []
            paths = [entry.full_path for entry in java_files]
            if self._path_list_too_long(base_argv, paths):
                print(
                    "warning: too many Java file paths for this platform's command-line "
                    f"limit ({len(paths)} files); scanning repo root instead",
                    file=sys.stderr,
                )
                cmd = self._repo_root_scan_argv(ast_grep_path, repo_path)
            else:
                cmd = base_argv + paths
        else:
            cmd = self._repo_root_scan_argv(ast_grep_path, repo_path)

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"warning: ast-grep exited with status {proc.returncode}", file=sys.stderr)
            print(proc.stderr, file=sys.stderr)
            return []
        try:
            return json.loads(proc.stdout) if proc.stdout.strip() else []
        except json.JSONDecodeError as e:
            print(f"warning: could not parse ast-grep output: {e}", file=sys.stderr)
            return []

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
        matches = self._run_ast_grep(repo_path, java_files=java_files)
        gitignore_spec = load_gitignore_spec(repo_path) if respect_gitignore else None

        evidence: Dict[str, List[Dict[str, Any]]] = {}
        entity_table_map_candidates: Dict[str, List[Dict[str, Any]]] = {}
        seen: set = set()

        for m in matches:
            file_path = m.get("file", "")
            rel = os.path.relpath(file_path, repo_path).replace(os.sep, "/")
            if gitignore_spec is not None and gitignore_spec.match_file(rel):
                continue
            line = m.get("range", {}).get("start", {}).get("line", 0) + 1
            text = m.get("text", "")
            rule_id = m.get("ruleId", "")
            match_str = first_line_match(text)

            dedup_key = (rel, line, rule_id)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            if rule_id == "persistence__entity":
                extracted = extract_entity(rel, text)
                if extracted is None:
                    continue
                class_name, map_entry = extracted
                map_entry["rule_id"] = rule_id
                map_entry["match"] = match_str
                entity_table_map_candidates.setdefault(class_name, []).append(map_entry)
                evidence.setdefault("persistence", []).append({
                    "file": rel, "line": line, "match": match_str,
                    "rule_id": rule_id, "class_name": class_name,
                })
                continue

            bucket, _, _ = rule_id.partition("__")
            if bucket not in evidence and bucket not in {
                "api_surface", "outbound_clients", "messaging", "persistence",
                "raw_queries", "security", "configuration", "error_handling",
                "observability", "deployment", "testing", "references",
            }:
                print(
                    f"warning: ast-grep rule id '{rule_id}' has no matching evidence bucket, skipping",
                    file=sys.stderr,
                )
                continue

            entry: Dict[str, Any] = {
                "file": rel, "line": line, "match": match_str, "rule_id": rule_id
            }
            if rule_id == "raw_queries__query":
                multi_args = m.get("metaVariables", {}).get("multi", {}).get("ARGS", [])
                query_kind, query_text = extract_query_from_astgrep_args(multi_args)
                entry["query_kind"] = query_kind
                if query_text is not None:
                    entry["query"] = query_text
            elif rule_id == "persistence__repository":
                entry.update(extract_repository(text))

            evidence.setdefault(bucket, []).append(entry)

        for bucket in evidence.values():
            bucket.sort(key=lambda e: (e["file"], e.get("line", 0)))

        return {
            "evidence": evidence,
            "entity_table_map_candidates": entity_table_map_candidates,
        }
