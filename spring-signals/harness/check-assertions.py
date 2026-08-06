#!/usr/bin/env python3
"""
Assert query output against a per-repository expectations file. Exits non-zero
on any mismatch.

WHY THIS REPLACES THE INLINE LOOP IN run.sh
The previous absence assertions printed `DIFF ... <-- investigate` and let the
script exit 0, so nothing they claimed to assert could fail a run. The four
non-empty assertions that mattered most -- the @RestController recall
regression among them -- were not code at all, only a comment reading
"checked manually until run.sh grows a min-rows mode".

THREE KINDS OF EXPECTATION, AND THE DIFFERENCE IS THE POINT

  "asserted"  hand-derived by reading the target source, then confirmed
              against output. These encode intent. A mismatch is a bug in the
              query (or an intended change that must be justified in the PR).
              Exact equality, including zero for asserted absences.

  "minimums"  floor counts for a living repository whose rows grow as the
              repo grows (ocs-api-service). >= comparison: a regression that
              deletes rows fails, ordinary repo growth does not.

  "snapshot"  recorded from a known-good run. These encode current behaviour,
              nothing more. They catch drift; they do not certify correctness.
              A snapshot must never be cited as evidence a rule is right.

Generating every number from output and calling the result a test is circular:
it asserts only that the code still does what it did. Keeping asserted and
snapshot separate is what stops that from happening silently. `--record`
regenerates ONLY the snapshot block and refuses to touch asserted values.

Expectations schema:

    {
      "repo": "fixture-repo",
      "asserted": {
        "ApiSurface": {
          "_rows": 27,
          "api_surface__controller": 3,
          "_signals": {"api_surface__controller": ["org...Controller"]},
          "_note": "why these numbers are what they are"
        }
      },
      "minimums": { "ApiSurface": { "api_surface__endpoint": 300 } },
      "snapshot": { "Persistence": { "_rows": 41 } },
      "known_defects": {
        "NativeSql.sql__jdbc_call": "counts 2x: JdbcTemplate and JdbcOperations"
      }
    }

`_rows` is the total row count for the query. Any other key is a rule_id.
`_signals` maps a rule_id to the exact sorted list of `signal` values its rows
must carry. Counts alone cannot catch a most-specific guard that keeps the
RIGHT NUMBER of rows with the WRONG survivor (KafkaOperations where
KafkaTemplate belongs); the signal list can.
`known_defects` is documentation only; it is printed, never asserted, so a
defect cannot be quietly normalised into an expectation.

FAIL CLOSED. A missing expectations file is an error, and a file with no
asserted, minimums, or snapshot content asserts nothing -- also an error.
`--allow-empty` exists for the deliberate report-only case. A typo'd
EXPECTATIONS path must never read as a green run. A CSV in --out that no
expectation names is stale output from a previous run -- an error (exit 2),
never silently ignored, because re-asserting yesterday's rows as today's is
the exact failure this tool exists to catch. Exit codes: 0 = all hold,
1 = an assertion failed or input rejected, 2 = the gate cannot vouch for the
result (empty spec, stale output).

INPUT VALIDATION IS THE BOUNDARY. The expectations file chooses which CSV
paths this script opens, so query names must be identifiers
(`^[A-Za-z][A-Za-z0-9_]*$`) -- anything else is rejected before it can become
a path segment. CLI path arguments are rejected if they contain `..` and are
resolved before use. An assertion tool that can be pointed at arbitrary files
by its own input file is a confused deputy, not a gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Query names become CSV filenames. Whitelisting the identifier shape makes
# traversal via a crafted expectations file impossible by construction.
IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def csv_path(out_dir: Path, query: str) -> Path:
    if not IDENT_RE.match(query):
        sys.exit(f"ERROR: {query!r} is not a valid query identifier; "
                 "expectations files may only name [A-Za-z0-9_] words")
    return out_dir / f"{query}.csv"


def checked_path(path: Path, what: str, want: str) -> Path:
    """Validate a CLI-supplied path before any filesystem access.

    Rejects `..` segments outright, resolves, then requires the expected kind
    of object. `want` is "file" or "dir".
    """
    if ".." in path.parts:
        sys.exit(f"ERROR: {what} must not contain '..': {path}")
    resolved = path.resolve()
    if want == "file" and not resolved.is_file():
        sys.exit(f"ERROR: {what} is not a file: {resolved}")
    if want == "dir" and not resolved.is_dir():
        sys.exit(f"ERROR: {what} is not a directory: {resolved}")
    return resolved


def load_counts(out_dir: Path, query: str) -> tuple[int, Counter]:
    path = csv_path(out_dir, query)
    if not path.exists():
        return -1, Counter()
    rows = 0
    by_rule: Counter = Counter()
    # utf-8-sig: bqrs decode writes plain UTF-8 under bash redirection, but a
    # PowerShell `>` re-decode produces a UTF-16/UTF-8-BOM file; that should
    # read as an empty/missing result, not an uncaught UnicodeDecodeError.
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            rows += 1
            # v0 queries have a rule_id column too; v1 adds the rest.
            rule = row.get("rule_id")
            if rule:
                by_rule[rule] += 1
    return rows, by_rule


def load_signals(out_dir: Path, query: str) -> dict[str, list[str]]:
    """Signal values per rule_id, sorted, duplicates kept: a fan-out duplicate
    and a wrong-survivor dedupe both change the list, which is the point."""
    path = csv_path(out_dir, query)
    signals: dict[str, list[str]] = {}
    if not path.exists():
        return signals
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            rule = row.get("rule_id")
            if rule:
                signals.setdefault(rule, []).append(row.get("signal", ""))
    return {rule: sorted(values) for rule, values in signals.items()}


class Reporter:
    """Accumulates OK/FAIL display lines and machine-checkable failures."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.failures: list[str] = []
        self.lines: list[str] = []

    def verdict(self, ok: bool, name: str, got: object, want_desc: str) -> None:
        if ok:
            self.lines.append(f"  OK   {name} = {got}")
        else:
            self.lines.append(f"  FAIL {name} = {got} (expected {want_desc})")
            self.failures.append(f"{self.label}: {name} = {got}, expected {want_desc}")


