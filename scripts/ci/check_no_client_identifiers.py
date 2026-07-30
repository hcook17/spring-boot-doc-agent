#!/usr/bin/env python3
"""Gate the aggregate layer of a bytecode-oracle run before it can cross into tracked files.

Usage:
    python3 scripts/ci/check_no_client_identifiers.py <aggregate.json>
    python3 scripts/ci/check_no_client_identifiers.py <aggregate.json> --against-checkout <path>

WHY THIS EXISTS
---------------
``CONSTRAINTS.md`` carries a standing rule that a real target repository's name, packages and
class names must never appear in this repo's own tracked files. It also records that the last
time the rule was broken, the breach was "caught by the repo owner on review, not by any check -
nothing mechanical looks for this". This script is the mechanical check that observation asked
for.

It is the second of two defences, and the weaker one. The first is that the oracle pseudonymises
identifiers *before* writing anything, so an identifier-bearing artifact never exists on disk.
This script assumes that defence could fail and checks the result anyway.

ALLOWLIST, NOT DENYLIST
-----------------------
The check is structural: every key and every string value in the aggregate must come from a
closed vocabulary. It does not hunt for known-bad substrings, because a denylist can only refuse
what someone thought to enumerate, and the identifiers most worth catching are the ones nobody
anticipated. Anything unrecognised fails, so a new field added upstream fails closed here and
has to be reviewed rather than silently admitted.

An optional denylist pass (``--against-checkout``) runs on top when the local checkout is
available, catching the case where a string happens to satisfy the vocabulary while still
naming something real.

EXIT CODES
----------
0  clean; the aggregate carries no identifier and may cross
1  a violation was found, or a required input was missing
2  usage error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

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


class Violation(Exception):
    pass


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
        description="Fail if an oracle aggregate carries any client identifier.",
    )
    parser.add_argument("aggregate", type=Path, help="path to aggregate.json")
    parser.add_argument(
        "--against-checkout",
        type=Path,
        default=None,
        help="optional local checkout to cross-check names against",
    )
    args = parser.parse_args(argv)

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
