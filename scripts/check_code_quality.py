#!/usr/bin/env python3
"""
check_code_quality.py — a monotonic ratchet on function size, control-flow
complexity, and type-annotation coverage across scripts/.

WHY THIS EXISTS
Every other quality property in this repo is enforced by something: tags by
check_pipeline_output.py, citations by citation_coverage.py, PR docs by
check_llms_coverage.py, scan freshness by spring_drift_check.py. The code
itself was enforced by nothing, and it shows in a way that is measurable
rather than aesthetic:

  - 21 of 149 production functions carry any type annotation (14%), and the
    distribution is the interesting part: it is all-or-nothing per module.
    build_cross_group_edges.py (6/6), check_llms_coverage.py (7/7) and
    check_pipeline_output.py (8/8) are fully annotated; every other module
    is at zero. The convention exists and simply was never applied
    backwards -- which is why the ratchet measures coverage rather than
    demanding a number. Meanwhile the four JSON artifacts that flow between
    pipeline stages are passed as bare dicts, read with chains like
    signals["evidence"]["raw_queries"].
  - 25 functions exceed complexity 10; the worst tracked one is
    partition_repo.build_groups(), which is exactly where the carry_forward
    termination bug lived (10-review-persona-and-standards.md section 1) and
    where the 2026-07-24 kitchen-sink suite then found a second infinite
    loop in the same guard.

Complexity concentrates where defects actually land. That is the argument
for bounding it, and it is an argument from this repo's own history rather
than from a style guide.

WHY A RATCHET AND NOT A LIMIT
A fixed threshold on an existing codebase is either set above everything
(enforces nothing) or below something (fails on day one and gets disabled).
This records what is true today and fails only on *regression* — so the
numbers can only improve, and improvements lock in via --update. Nothing
here demands that scan() be refactored; it demands that it not get worse.

The same reasoning as check_llms_coverage.py's ENFORCE toggle, reached the
other way: that script cannot enforce because its heuristic is still blunt,
so it reports. This one is local, deterministic, and has no such excuse, so
it blocks. See exit_code() below.

WHAT THIS DOES NOT DO
It does not lint, format, or sort imports — that is ruff's job (.ruff.toml),
and reimplementing 900 rules in stdlib would be silly. This script owns only
the three metrics ruff cannot ratchet against a committed baseline.

The complexity number below is this repo's own definition (see complexity()).
It is NOT comparable to ruff's C901 or to radon's, which count differently;
do not copy a threshold between them.

Run with:
    python3 scripts/check_code_quality.py
    python3 scripts/check_code_quality.py --update    # re-baseline
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BASELINE = SCRIPT_DIR / "code_quality_baseline.json"

# 2: "lines" (raw span) replaced by "statements". A v1 baseline compared
# against v2 measurements would silently pass everything, since every
# function would look like a new key. Bumped so it is rejected instead.
# 3: adds "docstring_violations". A v2 baseline has no such key, so every
# pre-existing violation would read as new and fail the build on day one.
SCHEMA_VERSION = 3

# "How do I run this" -- the one part of the docstring contract in
# CONTRIBUTING.md that is mechanically decidable. Whether a first sentence is
# a *good* summary is not, so it is not enforced.
USAGE_RE = re.compile(r"^\s*(usage|run with|run)\s*:", re.IGNORECASE)

# 20 sits in a gap in this repo's own distribution. Measured 2026-07-25, the
# docstring line at which each runnable module states how to run it:
#
#   4 5 8 9 11 13 13 14 15 15 17 18 | 29 36 38 40 44 44 51 58 62 64 78 79 194
#
# Twelve modules orient the reader by line 18; thirteen bury it at 29 or
# beyond; nothing lands between. No compliant module sits near the boundary,
# so ordinary edits to a good docstring should not trip it.
#
# What this number is NOT, stated because it would be easy to over-trust:
# in the threshold-derivation literature's terms this is *unsupervised*
# natural-breaks clustering on a single system with n=25 -- the weakest
# available basis. The canonical unsupervised method (Alves, Ypma & Visser,
# ICSM 2010) aggregates across a benchmark of ~100 systems precisely because
# single-system thresholds are unstable, and supervised methods key the
# cut-point to a measured outcome, which needs labels this repo does not have.
# The only outcome signal here is n=1: a reader reported the code hard to
# follow, and the 194-line outlier is what they would hit first. That supports
# the direction, not the exact cut.
#
# So treat it as a fact about the current population, not a constant:
# RE-DERIVE it when the tree's shape changes rather than defending it. The
# command that produced the numbers above is in CONTRIBUTING.md.
USAGE_WITHIN_LINES = 20

# Nodes that introduce a branch in the control-flow graph. BoolOp and
# comprehension are counted because `a and b or c` and a filtered
# comprehension are branches a reader has to hold in their head, even though
# neither indents. Assert counts for the same reason.
_BRANCH_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
    ast.With, ast.AsyncWith, ast.Assert, ast.IfExp,
)

# Nodes that add a level of visual indentation. Deliberately NOT the same
# set as _BRANCH_NODES: `assert` and a ternary branch without nesting, and
# Try nests without being a branch on its own (its handlers are).
_NESTING_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try,
)


def complexity(node: ast.AST) -> int:
    """Cyclomatic complexity: one, plus one per branch point.

    Counts each extra operand of a BoolOp (so `a and b and c` is two, not
    one) and each comprehension clause plus each of its filters. This is a
    deliberate superset of textbook McCabe; see the module docstring's
    warning about comparing it to other tools."""
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
    """Deepest nesting of block statements inside this function.

    Walks children directly rather than via ast.walk, because ast.walk
    flattens the tree and loses the containment relationship this measures.
    A nested function definition starts its own count -- its depth belongs
    to it, not to its parent."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        step = depth + 1 if isinstance(child, _NESTING_NODES) else depth
        deepest = max(deepest, nesting_depth(child, step))
    return deepest