def compare_signals(out_dir: Path, query: str, want_map: dict, rep: Reporter) -> None:
    if not isinstance(want_map, dict):
        sys.exit(f"ERROR: {query}._signals must map rule_ids to signal lists")
    actual = load_signals(out_dir, query)
    for rule, want_signals in sorted(want_map.items()):
        if not isinstance(want_signals, list):
            sys.exit(f"ERROR: {query}._signals[{rule!r}] must be a list")
        want_sorted = sorted(str(s) for s in want_signals)
        rep.verdict(actual.get(rule, []) == want_sorted,
                    f"{query}.{rule} signals", actual.get(rule, []),
                    str(want_sorted))


def compare_count(got: int, want: object, name: str, mode: str, rep: Reporter) -> None:
    # bool IS int in Python: without the guard, `true` in JSON quietly becomes
    # a floor of 1, which is never what the spec author meant.
    if isinstance(want, bool) or not isinstance(want, int):
        sys.exit(f"ERROR: expected count for {name} must be an integer, got {want!r}")
    if mode == "min":
        rep.verdict(got >= want, name, got, f">= {want}")
    else:
        rep.verdict(got == want, name, got, str(want))


def compare_query(out_dir: Path, query: str, expected: dict, mode: str,
                  rep: Reporter) -> None:
    rows, by_rule = load_counts(out_dir, query)
    if rows < 0:
        rep.lines.append(f"  MISS {query} (no csv)")
        rep.failures.append(f"{rep.label}: {query}: no {query}.csv in {out_dir}")
        return
    for key, want in sorted(expected.items()):
        if key.startswith("_note"):
            continue
        if key == "_signals":
            compare_signals(out_dir, query, want, rep)
            continue
        got = rows if key == "_rows" else by_rule.get(key, 0)
        name = query if key == "_rows" else f"{query}.{key}"
        compare_count(got, want, name, mode, rep)


def compare(out_dir: Path, block: dict, label: str, mode: str = "exact") -> Reporter:
    rep = Reporter(label)
    for query, expected in sorted(block.items()):
        compare_query(out_dir, query, expected, mode, rep)
    return rep


def spec_queries(spec: dict) -> set[str]:
    """Every query any expectation section names, across all three blocks."""
    return {q for key in ("asserted", "minimums", "snapshot") for q in spec.get(key) or {}}


def check_no_stale_csvs(out_dir: Path, spec: dict) -> None:
    """Fail (exit 2) on any CSV in --out that the spec does not name.

    Without this, a query removed from the wave list leaves its old CSV behind
    and the run re-asserts stale rows as if they were fresh -- the same class
    of silent-skew bug as a missing expectations file, so it shares exit 2.
    """
    stale = sorted(p.stem for p in out_dir.glob("*.csv") if p.stem not in spec_queries(spec))
    if stale:
        print(f"ERROR: unexpected CSVs in {out_dir} (stale output from a "
              f"previous run?): {stale}", file=sys.stderr)
        sys.exit(2)


