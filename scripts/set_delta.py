#!/usr/bin/env python3
"""Classify how the evidence set changed, into expected and unexplained.

Usage:
    python3 scripts/set_delta.py <repo-a> <repo-b>            # report the delta
    python3 scripts/set_delta.py <repo-a> <repo-b> --relation unchanged

WHY THIS EXISTS

Stage 0's output is a set. It changes for three different reasons -- the target
code changed, the rules changed, or something broke -- and today those are
indistinguishable in the output. `spring_drift_check.py` answers "did this
citation move?" precisely, but nothing answers "was this movement the one we
predicted?", so any review of a delta is a human squinting at a count.

That is the same defect `stage0_oracle_compare.py` was written to fix for
recall: a bare number cannot separate a cause that implies "fix the rules"
from one that implies "nothing to fix", so it is not a usable input to a
decision. This applies it to the set itself.

THE RESIDUE IS THE FINDING

A relation states which movements were expected. Everything the relation does
not permit is residue, and the residue -- not the size of the delta -- is what
fails. A change that adds a rule SHOULD grow the set; a change that reformats
a file should not move it at all. Gating on "the count changed" would flag the
first and miss the second.

Relations are a closed registry, the same discipline as check_repo_claims.py's
PREDICATE_HANDLERS and DERIVATIONS: a caller selects among behaviours defined
here and can never supply one.

MEMBERSHIP AND ITS EQUIVALENCE RELATION

A member is (file, rule_id, normalized_match). The normalizer is
drift_match_normalizers.tokens by default rather than the first_line status
quo, because that is what the measurement in
claude/drift-normalization-measurement-2026-07-25.md actually found: 0/208
false positives against first_line's 2/208, with neither missing a real edit.
Comparing raw match text instead would report every reindent as a change.

VALIDITY GATE

Borrowed from java_perturbations' harness: a delta is only scoreable if both
scans succeeded. A scan that failed and one that legitimately found nothing
produce the same empty set, and scoring that as "everything was removed" is a
confident wrong answer.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, NamedTuple, Sequence, Tuple

from doc_engine.tools import spring_signal_scan

sys.path.insert(0, str(Path(__file__).resolve().parent))

import drift_match_normalizers as norm  # noqa: E402  # meta: same-dir


class Member(NamedTuple):
    """One evidence fact, under the equivalence relation `normalizer` induces."""
    file: str
    rule_id: str
    match: str


class Delta(NamedTuple):
    added: FrozenSet[Member]
    removed: FrozenSet[Member]

    def is_empty(self) -> bool:
        return not self.added and not self.removed


class Residue(NamedTuple):
    """The part of a delta no relation accounted for."""
    added: FrozenSet[Member]
    removed: FrozenSet[Member]

    def is_empty(self) -> bool:
        return not self.added and not self.removed

    def describe(self) -> List[str]:
        lines = [f"  + {m.file} [{m.rule_id}] {m.match[:70]}" for m in sorted(self.added)]
        lines += [f"  - {m.file} [{m.rule_id}] {m.match[:70]}" for m in sorted(self.removed)]
        return lines


class ScanFailed(RuntimeError):
    """The validity gate. A failed scan must never be scored as a delta."""


# A relation answers: was this member's movement expected?
# `direction` is "added" or "removed".
Relation = Callable[[Member, str], bool]


def signals_set(repo_path, normalizer=norm.tokens) -> FrozenSet[Member]:
    """The evidence set for one repo, as members under `normalizer`.

    The path check is the validity gate and is not redundant: scan() walks a
    nonexistent directory to completion and returns a well-formed result with
    empty buckets, which is indistinguishable from a repo that genuinely
    contains nothing. Comparing against that reports every member as removed.
    A test asserting this raises is what found it.
    """
    path = Path(repo_path)
    if not path.is_dir():
        raise ScanFailed(f"{repo_path} is not a directory; refusing to score a "
                         f"delta against a scan that cannot have run")
    try:
        result = spring_signal_scan.scan(str(path), scanners=["filesystem", "ast-grep"])
    except Exception as exc:  # noqa: BLE001 - re-raised as the validity gate
        raise ScanFailed(f"scan of {repo_path} failed: {exc}") from exc
    members = set()
    for entries in result["evidence"].values():
        for entry in entries:
            members.add(Member(entry["file"],
                               entry.get("rule_id") or entry.get("match", ""),
                               normalizer(entry.get("match", ""))))
    return frozenset(members)


def delta(before: FrozenSet[Member], after: FrozenSet[Member]) -> Delta:
    return Delta(added=frozenset(after - before), removed=frozenset(before - after))


# ---------------------------------------------------------------------------
# The closed relation registry
# ---------------------------------------------------------------------------

def unchanged() -> Relation:
    """Nothing may move. For reordering, reindenting, comment-only edits."""
    return lambda member, direction: False


def confined_to(files: Sequence[str]) -> Relation:
    """Locality: only these files' members may move. This is the relation
    that catches a rule edit reaching further than the file it was aimed at."""
    allowed = frozenset(files)
    return lambda member, direction: member.file in allowed


def confined_to_rules(rule_ids: Sequence[str]) -> Relation:
    """Only these rules' members may move. Adding a rule must not disturb
    what the existing rules already found."""
    allowed = frozenset(rule_ids)
    return lambda member, direction: member.rule_id in allowed


def grows_only() -> Relation:
    """Additions are fine; any removal is a regression."""
    return lambda member, direction: direction == "added"


RELATIONS: Dict[str, Callable[..., Relation]] = {
    "unchanged": unchanged,
    "confined_to": confined_to,
    "confined_to_rules": confined_to_rules,
    "grows_only": grows_only,
}


def classify(change: Delta, relation: Relation) -> Residue:
    """Everything the relation does not permit."""
    return Residue(
        added=frozenset(m for m in change.added if not relation(m, "added")),
        removed=frozenset(m for m in change.removed if not relation(m, "removed")),
    )


def counts_by_rule(members: FrozenSet[Member]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for member in members:
        counts[member.rule_id] = counts.get(member.rule_id, 0) + 1
    return counts


def check_scaling(before: FrozenSet[Member], after: FrozenSet[Member],
                  factor: int) -> List[str]:
    """Duplicating a corpus n times must multiply every rule's count by n.

    Not expressible as a per-member relation, so it lives beside them rather
    than being bent into the registry. Members are deduplicated by
    construction, so this compares per-rule counts, not set sizes."""
    before_counts, after_counts = counts_by_rule(before), counts_by_rule(after)
    problems = []
    for rule, was in sorted(before_counts.items()):
        now = after_counts.get(rule, 0)
        if now != was * factor:
            problems.append(f"{rule}: {was} -> {now}, expected {was * factor}")
    return problems


def compare(repo_a, repo_b, relation: Relation) -> Tuple[Delta, Residue]:
    change = delta(signals_set(repo_a), signals_set(repo_b))
    return change, classify(change, relation)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_a")
    parser.add_argument("repo_b")
    parser.add_argument("--relation", default="unchanged", choices=sorted(RELATIONS),
                        help="relation with no arguments; richer relations are "
                             "used from tests, not the CLI")
    args = parser.parse_args(argv)

    if args.relation not in ("unchanged", "grows_only"):
        print(f"error: --relation {args.relation} needs arguments; call it from "
              f"a test rather than the CLI", file=sys.stderr)
        return 2
    try:
        change, residue = compare(args.repo_a, args.repo_b, RELATIONS[args.relation]())
    except ScanFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"delta: +{len(change.added)} -{len(change.removed)} "
          f"under relation '{args.relation}'")
    if residue.is_empty():
        print("OK: every change was expected under this relation.")
        return 0
    print(f"unexplained ({len(residue.added)} added, {len(residue.removed)} removed):",
          file=sys.stderr)
    for line in residue.describe():
        print(line, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