def statement_count(node: ast.AST) -> int:
    """How many statements this function executes, excluding its docstring
    and excluding the bodies of functions nested inside it.

    Deliberately NOT the line span (end_lineno - lineno). This repo writes
    unusually heavy explanatory prose -- 38-54% of the larger modules is
    comment or docstring, and that is a property worth keeping. A raw line
    span makes adding an eight-line comment that explains a subtle bug read
    as "this function got worse," which is exactly backwards, and a gate that
    fires when you document something is a gate that gets deleted. Counting
    statements measures how much the function *does*, which is what "too
    long" is actually a proxy for.

    Nested functions are excluded because they get their own baseline entry;
    counting them twice would make a parent regress whenever its child grew."""
    total = 0
    body = list(getattr(node, "body", []))
    # Drop the docstring: it is an Expr wrapping a bare string constant.
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
    """True if the function declares any type information at all.

    Deliberately generous: a return annotation OR any annotated parameter
    counts. A stricter "fully annotated" measure would read as 0% today and
    give the ratchet nothing to hold on to. `self`/`cls` are excluded so
    methods are not judged on a parameter nobody annotates."""
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
    "<relpath>::<qualname>" -- qualified, not line-numbered, so that editing
    a file above a function does not invalidate its baseline entry. Two
    functions sharing a qualname in one file (a conditional def, say) keep
    the worse of the two, which is the safe direction for a ratchet."""
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
    """True if the module has a top-level `if __name__ == "__main__":`.

    Walks only the module body, not the whole tree: the guard is meaningful
    at module level and a string "__main__" appearing anywhere else (a
    docstring, an error message) must not count."""
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
    """Why this module's docstring fails the orientation contract, or None.

    The contract is in CONTRIBUTING.md: say what the module is, then how to
    run it, then why it exists. Only the middle part is mechanically
    checkable, so that is the only part enforced -- "does a reader find the
    command near the top" is a decidable question; "is the first sentence a
    good summary" is not.

    Library modules are exempt by construction. doc_tag_utils.py,
    _shared_excludes.py, _config_keys.py and _secret_heuristics.py are
    imported and never run, so demanding a usage block from them would point
    the check at the wrong thing -- which is its own anti-pattern here."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None  # reported separately by measure_tree as unparseable
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
        return (f"{relpath}: runnable module, but its {len(lines)}-line docstring "
                f"never says how to run it")
    return (f"{relpath}: 'how to run it' is at docstring line {where}; the contract is "
            f"within {USAGE_WITHIN_LINES}. Move the Usage block above the rationale.")


def python_files(scripts_dir: Path) -> List[Path]:
    """The *.py files this baseline should describe: the tracked ones.

    Globbing the directory folds whatever happens to be sitting in the working
    tree into a committed artifact, and that is not a hypothetical.
    Regenerating this baseline while a concurrent session's untracked work was
    present captured 93 of its functions and raised the annotation floor to
    35.4% against a committed tree measuring 22.0% -- a gate that fails on its
    first CI run, reporting a regression caused entirely by files that were
    never in the commit.

    Falls back to the glob outside a git checkout, so this still works on an
    exported tarball. Top-level only: nested paths are fixtures, not modules."""
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


