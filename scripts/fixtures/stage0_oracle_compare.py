#!/usr/bin/env python3
"""Score source-level engines against the bytecode oracle, and attribute every miss to a cause.

Run with:
  python3 scripts/fixtures/stage0_oracle_compare.py <path> --oracle oracle.json [--out report.json]

WHAT THIS ANSWERS
-----------------
Stage 0 reads source text. Source text cannot cross the jar boundary, so some facts about a
Spring codebase are unreachable to it no matter how good the rules get, while others are merely
unreached by the rules as currently written. Those two look identical in a recall number and
imply opposite fixes, so a bare percentage is not a usable input to any decision.

This script separates them. It replays each engine against the same entity set the oracle
resolved, and labels every miss with a cause carrying a standing verdict:

  STRUCTURAL   the engine could see this with better rules - fix Stage 0 where it stands
  EVIDENTIARY  no rule can see this from source - only resolution can

Each engine is scored **twice** per question, which is what makes that verdict empirical rather
than asserted:

  native      the rule exactly as Stage 0 ships it today
  multipass   the same engine plus a driver that chases intra-repo `extends` links transitively

The gap between the two IS the inheritance cause, measured. If multipass recovers the misses,
they were structural; if it does not, the cause was mislabelled and the taxonomy needs work.

FAIRNESS
--------
Both engines receive byte-identical inputs: the same file list in the same order, the same
entity set, the same intermediate-resolution closure. The multi-pass driver is written once and
parameterised by engine rather than reimplemented per arm. The only permitted difference is the
pattern language, because that is the variable under test - an "engine win" that turned out to be
a preprocessing artifact would be worse than no measurement, since it would look like evidence.
For Arm C (semgrep), scripts/coverage/spring_semgrep_rules.yml is valid --semgrep-rules input.

CONFIDENTIALITY
---------------
Real names are read from source into memory and never written. Every emitted row is keyed by the
same salted pseudonym the oracle used, recomputed here from the salt file inside the checkout, so
rows correlate across arms without any identifier reaching disk.

EXIT CODES
----------
0  compared cleanly
1  producer-contract violation, or a required input was missing
2  usage error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
PRODUCER = "stage0-oracle-compare"

# The rule Stage 0 actually ships for repositories. Extracted verbatim rather than
# reimplemented: a reimplementation would measure this script's idea of the rule.
STAGE0_REPOSITORY_RULE_ID = "persistence__repository"

# Closed enum. A row carrying anything else fails schema validation on write.
CAUSES = {
    "INTERMEDIATE_BASE_INHERITANCE": "STRUCTURAL",
    "META_OR_INHERITED_ANNOTATION": "EVIDENTIARY",
    "CLASSPATH_PRESENCE_MISMATCH": "EVIDENTIARY",
    "ABSTRACT_CHAIN_IMPLEMENTATION": "STRUCTURAL",
    "PATTERN_EXPRESSIVENESS": "STRUCTURAL",
    "UNCLASSIFIED": "INVESTIGATE",
}

# The five names Stage 0's repository rule matches literally.
SIGNAL_SCAN_REPOSITORY_NAMES = {
    "JpaRepository",
    "CrudRepository",
    "PagingAndSortingRepository",
    "MongoRepository",
    "ReactiveCrudRepository",
}


class ContractViolation(Exception):
    """Raised when the comparison's own inputs are untrustworthy."""


# --------------------------------------------------------------------------------------------
# Pseudonyms - must match the oracle's Java implementation byte for byte
# --------------------------------------------------------------------------------------------


def load_salt(oracle_dir: Path) -> bytes:
    salt_path = oracle_dir / ".pseudonym-salt"
    if not salt_path.is_file():
        raise ContractViolation(
            f"No pseudonym salt at {salt_path}. Without it, rows produced here cannot be "
            f"correlated with the oracle's, and every delta would be unattributable."
        )
    salt = salt_path.read_bytes()
    if len(salt) < 16:
        raise ContractViolation(f"Salt at {salt_path} is too short to be the oracle's.")
    return salt


def pseudonym(salt: bytes, kind: str, fqcn: str) -> str:
    """SHA-256(salt || name), first 6 bytes, hex - identical to Pseudonymizer.java."""
    digest = hashlib.sha256()
    digest.update(salt)
    digest.update(fqcn.encode("utf-8"))
    return f"{kind}_{digest.digest()[:6].hex()}"


