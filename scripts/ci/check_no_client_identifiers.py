#!/usr/bin/env python3
"""Fail closed when client identifiers would enter this repo's tracked tree.

Usage:
    # Repo-wide denylist (CI default) — scan every tracked path + text content
    python3 scripts/ci/check_no_client_identifiers.py --tracked-tree

    # Oracle aggregate allowlist (bytecode-oracle gate)
    python3 scripts/ci/check_no_client_identifiers.py <aggregate.json>
    python3 scripts/ci/check_no_client_identifiers.py <aggregate.json> --against-checkout <path>

WHY THIS EXISTS
---------------
``CONSTRAINTS.md`` carries a standing rule that a real target repository's name,
packages and class names must never appear in this repo's own tracked files.
The last breach was "caught by the repo owner on review, not by any check".

Two complementary gates live in this module:

1. **Tracked-tree denylist** (``--tracked-tree``) — known-bad tokens from
   ``scripts/ci/client_identifier_denylist.txt`` must not appear in any tracked
   path or UTF-8 text file. The denylist file itself is the only allowed home
   for those strings.

2. **Aggregate allowlist** — every key/string in an oracle ``aggregate.json``
   must come from a closed vocabulary (fail closed on unknown fields). Optional
   ``--against-checkout`` cross-checks names present in a local target tree.

EXIT CODES
----------
0  clean
1  a violation was found, or a required input was missing
2  usage error
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from doc_engine.paths import repo_root

REPO_ROOT = repo_root()
DENYLIST_REL = Path("scripts/ci/client_identifier_denylist.txt")

# Keys permitted anywhere in the aggregate. A key outside this set fails rather than being
# skipped: an unknown key is exactly where an identifier would arrive.
ALLOWED_KEYS = {
    "schema_version", "_producer", "evidence_tier", "shared_input_digest",
    "java_files_scanned", "interfaces_with_extends",
    "summaries", "misses", "unclassified_total", "thresholds",
    # summaries[] / misses[] entries (when _walk recurses into list elements, parent_key
    # becomes "summaries"/"misses" unchanged, so these must be flat ALLOWED_KEYS members)
    "arm", "variant", "question", "oracle_total", "matched", "missed",
    "recall", "precision", "false_positives", "delta_by_cause", "verdict_by_cause",
    "entity_pseudonym", "oracle_state", "engine_state", "cause",
    # thresholds
    "min_recall", "max_unclassified", "note",
}

# Keys whose sub-keys are generated rather than fixed, with the pattern each must match.
GENERATED_KEY_PATTERNS = {
    # Both keyed on the CAUSES enum's full closed set (6 names), not just the 3
    # assign_cause() can reach today -- the enum is the shared contract.
    "delta_by_cause": re.compile(
        r"^(INTERMEDIATE_BASE_INHERITANCE|META_OR_INHERITED_ANNOTATION|"
        r"CLASSPATH_PRESENCE_MISMATCH|ABSTRACT_CHAIN_IMPLEMENTATION|"
        r"PATTERN_EXPRESSIVENESS|UNCLASSIFIED)$"),
    "verdict_by_cause": re.compile(
        r"^(INTERMEDIATE_BASE_INHERITANCE|META_OR_INHERITED_ANNOTATION|"
        r"CLASSPATH_PRESENCE_MISMATCH|ABSTRACT_CHAIN_IMPLEMENTATION|"
        r"PATTERN_EXPRESSIVENESS|UNCLASSIFIED)$"),
}

ALLOWED_STRING_VALUES = {
    "stage0-oracle-compare",
    "source-text",
    "astgrep", "semgrep",
    "native", "multipass",
    "q1_repository_chains",
    "USED",
    "PRESENT_UNUSED", "ABSENT_FROM_CLASSPATH",
    "STRUCTURAL", "EVIDENTIARY", "INVESTIGATE",
}

# Values that are generated rather than drawn from a fixed vocabulary, each pinned to a shape
# tight enough that an identifier could not satisfy it.
PATTERNED_STRING_VALUES = {
    "shared_input_digest": re.compile(r"^[0-9a-f]{64}$"),
    # kind is hardcoded "iface" at every pseudonym() call site in stage0_oracle_compare.py;
    # pin to that rather than generalize speculatively.
    "entity_pseudonym": re.compile(r"^iface_[0-9a-f]{12}$"),
}

# Free-text fields, allowed to be prose but still checked for identifier shapes.
PROSE_KEYS = {"note"}

# A dotted lowercase package path of three or more segments, or a CamelCase identifier long
# enough to be a real type name. Used only for the prose fields and the denylist pass.
PACKAGE_SHAPE = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}\b")

# Skip content scan for these extensions (path names still checked).
_BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".jar",
    ".class", ".so", ".dll", ".exe", ".whl", ".pyc", ".pyo",
}


class Violation(Exception):
    pass


def load_denylist(root: Path) -> List[str]:
    """Return non-empty denylist tokens from the committed denylist file."""
    path = root / DENYLIST_REL
    if not path.is_file():
        raise FileNotFoundError(f"denylist missing: {DENYLIST_REL.as_posix()}")
    tokens: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens.append(stripped)
    if not tokens:
        raise ValueError(f"{DENYLIST_REL.as_posix()} has no tokens")
    return tokens


def _tracked_paths(root: Path) -> List[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    return [p for p in result.stdout.decode("utf-8", errors="replace").split("\0") if p]


def scan_paths_for_tokens(
    root: Path,
    rel_paths: Iterable[str],
    tokens: Optional[Sequence[str]] = None,
    *,
    skip_denylist_file: bool = True,
) -> List[str]:
    """Return findings for denylist tokens in paths and UTF-8 file contents.

    Used by ``--tracked-tree`` and by unit tests against a synthetic file set.
    """
    token_list = list(tokens) if tokens is not None else load_denylist(root)
    denylist_posix = DENYLIST_REL.as_posix()
    findings: List[str] = []
    for rel in rel_paths:
        posix = rel.replace("\\", "/")
        if skip_denylist_file and posix == denylist_posix:
            continue
        for token in token_list:
            if token in posix:
                findings.append(f"path {posix!r} contains denylist token {token!r}")
        path = root / rel
        if not path.is_file():
            continue
        if path.suffix.lower() in _BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in token_list:
            if token in text:
                findings.append(
                    f"{posix}: content contains denylist token {token!r}"
                )
    return findings


def scan_tracked_tree(root: Path | None = None) -> List[str]:
    """Scan every git-tracked path under *root* for denylist tokens."""
    base = root if root is not None else REPO_ROOT
    return scan_paths_for_tokens(base, _tracked_paths(base))


def _walk(node: Any, path: str, parent_key: str | None, findings: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            pattern = GENERATED_KEY_PATTERNS.get(parent_key or "")
            if pattern is not None:
                if not pattern.match(key):
                    findings.append(
                        f"{here}: generated key {key!r} does not match the permitted shape for "
                        f"{parent_key!r}"
                    )
            elif key not in ALLOWED_KEYS:
                findings.append(
                    f"{here}: key {key!r} is not in the allowlist. If this field is legitimate, "
                    f"add it deliberately - failing closed here is the point."
                )
            _walk(value, here, key, findings)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, f"{path}[{index}]", parent_key, findings)
    elif isinstance(node, str):
        if parent_key in PROSE_KEYS:
            for match in PACKAGE_SHAPE.findall(node):
                findings.append(f"{path}: prose contains a package-shaped token {match!r}")
        elif parent_key in PATTERNED_STRING_VALUES:
            if not PATTERNED_STRING_VALUES[parent_key].match(node):
                findings.append(
                    f"{path}: value {node!r} does not match the permitted shape "
                    f"for {parent_key!r}"
                )
        elif node not in ALLOWED_STRING_VALUES:
            findings.append(
                f"{path}: string value {node!r} is not in the permitted vocabulary"
            )
    elif isinstance(node, bool) or isinstance(node, int) or isinstance(node, float):
        return
    elif node is None:
        return
    else:
        findings.append(f"{path}: unexpected value type {type(node).__name__}")


def _denylist_pass(payload: str, checkout: Path, findings: list[str]) -> None:
    """Cross-check against names actually present in the local checkout.

    Catches the residual case the allowlist cannot: a value that satisfies the vocabulary while
    still naming something real. Only runs when the checkout is available, so it is a bonus
    rather than a dependency.
    """
    names: set[str] = set()
    for java in checkout.rglob("*.java"):
        try:
            rel = java.relative_to(checkout)
        except ValueError:
            continue
        names.add(java.stem)
        parts = [p for p in rel.parts[:-1] if p not in {"src", "main", "test", "java", "mocks"}]
        if len(parts) >= 2:
            names.add(".".join(parts))
    # Very short stems produce noise ("Ids"); require enough length to be meaningful.
    for name in sorted(n for n in names if len(n) >= 6):
        if re.search(rf"\b{re.escape(name)}\b", payload):
            findings.append(f"denylist: aggregate contains {name!r}, a name from the checkout")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if client identifiers appear in tracked files or an oracle aggregate.",
    )
    parser.add_argument(
        "aggregate",
        type=Path,
        nargs="?",
        default=None,
        help="path to aggregate.json (omit when using --tracked-tree)",
    )
    parser.add_argument(
        "--tracked-tree",
        action="store_true",
        help="scan every git-tracked path/content against the client denylist",
    )
    parser.add_argument(
        "--against-checkout",
        type=Path,
        default=None,
        help="optional local checkout to cross-check aggregate names against",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repo root for --tracked-tree (default: doc_engine.paths.repo_root())",
    )
    args = parser.parse_args(argv)

    if args.tracked_tree:
        if args.aggregate is not None:
            print(
                "ERROR: pass either --tracked-tree or an aggregate path, not both",
                file=sys.stderr,
            )
            return 2
        root = args.root if args.root is not None else REPO_ROOT
        try:
            findings = scan_tracked_tree(root)
        except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if findings:
            print(
                f"CLIENT IDENTIFIER GATE FAILED: {len(findings)} finding(s) in tracked tree",
                file=sys.stderr,
            )
            for finding in findings:
                print(f"  - {finding}", file=sys.stderr)
            print(
                "\nPurge the token from tracked files, or add it only to "
                f"{DENYLIST_REL.as_posix()} if it is a newly forbidden name.",
                file=sys.stderr,
            )
            return 1
        print(f"client identifier gate: clean tracked tree ({root})")
        return 0

    if args.aggregate is None:
        parser.print_usage(sys.stderr)
        print(
            "error: aggregate path required unless --tracked-tree is set",
            file=sys.stderr,
        )
        return 2

    if not args.aggregate.is_file():
        print(f"ERROR: no aggregate at {args.aggregate}", file=sys.stderr)
        return 1

    raw = args.aggregate.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: {args.aggregate} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    findings: list[str] = []
    _walk(payload, "", None, findings)

    if args.against_checkout is not None:
        if not args.against_checkout.is_dir():
            print(
                f"ERROR: --against-checkout {args.against_checkout} is not a directory",
                file=sys.stderr,
            )
            return 1
        _denylist_pass(raw, args.against_checkout, findings)

    if findings:
        print(
            f"REDACTION GATE FAILED: {len(findings)} finding(s) in {args.aggregate}",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print(
            "\nThis file must not cross into tracked files until every finding is resolved.",
            file=sys.stderr,
        )
        return 1

    print(f"redaction gate: clean ({args.aggregate})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