def measure_tree(scripts_dir: Path) -> Dict[str, object]:
    """Measure every *.py under scripts_dir, sorted for byte-stable output.

    Sorted because this file is committed and diffed: an unsorted dict makes
    every regeneration look like a change. Same reasoning that made
    spring_signals.json sort entity_table_map (commit b2410fd)."""
    functions: Dict[str, Dict[str, int]] = {}
    total = 0
    annotated = 0
    unparseable: List[str] = []
    docstring_violations: Dict[str, str] = {}

    for path in python_files(scripts_dir):
        relpath = path.name
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
        # Size and complexity are ratcheted over everything, tests included --
        # a test file rots the same way any other file does. Annotation
        # coverage deliberately counts production modules only: test methods
        # are never annotated by anyone, so including them would mean adding
        # a suite lowers the ratio and fails the gate. A check that penalizes
        # writing tests is a check that gets deleted.
        if not relpath.startswith("test_"):
            total += count
            annotated += ann

    worst_statements = max((f["statements"] for f in functions.values()), default=0)
    worst_complexity = max((f["complexity"] for f in functions.values()), default=0)
    worst_depth = max((f["depth"] for f in functions.values()), default=0)

    return {
        "schema_version": SCHEMA_VERSION,
        # A count pair rather than a stored percentage: a float in a
        # committed file churns on rounding, and compare() derives the ratio
        # it needs anyway.
        "production_functions": total,
        "production_functions_annotated": annotated,
        "limits_for_new_functions": {
            "statements": worst_statements,
            "complexity": worst_complexity,
            "depth": worst_depth,
        },
        "unparseable": sorted(unparseable),
        # Keyed by module, not by message, and compared on keys alone. The
        # messages carry line numbers, so comparing them would report a "new"
        # violation every time an unrelated edit shifted a line. Keyed by
        # module it also beats a count, which would let one module get fixed
        # while another broke with no net change.
        "docstring_violations": dict(sorted(docstring_violations.items())),
        "functions": dict(sorted(functions.items())),
    }


def annotation_ratio(measured: Dict[str, object]) -> float:
    total = int(measured["production_functions"])  # type: ignore[arg-type]
    if total == 0:
        return 1.0
    return int(measured["production_functions_annotated"]) / total  # type: ignore[arg-type]


def compare(baseline: Dict[str, object], current: Dict[str, object]) -> List[str]:
    """Every way the current tree is worse than the baseline.

    Three separate failure modes, kept separate in the output because they
    have different fixes: an existing function regressed, a new function
    landed worse than anything that existed when the baseline was taken, or
    annotation coverage fell."""
    issues: List[str] = []

    base_functions: Dict[str, Dict[str, int]] = baseline.get("functions", {})  # type: ignore[assignment]
    cur_functions: Dict[str, Dict[str, int]] = current.get("functions", {})  # type: ignore[assignment]
    limits: Dict[str, int] = baseline.get("limits_for_new_functions", {})  # type: ignore[assignment]

    for key in sorted(cur_functions):
        cur = cur_functions[key]
        base = base_functions.get(key)
        if base is None:
            for metric, limit in sorted(limits.items()):
                if cur.get(metric, 0) > limit:
                    issues.append(
                        f"new function {key} has {metric}={cur[metric]}, above the "
                        f"worst that existed when the baseline was taken ({limit}). "
                        f"Split it, or re-baseline deliberately with --update."
                    )
            continue
        for metric in ("statements", "complexity", "depth"):
            if cur.get(metric, 0) > base.get(metric, 0):
                issues.append(
                    f"{key} regressed: {metric} {base[metric]} -> {cur[metric]}"
                )

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
    """Split out so the blocking behavior is unit-testable, exactly as
    check_pipeline_output.py does. A gate whose failure path is never
    executed in a test is a gate nobody has shown can fail."""
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scripts-dir", default=str(SCRIPT_DIR),
                    help="directory of *.py to measure (default: this script's own directory)")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE),
                    help="the committed baseline to compare against")
    ap.add_argument("--update", action="store_true",
                    help="rewrite the baseline from the current tree instead of checking it")
    args = ap.parse_args()

    scripts_dir = Path(args.scripts_dir)
    if not scripts_dir.is_dir():
        print(f"error: {scripts_dir} is not a directory", file=sys.stderr)
        return 2

    baseline_path = Path(args.baseline)
    current = measure_tree(scripts_dir)

    if args.update:
        write_baseline(baseline_path, current)
        print(f"baseline written: {baseline_path}")
        print(f"  {len(current['functions'])} functions ratcheted "  # type: ignore[arg-type]
              f"(size/complexity/depth, tests included)")
        print(f"  {current['production_functions_annotated']} of "
              f"{current['production_functions']} production functions annotated "
              f"({annotation_ratio(current):.1%})")
        limits = current["limits_for_new_functions"]  # type: ignore[index]
        print(f"  ceiling for new functions: statements={limits['statements']}, "
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

    if issues:
        print(f"code quality check failed ({len(issues)} issue(s)):", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        print("\nNothing here asks for a refactor. It asks that these numbers not grow.",
              file=sys.stderr)
    else:
        print(f"OK: {len(current['functions'])} functions, none regressed against "  # type: ignore[arg-type]
              f"the baseline. Annotation coverage {annotation_ratio(current):.1%} "
              f"across {current['production_functions']} production functions.")

    return exit_code(issues)


if __name__ == "__main__":
    sys.exit(main())
