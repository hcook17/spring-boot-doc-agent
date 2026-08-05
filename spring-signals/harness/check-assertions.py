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
`known_defects` is documentation only; it is printed, never asserted, so a
defect cannot be quietly normalised into an expectation.
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
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows += 1
            # v0 queries have a rule_id column too; v1 adds the rest.
            rule = row.get("rule_id")
            if rule:
                by_rule[rule] += 1
    return rows, by_rule


def compare(out_dir: Path, block: dict, label: str) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    lines: list[str] = []
    for query, expected in sorted(block.items()):
        rows, by_rule = load_counts(out_dir, query)
        if rows < 0:
            failures.append(f"{label}: {query}: no {query}.csv in {out_dir}")
            lines.append(f"  MISS {query} (no csv)")
            continue
        for key, want in expected.items():
            if key.startswith("_note"):
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
        return {"repo": spec_path.stem, "asserted": {}, "snapshot": {}}


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
    snapshot = spec.setdefault("snapshot", {})
    asserted = spec.get("asserted", {})
    snapshot.update(build_recorded_block(out_dir, asserted))
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
    args = ap.parse_args()

    if args.record:
        return record(args.out, args.expectations)

    spec = load_spec(args.expectations)
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