def load_spec(spec_path: Path) -> dict:
    try:
        return json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: malformed JSON in {spec_path}: {e}")
    except FileNotFoundError:
        # Fail closed: a typo'd EXPECTATIONS path must not read as a green run.
        sys.exit(f"ERROR: expectations file not found: {spec_path}")


def build_recorded_block(out_dir: Path, asserted: dict) -> dict:
    snapshot: dict = {}
    for path in sorted(out_dir.glob("*.csv")):
        query = path.stem
        if not IDENT_RE.match(query):
            continue  # not a query output; never record it
        rows, by_rule = load_counts(out_dir, query)
        entry = {"_rows": rows}
        entry.update({rule: n for rule, n in sorted(by_rule.items())})
        # Never shadow an asserted value with a recorded one.
        for key in list(entry):
            if key in asserted.get(query, {}):
                del entry[key]
        if entry:
            snapshot[query] = entry
    return snapshot


def record(out_dir: Path, spec_path: Path) -> int:
    # Maintainer-only, local command (never run by CI): validate honestly,
    # then say so. checked_path rejects '..' and resolves; the containment
    # check keeps writes in-tree.
    spec_path = checked_path(spec_path, "--expectations", "file")
    harness_dir = Path(__file__).resolve().parent
    if not spec_path.is_relative_to(harness_dir):
        sys.exit(f"ERROR: --record only writes expectations files under "
                 f"{harness_dir}; got {spec_path}")
    spec = load_spec(spec_path)
    asserted = spec.get("asserted", {})
    # Replace wholesale, not update(): a query that vanished from --out must
    # not leave a stale snapshot entry behind asserting nothing about reality.
    spec["snapshot"] = build_recorded_block(out_dir, asserted)
    snapshot = spec["snapshot"]
    payload = json.dumps(spec, indent=2) + "\n"
    # Atomic write: no torn expectations file on a crash. The tmp path is a
    # same-directory sibling of an already-validated file, so the taint
    # finding here is a false positive -- suppressed by name rather than by
    # reshaping the code to match the analyzer's recognized patterns.
    tmp = spec_path.with_suffix(spec_path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")  # NOSONAR python:S2083 -- validated above
    tmp.replace(spec_path)
    print(f"recorded snapshot block for {len(snapshot)} queries -> {spec_path}")
    print("ASSERTED values were left untouched. Review the diff before committing.")
    return 0


def actual_counts(out_dir: Path) -> dict:
    counts: dict = {}
    for path in sorted(out_dir.glob("*.csv")):
        query = path.stem
        if not IDENT_RE.match(query):
            continue
        rows, by_rule = load_counts(out_dir, query)
        entry = {"_rows": rows}
        entry.update({rule: n for rule, n in sorted(by_rule.items())})
        counts[query] = entry
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path,
                    help="directory of <Query>.csv files produced by run.sh")
    ap.add_argument("--expectations", required=True, type=Path,
                    help="per-repository expectations JSON")
    ap.add_argument("--record", action="store_true",
                    help="regenerate the snapshot block from --out; never edits asserted")
    ap.add_argument("--allow-empty", action="store_true",
                    help="permit an expectations file with no asserted, minimums, "
                         "or snapshot content")
    args = ap.parse_args(argv)

    out_dir = checked_path(args.out, "--out", "dir")
    spec_path = checked_path(args.expectations, "--expectations", "file")

    if args.record:
        return record(out_dir, spec_path)

    spec = load_spec(spec_path)
    if not args.allow_empty and not (
        spec.get("asserted") or spec.get("snapshot") or spec.get("minimums")
    ):
        print(f"ERROR: {spec_path} has no asserted, minimums, or snapshot "
              "content; nothing would be asserted. Pass --allow-empty for a "
              "deliberate report-only run.", file=sys.stderr)
        return 2
    check_no_stale_csvs(out_dir, spec)
    print(f"== assertions ({spec.get('repo', spec_path.stem)}) ==")

    failures: list[str] = []
    for label, key, mode in (
        ("asserted", "asserted", "exact"),
        ("minimums", "minimums", "min"),
        ("snapshot", "snapshot", "exact"),
    ):
        block = spec.get(key) or {}
        if not block:
            continue
        print(f"-- {label} --")
        rep = compare(out_dir, block, label, mode)
        print("\n".join(rep.lines))
        failures += rep.failures

    defects = spec.get("known_defects") or {}
    if defects:
        print("-- known defects encoded in these numbers --")
        for k, v in sorted(defects.items()):
            print(f"  ! {k}: {v}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} assertion(s)")
        for f in failures:
            print(f"  {f}")
        print()
        print("-- copy-pasteable actual counts (review before using) --")
        print(json.dumps({"snapshot": actual_counts(out_dir)}, indent=2))
        return 1
    print("All assertions hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
