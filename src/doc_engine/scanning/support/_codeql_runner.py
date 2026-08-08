"""CodeQL runner wrapper for Stage 0.

Replaces the ast-grep structural pass with a build-based CodeQL extraction.
This module is responsible for:
  - locating the CodeQL CLI
  - creating a CodeQL database from a target repo (using a build command)
  - running the spring-signals query pack against the database
  - decoding BQRS results to a list of dicts that spring_signal_scan.py can
    consume in the same shape as the old ast-grep evidence entries

The output schema is intentionally close to the old ast-grep JSON:
  {"file": "src/.../Foo.java", "line": 42, "match": "...", "rule_id": "..."}
plus extra typed columns where the query provides them (e.g., class_name,
query, query_kind, repository, entity, id_type).

Reading the actual source text from the file line is done by
spring_signal_scan.py, not here, because CodeQL does not return raw source
bytes and because the existing Python extraction helpers already know how to
parse the relevant declaration/annotation text.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from doc_engine.core.timeouts import codeql_database_timeout_seconds, tool_timeout_seconds
from doc_engine.scanning.build_command import BuildCommandError, validate_build_command

# Directories whose contents do not affect the Java build/CodeQL extraction and
# should be ignored when computing the content hash for database caching.
_HASH_EXCLUDED_DIRS = {
    ".git", ".gradle", "build", "target", "out", "node_modules", ".idea", ".vscode",
    "__pycache__", ".pytest_cache", ".mypy_cache",
}

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PACK_DIR = REPO_ROOT / "codeql" / "spring-signals"


class CodeQLError(RuntimeError):
    """Any CodeQL CLI failure that should not silently kill the process."""


class CodeQLNotFoundError(CodeQLError):
    """Raised when the CodeQL CLI cannot be found on PATH or DOC_ENGINE_CODEQL."""


def find_codeql() -> Path:
    """Return the CodeQL CLI executable path.

    Resolution order: ``DOC_ENGINE_CODEQL`` (if set to an existing file), then
    ``PATH``. No machine-local fallback paths are consulted.
    """
    env = os.environ.get("DOC_ENGINE_CODEQL")
    if env and str(env).strip():
        candidate = Path(env)
        if candidate.is_file():
            return candidate
        raise CodeQLNotFoundError(
            f"error: DOC_ENGINE_CODEQL={env!r} is not an existing file"
        )
    path = shutil.which("codeql")
    if path:
        return Path(path)
    raise CodeQLNotFoundError(
        "error: the 'codeql' binary is not on PATH. Install the CodeQL CLI "
        "(e.g. from https://github.com/github/codeql-cli-binaries/releases), "
        "add it to PATH, or set DOC_ENGINE_CODEQL to the executable."
    )


# Closed CLI surface. An open ``argv: list[str]`` API would let a confused or
# LLM-driven caller substitute ``bash -c …`` (or any other binary on disk) for
# ``codeql``. Subcommands are the only verbs this module may ever invoke.
_CODEQL_SUBCOMMANDS: frozenset[tuple[str, ...]] = frozenset({
    ("--version",),
    ("database", "create"),
    ("pack", "install"),
    ("query", "run"),
    ("bqrs", "decode"),
})


def _resolve_codeql_exe(codeql_path: Path) -> Path:
    exe = Path(codeql_path).resolve()
    if not exe.is_file():
        raise CodeQLError(f"codeql executable is not a file: {exe}")
    return exe


def _reject_unsafe_option(opt: str) -> None:
    if not isinstance(opt, str) or not opt:
        raise CodeQLError("codeql option must be a non-empty string")
    if "\x00" in opt or "\n" in opt or "\r" in opt:
        raise CodeQLError("codeql option must be a single-line string without NUL")


def _invoke_codeql(
    codeql_path: Path,
    subcommand: tuple[str, ...],
    *options: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Invoke one allowlisted CodeQL subcommand (never a free-form argv list).

    Executable comes only from ``codeql_path`` (resolved to a real file).
    ``subcommand`` must be a member of ``_CODEQL_SUBCOMMANDS``. Callers build
    options from typed paths / already-validated build commands — they cannot
    pick a different binary or invent a new verb.
    """
    if subcommand not in _CODEQL_SUBCOMMANDS:
        raise CodeQLError(
            f"refusing non-allowlisted codeql subcommand {subcommand!r}; "
            f"allowed: {sorted(_CODEQL_SUBCOMMANDS)}"
        )
    for opt in options:
        _reject_unsafe_option(opt)

    exe = _resolve_codeql_exe(codeql_path)
    argv = [str(exe), *subcommand, *options]
    try:
        return subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeQLError(
            f"codeql timed out after {timeout}s: {' '.join(argv[:4])}…"
        ) from exc


