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
    read_source_lines,
)

RULE_FILE = ast_grep_rules_path()

# Windows CreateProcess fails with WinError 206 when hundreds of absolute paths
# are passed as separate argv entries (common on large Java repos).
# Budget is conservative vs the ~32KiB CreateProcess ceiling; chunking keeps
# ScanContext's exact inventory instead of falling back to a repo-root walk.
_PATH_LIST_CHAR_LIMIT = 7000 if sys.platform == "win32" else 2 ** 31


def _argv_char_len(parts: List[str]) -> int:
    """Approximate CreateProcess argv cost: sum of lengths plus one separator each."""
    return sum(len(part) + 1 for part in parts)


def chunk_paths_for_argv(
    base_argv: List[str],
    paths: List[str],
    limit: int,
) -> List[List[str]]:
    """Partition ``paths`` so each ``base_argv + chunk`` stays within ``limit`` chars.

    Preserves path order. A single path that alone exceeds the remaining budget
    still becomes its own chunk (CreateProcess will fail loudly rather than
    silently widening the scan to the repo root).
    """
    if not paths:
        return []
    base_len = _argv_char_len(base_argv)
    budget = max(limit - base_len, 1)
    chunks: List[List[str]] = []
    current: List[str] = []
    current_len = 0
    for path in paths:
        cost = len(path) + 1
        if current and current_len + cost > budget:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(path)
        current_len += cost
        if current_len > budget and len(current) == 1:
            # Solo path exceeds budget — emit it alone and continue.
            chunks.append(current)
            current = []
            current_len = 0
    if current:
        chunks.append(current)
    return chunks


def _is_windows_cmdline_too_long(exc: OSError) -> bool:
    """True when CreateProcess rejected the argv (WinError 206)."""
    return getattr(exc, "winerror", None) == 206


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

    def _invoke_ast_grep(self, cmd: List[str]) -> List[Dict[str, Any]]:
        """Run one ast-grep argv; return parsed match list or [] on soft failure."""
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            if _is_windows_cmdline_too_long(exc):
                raise
            print(f"warning: ast-grep failed to start: {exc}", file=sys.stderr)
            return []
        if proc.returncode != 0:
            print(f"warning: ast-grep exited with status {proc.returncode}", file=sys.stderr)
            print(proc.stderr, file=sys.stderr)
            return []
        try:
            return json.loads(proc.stdout) if proc.stdout.strip() else []
        except json.JSONDecodeError as e:
            print(f"warning: could not parse ast-grep output: {e}", file=sys.stderr)
            return []

    def _invoke_ast_grep_chunked(
        self,
        base_argv: List[str],
        paths: List[str],
        *,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Scan ``paths`` in argv-sized chunks; never widen to repo-root."""
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
        for chunk in chunks:
            cmd = base_argv + chunk
            try:
                matches.extend(self._invoke_ast_grep(cmd))
            except OSError as exc:
                if not _is_windows_cmdline_too_long(exc):
                    raise
                if len(chunk) == 1:
                    print(
                        "warning: single Java path still exceeds CreateProcess "
                        f"argv limit; skipping: {chunk[0]}",
                        file=sys.stderr,
                    )
                    continue
                # Heuristic under-shot the real ceiling — bisect this chunk.
                mid = len(chunk) // 2
                print(
                    "warning: CreateProcess WinError 206 on a path batch "
                    f"({len(chunk)} files); bisecting and retrying",
                    file=sys.stderr,
                )
                matches.extend(
                    self._invoke_ast_grep_chunked(
                        base_argv, chunk[:mid], limit=char_limit,
                    )
                )
                matches.extend(
                    self._invoke_ast_grep_chunked(
                        base_argv, chunk[mid:], limit=char_limit,
                    )
                )
        return matches

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
            return self._invoke_ast_grep_chunked(base_argv, paths)

        # No inventory supplied — single root scan with exclude globs (legacy).
        return self._invoke_ast_grep(self._repo_root_scan_argv(ast_grep_path, repo_path))

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
                header = read_source_lines(repo_path, rel, 1, max_lines=40)
                extracted = extract_entity(rel, text, package_source=header or None)
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
