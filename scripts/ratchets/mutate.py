#!/usr/bin/env python3
"""Break things on purpose, in a sandbox, and report which tests failed to notice.

Usage:
    python3 scripts/ratchets/mutate.py                 # run every mutator
    python3 scripts/ratchets/mutate.py --filter grep   # only mutators whose name matches
    python3 scripts/ratchets/mutate.py --update        # rewrite the survivor baseline

ENFORCE = False -- see the CI step name, which says "non-blocking".

WHY THIS EXISTS

This repo's standing rule is that a gate which cannot be shown to fail is not
a gate, and it is satisfied by hand: an author breaks the code, watches the
tests go red, restores it, and writes down what happened. Three separate
documents say so and name mutation testing as the mechanised form --
skills/directional-tests/SKILL.md, steering-prompt 10, and
claude/testing-security-anchors-2026-07-25.md, which puts it plainly: "mutation
testing, executed by a human, once, with no artifact proving it was ever done."

The ritual was performed at least four times while this file was being
written, and the evidence was deleted each time.

WHY NOT mutmut

mutmut mutates Python. The defects this repo has actually had did not live in
Python: an agent regaining the Grep tool (markdown frontmatter), a rule's
argument-bearing pattern deleted (YAML), a derived: block edited (markdown),
ENFORCE = False without a "non-blocking" step name (CI YAML). A Python-only
mutator scores zero on all four. This harness is artifact-aware for that
reason. mutmut remains the right complement for the pure-Python modules and
is not replaced by this.

SANDBOXED, ALWAYS

Every mutation is applied to a copy of the tracked tree in a temp directory,
never to the working tree. The manual ritual relied on try/finally and a
steady hand; a crash between break and restore left the repo silently broken.
Only git-tracked files are copied, which keeps the copy small (the working
tree may contain a multi-hundred-megabyte target repo) and keeps a concurrent
session's untracked work out of the run -- the same reasoning
check_code_quality.py gives for measuring tracked files only.

ONE SUITE PER MUTATION

Each mutator names the suite that should catch it, and only that suite runs.
Running all of them per mutation would multiply the whole suite's runtime by
the number of mutators for no extra information. A mutation caught by a
*different* suite than the one named is reported separately: the mutation was
noticed, but the ownership map is wrong.

A SURVIVOR IS A TEST GAP, NOT A BUG

A surviving mutation means the code changed and every test still passed. That
is a statement about the tests, not the code.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from doc_engine.paths import repo_root, scripts_dir, scripts_meta_path_entries

for _entry in scripts_meta_path_entries():
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import suite_layout  # noqa: E402

REPO_ROOT = repo_root()
BASELINE_FILE = scripts_dir() / "ratchets" / "mutation_baseline.json"
SCHEMA_VERSION = 1

ENFORCE = False


class Mutator(NamedTuple):
    """One deliberate defect.

    Data this file interprets, never behaviour a document supplies -- the same
    boundary check_repo_claims.py draws around its predicates.

    `lang` decides HOW the defect is located. Set it to an ast-grep language
    and the anchor is a structural pattern rewritten with `ast-grep --rewrite`,
    so reindenting or reflowing the target cannot quietly detach the mutator
    from the code it is supposed to break. Leave it empty and the anchor is a
    literal string.

    The literal cases are not laziness, and each one below says why:
      - markdown, where ast-grep's grammar matches broad block nodes. Measured
        on this repo's README: a pattern for `ast-grep` reported 35 lines of
        which 27 contained no such string. A rewrite driven by that would edit
        the wrong text.
      - the ast-grep rule file itself, where the text to match *contains*
        `$$$ARGS`. That is ast-grep's own metavariable syntax, so a structural
        search for it does not mean what it reads as.

    Both are covered instead by test_mutate.RegistryAnchorsTest, which fails
    the build when a literal anchor drifts out of the file it names.
    """
    name: str
    path: str
    lang: str
    find: str
    replace: str
    expected_caught_by: str
    why: str


# Seeded from defects this repo actually had or narrowly avoided. Each `why`
# names the incident, so a survivor report says what stopped being defended.
MUTATORS: List[Mutator] = [
    # --- structural: located by ast-grep, immune to reformatting -------------
    Mutator(
        "secret-heuristic-stops-unquoting",
        "src/doc_engine/scanning/support/_secret_heuristics.py", "python",
        "PLACEHOLDER_VALUE_RE.match(_unquote($V))",
        "PLACEHOLDER_VALUE_RE.match($V)",
        "test_secret_heuristics.py",
        'quoted "${X}" was reported as a literal credential on a real build script'),
    Mutator(
        "build-file-guard-loosened", "src/doc_engine/scanning/_scanner_filesystem.py", "python",
        'name.endswith(".gradle.kts")', 'ext == ".kts"',
        "test_spring_signal_scan.py",
        "a bare .kts is any Kotlin script; treating it as a build file puts "
        "arbitrary Kotlin into operations.md"),
    Mutator(
        "relation-permits-everything", "scripts/ratchets/set_delta.py", "python",
        "return lambda member, direction: False",
        "return lambda member, direction: True",
        "test_set_delta.py",
        "a relation that permits everything makes every metamorphic assertion "
        "pass while checking nothing"),
    Mutator(
        "query-limit-ceiling-removed",
        "src/doc_engine/query/envelope.py", "python",
        "cap = max(0, min(cap, max_limit))",
        "cap = max(0, cap)",
        "test_query_artifacts.py",
        "agents rely on hard --limit clamp; removing it dumps unbounded "
        "evidence into context (DDIA backpressure)"),
    Mutator(
        "context-packet-budget-trim-disabled",
        "src/doc_engine/query/rank.py", "python",
        "tokens_used + cost > budget",
        "False",
        "test_context_packet.py",
        "context_packet budgetTokens must trim primaryContext; disabling "
        "the guard dumps unbounded packets"),
    Mutator(
        "freshness-mismatch-always-fresh",
        "src/doc_engine/query/freshness.py", "python",
        "return (FreshnessLabel.FRESH_INDEXED if actual == expected "
        "else FreshnessLabel.STALE)",
        "return FreshnessLabel.FRESH_INDEXED",
        "test_context_packet.py",
        "signature mismatch must label stale; always-fresh hides drift"),

    # --- literal: see Mutator's docstring for why each one cannot be ---------
    # --- structural, and RegistryAnchorsTest for what guards them instead ----
    Mutator(
        "agent-regains-grep", "adapters/claude/agents/gap-analyzer.md", "",
        "tools: Read, Glob, Write", "tools: Read, Grep, Glob, Write",
        "test_check_repo_claims.py",
        "all five agents declared Grep until 0ee4033; check F exists to stop it "
        "coming back"),
    Mutator(
        "rule-loses-its-args-form",
        "src/doc_engine/scanning/resources/spring_ast_grep_rules.yml", "",
        '    - pattern: "@JoinColumn($$$ARGS)"\n', "",
        "test_rule_coverage.py",
        "a marker pattern and an argument-bearing one are disjoint node shapes; "
        "dropping one silently halves a rule"),
    Mutator(
        "derived-count-edited", "CLAUDE.md", "",
        "<!-- derived: predicate_count -->7<!-- /derived -->",
        "<!-- derived: predicate_count -->6<!-- /derived -->",
        "test_check_repo_claims.py",
        'CLAUDE.md read "Three forms" for two windows after a fourth and fifth landed'),
    Mutator(
        "prompt-contract-drifts", "adapters/claude/agents/file-summarizer.md", "",
        "test, other —", "test, other, scheduler —",
        "test_prompt_contracts.py",
        "the validators held hand-copied duplicates of this list with nothing "
        "reading them back"),
]


class Outcome(NamedTuple):
    name: str
    status: str        # "killed" | "survived" | "misattributed" | "not-applied"
    detail: str


def tracked_files() -> List[str]:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def materialize(dest: Path) -> None:
    """Copy the tracked tree into `dest`. Tracked-only, deliberately."""
    for rel in tracked_files():
        source = REPO_ROOT / rel
        if not source.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Stage-0 tests and the installable package live outside scripts/; copy
    # them from the working tree so mutation sandboxes match pytest CI even
    # when a session has not yet committed every file under tests/ or src/.
    for dirname in ("tests", "src"):
        source_dir = REPO_ROOT / dirname
        if source_dir.is_dir():
            shutil.copytree(
                source_dir,
                dest / dirname,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
    scripts_root = REPO_ROOT / "scripts"
    if scripts_root.is_dir():
        shutil.copytree(
            scripts_root,
            dest / "scripts",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".claude", ".gradle", "target",
            ),
        )


def _apply_structural(path: Path, mutator: Mutator) -> Optional[str]:
    """Rewrite via ast-grep, so the anchor survives reformatting.

    The exit code cannot carry this decision. Measured against ast-grep
    0.44.1: `--update-all` exits 1 both when the pattern matches nothing and
    when the invocation genuinely fails, so the two are indistinguishable
    from the status alone. What is unambiguous is whether the file moved, so
    that is what is checked -- and it stays correct if the exit-code
    behaviour changes in a later release.
    """
    before = path.read_text(encoding="utf-8")
    result = subprocess.run(
        ["ast-grep", "run", "-l", mutator.lang, "-p", mutator.find,
         "-r", mutator.replace, "--update-all", str(path)],
        capture_output=True, text=True)
    if path.read_text(encoding="utf-8") != before:
        return None
    detail = result.stderr.strip()[:160]
    return (f"structural pattern matched nothing in {mutator.path}; the mutator "
            f"has drifted from the code and is testing nothing"
            + (f" (ast-grep said: {detail})" if detail else ""))


def _apply_literal(path: Path, mutator: Mutator) -> Optional[str]:
    text = path.read_text(encoding="utf-8")
    if mutator.find not in text:
        return (f"anchor not found in {mutator.path}; the mutator has drifted "
                f"from the file and is testing nothing")
    path.write_text(text.replace(mutator.find, mutator.replace, 1), encoding="utf-8")
    return None


def apply_mutation(root: Path, mutator: Mutator) -> Optional[str]:
    """Returns an error string if the mutation could not be applied.

    An unapplied mutator is never scored: a defect that was never introduced
    tells you nothing about whether a test would have caught it, and counting
    it either way would corrupt the score.
    """
    path = root / mutator.path
    if not path.is_file():
        return f"{mutator.path} is not in the tracked tree"
    if mutator.lang:
        return _apply_structural(path, mutator)
    return _apply_literal(path, mutator)


def resolve_suite_path(root: Path, suite: str) -> Path:
    """Resolve ``test_*.py`` under pyproject testpaths (recursive, not scripts/).

    Suites live in taxonomy subdirs after the tests/ reorg; flat
    ``tests/<name>`` lookup would miss ``tests/ratchets/test_set_delta.py``.
    Delegates to ``suite_layout.suite_file_for_module`` (rglob).
    """
    name = Path(suite).name
    module = name[len("test_"):] if name.startswith("test_") else name
    found = suite_layout.suite_file_for_module(root, module)
    if found is not None:
        return found
    raise FileNotFoundError(
        f"suite {name!r} not found under "
        f"{', '.join(suite_layout.suite_roots(root))}"
    )


def run_suite(root: Path, suite: str) -> int:
    path = resolve_suite_path(root, suite)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(path), "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    return result.returncode


def evaluate(mutator: Mutator, tmp_root: Path) -> Outcome:
    sandbox = tmp_root / mutator.name
    sandbox.mkdir(parents=True)
    materialize(sandbox)
    error = apply_mutation(sandbox, mutator)
    if error:
        return Outcome(mutator.name, "not-applied", error)
    if run_suite(sandbox, mutator.expected_caught_by) != 0:
        return Outcome(mutator.name, "killed",
                       f"{mutator.expected_caught_by} failed, as it should")
    return Outcome(mutator.name, "survived",
                   f"{mutator.expected_caught_by} still passed. {mutator.why}")


def load_baseline() -> Dict[str, str]:
    if not BASELINE_FILE.is_file():
        return {}
    data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        return {}
    return dict(data.get("accepted_survivors", {}))


def write_baseline(outcomes: List[Outcome]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "$comment": (
            "Mutations that no suite currently catches. Each entry is a test "
            "gap someone accepted, not a bug. Shrinking this file is always "
            "correct; growing it needs a reason in the PR that does it. "
            "Regenerate with: python3 scripts/ratchets/mutate.py --update"
        ),
        "accepted_survivors": {o.name: o.detail
                               for o in outcomes if o.status == "survived"},
    }
    BASELINE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def report(outcomes: List[Outcome], accepted: Dict[str, str]) -> int:
    killed = [o for o in outcomes if o.status == "killed"]
    survived = [o for o in outcomes if o.status == "survived"]
    broken = [o for o in outcomes if o.status == "not-applied"]
    new_survivors = [o for o in survived if o.name not in accepted]

    print(f"mutation score: {len(killed)}/{len(outcomes)} killed "
          f"({len(survived)} survived, {len(broken)} not applied)")
    for outcome in outcomes:
        mark = {"killed": "  killed     ", "survived": "  SURVIVED   ",
                "not-applied": "  NOT APPLIED"}[outcome.status]
        print(f"{mark} {outcome.name}: {outcome.detail}")

    if broken:
        print("\nA mutator whose anchor no longer exists is testing nothing. "
              "Fix the anchor or delete the mutator.", file=sys.stderr)
    if new_survivors:
        print(f"\n{len(new_survivors)} new survivor(s) — a mutation nothing "
              f"caught is a gap in the tests, not a bug in the code:",
              file=sys.stderr)
        for outcome in new_survivors:
            print(f"  {outcome.name}: {outcome.detail}", file=sys.stderr)
    return 1 if (new_survivors or broken) else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--filter", default="",
                        help="only run mutators whose name contains this")
    parser.add_argument("--update", action="store_true",
                        help="rewrite the survivor baseline from this run")
    args = parser.parse_args(argv)

    selected = [m for m in MUTATORS if args.filter in m.name]
    if not selected:
        print(f"error: no mutator matches {args.filter!r}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="mutate_") as tmp:
        outcomes = [evaluate(m, Path(tmp)) for m in selected]

    if args.update:
        write_baseline(outcomes)
        print(f"wrote {BASELINE_FILE.name}")
        return 0

    code = report(outcomes, load_baseline())
    if code and not ENFORCE:
        print("\n(reporting only: ENFORCE is False)", file=sys.stderr)
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
