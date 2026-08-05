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

TWO KINDS OF EXPECTATION, AND THE DIFFERENCE IS THE POINT

  "asserted"  hand-derived by reading the fixture source, then confirmed
              against output. These encode intent. A mismatch is a bug in the
              query (or an intended change that must be justified in the PR).

  "snapshot"  recorded from a known-good run. These encode current behaviour,
              nothing more. They catch drift; they do not certify correctness.
              A snapshot must never be cited as evidence a rule is right.

Generating every number from output and calling the result a test is circular:
it asserts only that the code still does what it did. Keeping the two lists
separate is what stops that from happening silently. `--record` regenerates
ONLY the snapshot block and refuses to touch asserted values.

Expectations schema:

    {
      "repo": "fixture-repo",
      "asserted": {
        "ApiSurface": {
          "_rows": 27,
          "api_surface__controller": 3,
          "_note": "why these numbers are what they are"
        }
      },
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

FAIL CLOSED. A missing expectations file is an error, and a file whose
asserted and snapshot blocks are both empty asserts nothing -- also an error.
`--allow-empty` exists for the deliberate report-only case. A typo'd
EXPECTATIONS path must never read as a green run.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path


def load_counts(out_dir: Path, query: str) -> tuple[int, Counter]:
    path = out_dir / f"{query}.csv"
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
    path = out_dir / f"{query}.csv"
    signals: dict[str, list[str]] = {}
    if not path.exists():
        return signals
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            rule = row.get("rule_id")
            if rule:
                signals.setdefault(rule, []).append(row.get("signal", ""))
    return {rule: sorted(values) for rule, values in signals.items()}


def compare(out_dir: Path, block: dict, label: str) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    lines: list[str] = []
    for query, expected in sorted(block.items()):
        rows, by_rule = load_counts(out_dir, query)
        if rows < 0:
            failures.append(f"{label}: {query}: no {query}.csv in {out_dir}")
            lines.append(f"  MISS {query} (no csv)")
            continue
        signals: dict[str, list[str]] | None = None
        for key, want in expected.items():
            if key.startswith("_note"):
                continue
            if key == "_signals":
                if signals is None:
                    signals = load_signals(out_dir, query)
                for rule, want_signals in sorted(want.items()):
                    got_signals = signals.get(rule, [])
                    name = f"{query}.{rule} signals"
                    if got_signals == sorted(want_signals):
                        lines.append(f"  OK   {name} = {got_signals}")
                    else:
                        lines.append(f"  FAIL {name} = {got_signals} (expected {sorted(want_signals)})")
                        failures.append(
                            f"{label}: {name} = {got_signals}, expected {sorted(want_signals)}"
                        )
                continue
            got = rows if key == "_rows" else by_rule.get(key, 0)
            name = f"{query}" if key == "_rows" else f"{query}.{key}"
            if got == want:
                lines.append(f"  OK   {name} = {got}")
            else:
                lines.append(f"  FAIL {name} = {got} (expected {want})")
                failures.append(f"{label}: {name} = {got}, expected {want}")
    return failures, lines


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
    spec = load_spec(spec_path)
    asserted = spec.get("asserted", {})
    # Replace wholesale, not update(): a query that vanished from --out must
    # not leave a stale snapshot entry behind asserting nothing about reality.
    spec["snapshot"] = build_recorded_block(out_dir, asserted)
    snapshot = spec["snapshot"]
    payload = json.dumps(spec, indent=2) + "\n"
    # Atomic write: do not leave a partially-written expectations file on failure.
    tmp = spec_path.with_suffix(spec_path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(spec_path)
    print(f"recorded snapshot block for {len(snapshot)} queries -> {spec_path}")
    print("ASSERTED values were left untouched. Review the diff before committing.")
    return 0


def actual_counts(out_dir: Path) -> dict:
    counts: dict = {}
    for path in sorted(out_dir.glob("*.csv")):
        query = path.stem
        rows, by_rule = load_counts(out_dir, query)
        entry = {"_rows": rows}
        entry.update({rule: n for rule, n in sorted(by_rule.items())})
        counts[query] = entry
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--expectations", required=True, type=Path)
    ap.add_argument("--record", action="store_true",
                    help="regenerate the snapshot block from --out; never edits asserted")
    ap.add_argument("--allow-empty", action="store_true",
                    help="permit an expectations file with no asserted or snapshot block")
    args = ap.parse_args()

    if args.record:
        return record(args.out, args.expectations)

    spec = load_spec(args.expectations)
    if not args.allow_empty and not (spec.get("asserted") or spec.get("snapshot")):
        print(f"ERROR: {args.expectations} has empty asserted AND snapshot blocks; "
              "nothing would be asserted. Pass --allow-empty for a deliberate "
              "report-only run.", file=sys.stderr)
        return 2
    print(f"== assertions ({spec.get('repo', args.expectations.stem)}) ==")

    failures: list[str] = []
    for label, key in (("asserted", "asserted"), ("snapshot", "snapshot")):
        block = spec.get(key) or {}
        if not block:
            continue
        print(f"-- {label} --")
        f, lines = compare(args.out, block, label)
        print("\n".join(lines))
        failures += f

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
        print(json.dumps({"snapshot": actual_counts(args.out)}, indent=2))
        return 1
    print("All assertions hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