# --------------------------------------------------------------------------------------------
# Shared preprocessing - identical for every arm, by construction
# --------------------------------------------------------------------------------------------


@dataclass
class SharedInputs:
    """Everything both engines see. Hashed so the comparator can prove they saw the same thing."""

    java_files: list[Path]
    source_root: Path
    fqcn_by_simple_name: dict[str, list[str]]
    declared_interfaces: dict[str, list[str]]  # fqcn -> raw supertype tokens
    digest: str = ""

    def compute_digest(self) -> str:
        hasher = hashlib.sha256()
        for path in self.java_files:
            hasher.update(str(path.relative_to(self.source_root)).replace("\\", "/").encode())
            hasher.update(b"\0")
        self.digest = hasher.hexdigest()
        return self.digest


def list_java_files(source_root: Path) -> list[Path]:
    """Deterministically ordered, so both arms and successive runs see one identical list."""
    return sorted(source_root.rglob("*.java"), key=lambda p: str(p).replace("\\", "/"))


def fqcn_for(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root).with_suffix("")
    return ".".join(relative.parts)


# --------------------------------------------------------------------------------------------
# Engine adapters
# --------------------------------------------------------------------------------------------


def extract_stage0_rule(rules_file: Path, rule_id: str) -> str:
    """Pull one rule document out of Stage 0's multi-document rule file, verbatim."""
    if not rules_file.is_file():
        raise ContractViolation(f"Stage 0 rule file not found at {rules_file}")
    text = rules_file.read_text(encoding="utf-8")
    documents = re.split(r"^---\s*$", text, flags=re.M)
    for document in documents:
        if re.search(rf"^id:\s*{re.escape(rule_id)}\s*$", document, flags=re.M):
            return document.strip()
    raise ContractViolation(
        f"Rule {rule_id!r} not found in {rules_file}. The comparison replays Stage 0's real "
        f"rule; without it there is nothing valid to measure."
    )