def _version_token_from_line(line: str) -> Optional[str]:
    """Return a dotted version token from one ``codeql --version`` line, if any."""
    if "release" not in line:
        return None
    for part in line.split():
        if part and part[0].isdigit():
            return part.rstrip(".")
    return None


def _parse_codeql_version_stdout(stdout: str) -> str:
    """Parse ``codeql --version`` stdout into a dotted version string."""
    for line in stdout.splitlines():
        token = _version_token_from_line(line)
        if token is not None:
            return token
    raise CodeQLError(f"could not parse codeql version from: {stdout}")


def codeql_version(codeql_path: Path) -> str:
    """Return the CodeQL CLI version string, e.g. '2.26.0'."""
    proc = _invoke_codeql(
        codeql_path,
        ("--version",),
        timeout=tool_timeout_seconds(),
    )
    if proc.returncode != 0:
        raise CodeQLError(f"codeql --version failed: {proc.stderr}")
    return _parse_codeql_version_stdout(proc.stdout)


def _cache_base_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg and str(xdg).strip():
        return Path(xdg)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return Path(local) if local else Path.home() / "AppData" / "Local"
    return Path.home() / ".cache"


def _refuse_symlink_cache_path(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise CodeQLError(f"refusing CodeQL cache path that is a symlink: {path}")
    if path.is_symlink():
        raise CodeQLError(f"refusing CodeQL cache path that is a symlink: {path}")


def _cache_dir() -> Path:
    """User-owned CodeQL cache root (mode 0700); never world-writable /tmp.

    Shared-host /tmp with exist_ok mkdir is a forgery vector for results JSON
    (CWE-377). Prefer XDG_CACHE_HOME / LOCALAPPDATA / ~/.cache under doc-engine.
    """
    path = _cache_base_dir() / "doc-engine" / "codeql-cache"
    _refuse_symlink_cache_path(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    _refuse_symlink_cache_path(path)
    return path


def _ensure_regular_file(path: Path) -> None:
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise CodeQLError(f"refusing non-regular cache file: {path}")


def _validate_one_cached_row(i: int, row: Any) -> Dict[str, Any]:
    if not isinstance(row, dict):
        raise CodeQLError(f"cached CodeQL row {i} is not an object")
    if not isinstance(row.get("file"), str) or not row["file"]:
        raise CodeQLError(f"cached CodeQL row {i} missing file")
    return row


def _validate_cached_evidence_rows(rows: Any) -> List[Dict[str, Any]]:
    """Treat cache JSON as untrusted input — shape-gate before returning as evidence."""
    if not isinstance(rows, list):
        raise CodeQLError("cached CodeQL results are not a list")
    return [_validate_one_cached_row(i, row) for i, row in enumerate(rows)]


def _update_hash_pair(h: Any, key: str, value: bytes | str) -> None:
    h.update(key.encode("utf-8"))
    h.update(b"\0")
    h.update(value if isinstance(value, bytes) else value.encode("utf-8"))
    h.update(b"\0")


def _hash_from_scan_context(scan_context: Any) -> str:
    h = hashlib.sha256()
    java_rels = {entry.rel_path for entry in scan_context.java_files}
    for rel in sorted(scan_context.file_signatures):
        if rel in java_rels or _is_codeql_hash_file(rel):
            _update_hash_pair(h, rel, scan_context.file_signatures[rel])
    return h.hexdigest()[:32]


def _is_codeql_walk_filename(name: str) -> bool:
    return name.endswith(".java") or _is_codeql_hash_file(name)


def _prune_hash_walk_dirs(dirs: List[str]) -> None:
    dirs[:] = [d for d in dirs if d not in _HASH_EXCLUDED_DIRS]


def _matching_walk_paths(walk_root: str, files: List[str]):
    for name in sorted(files):
        if _is_codeql_walk_filename(name):
            yield Path(walk_root) / name


def _iter_codeql_hash_paths(repo_path: Path):
    for walk_root, dirs, files in os.walk(repo_path):
        _prune_hash_walk_dirs(dirs)
        yield from _matching_walk_paths(walk_root, files)


def _hash_one_walk_file(
    h: Any,
    repo_path: Path,
    root: str,
    path: Path,
    is_path_inside_root: Any,
) -> None:
    if not is_path_inside_root(str(path), root):
        return
    try:
        data = path.read_bytes()
    except OSError:
        return
    _update_hash_pair(h, str(path.relative_to(repo_path)), data)


def _hash_from_repo_walk(repo_path: Path) -> str:
    from doc_engine.core.walk import is_path_inside_root

    h = hashlib.sha256()
    root = str(repo_path.resolve())
    for path in _iter_codeql_hash_paths(repo_path):
        _hash_one_walk_file(h, repo_path, root, path, is_path_inside_root)
    return h.hexdigest()[:32]


def _repo_content_hash(repo_path: Path, scan_context: Any = None) -> str:
    """Return a deterministic hash of the source files that affect CodeQL extraction."""
    if scan_context is not None:
        return _hash_from_scan_context(scan_context)
    return _hash_from_repo_walk(repo_path)


def _query_pack_hash(pack_dir: Path) -> str:
    """Hash every .ql file in the pack so query changes invalidate the cache."""
    h = hashlib.sha256()
    for ql in sorted(pack_dir.glob("*.ql")):
        h.update(ql.name.encode("utf-8"))
        h.update(b"\0")
        h.update(ql.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:32]


def _is_codeql_hash_file(rel: str) -> bool:
    name = Path(rel).name
    return (
        name.endswith(".gradle")
        or name.endswith(".gradle.kts")
        or name in {"pom.xml", "build.xml", "settings.gradle", "settings.gradle.kts"}
        or name.endswith(".properties")
        or name.endswith(".yml")
        or name.endswith(".yaml")
    )


def _cache_key(
    repo_path: Path,
    pack_dir: Path,
    build_command: str,
    scan_context: Any = None,
    codeql_cli_version: str = "",
) -> str:
    """Combined cache key: repo + build command + pack + CodeQL CLI version."""
    h = hashlib.sha256()
    h.update(_repo_content_hash(repo_path, scan_context=scan_context).encode("utf-8"))
    h.update(b"\0")
    h.update(build_command.encode("utf-8"))
    h.update(b"\0")
    h.update(_query_pack_hash(pack_dir).encode("utf-8"))
    h.update(b"\0")
    h.update(codeql_cli_version.encode("utf-8"))
    return h.hexdigest()[:32]


def _cache_db_path(
    repo_path: Path,
    pack_dir: Path,
    build_command: str,
    scan_context: Any = None,
    codeql_cli_version: str = "",
) -> Path:
    cache_dir = _cache_dir()
    return cache_dir / _cache_key(
        repo_path, pack_dir, build_command, scan_context=scan_context,
        codeql_cli_version=codeql_cli_version,
    )


def _cache_metadata(db_path: Path) -> Optional[Dict[str, str]]:
    meta = db_path / "spring_signal_scan_cache.json"
    if not meta.is_file():
        return None
    try:
        _ensure_regular_file(meta)
        return json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, CodeQLError):
        return None


def _write_cache_metadata(
    db_path: Path,
    repo_path: Path,
    pack_dir: Path,
    build_command: str,
    scan_context: Any = None,
    codeql_cli_version: str = "",
) -> None:
    meta = db_path / "spring_signal_scan_cache.json"
    meta.write_text(json.dumps({
        "cache_key": _cache_key(
            repo_path, pack_dir, build_command, scan_context=scan_context,
            codeql_cli_version=codeql_cli_version,
        ),
        "codeql_cli_version": codeql_cli_version,
    }), encoding="utf-8")


def _cache_is_valid(
    db_path: Path,
    repo_path: Path,
    pack_dir: Path,
    build_command: str,
    scan_context: Any = None,
    codeql_cli_version: str = "",
) -> bool:
    meta = _cache_metadata(db_path)
    if meta is None:
        return False
    return meta.get("cache_key") == _cache_key(
        repo_path, pack_dir, build_command, scan_context=scan_context,
        codeql_cli_version=codeql_cli_version,
    )


def _results_cache_path(
    repo_path: Path,
    pack_dir: Path,
    build_command: str,
    scanner_version: str,
    scan_context: Any = None,
    codeql_cli_version: str = "",
) -> Path:
    """Path to the cached query results for a fully determined scan."""
    h = hashlib.sha256()
    h.update(scanner_version.encode("utf-8"))
    h.update(b"\0")
    h.update(codeql_cli_version.encode("utf-8"))
    h.update(b"\0")
    h.update(_cache_key(
        repo_path, pack_dir, build_command, scan_context=scan_context,
        codeql_cli_version=codeql_cli_version,
    ).encode("utf-8"))
    return _cache_dir() / (h.hexdigest()[:32] + "_results.json")


def _load_results_cache(
    repo_path: Path,
    pack_dir: Path,
    build_command: str,
    scanner_version: str,
    scan_context: Any = None,
    codeql_cli_version: str = "",
) -> Optional[List[Dict[str, Any]]]:
    path = _results_cache_path(
        repo_path, pack_dir, build_command, scanner_version, scan_context=scan_context,
        codeql_cli_version=codeql_cli_version,
    )
    if not path.is_file():
        return None
    try:
        _ensure_regular_file(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _validate_cached_evidence_rows(raw)
    except (OSError, json.JSONDecodeError, CodeQLError):
        return None


def _save_results_cache(
    repo_path: Path,
    pack_dir: Path,
    build_command: str,
    scanner_version: str,
    rows: List[Dict[str, Any]],
    scan_context: Any = None,
    codeql_cli_version: str = "",
) -> None:
    path = _results_cache_path(
        repo_path, pack_dir, build_command, scanner_version, scan_context=scan_context,
        codeql_cli_version=codeql_cli_version,
    )
    if path.exists():
        _ensure_regular_file(path)
    path.write_text(json.dumps(rows), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def create_database(
    codeql_path: Path,
    repo_path: Path,
    db_path: Path,
    build_command: str,
    overwrite: bool = True,
) -> None:
    """Create a CodeQL Java database for the repo using the supplied build.

    ``build_command`` is re-validated here before being passed as a single
    ``--command=`` argv element (no shell). CodeQL still executes that build
    inside ``--source-root`` — callers must also pass ``--allow-codeql-build``
    for untrusted trees; this layer only removes free-form OS argv and
    foot-gun build strings.
    """
    safe_build = validate_build_command(build_command)
    options = [
        str(db_path),
        "--language=java",
        f"--command={safe_build}",
        f"--source-root={repo_path}",
    ]
    if overwrite:
        options.append("--overwrite")
    proc = _invoke_codeql(
        codeql_path,
        ("database", "create"),
        *options,
        timeout=codeql_database_timeout_seconds(),
    )
    if proc.returncode != 0:
        raise CodeQLError(
            f"codeql database create failed (exit {proc.returncode}):\n"
            f"{proc.stderr}\n{proc.stdout}"
        )


def install_pack(codeql_path: Path, pack_dir: Path) -> None:
    """Install the QL pack dependencies (codeql/java-all, etc.)."""
    proc = _invoke_codeql(
        codeql_path,
        ("pack", "install"),
        str(pack_dir),
        timeout=tool_timeout_seconds(),
    )
    if proc.returncode != 0:
        raise CodeQLError(
            f"codeql pack install failed (exit {proc.returncode}):\n"
            f"{proc.stderr}\n{proc.stdout}"
        )


def discover_queries(pack_dir: Path) -> List[Path]:
    """Return all .ql files in the pack directory, sorted."""
    return sorted(pack_dir.glob("*.ql"))


def run_query(
    codeql_path: Path,
    db_path: Path,
    query_file: Path,
    bqrs_path: Path,
) -> None:
    """Run a single .ql query against a database, writing a BQRS file."""
    proc = _invoke_codeql(
        codeql_path,
        ("query", "run"),
        f"--database={db_path}",
        f"--output={bqrs_path}",
        str(query_file),
        timeout=tool_timeout_seconds(),
    )
    if proc.returncode != 0:
        raise CodeQLError(
            f"codeql query run failed for {query_file.name} "
            f"(exit {proc.returncode}):\n{proc.stderr}\n{proc.stdout}"
        )


def decode_bqrs(
    codeql_path: Path,
    bqrs_path: Path,
) -> List[Dict[str, Any]]:
    """Decode a BQRS file to a list of dicts keyed by column name.

    CodeQL's JSON output is:
      {"#select": {"columns": [{"name": "file", "kind": "String"}, ...],
                   "tuples": [[...], ...]}}
    We map each tuple to a dict using the column names. Columns without a
    name get synthetic names (col_0, col_1, ...).
    """
    proc = _invoke_codeql(
        codeql_path,
        ("bqrs", "decode"),
        "--format=json",
        # Include source locations and strings as plain values.
        "--entities=string,url",
        str(bqrs_path),
        timeout=tool_timeout_seconds(),
    )
    if proc.returncode != 0:
        raise CodeQLError(
            f"codeql bqrs decode failed for {bqrs_path} "
            f"(exit {proc.returncode}):\n{proc.stderr}\n{proc.stdout}"
        )
    return _rows_from_bqrs_json(json.loads(proc.stdout))


def _column_names_from_bqrs(columns: List[Dict[str, Any]]) -> List[str]:
    names = []
    for i, col in enumerate(columns):
        name = col.get("name") or f"col_{i}"
        names.append(name)
    return names


def _rows_from_bqrs_json(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    select = raw.get("#select", {})
    names = _column_names_from_bqrs(select.get("columns", []))
    return [
        {names[i]: value for i, value in enumerate(row)}
        for row in select.get("tuples", [])
    ]


def run_all_queries(
    codeql_path: Path,
    db_path: Path,
    pack_dir: Path,
    tmp_dir: Path,
) -> List[Dict[str, Any]]:
    """Run every .ql query in the pack and return merged decoded results."""
    queries = discover_queries(pack_dir)
    if not queries:
        raise CodeQLError(f"no .ql queries found in {pack_dir}")

    all_rows: List[Dict[str, Any]] = []
    for query in queries:
        bqrs_path = tmp_dir / f"{query.stem}.bqrs"
        run_query(codeql_path, db_path, query, bqrs_path)
        rows = decode_bqrs(codeql_path, bqrs_path)
        for row in rows:
            # Tag every row with the query file that produced it, useful for
            # debugging and drift-check provenance.
            row["_query_file"] = query.name
        all_rows.extend(rows)
    return all_rows


def _prepare_scan_targets(
    repo_path: Path,
    build_command: str,
    pack_dir: Optional[Path],
    db_path: Optional[Path],
    keep_database: bool,
    scan_context: Any,
    cli_version: str,
) -> tuple[Path, Path, bool, bool]:
    """Return ``(pack_dir, db_path, using_cache, keep_database)``."""
    resolved_pack = pack_dir or DEFAULT_PACK_DIR
    if not resolved_pack.is_dir():
        raise CodeQLError(f"query pack not found: {resolved_pack}")
    using_cache = db_path is None
    if using_cache:
        db_path = _cache_db_path(
            repo_path, resolved_pack, build_command, scan_context=scan_context,
            codeql_cli_version=cli_version,
        )
        keep_database = True
    assert db_path is not None
    return resolved_pack, db_path, using_cache, keep_database


def _ensure_codeql_database(
    *,
    codeql_path: Path,
    repo_path: Path,
    db_path: Path,
    pack_dir: Path,
    build_command: str,
    using_cache: bool,
    keep_database: bool,
    scan_context: Any,
    cli_version: str,
) -> None:
    if db_path.exists() and keep_database:
        _reuse_or_rebuild_cached_db(
            codeql_path=codeql_path,
            repo_path=repo_path,
            db_path=db_path,
            pack_dir=pack_dir,
            build_command=build_command,
            using_cache=using_cache,
            scan_context=scan_context,
            cli_version=cli_version,
        )
        return
    create_database(codeql_path, repo_path, db_path, build_command, overwrite=True)
    if using_cache:
        _write_cache_metadata(
            db_path, repo_path, pack_dir, build_command, scan_context=scan_context,
            codeql_cli_version=cli_version,
        )


def _reuse_or_rebuild_cached_db(
    *,
    codeql_path: Path,
    repo_path: Path,
    db_path: Path,
    pack_dir: Path,
    build_command: str,
    using_cache: bool,
    scan_context: Any,
    cli_version: str,
) -> None:
    if not using_cache:
        # Caller-provided db_path with keep_database: trust it.
        return
    if _cache_is_valid(
        db_path, repo_path, pack_dir, build_command, scan_context=scan_context,
        codeql_cli_version=cli_version,
    ):
        return
    # Cache is stale (source, build command, or queries changed): rebuild.
    shutil.rmtree(db_path, ignore_errors=True)
    create_database(codeql_path, repo_path, db_path, build_command, overwrite=True)
    _write_cache_metadata(
        db_path, repo_path, pack_dir, build_command, scan_context=scan_context,
        codeql_cli_version=cli_version,
    )


def _validated_build_command(build_command: str) -> str:
    try:
        return validate_build_command(build_command)
    except BuildCommandError as exc:
        raise CodeQLError(str(exc)) from exc


def _load_cached_scan_rows(
    *,
    using_cache: bool,
    scanner_version: Optional[str],
    repo_path: Path,
    pack_dir: Path,
    build_command: str,
    scan_context: Any,
    cli_version: str,
) -> Optional[List[Dict[str, Any]]]:
    """Return results-cache rows when cache+version allow a full skip."""
    if not (using_cache and scanner_version):
        return None
    return _load_results_cache(
        repo_path,
        pack_dir,
        build_command,
        scanner_version,
        scan_context=scan_context,
        codeql_cli_version=cli_version,
    )


def _run_queries_and_maybe_cache(
    *,
    codeql_path: Path,
    repo_path: Path,
    db_path: Path,
    pack_dir: Path,
    build_command: str,
    using_cache: bool,
    scanner_version: Optional[str],
    scan_context: Any,
    cli_version: str,
    tmp: Path,
) -> List[Dict[str, Any]]:
    rows = run_all_queries(codeql_path, db_path, pack_dir, tmp)
    if using_cache and scanner_version:
        _save_results_cache(
            repo_path,
            pack_dir,
            build_command,
            scanner_version,
            rows,
            scan_context=scan_context,
            codeql_cli_version=cli_version,
        )
    return rows


def _cleanup_scan_temps(db_path: Path, tmp: str, keep_database: bool) -> None:
    if not keep_database:
        shutil.rmtree(db_path, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)


def scan_with_codeql(
    repo_path: Path,
    build_command: str,
    pack_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
    keep_database: bool = False,
    scanner_version: Optional[str] = None,
    scan_context: Any = None,
) -> List[Dict[str, Any]]:
    """End-to-end: create database, run queries, return evidence rows.

    Args:
        repo_path: path to the target repository
        build_command: command used by CodeQL to compile the Java sources
        pack_dir: path to the spring-signals QL pack; defaults to the bundled
                  pack under the project root
        db_path: optional path for the CodeQL database; if omitted, a
                 content-addressed cache is used. The cache key is a hash of
                 the repo's source/build files, the build command, and the query
                 pack, so the DB is reused when none of those change.
        keep_database: if True and db_path is provided, keep the database on
                       disk; otherwise it is removed after scanning. Ignored when
                       db_path is omitted (the cache is always kept).
        scanner_version: hash of the scanner code and query pack; when the
                         cache is used, query results are also cached keyed by
                         this version, so unchanged code skips re-running queries.

    Returns:
        A list of evidence dicts ready for spring_signal_scan.py to bucket.
    """
    build_command = _validated_build_command(build_command)
    codeql_path = find_codeql()
    cli_version = codeql_version(codeql_path)
    pack_dir, db_path, using_cache, keep_database = _prepare_scan_targets(
        repo_path,
        build_command,
        pack_dir,
        db_path,
        keep_database,
        scan_context,
        cli_version,
    )

    # If we have a fully deterministic result cache, we can skip everything
    # (including the ~10s `codeql pack install` call).
    cached_rows = _load_cached_scan_rows(
        using_cache=using_cache,
        scanner_version=scanner_version,
        repo_path=repo_path,
        pack_dir=pack_dir,
        build_command=build_command,
        scan_context=scan_context,
        cli_version=cli_version,
    )
    if cached_rows is not None:
        return cached_rows

    install_pack(codeql_path, pack_dir)

    tmp = tempfile.mkdtemp(prefix="codeql_stage0_")
    try:
        _ensure_codeql_database(
            codeql_path=codeql_path,
            repo_path=repo_path,
            db_path=db_path,
            pack_dir=pack_dir,
            build_command=build_command,
            using_cache=using_cache,
            keep_database=keep_database,
            scan_context=scan_context,
            cli_version=cli_version,
        )
        return _run_queries_and_maybe_cache(
            codeql_path=codeql_path,
            repo_path=repo_path,
            db_path=db_path,
            pack_dir=pack_dir,
            build_command=build_command,
            using_cache=using_cache,
            scanner_version=scanner_version,
            scan_context=scan_context,
            cli_version=cli_version,
            tmp=Path(tmp),
        )
    finally:
        _cleanup_scan_temps(db_path, tmp, keep_database)


if __name__ == "__main__":
    # Simple CLI for quick manual testing of the runner.
    # Usage: python -m doc_engine.scanning.support._codeql_runner <repo_path> <build_command> [db_path]
    # If db_path is provided, the database is kept there and reused if it exists.
    if len(sys.argv) < 3:
        print("usage: python -m doc_engine.scanning.support._codeql_runner <repo_path> <build_command> [db_path]")
        sys.exit(1)
    repo = Path(sys.argv[1])
    build = sys.argv[2]
    db = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    rows = scan_with_codeql(repo, build, db_path=db, keep_database=True)
    print(json.dumps({"row_count": len(rows), "sample": rows[:5]}, indent=2))
