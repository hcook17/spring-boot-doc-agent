#!/usr/bin/env python3
"""
check_code_quality.py — hard gates on annotation coverage and docstring
orientation; advisory reporting on function size/complexity/depth.

WHY THIS EXISTS
Every other quality property in this repo is enforced by something: tags by
check_pipeline_output.py, citations by citation_coverage.py, PR docs by
check_llms_coverage.py, scan freshness by spring_drift_check.py. The code
itself was enforced by nothing, and it shows in a way that is measurable
rather than aesthetic.

Schema v4 (2026-07-29) demotes per-function statements/complexity/depth from
*blocking* CI to *advisory* output. A monotonic size ratchet taught
extract-or `--update` theater (e.g. wiring Check G into collect_all) without
catching the defects kitchen-sink found in build_groups. What stays hard:

  - production type-annotation coverage must not fall
  - runnable modules must orient the reader (Usage/Run with) near the top

Size metrics are still measured and printed when they grow, so hotspots stay
visible without forcing merge rituals.

WHAT THIS DOES NOT DO
It does not lint, format, or sort imports — that is ruff's job (.ruff.toml).
The complexity number below is this repo's own definition; it is NOT
comparable to ruff's C901 or radon.

Run with:
    python3 scripts/check_code_quality.py
    python3 scripts/check_code_quality.py --update    # re-baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_BASELINE = SCRIPT_DIR / "code_quality_baseline.json"
DEFAULT_ROOTS = (SCRIPT_DIR, REPO_ROOT / "src" / "doc_engine")

# 2: "lines" (raw span) replaced by "statements".
# 3: adds "docstring_violations".
# 4: size/complexity/depth become advisory; measure scripts/ + src/doc_engine/.
SCHEMA_VERSION = 4

USAGE_RE = re.compile(r"^\s*(usage|run with|run)\s*:", re.IGNORECASE)
USAGE_WITHIN_LINES = 20

_BRANCH_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
    ast.With, ast.AsyncWith, ast.Assert, ast.IfExp,
)

_NESTING_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try,
)


def complexity(node: ast.AST) -> int:
    """Cyclomatic complexity: one, plus one per branch point."""
    total = 1
    for child in ast.walk(node):
        if isinstance(child, _BRANCH_NODES):
            total += 1
        elif isinstance(child, ast.BoolOp):
            total += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            total += 1 + len(child.ifs)
    return total


def nesting_depth(node: ast.AST, depth: int = 0) -> int:
    """Deepest nesting of block statements inside this function."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        step = depth + 1 if isinstance(child, _NESTING_NODES) else depth
        deepest = max(deepest, nesting_depth(child, step))
    return deepest