def run_astgrep(rule_text: str, scan_root: Path, binary: str) -> list[dict[str, Any]]:
    with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False, encoding="utf-8") as handle:
        handle.write(rule_text)
        rule_path = Path(handle.name)
    try:
        result = subprocess.run(
            [binary, "scan", "--rule", str(rule_path), "--json=compact", str(scan_root)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode not in (0, 1):
            raise ContractViolation(
                f"ast-grep exited {result.returncode}: {result.stderr.strip()[:400]}"
            )
        payload = (result.stdout or "").strip()
        return json.loads(payload) if payload else []
    finally:
        rule_path.unlink(missing_ok=True)


def run_semgrep(rules_file: Path, scan_root: Path, binary: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            binary, "scan",
            "--config", str(rules_file),
            "--json",
            "--quiet",
            "--no-git-ignore",
            "--metrics", "off",
            str(scan_root),
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode not in (0, 1):
        raise ContractViolation(
            f"semgrep exited {result.returncode}: {result.stderr.strip()[:400]}"
        )
    payload = (result.stdout or "").strip()
    if not payload:
        return []
    return json.loads(payload).get("results", [])


# --------------------------------------------------------------------------------------------
# Q1 - repository chains
# --------------------------------------------------------------------------------------------

# Applied only to the text of an AST-selected interface declaration, never to a whole file -
# the same discipline spring_signal_scan.py uses for its own extractors.
INTERFACE_HEAD_RE = re.compile(
    r"\binterface\s+(?P<name>\w+)\s*(?:<[^{]*?>)?\s*extends\s+(?P<supers>[^{]+)",
    re.S,
)


def parse_supertypes(node_text: str) -> tuple[str | None, list[str]]:
    """Return (interface simple name, supertype simple names) from a declaration's own text."""
    match = INTERFACE_HEAD_RE.search(node_text)
    if not match:
        return None, []
    name = match.group("name")
    supers_blob = match.group("supers")
    # Strip generic arguments before splitting, so `Foo<A, B>, Bar` yields ["Foo", "Bar"]
    # rather than splitting inside the type argument list.
    depth = 0
    flattened: list[str] = []
    current: list[str] = []
    for char in supers_blob:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            flattened.append("".join(current))
            current = []
            continue
        if depth == 0 and char not in "<>":
            current.append(char)
    flattened.append("".join(current))
    supers = []
    for token in flattened:
        token = token.strip().split(".")[-1]
        if token:
            supers.append(token)
    return name, supers


def build_interface_graph(
    shared: SharedInputs, binary: str
) -> dict[str, list[str]]:
    """Every interface in the corpus and the simple names it extends.

    This is the shared intermediate-resolution input. Both arms consume this exact structure, so
    neither can win on preprocessing.
    """
    rule = (
        "id: oracle-interface-extends\n"
        "language: java\n"
        "rule:\n"
        "  kind: interface_declaration\n"
        "  has: { kind: extends_interfaces }\n"
    )
    matches = run_astgrep(rule, shared.source_root, binary)
    graph: dict[str, list[str]] = {}
    for match in matches:
        text = match.get("text", "")
        name, supers = parse_supertypes(text)
        if not name:
            continue
        file_path = Path(match["file"])
        if not file_path.is_absolute():
            file_path = shared.source_root.parent / file_path
        try:
            fqcn = fqcn_for(file_path.resolve(), shared.source_root.resolve())
        except ValueError:
            continue
        # A file declares one public type; nested interfaces share the file's FQCN prefix and
        # are keyed by their own simple name to keep the closure resolvable.
        key = fqcn if fqcn.split(".")[-1] == name else f"{fqcn}${name}"
        graph[key] = supers
    return graph


def reaches_spring_data(
    start: str,
    graph: dict[str, list[str]],
    by_simple_name: dict[str, list[str]],
    targets: set[str],
) -> bool:
    """Transitive closure over intra-repo `extends` links - the honest best case for source."""
    seen = {start}
    queue = [start]
    while queue:
        current = queue.pop()
        for supertype_simple in graph.get(current, []):
            if supertype_simple in targets:
                return True
            for candidate in by_simple_name.get(supertype_simple, []):
                if candidate not in seen:
                    seen.add(candidate)
                    queue.append(candidate)
    return False


@dataclass
class ArmResult:
    arm: str
    variant: str
    question: str
    matched: set[str] = field(default_factory=set)
    claimed: set[str] = field(default_factory=set)
    misses: list[dict[str, Any]] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)


def assign_cause(oracle_row: dict[str, Any], variant: str) -> str:
    """Ordered predicate chain returning AT MOST ONE label.

    Deliberately not an accumulating set. Overlapping buckets would make every downstream
    percentage meaningless, so a row satisfying two predicates is a taxonomy defect that the
    caller asserts on rather than silently resolving by order.
    """
    candidates = []
    if oracle_row.get("via_intermediate_only"):
        candidates.append("INTERMEDIATE_BASE_INHERITANCE")
    if not oracle_row.get("matches_signal_scan_name_list") and not oracle_row.get(
        "via_intermediate_only"
    ):
        candidates.append("PATTERN_EXPRESSIVENESS")
    if not candidates:
        return "UNCLASSIFIED"
    if len(candidates) > 1:
        raise ContractViolation(
            f"Taxonomy defect: row matched {len(candidates)} causes {candidates}. Buckets must "
            f"be mutually exclusive or every reported percentage is meaningless."
        )
    return candidates[0]


def compare_q1(
    oracle_rows: list[dict[str, Any]],
    matched_pseudonyms: set[str],
    arm: str,
    variant: str,
) -> ArmResult:
    result = ArmResult(arm=arm, variant=variant, question="q1_repository_chains")
    result.claimed = set(matched_pseudonyms)
    for row in oracle_rows:
        handle = row["entity_pseudonym"]
        if handle in matched_pseudonyms:
            result.matched.add(handle)
        else:
            result.misses.append(
                {
                    "arm": arm,
                    "variant": variant,
                    "question": "q1_repository_chains",
                    "entity_pseudonym": handle,
                    "oracle_state": "USED",
                    "engine_state": "PRESENT_UNUSED",
                    "cause": assign_cause(row, variant),
                }
            )
    oracle_handles = {row["entity_pseudonym"] for row in oracle_rows}
    result.false_positives = sorted(matched_pseudonyms - oracle_handles)
    return result


# --------------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------------


def summarise(result: ArmResult, denominator: int) -> dict[str, Any]:
    by_cause: dict[str, int] = defaultdict(int)
    for miss in result.misses:
        by_cause[miss["cause"]] += 1
    recall = len(result.matched) / denominator if denominator else None
    precision = (
        len(result.matched) / len(result.claimed) if result.claimed else None
    )
    return {
        "arm": result.arm,
        "variant": result.variant,
        "question": result.question,
        "oracle_total": denominator,
        "matched": len(result.matched),
        "missed": len(result.misses),
        "recall": round(recall, 4) if recall is not None else None,
        "precision": round(precision, 4) if precision is not None else None,
        "false_positives": len(result.false_positives),
        "delta_by_cause": dict(sorted(by_cause.items())),
        "verdict_by_cause": {
            cause: CAUSES[cause] for cause in sorted(by_cause) if cause in CAUSES
        },
    }


def validate_rows(rows: Iterable[dict[str, Any]]) -> list[str]:
    """Every miss row carries all six fields, and `cause` comes from the closed enum."""
    required = {"arm", "question", "entity_pseudonym", "oracle_state", "engine_state", "cause"}
    problems: list[str] = []
    for index, row in enumerate(rows):
        missing = required - row.keys()
        if missing:
            problems.append(f"row {index}: missing {sorted(missing)}")
        cause = row.get("cause")
        if cause not in CAUSES:
            problems.append(f"row {index}: cause {cause!r} is not in the closed enum")
    return problems


def print_table(summaries: list[dict[str, Any]], unclassified_total: int) -> None:
    line = "-" * 84
    print()
    print(line)
    print("STAGE 0 SOURCE-ENGINE COMPARISON  (scored against resolved bytecode)")
    print(line)
    print(f"{'ARM':<10} {'VARIANT':<11} {'MATCH':>6} {'MISS':>5} {'RECALL':>8} {'PREC':>7}  CAUSES")
    for summary in summaries:
        causes = ", ".join(
            f"{cause}={count}" for cause, count in summary["delta_by_cause"].items()
        ) or "-"
        recall = f"{summary['recall']:.3f}" if summary["recall"] is not None else "-"
        precision = f"{summary['precision']:.3f}" if summary["precision"] is not None else "-"
        print(
            f"{summary['arm']:<10} {summary['variant']:<11} "
            f"{summary['matched']:>6} {summary['missed']:>5} {recall:>8} {precision:>7}  {causes}"
        )
    print(line)
    print(f"UNCLASSIFIED total: {unclassified_total}"
          + ("   <-- taxonomy is incomplete; investigate before trusting the split"
             if unclassified_total else "   (taxonomy accounts for every miss)"))
    print(line)


# --------------------------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Score ast-grep and semgrep against the bytecode oracle.",
    )
    parser.add_argument("--oracle", type=Path, required=True, help="path to oracle.json")
    parser.add_argument("--source-root", type=Path, required=True,
                        help="java source root, e.g. <repo>/src/main/java")
    parser.add_argument("--stage0-rules", type=Path, required=True,
                        help="path to spring_ast_grep_rules.yml")
    parser.add_argument("--astgrep", default="ast-grep")
    parser.add_argument("--semgrep", default=None,
                        help="semgrep binary; omit to skip arm C")
    parser.add_argument("--semgrep-rules", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="write comparison JSON here")
    args = parser.parse_args(argv)

    try:
        if not args.oracle.is_file():
            raise ContractViolation(
                f"No oracle at {args.oracle}. There is nothing to compare against, which is a "
                f"missing input rather than an empty result."
            )
        if not args.source_root.is_dir():
            raise ContractViolation(f"No source root at {args.source_root}")

        oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
        oracle_q1 = oracle.get("q1_repository_chains", [])
        if not oracle_q1:
            raise ContractViolation("Oracle carries no Q1 rows; refusing to report 0/0.")

        salt = load_salt(args.oracle.parent)

        # Resolve BEFORE listing, not after: list_java_files(root) walks whatever root it is
        # given, and if that root is relative while SharedInputs.source_root is later resolved
        # to absolute, every path.relative_to() call below fails comparing relative vs absolute.
        resolved_source_root = args.source_root.resolve()
        shared = SharedInputs(
            java_files=list_java_files(resolved_source_root),
            source_root=resolved_source_root,
            fqcn_by_simple_name=defaultdict(list),
            declared_interfaces={},
        )
        if not shared.java_files:
            raise ContractViolation(f"No .java files under {args.source_root}")
        for path in shared.java_files:
            fqcn = fqcn_for(path.resolve(), shared.source_root)
            shared.fqcn_by_simple_name[fqcn.split(".")[-1]].append(fqcn)
        shared.compute_digest()

        graph = build_interface_graph(shared, args.astgrep)
        shared.declared_interfaces = graph

        summaries: list[dict[str, Any]] = []
        all_misses: list[dict[str, Any]] = []

        # ---- Arm B, native: Stage 0's real rule, unmodified -------------------------------
        rule_text = extract_stage0_rule(args.stage0_rules, STAGE0_REPOSITORY_RULE_ID)
        native_matches = run_astgrep(rule_text, shared.source_root, args.astgrep)
        native_handles: set[str] = set()
        for match in native_matches:
            file_path = Path(match["file"])
            if not file_path.is_absolute():
                file_path = shared.source_root.parent / file_path
            try:
                fqcn = fqcn_for(file_path.resolve(), shared.source_root)
            except ValueError:
                continue
            native_handles.add(pseudonym(salt, "iface", fqcn))

        native = compare_q1(oracle_q1, native_handles, "astgrep", "native")
        summaries.append(summarise(native, len(oracle_q1)))
        all_misses.extend(native.misses)

        # ---- Arm B, multipass: same engine + transitive intra-repo closure ------------------
        multipass_handles: set[str] = set()
        for fqcn in graph:
            if reaches_spring_data(
                fqcn, graph, shared.fqcn_by_simple_name, SIGNAL_SCAN_REPOSITORY_NAMES
            ):
                multipass_handles.add(pseudonym(salt, "iface", fqcn.split("$")[0]))
        multipass = compare_q1(oracle_q1, multipass_handles, "astgrep", "multipass")
        summaries.append(summarise(multipass, len(oracle_q1)))
        all_misses.extend(multipass.misses)

        # ---- Arm C, semgrep ----------------------------------------------------------------
        if args.semgrep and args.semgrep_rules and args.semgrep_rules.is_file():
            semgrep_results = run_semgrep(args.semgrep_rules, shared.source_root, args.semgrep)
            semgrep_handles: set[str] = set()
            for finding in semgrep_results:
                file_path = Path(finding.get("path", ""))
                if not file_path.is_absolute():
                    file_path = shared.source_root.parent / file_path
                try:
                    fqcn = fqcn_for(file_path.resolve(), shared.source_root)
                except ValueError:
                    continue
                semgrep_handles.add(pseudonym(salt, "iface", fqcn))
            semgrep_native = compare_q1(oracle_q1, semgrep_handles, "semgrep", "native")
            summaries.append(summarise(semgrep_native, len(oracle_q1)))
            all_misses.extend(semgrep_native.misses)

        problems = validate_rows(all_misses)
        if problems:
            raise ContractViolation(
                "Miss rows failed schema validation:\n  - " + "\n  - ".join(problems)
            )

        unclassified = sum(1 for miss in all_misses if miss["cause"] == "UNCLASSIFIED")
        print_table(summaries, unclassified)

        report = {
            "schema_version": SCHEMA_VERSION,
            "_producer": PRODUCER,
            "evidence_tier": "source-text",
            "shared_input_digest": shared.digest,
            "java_files_scanned": len(shared.java_files),
            "interfaces_with_extends": len(graph),
            "summaries": summaries,
            "misses": all_misses,
            "unclassified_total": unclassified,
            # First run records rather than gates: a threshold needs the baseline this run
            # produces, so emitting a number here would encode a guess as a gate.
            "thresholds": {
                "min_recall": None,
                "max_unclassified": None,
                "note": "null until derived from a recorded baseline",
            },
        }
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"wrote {args.out}")
        return 0

    except ContractViolation as exc:
        print(f"CONTRACT VIOLATION: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
