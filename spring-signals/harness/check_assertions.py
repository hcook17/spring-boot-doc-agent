#!/usr/bin/env python3
"""Fail-closed JSON assertion engine for spring-signals query output.

Replaces the expected-empty.txt loop in run.sh, which printed ``DIFF ... <--
investigate`` on a mismatch and still exited 0 -- it asserted nothing. This
engine separates three expectation classes:

- ``asserted``  exact row counts: graded intent. Any miss fails the gate.
- ``minimums``  ``>=`` row counts: graded intent with headroom (e.g. campaign
  exit criteria like "NativeSql >= 250 sites"). Any miss fails the gate.
- ``snapshot``  recorded reality: drift is reported, non-fatal unless
  ``--strict`` is passed. ``--record`` refreshes recorded values in place.
- ``rule_minimums``  per-rule_id ``>=`` counts: rows of Query.csv filtered to
  one rule_id. Queries emit several rule_ids each, so whole-file counts cannot
  express the campaign exit criteria ("api_surface__controller >= 49").

A spec SELECTS registered expectation kinds; it can never define one. The

A spec SELECTS registered expectation kinds; it can never define one. The
KINDS registry is closed, the same idiom as DERIVATIONS in
scripts/ci/check_repo_claims.py -- markdown/JSON supplies data, never behavior.

Fail-closed rules (all exit 2, distinct from assertion failures at exit 1):
missing/empty/malformed spec, unknown spec_version, unknown top-level keys,
non-identifier query names (IDENT_RE), missing CSV for a named query (never
treated as zero rows -- absence vs. broken stays distinguishable), unexpected
CSV in the out dir (stale output from a previous run), and --record aimed at a
spec file that does not live in an ``expectations/`` directory.

Mutation kill list (applied and verified dead by
tests/spring_signals/test_check_assertions.py):
  M1  `>=` -> `>` in AtLeast            killed by test_minimum_passes_at_equality
  M2  `==` -> `>=` in AssertedExact     killed by test_asserted_fails_low
  M3  `==` -> `<=` in AssertedExact     killed by test_asserted_fails_high
  M4  missing-CSV branch returns 0 rows killed by test_missing_csv_is_data_error_not_zero
  M5  IDENT_RE weakened to `.*`         killed by TestQueryNameHygiene rejected-names cases
  M6  containment check removed         killed by test_checked_path_rejects_symlink_escape
  M7  signal match on rule_id only      killed by test_signal_wrong_survivor_fails
  M8  unexpected-CSV check removed      killed by test_unexpected_csv_is_data_error
  M9  rule_minimums counts all rows     killed by test_counts_only_matching_rule_id
  M10 rule_minimums `>=` -> `>`         killed by test_rule_minimum_passes_at_equality
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SPEC_VERSION = "v1"
IDENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
RULE_ID_RE = re.compile(r"[a-z][a-z0-9_]*")
SPEC_KEYS = {
    "spec_version",
    "description",
    "asserted",
    "minimums",
    "snapshot",
    "rule_minimums",
    "signals",
}
COUNT_SECTIONS = ("asserted", "minimums", "snapshot")
SIGNAL_KEYS = {"query", "rule_id", "symbol", "signal"}

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_ERROR = 2


class SpecError(Exception):
    """The spec file is missing, malformed, or names something it must not."""


class DataError(Exception):
    """The out directory does not match what the spec expects to grade."""


@dataclass(frozen=True)
class Expectation:
    query: str
    kind: str
    value: int


@dataclass(frozen=True)
class SignalPin:
    query: str
    rule_id: str
    symbol: str
    signal: str


@dataclass(frozen=True)
class QueryResult:
    query: str
    rows: int
    records: tuple[dict, ...]


@dataclass(frozen=True)
class Outcome:
    query: str
    kind: str
    ok: bool
    message: str


class AssertedExact:
    def evaluate(self, exp: Expectation, result: QueryResult) -> Outcome:
        ok = result.rows == exp.value
        return Outcome(exp.query, exp.kind, ok, f"rows={result.rows} asserted={exp.value}")


class AtLeast:
    def evaluate(self, exp: Expectation, result: QueryResult) -> Outcome:
        ok = result.rows >= exp.value
        return Outcome(exp.query, exp.kind, ok, f"rows={result.rows} minimum={exp.value}")


class DriftOnly:
    def evaluate(self, exp: Expectation, result: QueryResult) -> Outcome:
        ok = result.rows == exp.value
        return Outcome(exp.query, exp.kind, ok, f"drift: rows={result.rows} recorded={exp.value}")


KINDS = {"asserted": AssertedExact(), "minimums": AtLeast(), "snapshot": DriftOnly()}


def _check_name(name: object) -> str:
    if not isinstance(name, str) or not IDENT_RE.fullmatch(name):
        raise SpecError(f"invalid query name {name!r}: must match {IDENT_RE.pattern}")
    return name


def _check_count(query: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SpecError(f"{query}: count {value!r} is not a non-negative integer")
    return value


def checked_path(base_dir: Path, name: str) -> Path:
    """Resolve ``base_dir/<name>.csv``, refusing symlinked base escapes.

    Rejecting ``..`` in the name is not enough on its own: a base directory
    that is itself a symlink pointing outside the intended tree sails through
    a string check. The resolved base must stay under its own resolved parent.
    """
    _check_name(name)
    root = Path(base_dir)
    resolved = root.resolve()
    parent = root.parent.resolve()
    if resolved != parent and parent not in resolved.parents:
        raise SpecError(f"output directory {root} resolves outside its parent (symlink escape?)")
    return resolved / f"{name}.csv"


def load_spec(spec_path: Path) -> dict:
    path = Path(spec_path)
    if not path.is_file():
        raise SpecError(f"spec not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise SpecError(f"spec is empty: {path}")
    try:
        spec = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SpecError(f"spec is not valid JSON: {path}: {exc}") from exc
    if not isinstance(spec, dict):
        raise SpecError("spec root must be a JSON object")
    unknown = set(spec) - SPEC_KEYS
    if unknown:
        raise SpecError(f"unknown spec keys: {sorted(unknown)}")
    if spec.get("spec_version") != SPEC_VERSION:
        raise SpecError(f"spec_version must be {SPEC_VERSION!r}, got {spec.get('spec_version')!r}")
    if not any(spec.get(section) for section in (*COUNT_SECTIONS, "rule_minimums", "signals")):
        raise SpecError("spec has no expectations: all sections empty")
    for section in COUNT_SECTIONS:
        raw = spec.get(section, {})
        if not isinstance(raw, dict):
            raise SpecError(f"{section} must be an object of query -> count")
        for query, count in raw.items():
            _check_count(_check_name(query), count)
    rule_mins = spec.get("rule_minimums", {})
    if not isinstance(rule_mins, dict):
        raise SpecError("rule_minimums must be an object of query -> {rule_id: count}")
    for query, rules in rule_mins.items():
        _check_name(query)
        if not isinstance(rules, dict) or not rules:
            raise SpecError(f"rule_minimums[{query}] must be a non-empty object of rule_id -> count")
        for rule_id, count in rules.items():
            if not isinstance(rule_id, str) or not RULE_ID_RE.fullmatch(rule_id):
                raise SpecError(f"invalid rule_id {rule_id!r}: must match {RULE_ID_RE.pattern}")
            _check_count(rule_id, count)
    pins = spec.get("signals", [])
    if not isinstance(pins, list):
        raise SpecError("signals must be a list")
    for pin in pins:
        if not isinstance(pin, dict) or set(pin) != SIGNAL_KEYS:
            raise SpecError(f"signal entries must have exactly {sorted(SIGNAL_KEYS)}: {pin!r}")
        if not all(isinstance(pin[k], str) and pin[k] for k in SIGNAL_KEYS):
            raise SpecError(f"signal fields must be non-empty strings: {pin!r}")
        _check_name(pin["query"])
    return spec


def load_result(out_dir: Path, query: str) -> QueryResult:
    csv_path = checked_path(out_dir, query)
    if not csv_path.is_file():
        raise DataError(f"missing CSV for {query}: {csv_path} (absence is not zero rows)")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        records = tuple(csv.DictReader(handle))
    return QueryResult(query=query, rows=len(records), records=records)


def spec_queries(spec: dict) -> set[str]:
    queries = {q for section in COUNT_SECTIONS for q in spec.get(section, {})}
    queries.update(spec.get("rule_minimums", {}))
    queries.update(pin["query"] for pin in spec.get("signals", []))
    return queries


def check_unexpected_csvs(out_dir: Path, spec: dict) -> None:
    root = Path(out_dir)
    if not root.is_dir():
        raise DataError(f"out directory not found: {root}")
    unexpected = sorted(p.stem for p in root.glob("*.csv") if p.stem not in spec_queries(spec))
    if unexpected:
        raise DataError(f"unexpected CSVs in {root} (stale output?): {unexpected}")


def evaluate(spec: dict, out_dir: Path) -> list[Outcome]:
    check_unexpected_csvs(out_dir, spec)
    outcomes: list[Outcome] = []
    for section in COUNT_SECTIONS:
        strategy = KINDS[section]
        for query, value in spec.get(section, {}).items():
            exp = Expectation(query=query, kind=section, value=value)
            outcomes.append(strategy.evaluate(exp, load_result(out_dir, query)))
    for query, rules in spec.get("rule_minimums", {}).items():
        result = load_result(out_dir, query)
        for rule_id, minimum in rules.items():
            rows = sum(1 for rec in result.records if rec.get("rule_id") == rule_id)
            outcomes.append(
                Outcome(
                    query,
                    "rule_minimums",
                    rows >= minimum,
                    f"{rule_id}: rows={rows} minimum={minimum}",
                )
            )
    for pin in spec.get("signals", []):
        result = load_result(out_dir, pin["query"])
        hit = any(
            rec.get("rule_id") == pin["rule_id"]
            and rec.get("symbol") == pin["symbol"]
            and rec.get("signal") == pin["signal"]
            for rec in result.records
        )
        outcomes.append(
            Outcome(
                pin["query"],
                "signals",
                hit,
                f"pin {pin['rule_id']} symbol={pin['symbol']} signal={pin['signal']}",
            )
        )
    return outcomes


def record_snapshots(spec_path: Path, spec: dict, out_dir: Path) -> None:
    if Path(spec_path).parent.name != "expectations":
        raise SpecError(f"--record only writes specs under an expectations/ directory: {spec_path}")
    for query in spec.get("snapshot", {}):
        spec["snapshot"][query] = load_result(out_dir, query).rows
    Path(spec_path).write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spec", required=True, help="path to the expectations JSON spec")
    parser.add_argument("--out", required=True, help="directory holding <query>.csv files")
    parser.add_argument("--record", action="store_true", help="refresh snapshot values in the spec")
    parser.add_argument("--strict", action="store_true", help="treat snapshot drift as failure")
    args = parser.parse_args(argv)

    try:
        spec = load_spec(Path(args.spec))
        outcomes = evaluate(spec, Path(args.out))
        if args.record:
            record_snapshots(Path(args.spec), spec, Path(args.out))
    except (SpecError, DataError) as exc:
        print(f"ERROR: {exc}")
        return EXIT_ERROR

    failures = 0
    for outcome in outcomes:
        fatal = outcome.kind != "snapshot" or args.strict
        if not outcome.ok and fatal:
            failures += 1
        tag = "OK" if outcome.ok else ("DRIFT" if outcome.kind == "snapshot" and not fatal else "FAIL")
        print(f"  {tag:<5} {outcome.kind:<9} {outcome.query}: {outcome.message}")
    return EXIT_FAILED if failures else EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
