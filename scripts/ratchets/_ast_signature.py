#!/usr/bin/env python3
"""
_ast_signature.py — content fingerprints for "has this subject changed?",
under an explicitly named equivalence relation.

Library-only: imported, never run, so it carries no Usage: block by design
(see CONTRIBUTING.md's docstring contract, which exempts modules with no
__main__ entry point).

THE LEVELS, AND WHY THE NAME TRAVELS WITH THE DIGEST

Code-clone research classifies "the same code" by type. Zhang & Saber,
arXiv:2506.14470 section II-A, define Type-1 as "identical except for
superficial differences such as formatting and comments" and Type-2 as
adding "renamed variables, altered data types, or changes in literals."

    raw  sha256 of the file's bytes. Moves on whitespace. Included only so
         a non-Python subject has an honest level rather than being aliased
         to something it is not.
    t1   Type-1. sha256 of ast.dump(..., include_attributes=False), which
         drops comments (never in the AST) and positions.
    t2   Type-1 plus docstrings. Docstrings are string literals, so this is
         deliberately a *partial* Type-2 -- it normalizes one class of
         literal and no other. That asymmetry is a choice, made below.

A DIGEST WITHOUT ITS LEVEL IS NOT COMPARABLE TO ANYTHING. Measured across 14
modules in this repo, t1 and t2 agreed on zero of them. So signature()
returns "level:digest", never a bare hash: two digests computed under
different relations must never silently compare equal or unequal.

WHY t2 IS THE DEFAULT FOR DOCUMENTATION CLAIMS

t1 is the principled standard class, and the first draft of this module
defaulted to it on that basis. Measurement overturned that. PR #49
restructured three modules' docstrings: 18, 12 and 11 changed lines, with
*zero* changed lines outside the docstring in all three. Under t1 that one
PR stales every claim about those modules for a change that altered nothing
executable -- and 15 further modules are queued for the same treatment by
the docstring contract.

The error costs are asymmetric: a false positive does not cost one wasted
check, it costs the checker, because someone switches it off. t1 remains
available and named for a claim that really is about a module's
documentation -- 12 scripts here pass description=__doc__ to argparse, so
their module docstring genuinely is user-facing --help output.
"""

import ast
import hashlib
from pathlib import Path
from typing import Set

LEVELS: Set[str] = {"raw", "t1", "t2"}
DEFAULT_LEVEL = "t2"


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """Remove the docstring Expr from every module, class and function."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:]
    return tree


def signature_of_source(source: str, level: str = DEFAULT_LEVEL) -> str:
    """`level:digest` for Python source held in memory.

    Raises ValueError on an unknown level rather than falling back: a level
    nobody implemented must not quietly become a different relation, because
    the caller would then compare two incomparable digests and believe the
    answer."""
    if level not in LEVELS:
        raise ValueError(f"unknown signature level {level!r}; expected one of "
                         f"{', '.join(sorted(LEVELS))}")
    if level == "raw":
        return f"raw:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"
    tree = ast.parse(source)
    if level == "t2":
        tree = _strip_docstrings(tree)
    dumped = ast.dump(tree, include_attributes=False)
    return f"{level}:{hashlib.sha256(dumped.encode('utf-8')).hexdigest()}"


def signature(path: Path, level: str = DEFAULT_LEVEL) -> str:
    """`level:digest` for a file on disk.

    A non-Python subject is hashed raw and *labelled* raw, whatever level was
    requested. Silently honouring the request would return a `t2:` digest for
    a file that was never parsed -- a label asserting a normalization that did
    not happen."""
    if path.suffix != ".py":
        return f"raw:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    return signature_of_source(path.read_text(encoding="utf-8"), level)


def split_signature(value: str) -> tuple:
    """(level, digest) from a stored `level:digest`. Raises on a bare hash,
    which is the shape that predates this module and cannot be interpreted."""
    level, _, digest = value.partition(":")
    if not digest or level not in LEVELS:
        raise ValueError(f"malformed signature {value!r}; expected "
                         f"'<level>:<digest>' with level in {sorted(LEVELS)}")
    return level, digest