def statement_count(node: ast.AST) -> int:
    """How many statements this function executes, excluding docstring and
    nested function bodies."""
    total = 0
    body = list(getattr(node, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(
            getattr(body[0], "value", None), ast.Constant) and isinstance(
            body[0].value.value, str):
        body = body[1:]

    stack = list(body)
    while stack:
        stmt = stack.pop()
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        total += 1
        for field in ("body", "orelse", "finalbody", "handlers"):
            stack.extend(getattr(stmt, field, []) or [])
    return total


def is_annotated(node: ast.AST) -> bool:
    """True if the function declares any type information at all."""
    if getattr(node, "returns", None) is not None:
        return True
    args = node.args
    every_arg = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    if args.vararg is not None:
        every_arg.append(args.vararg)
    if args.kwarg is not None:
        every_arg.append(args.kwarg)
    return any(a.annotation is not None for a in every_arg
               if a.arg not in ("self", "cls"))


def measure_source(source: str, relpath: str) -> Tuple[Dict[str, Dict[str, int]], int, int]:
    """Measure every function in one module.

    Returns (functions, total_count, annotated_count). Keys are
    "<relpath>::<qualname>".
    """
    tree = ast.parse(source)
    functions: Dict[str, Dict[str, int]] = {}
    total = 0
    annotated = 0

    def visit(node: ast.AST, prefix: str) -> None:
        nonlocal total, annotated
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                total += 1
                if is_annotated(child):
                    annotated += 1
                record = {
                    "statements": statement_count(child),
                    "complexity": complexity(child),
                    "depth": nesting_depth(child),
                }
                existing = functions.get(f"{relpath}::{qualname}")
                if existing is not None:
                    record = {k: max(v, existing[k]) for k, v in record.items()}
                functions[f"{relpath}::{qualname}"] = record
                visit(child, f"{qualname}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return functions, total, annotated


def has_cli_entry_point(tree: ast.AST) -> bool:
    """True if the module has a top-level `if __name__ == "__main__":`."""
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or not isinstance(test.left, ast.Name):
            continue
        if test.left.id != "__name__":
            continue
        if any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators):
            return True
    return False


def docstring_violation(source: str, relpath: str) -> Optional[str]:
    """Why this module's docstring fails the orientation contract, or None."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if not has_cli_entry_point(tree):
        return None
    doc = ast.get_docstring(tree)
    if not doc:
        return f"{relpath}: has a __main__ entry point but no module docstring"
    lines = doc.splitlines()
    for line in lines[:USAGE_WITHIN_LINES]:
        if USAGE_RE.match(line):
            return None
    where = next(
        (i + 1 for i, line in enumerate(lines) if USAGE_RE.match(line)), None
    )
    if where is None:
        return (f"{relpath}: runnable module, but its {len(lines)}-line "
                f"docstring never says how to run it")
    return (f"{relpath}: 'how to run it' is at docstring line {where}; "
            f"the contract is within {USAGE_WITHIN_LINES}. Move the Usage "
            f"block above the rationale.")


def _is_production_module(relpath: str) -> bool:
    name = Path(relpath).name
    return not name.startswith("test_")


def list_script_py_files(scripts_dir: Path) -> List[Path]:
    """Top-level scripts/*.py only (historical surface)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(scripts_dir), "ls-files", "--", "*.py"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError:
        return sorted(scripts_dir.glob("*.py"))
    if proc.returncode != 0:
        return sorted(scripts_dir.glob("*.py"))
    names = sorted(
        line.strip() for line in proc.stdout.splitlines()
        if line.strip().endswith(".py") and "/" not in line.strip()
    )
    return [scripts_dir / name for name in names]


def iter_modules(roots: Sequence[Path], repo_root: Path) -> List[Tuple[Path, str]]:
    """(absolute path, repo-relative posix key) for every measured module."""
    out: List[Tuple[Path, str]] = []
    scripts = (repo_root / "scripts").resolve()
    for root in roots:
        root = root.resolve()
        if not root.is_dir():
            continue
        if root == scripts:
            for path in list_script_py_files(root):
                out.append((path, f"scripts/{path.name}"))
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                rel = path.relative_to(repo_root).as_posix()
            except ValueError:
                rel = path.name
            out.append((path, rel))
    return out


def measure_tree(
    scripts_dir: Path,
    extra_roots: Optional[Sequence[Path]] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, object]:
    """Measure scripts_dir plus optional package roots.

    When ``extra_roots`` is None (unit tests / --scripts-only), only the flat
    top-level ``*.py`` files under ``scripts_dir`` are measured and keys stay
    ``<filename>::qualname``. Production measurement passes ``extra_roots`` so
    keys become repo-relative (``scripts/…``, ``src/doc_engine/…``).
    """
    root = repo_root or REPO_ROOT
    functions: Dict[str, Dict[str, int]] = {}
    total = 0
    annotated = 0
    unparseable: List[str] = []
    docstring_violations: Dict[str, str] = {}

    if extra_roots is None:
        modules = [(p, p.name) for p in list_script_py_files(scripts_dir)]
    else:
        modules = iter_modules(list(extra_roots), root)

    for path, relpath in modules:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            unparseable.append(f"{relpath}: {exc}")
            continue
        try:
            found, count, ann = measure_source(source, relpath)
        except SyntaxError as exc:
            unparseable.append(f"{relpath}: {exc}")
            continue
        violation = docstring_violation(source, relpath)
        if violation is not None:
            docstring_violations[relpath] = violation
        functions.update(found)
        if _is_production_module(relpath):
            total += count
            annotated += ann

    worst_statements = max((f["statements"] for f in functions.values()), default=0)
    worst_complexity = max((f["complexity"] for f in functions.values()), default=0)
    worst_depth = max((f["depth"] for f in functions.values()), default=0)

    return {
        "schema_version": SCHEMA_VERSION,
        "production_functions": total,
        "production_functions_annotated": annotated,
        "limits_for_new_functions": {
            "statements": worst_statements,
            "complexity": worst_complexity,
            "depth": worst_depth,
        },
        "unparseable": sorted(unparseable),
        "docstring_violations": dict(sorted(docstring_violations.items())),
        "functions": dict(sorted(functions.items())),
    }


def annotation_ratio(measured: Dict[str, object]) -> float:
    total = int(measured["production_functions"])  # type: ignore[arg-type]
    if total == 0:
        return 1.0
    return int(measured["production_functions_annotated"]) / total  # type: ignore[arg-type]


def size_advisories(baseline: Dict[str, object], current: Dict[str, object]) -> List[str]:
    """Non-blocking notes when size/complexity/depth grow."""
    notes: List[str] = []
    base_functions: Dict[str, Dict[str, int]] = baseline.get("functions", {})  # type: ignore[assignment]
    cur_functions: Dict[str, Dict[str, int]] = current.get("functions", {})  # type: ignore[assignment]
    limits: Dict[str, int] = baseline.get("limits_for_new_functions", {})  # type: ignore[assignment]

    for key in sorted(cur_functions):
        cur = cur_functions[key]
        base = base_functions.get(key)
        if base is None:
            for metric, limit in sorted(limits.items()):
                if cur.get(metric, 0) > limit:
                    notes.append(
                        f"[advisory] new function {key} has {metric}={cur[metric]}, "
                        f"above prior worst ({limit})"
                    )
            continue
        for metric in ("statements", "complexity", "depth"):
            if cur.get(metric, 0) > base.get(metric, 0):
                notes.append(
                    f"[advisory] {key} grew: {metric} "
                    f"{base[metric]} -> {cur[metric]}"
                )
    return notes


def compare(baseline: Dict[str, object], current: Dict[str, object]) -> List[str]:
    """Hard failures only: annotation coverage, new docstring violations,
    unparseable modules. Size metrics are advisory (see size_advisories)."""
    issues: List[str] = []

    base_ratio = annotation_ratio(baseline)
    cur_ratio = annotation_ratio(current)
    if cur_ratio < base_ratio:
        issues.append(
            f"type-annotation coverage fell: "
            f"{base_ratio:.1%} ({baseline['production_functions_annotated']}/{baseline['production_functions']}) "
            f"-> {cur_ratio:.1%} ({current['production_functions_annotated']}/{current['production_functions']})"
        )

    base_docs: Dict[str, str] = baseline.get("docstring_violations", {})  # type: ignore[assignment]
    cur_docs: Dict[str, str] = current.get("docstring_violations", {})  # type: ignore[assignment]
    for module in sorted(set(cur_docs) - set(base_docs)):
        issues.append(f"docstring contract: {cur_docs[module]}")

    for entry in current.get("unparseable", []):  # type: ignore[union-attr]
        issues.append(f"could not parse {entry}")

    return issues


def exit_code(issues: List[str]) -> int:
    return 1 if issues else 0


def load_baseline(path: Path) -> Optional[Dict[str, object]]:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def write_baseline(path: Path, measured: Dict[str, object]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(measured, handle, indent=2, sort_keys=False)
        handle.write("\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scripts-dir", default=str(SCRIPT_DIR),
                    help="scripts/ directory (default: this script's directory)")
    ap.add_argument("--package-dir", default=str(REPO_ROOT / "src" / "doc_engine"),
                    help="product package to measure alongside scripts/")
    ap.add_argument("--scripts-only", action="store_true",
                    help="measure only --scripts-dir (tests / legacy)")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE),
                    help="the committed baseline to compare against")
    ap.add_argument("--update", action="store_true",
                    help="rewrite the baseline from the current tree instead of checking it")
    args = ap.parse_args(argv)

    scripts_dir = Path(args.scripts_dir)
    if not scripts_dir.is_dir():
        print(f"error: {scripts_dir} is not a directory", file=sys.stderr)
        return 2

    baseline_path = Path(args.baseline)
    if args.scripts_only:
        current = measure_tree(scripts_dir)
    else:
        roots = [scripts_dir]
        package = Path(args.package_dir)
        if package.is_dir():
            roots.append(package)
        current = measure_tree(scripts_dir, extra_roots=roots, repo_root=REPO_ROOT)

    if args.update:
        write_baseline(baseline_path, current)
        print(f"baseline written: {baseline_path}")
        print(f"  {len(current['functions'])} functions measured "  # type: ignore[arg-type]
              f"(size/complexity/depth advisory; tests included)")
        print(f"  {current['production_functions_annotated']} of "
              f"{current['production_functions']} production functions annotated "
              f"({annotation_ratio(current):.1%})")
        limits = current["limits_for_new_functions"]  # type: ignore[index]
        print(f"  advisory ceiling for new functions: statements={limits['statements']}, "
              f"complexity={limits['complexity']}, depth={limits['depth']}")
        return 0

    baseline = load_baseline(baseline_path)
    if baseline is None:
        print(f"error: no baseline at {baseline_path}. Create one with --update.",
              file=sys.stderr)
        return 2
    if baseline.get("schema_version") != SCHEMA_VERSION:
        print(f"error: baseline schema_version {baseline.get('schema_version')} "
              f"!= {SCHEMA_VERSION}; regenerate with --update.", file=sys.stderr)
        return 2

    issues = compare(baseline, current)
    advisories = size_advisories(baseline, current)

    if issues:
        print(f"code quality check failed ({len(issues)} issue(s)):", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        print("\nHard failures are annotation coverage and docstring orientation.",
              file=sys.stderr)
    else:
        print(f"OK: {len(current['functions'])} functions measured. "  # type: ignore[arg-type]
              f"Annotation coverage {annotation_ratio(current):.1%} "
              f"across {current['production_functions']} production functions.")

    if advisories:
        print(f"size/complexity advisories ({len(advisories)}):")
        for note in advisories:
            print(f"  {note}")

    return exit_code(issues)


if __name__ == "__main__":
    sys.exit(main())
