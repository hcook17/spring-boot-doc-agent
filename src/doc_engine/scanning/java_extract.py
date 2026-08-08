"""Shared Java source text extraction for ast-grep and CodeQL scanners."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CLASS_NAME_RE = re.compile(r"\bclass\s+(\w+)")
INTERFACE_NAME_RE = re.compile(r"\binterface\s+(\w+)")
PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
TABLE_ARGS_RE = re.compile(r"@Table\s*\(([^)]*)\)", re.DOTALL)
TABLE_NAME_ARG_RE = re.compile(r'name\s*=\s*"([^"]+)"')
REPO_EXTENDS_RE = re.compile(
    r"(?:JpaRepository|CrudRepository|PagingAndSortingRepository|MongoRepository|ReactiveCrudRepository)"
    r"\s*<\s*([^,>]+?)\s*,\s*([^>]+?)\s*>"
)
NATIVE_QUERY_RE = re.compile(r"nativeQuery\s*=\s*true")
QUERY_STRING_RE = re.compile(r'"([^"]*)"')


def extract_java_package(text: str) -> Optional[str]:
    """Return the Java ``package`` declaration, or None if absent.

    Do not invent packages from file paths — missing package stays missing.
    """
    m = PACKAGE_RE.search(text or "")
    return m.group(1) if m else None


def fqcn_for_class(package: Optional[str], class_name: str) -> str:
    """Java-style FQCN for Path A additive fields / fact qualifiers."""
    if package:
        return f"{package}.{class_name}"
    return class_name


def to_snake_case(name: str) -> str:
    """Match Hibernate's default physical naming strategy for simple class names."""
    buf = list(name.replace(".", "_"))
    i = 1
    while i < len(buf) - 1:
        before, current, after = buf[i - 1], buf[i], buf[i + 1]
        if before.islower() and current.isupper() and after.islower():
            buf.insert(i, "_")
            i += 1
        i += 1
    return "".join(buf).lower()


def first_line_match(text: str) -> str:
    if not text:
        return ""
    return text.splitlines()[0].strip()[:200]


def read_source_lines(repo_path: str, rel: str, start_line: int, max_lines: int = 20) -> str:
    """Read up to max_lines from a Java source file starting at 1-indexed start_line."""
    full = os.path.join(repo_path, rel.replace("/", os.sep))
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return ""
    if not lines or start_line < 1:
        return ""
    slice_ = lines[start_line - 1:start_line - 1 + max_lines]
    return "".join(slice_).rstrip("\n")


def _explicit_table_name(text: str) -> Optional[str]:
    table_args = TABLE_ARGS_RE.search(text)
    if not table_args:
        return None
    name_arg = TABLE_NAME_ARG_RE.search(table_args.group(1))
    if not name_arg:
        return None
    return name_arg.group(1)


def _entity_entry(
    rel: str,
    class_name: str,
    *,
    table_name: Optional[str],
    package: Optional[str],
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "file": rel,
        "table": table_name if table_name else to_snake_case(class_name),
        "table_name_source": "explicit" if table_name else "inferred-default-naming",
        "fqcn": fqcn_for_class(package, class_name),
    }
    if package is not None:
        entry["package"] = package
    return entry


def extract_entity(
    rel: str,
    text: str,
    *,
    package_source: Optional[str] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Extract entity map fields from Java source text.

    ``text`` should include the class / ``@Table`` region. Optional
    ``package_source`` (typically a file header) supplies the ``package``
    declaration when it is not present in ``text`` (ast-grep match snippets).
    """
    name_match = CLASS_NAME_RE.search(text)
    class_name = name_match.group(1) if name_match else None
    if class_name is None:
        return None
    package = extract_java_package(
        package_source if package_source is not None else text
    )
    return class_name, _entity_entry(
        rel,
        class_name,
        table_name=_explicit_table_name(text),
        package=package,
    )


def extract_repository(text: str) -> Dict[str, str]:
    name_match = INTERFACE_NAME_RE.search(text)
    entity_match = REPO_EXTENDS_RE.search(text)
    extra: Dict[str, str] = {}
    if name_match:
        extra["repository"] = name_match.group(1)
    if entity_match:
        extra["entity"] = entity_match.group(1).strip()
        extra["id_type"] = entity_match.group(2).strip()
    return extra


def extract_query_from_astgrep_args(multi_args: List[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    joined = " ".join(frag.get("text", "") for frag in multi_args)
    query_kind = "native" if NATIVE_QUERY_RE.search(joined) else "jpql"
    query_text = None
    m = QUERY_STRING_RE.search(joined)
    if m:
        query_text = m.group(1)
    return query_kind, query_text


def normalize_repo_path(repo_path: str, file_path: str) -> str:
    abs_repo = Path(repo_path).resolve()
    abs_file = Path(file_path).resolve()
    try:
        rel = abs_file.relative_to(abs_repo)
    except ValueError:
        return file_path.replace(os.sep, "/")
    return str(rel).replace(os.sep, "/")
