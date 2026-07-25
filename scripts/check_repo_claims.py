#!/usr/bin/env python3
"""
check_repo_claims.py — makes a stale claim about this repo's own state
impossible to commit, rather than recorded after the fact.

Usage:
    python3 scripts/check_repo_claims.py
    python3 scripts/check_repo_claims.py --fix       # rewrite derived blocks
    python3 scripts/check_repo_claims.py --update    # re-baseline
    python3 scripts/check_repo_claims.py --metrics   # measure, never gate

Five checks: derived blocks recompute, verify: predicates hold, references
resolve, every test suite is wired into CI, and no CI step is named as a gate
it cannot fail. Claims are read from a registry of corpora (CLAIM_CORPORA) --
steering-prompt frontmatter and CONSTRAINTS.md's bracket tags today.

WHY THIS EXISTS
This repo does not have a record-keeping problem. Its record is unusually
good: an append-only claude/session-log.md, a claude/tool-quirks.md index,
a bracket-tagged CONSTRAINTS.md, and status frontmatter on every steering
prompt. Every failure below happened anyway, with the record right there.

  - claude/steering-prompts/06-wiredrift-check-task-prompt.md carried
    `status: not started` after the work had landed. The session log
    flagged it three separate times (2026-07-25 "Sync STATUS.md...",
    and twice more) before anyone edited the field. Logging caught it
    three times and fixed it zero times. 07 and 08 went the same way.
  - CLAUDE.md's own rule *against* hardcoded counts was itself written
    with a stale count, on the day it was written.
  - 12-review-session-launcher.md told a fresh session to read two
    steering-prompt files that did not exist, after a renumbering.
  - CONSTRAINTS.md cited verify_llms_docs.py after it was deleted, so
    the file contradicted itself in two places.

The common shape, in the log's own words (claude/session-log.md, the
citation-coverage entry): "every tag form is auditable, and no tag is
not. Omitting a tag is always the locally cheapest move." Generalized: a
claim about repo state costs nothing to write and nothing ever reads it
back. So another log is more of the thing that already failed. This reads
the claims back.

THE DERIVED BLOCK, AND WHY IT IS NOT AN INJECTION VECTOR
Flagging a stale number is still just reporting. Generating it is the fix:

    The workflow runs <!-- derived: ci_test_steps -->17<!-- /derived --> suites.

check_derived_blocks() recomputes each one and fails on mismatch; --fix
rewrites them. A stale count cannot survive CI, and correcting one is a
command rather than a repo-wide sweep.

This repo already deleted a script for the obvious-but-wrong version of
this idea. verify_llms_docs.py extracted fenced spans out of LLM-authored
markdown and ran them through `bash -c` with GH_TOKEN in scope on every
PR; matching was by prefix, so any `;` in a span was arbitrary code
execution. It was removed rather than hardened, and .github/workflows/ci.yml
still carries the tombstone ("do not re-add it").

So markdown here never carries a command. A derived block names a *key*,
constrained to [a-z0-9_]+ by the regex itself, which is looked up in the
DERIVATIONS dict below. An unknown key is an error, never a silent skip.
The markdown can only select a derivation this file already implements;
it cannot introduce one. No shell, no eval, no format-string evaluation.
test_check_repo_claims.py pins that property directly.

WHAT IS CHECKED
  A derived-block drift      — a committed number that no longer recomputes
  B unresolvable references  — a backticked repo path or symbol that is gone
  C verify: predicates       — a steering prompt's status vs. decidable facts
  D CI suite coverage        — a test suite that CI never runs
  E gates that can fail      — an ENFORCE=False script named as if it blocks

WHAT IS NOT CHECKED, DELIBERATELY
Whether a [Resolved] tag is *true*. Well-formedness is decidable; truth is
not. That stays a human judgment, and CLAUDE.md keeps asking for it. This
script narrows where to look; it does not decide. Same boundary
check_pipeline_output.py draws against semantic-pipeline-eval.

THE BASELINE, AND WHY THERE IS NO ENFORCE TOGGLE
Check B over a repo that is 38-54% deliberate prose finds real history on
day one. Cleaning all of it would be a repo-wide prose churn burying the
mechanism in its own diff, so findings present at adoption are recorded in
repo_claims_baseline.json and only *new* ones fail — the same ratchet
check_code_quality.py already uses, for the same reason.

That is the only softening. check_llms_coverage.py ships ENFORCE = False
because it needs a live `gh` call and merged out of order during a fast
burst. This script is local, deterministic, needs no network, and makes
zero LLM calls, so it blocks from day one. A step named as a gate that
cannot fail is worse than no gate — which is precisely what check E exists
to keep true of everything else in ci.yml.
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ast_signature  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_BASELINE = SCRIPT_DIR / "repo_claims_baseline.json"

SCHEMA_VERSION = 1

# The key charset is the security boundary, not a style choice: it is what
# makes a derived block incapable of naming anything but a dict lookup.
DERIVED_RE = re.compile(
    r"<!--\s*derived:\s*([a-z0-9_]+)\s*-->(.*?)<!--\s*/derived\s*-->",
    re.DOTALL,
)

# References come in two shapes, and the second one is not optional.
#
# `ticked` -- anything the author marked as code. Prose outside backticks is
# never inspected, which is what keeps the false-positive surface small.
#
# `bare` -- an unmarked token that begins with one of this repo's own
# top-level directories. Needed because a file *list* is rarely backticked:
# 12-review-session-launcher.md lists the three files a session must read as
# plain indented lines, and those are precisely the paths that once pointed
# at files where "neither exists". Requiring a backtick there would mean
# checking everything except the case that actually broke.
#
# The ticked branch is first, so a path inside backticks is consumed there
# and never double-counted.
_OWN_PREFIX_ALT = "|".join(re.escape(prefix) for prefix in (
    "scripts/", "agents/", "skills/", "claude/", ".github/",
    "baseline-reference/", ".claude/", ".claude-plugin/",
))
REFERENCE_RE = re.compile(
    r"`(?P<ticked>[^`\n]+)`"
    rf"|(?<![\w`/.-])(?P<bare>(?:{_OWN_PREFIX_ALT})[\w./*?-]*[\w*?])"
)

# A path is only checked when it starts with one of this repo's own
# top-level directories, or is a root-level doc. Everything else backs off
# on purpose: these docs are full of illustrative target-repo paths
# (src/main/java/..., docs/readme.md, application.yml) that describe some
# *other* service and must not be resolved against this tree.
OWN_PATH_PREFIXES = (
    "scripts/", "agents/", "skills/", "claude/", ".github/",
    "baseline-reference/", ".claude/", ".claude-plugin/",
)
OWN_ROOT_FILES = frozenset({
    "CLAUDE.md", "CONSTRAINTS.md", "CONTRIBUTING.md", "README.md", "STATUS.md",
    "MATURITY_ASSESSMENT.md", "IMPLEMENTATION_HANDOFF.md", "LICENSE",
    "requirements.txt", "requirements-dev.txt", ".ruff.toml", ".gitignore",
})

# Check B runs against current-state documents only, and this scoping is the
# whole reason it has a usable signal rate.
#
# An append-only record -- claude/session-log.md, claude/llms/pr-N.md,
# claude/tool-quirks.md -- correctly cites files that existed when it was
# written. verify_llms_docs.py was real for 19 PRs before 2f82971 deleted it,
# so every historical mention of it is accurate history, not drift. The same
# holds for the steering-prompt *bodies*, which CLAUDE.md explicitly says are
# "left as historical record rather than rewritten," and for forward-looking
# plans naming artifacts they propose to create.
#
# Their frontmatter is a different matter: `status:` is a claim about *now*,
# which is what check C exists for. So the split is not file-by-file
# squeamishness, it is that the two kinds of text make different claims.
CURRENT_STATE_ROOT_DOCS = frozenset({
    "CLAUDE.md", "CONSTRAINTS.md", "CONTRIBUTING.md", "README.md",
    "STATUS.md", "MATURITY_ASSESSMENT.md",
})
CURRENT_STATE_PREFIXES = ("skills/", "agents/", ".claude/")

# `pr-N.md`, `<name>.md`, `stage-N/` -- a template, not a path. An isolated
# capital letter inside the filename is the tell; real names here are either
# all-caps words (README.md, SKILL.md) or lowercase, neither of which has a
# single capital standing alone between non-word characters.
PLACEHOLDER_RE = re.compile(r"<[^>]+>|(?:^|[^A-Za-z0-9])[A-Z](?:[^A-Za-z0-9]|$)")

# Fenced code, and the exemption applies to check A only -- a fence hides a
# *value*, never a *path*.
#
# A `derived:` block inside a fence is documentation of the syntax: CLAUDE.md
# explains the feature by showing it, and treating that as a live claim made
# this file fail its own check on first run. A deliberately-wrong value is
# exactly what an example is for.
#
# A path inside a fence is the opposite. Fences here hold commands to run and
# files to read, and `12-review-session-launcher.md` is the case that settles
# it: its entire payload is one fenced block that a fresh session is told to
# copy, and the two prompt paths that once pointed at files where "neither
# exists" sit inside it. Exempting fences from check B made the repo's most
# load-bearing path claims invisible -- caught by backtesting against that
# very incident, which is the whole reason the backtest was worth running.
FENCE_RE = re.compile(r"^[ \t]*(?:```|~~~).*?^[ \t]*(?:```|~~~)",
                      re.DOTALL | re.MULTILINE)

# A tombstone: a current-state doc naming something precisely to record that
# it is gone. CONSTRAINTS.md item 4 and STATUS.md both name
# verify_llms_docs.py to say it was deleted as a security defect -- correct
# current-state claims, not drift, and the exact sentences a reader needs.
#
# These are exempted rather than absorbed by the baseline on purpose. A
# baseline entry says "known, unfixed"; that is the wrong label for a
# sentence which is right, and putting it there would teach the baseline as
# an escape hatch for anything inconvenient. Strikethrough is markdown's own
# marker for "no longer applies", and the check is line-scoped so it cannot
# silently excuse a neighbouring claim.
TOMBSTONE_RE = re.compile(
    r"~~|\b(?:deleted|removed|no longer exists?|withdrawn|deprecated)\b"
    r"|not in this repo|live in the Claude project",
    re.IGNORECASE,
)

# A citation carrying a line anchor: `path.py:248`, `path.md:248-257`.
LINE_ANCHOR_RE = re.compile(r"^(?P<path>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$")

# `name()` shaped spans. The underscore requirement is what keeps Java out:
# the pipeline documents camelCase methods (findAll(), getUserById()) by the
# hundred, and none of them are Python symbols in this repo. It also drops
# bare main()/scan()/open(), which are ambiguous between this repo's code,
# stdlib, and prose.
SYMBOL_RE = re.compile(r"^([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\(\)$")

# Symbols that read as this repo's own but belong to stdlib/third parties.
# Kept explicit rather than absorbed by the baseline, since a reader
# should see why they are skipped.
FOREIGN_SYMBOLS = frozenset({
    "os_replace", "check_output", "check_call", "iter_lines", "read_text",
    "write_text", "from_lines", "sub_run", "match_file",
})

# Suites CI does not run, each with the reason. An entry here is a claim in
# its own right, so it states why rather than just naming the file.
CI_EXEMPT_SUITES: Dict[str, str] = {
    "test_partition_repo_real_world.py":
        "opt-in; needs a real Spring repo via an env var, absent in CI",
}

PREDICATE_PREFIXES = ("path_exists:", "path_absent:", "contains:", "unchanged_since:")

# `unchanged_since:<path>:<level>:<digest>` -- the digest is the second
# operand of a binary relation, so it rides in the claim rather than in a side
# store. That keeps a claim self-contained ("this was true against exactly
# this version") and means a fresh clone can evaluate it with no extra state,
# which is also where in-toto puts the subject digest.
UNCHANGED_SINCE_RE = re.compile(
    r"(unchanged_since:)(?P<path>[^\s:]+):(?P<level>[a-z0-9]+):(?P<digest>[0-9a-f]*)")


def fenced_spans(text: str) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in FENCE_RE.finditer(text)]


def in_fence(spans: Sequence[Tuple[int, int]], offset: int) -> bool:
    return any(start <= offset < end for start, end in spans)


class Finding(NamedTuple):
    """One violation. `fingerprint` deliberately excludes the line number so
    that moving a paragraph does not read as a new finding -- the baseline
    would otherwise go stale every time a doc was reflowed, which is the
    failure mode this whole script exists to prevent."""
    check: str
    path: str
    line: int
    message: str
    fingerprint: str


# --------------------------------------------------------------------------
# Derivations. The closed set. Adding a number to prose means adding a
# function here first, which is the point: it forces the author to say how
# the number is recomputed before they are allowed to state it.
# --------------------------------------------------------------------------

def _test_suite_paths(root: Path) -> List[Path]:
    return sorted((root / "scripts").glob("test_*.py"))


def derive_test_suite_count(root: Path) -> str:
    return str(len(_test_suite_paths(root)))


def derive_test_method_count(root: Path) -> str:
    total = 0
    for path in _test_suite_paths(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    node.name.startswith("test_"):
                total += 1
    return str(total)


def _ci_run_lines(root: Path) -> List[str]:
    workflow = root / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        return []
    return workflow.read_text(encoding="utf-8").splitlines()


def derive_ci_test_steps(root: Path) -> str:
    pattern = re.compile(r"run:\s*python3?\s+scripts/(test_\w+\.py)")
    hits = {m.group(1) for line in _ci_run_lines(root)
            for m in [pattern.search(line)] if m}
    return str(len(hits))


def derive_steering_prompt_count(root: Path) -> str:
    prompts = (root / "claude" / "steering-prompts").glob("[0-9][0-9]-*.md")
    return str(len(list(prompts)))


def derive_pipeline_agent_count(root: Path) -> str:
    return str(len(list((root / "agents").glob("*.md"))))


DERIVATIONS: Dict[str, Callable[[Path], str]] = {
    "test_suite_count": derive_test_suite_count,
    "test_method_count": derive_test_method_count,
    "ci_test_steps": derive_ci_test_steps,
    "steering_prompt_count": derive_steering_prompt_count,
    "pipeline_agent_count": derive_pipeline_agent_count,
}


# --------------------------------------------------------------------------
# Tracked-file discovery
# --------------------------------------------------------------------------

def tracked_files(root: Path) -> List[str]:
    """Tracked paths only. This is a scope decision, not an optimization:
    the working tree routinely holds a ~101MB checkout of a third party's
    service (.gitignore'd by name for exactly that reason), and scratch
    notes that were never meant to be claims about anything."""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=str(root), capture_output=True,
            text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def tracked_markdown(root: Path) -> List[str]:
    return [p for p in tracked_files(root) if p.endswith(".md")]


# --------------------------------------------------------------------------
# Check A -- derived-block drift
# --------------------------------------------------------------------------

def check_derived_blocks(root: Path, paths: Sequence[str]) -> List[Finding]:
    findings: List[Finding] = []
    for rel in paths:
        text = (root / rel).read_text(encoding="utf-8")
        spans = fenced_spans(text)
        for match in DERIVED_RE.finditer(text):
            if in_fence(spans, match.start()):
                continue
            key, committed = match.group(1), match.group(2)
            line = text.count("\n", 0, match.start()) + 1
            fingerprint = f"A:{rel}:{key}"
            if key not in DERIVATIONS:
                findings.append(Finding(
                    "A", rel, line,
                    f"unknown derivation key {key!r}; known keys: "
                    f"{', '.join(sorted(DERIVATIONS))}",
                    fingerprint))
                continue
            actual = DERIVATIONS[key](root)
            if committed.strip() != actual:
                findings.append(Finding(
                    "A", rel, line,
                    f"derived:{key} says {committed.strip()!r}, recomputes to "
                    f"{actual!r} -- run --fix",
                    fingerprint))
    return findings


def apply_affirm(root: Path, paths: Sequence[str]) -> List[str]:
    """Stamp every `unchanged_since:` predicate with its subject's current
    signature. Returns the paths actually changed.

    Without this the predicate is unusable: a claim can only be re-affirmed by
    hand-computing a digest, which nobody will do, and an unusable check is an
    ignored check. `--fix` exists for derived blocks for the same reason.

    Deliberately unconditional -- it stamps what is true now, it does not ask
    whether the claim is still *correct*. That judgement is the human's, and
    the point of running this is that they have just made it."""
    changed: List[str] = []
    for rel in paths:
        target = root / rel
        text = target.read_text(encoding="utf-8")
        spans = fenced_spans(text)

        def replace(match: "re.Match[str]",
                    spans: Sequence[Tuple[int, int]] = spans,
                    root: Path = root) -> str:
            # Same late-binding guard as apply_fix: this closure is defined
            # in a loop, which is the B023 class of bug.
            if in_fence(spans, match.start()):
                return match.group(0)
            subject = root / match.group("path")
            if not subject.exists():
                return match.group(0)
            try:
                current = _ast_signature.signature(subject, match.group("level"))
            except (ValueError, SyntaxError):
                # A bad level or an unparseable subject must keep failing the
                # check rather than being rewritten to something plausible.
                return match.group(0)
            return f"unchanged_since:{match.group('path')}:{current}"

        updated = UNCHANGED_SINCE_RE.sub(replace, text)
        if updated != text:
            target.write_text(updated, encoding="utf-8", newline="")
            changed.append(rel)
    return changed


def apply_fix(root: Path, paths: Sequence[str]) -> List[str]:
    """Rewrite every derived block to its recomputed value. Returns the
    paths actually changed. Unknown keys are left untouched and still fail
    the check -- silently rewriting one to a guessed value would be the
    same class of bug as a gate that cannot fail."""
    changed: List[str] = []
    for rel in paths:
        target = root / rel
        text = target.read_text(encoding="utf-8")
        spans = fenced_spans(text)

        # spans/root bound as defaults rather than captured: this closure is
        # defined inside a loop, and late binding there is the B023 class of
        # bug -- correct today only because sub() runs in the same iteration.
        def replace(match: "re.Match[str]",
                    spans: Sequence[Tuple[int, int]] = spans,
                    root: Path = root) -> str:
            key = match.group(1)
            # A fenced block is documentation of the syntax, not a claim.
            # Rewriting the example in CLAUDE.md that explains this feature
            # would be a small, funny disaster.
            if key not in DERIVATIONS or in_fence(spans, match.start()):
                return match.group(0)
            return (f"<!-- derived: {key} -->{DERIVATIONS[key](root)}"
                    f"<!-- /derived -->")

        updated = DERIVED_RE.sub(replace, text)
        if updated != text:
            target.write_text(updated, encoding="utf-8")
            changed.append(rel)
    return changed


# --------------------------------------------------------------------------
# Check B -- unresolvable references
# --------------------------------------------------------------------------

def live_method_prompts(root: Path) -> Set[str]:
    """Steering prompts with no `status:` field.

    A prompt that tracks a task carries a status, and CLAUDE.md says its body
    is "left as historical record rather than rewritten" -- so 07's body still
    reporting no CI is correct history, not drift.

    A prompt with no status is not tracking anything; it is a method document
    meant to be followed *now*. `12-review-session-launcher.md` is the proof:
    it tells a fresh session "Read, in this order, before doing anything else"
    and then lists paths. After a renumbering it pointed at two files where
    "neither exists", and every session it launched started from a broken
    instruction. That is a current-state claim by any reading.
    """
    prompts = (root / "claude" / "steering-prompts").glob("[0-9][0-9]-*.md")
    return {p.relative_to(root).as_posix() for p in prompts
            if "status" not in parse_frontmatter(p.read_text(encoding="utf-8"))}


def is_current_state_doc(rel: str, live_prompts: Set[str]) -> bool:
    return (rel in CURRENT_STATE_ROOT_DOCS
            or rel.startswith(CURRENT_STATE_PREFIXES)
            or rel in live_prompts)


def is_own_path(token: str) -> bool:
    if " " in token or token.endswith("/"):
        return False
    if token in OWN_ROOT_FILES:
        return True
    return token.startswith(OWN_PATH_PREFIXES) and "." in Path(token).name


def resolve_reference(root: Path, token: str) -> Optional[str]:
    """Returns None when the reference resolves, or a reason when it does not.

    Handles the three shapes a repo path actually takes in this project's
    prose, each of which was a false positive on the first run:
      - a glob (`scripts/test_*.py`) -- resolves if it matches anything
      - a line anchor (`partition_repo.py:248-257`) -- the path must exist
        and the line must be inside the file, which is the mis-anchored
        citation this repo has already shipped once
      - a placeholder (`claude/llms/pr-N.md`) -- a template, never resolved
    """
    if PLACEHOLDER_RE.search(token):
        return None

    anchor = LINE_ANCHOR_RE.match(token)
    if anchor:
        path_part = anchor.group("path")
        if not is_own_path(path_part):
            return None
        target = root / path_part
        if not target.is_file():
            return f"references {token!r}, whose file does not exist"
        line_count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        highest = int(anchor.group("end") or anchor.group("start"))
        if highest > line_count:
            return (f"cites {token!r} but {path_part} has only "
                    f"{line_count} lines")
        return None

    if not is_own_path(token):
        return None

    if "*" in token or "?" in token:
        return (None if any(root.glob(token))
                else f"references {token!r}, which matches no file")

    if not (root / token).exists():
        return f"references {token!r}, which does not exist"
    return None


def collect_python_symbols(root: Path) -> Set[str]:
    """Every function and method name defined under scripts/. Names, not
    qualified paths: a doc citing `find_ast_grep()` should resolve wherever
    it lives, and tracking moves between modules is not this check's job."""
    names: Set[str] = set()
    for path in sorted((root / "scripts").glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
    return names


def check_references(root: Path, paths: Sequence[str]) -> List[Finding]:
    symbols = collect_python_symbols(root)
    live_prompts = live_method_prompts(root)
    findings: List[Finding] = []
    for rel in paths:
        if not is_current_state_doc(rel, live_prompts):
            continue
        text = (root / rel).read_text(encoding="utf-8")
        lines = text.splitlines()
        for match in REFERENCE_RE.finditer(text):
            token = (match.group("ticked") or match.group("bare") or "").strip()
            if not token:
                continue
            line = text.count("\n", 0, match.start()) + 1
            if line <= len(lines) and TOMBSTONE_RE.search(lines[line - 1]):
                continue
            reason = resolve_reference(root, token)
            if reason:
                findings.append(Finding("B", rel, line, reason, f"B:{rel}:{token}"))
                continue
            symbol_match = SYMBOL_RE.match(token)
            if symbol_match:
                name = symbol_match.group(1)
                if name not in symbols and name not in FOREIGN_SYMBOLS:
                    findings.append(Finding(
                        "B", rel, line,
                        f"references {name}(), which is defined nowhere in scripts/",
                        f"B:{rel}:{name}()"))
    return findings


# --------------------------------------------------------------------------
# Check C -- verify: predicates on steering prompts
# --------------------------------------------------------------------------

def parse_frontmatter(text: str) -> Dict[str, object]:
    """Minimal frontmatter reader: scalars and `- ` lists only. Deliberately
    not PyYAML -- this repo has no YAML dependency and added _config_keys.py
    rather than take one on for a similarly narrow need."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fields: Dict[str, object] = {}
    current_list: Optional[List[str]] = None
    for raw in text[3:end].splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- ") and current_list is not None:
            current_list.append(line.lstrip()[2:].strip())
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value:
            fields[key] = value
            current_list = None
        else:
            current_list = []
            fields[key] = current_list
    return fields


def evaluate_predicate(root: Path, predicate: str) -> Tuple[bool, str]:
    """Returns (passed, explanation). The vocabulary is closed for the same
    reason DERIVATIONS is: a predicate must be decidable by this file, not
    supplied by the document being checked."""
    if predicate.startswith("path_exists:"):
        target = predicate[len("path_exists:"):].strip()
        return (root / target).exists(), f"{target} does not exist"
    if predicate.startswith("path_absent:"):
        target = predicate[len("path_absent:"):].strip()
        return not (root / target).exists(), f"{target} exists but was declared absent"
    if predicate.startswith("contains:"):
        rest = predicate[len("contains:"):]
        target, _, literal = rest.partition(":")
        target, literal = target.strip(), literal.strip()
        if not literal:
            return False, f"malformed contains: predicate {predicate!r} (no literal)"
        path = root / target
        if not path.is_file():
            return False, f"{target} does not exist, so it cannot contain {literal!r}"
        found = literal in path.read_text(encoding="utf-8")
        return found, f"{target} does not contain {literal!r}"
    if predicate.startswith("unchanged_since:"):
        return _evaluate_unchanged_since(root, predicate)
    return False, (f"unknown predicate {predicate!r}; expected one of "
                   f"{', '.join(PREDICATE_PREFIXES)}")


def _evaluate_unchanged_since(root: Path, predicate: str) -> Tuple[bool, str]:
    """Has the subject moved since this claim was last affirmed?

    This does NOT assert the claim is true -- nothing here can judge that. It
    asserts that nobody has re-read the claim since the thing it describes
    changed, which is a staleness signal and is honest about being one.

    Never-affirmed is reported separately from failed: an empty digest means
    the claim opted in but nobody has stamped it yet, which is a different
    (and much cheaper) thing to fix than a real mismatch."""
    rest = predicate[len("unchanged_since:"):].strip()
    parts = rest.rsplit(":", 2)
    if len(parts) != 3:
        return False, (f"malformed {predicate!r}; expected "
                       f"unchanged_since:<path>:<level>:<digest>")
    target, level, digest = (part.strip() for part in parts)
    path = root / target
    if not path.exists():
        return False, f"{target} does not exist, so it cannot be unchanged"
    if not digest:
        return False, (f"{target} has never been affirmed at level {level}; "
                       f"run --affirm to stamp its current signature")
    try:
        current = _ast_signature.signature(path, level)
    except ValueError as exc:
        # An unknown level is a failure, never a silent pass: falling back to
        # a different relation would compare two incomparable digests and
        # report the answer confidently.
        return False, str(exc)
    except SyntaxError as exc:
        return False, f"{target} does not parse, so it cannot be fingerprinted: {exc}"
    if current == f"{level}:{digest}":
        return True, ""
    return False, (f"{target} changed since this claim was affirmed (level "
                   f"{level}) — re-read the claim, then run --affirm")


class Claim(NamedTuple):
    """One assertion this repo makes about its own current state.

    The grain matters and is deliberately one row per *claim*, not per file:
    every ratio below divides by this, and mixing file-level and claim-level
    denominators produces numbers that look reasonable and mean nothing."""
    corpus: str
    path: str
    line: int
    status: str
    predicates: Tuple[str, ...]
    key: str


# Inline opt-in for prose that has no frontmatter to put a verify: list in.
# An HTML comment renders as nothing, so a claim can carry its own predicates
# without changing how the document reads -- the same trick the derived:
# blocks already use, and the reason CONSTRAINTS.md needs no migration to
# join this check. Semicolon-separated so one claim can carry several.
INLINE_VERIFY_RE = re.compile(r"<!--\s*verify:\s*(.+?)\s*-->", re.DOTALL)

# A CONSTRAINTS.md entry opens with a bolded bracket tag: **[Resolved]**,
# **[Partially resolved, 2026-07-24]**, **[Flagged, not yet resolved]**.
#
# Bounded by "no newline", not by a character count. A 60-char cap looked
# reasonable and silently dropped three claims -- the long "[New info — the
# wording above ran ahead of the code...]" corrections, which are the most
# interesting entries in the file precisely because they record a claim that
# had already gone wrong. A checker that quietly omits the hardest cases
# reports a better number than the truth, which is this project's own
# "silent truncation reading as completeness" anti-pattern. The newline bound
# is the real one: a tag is a single line, and forbidding newlines stops the
# match running away across the document without inventing a length.
BRACKET_TAG_RE = re.compile(r"\*\*\[([A-Za-z][^\]\n]*)\]\*\*")


def extract_frontmatter_claims(root: Path, path: Path) -> List[Claim]:
    """A steering prompt's `status:` is the claim; its `verify:` list is what
    would falsify it."""
    rel = path.relative_to(root).as_posix()
    fields = parse_frontmatter(path.read_text(encoding="utf-8"))
    if "status" not in fields:
        return []
    predicates = fields.get("verify")
    listed = tuple(predicates) if isinstance(predicates, list) else ()
    status = str(fields.get("status", "?"))
    return [Claim("steering-prompts", rel, 1, status, listed, f"{rel}")]


def extract_bracket_tag_claims(root: Path, path: Path) -> List[Claim]:
    """Every `**[Status]**` entry in a current-state doc is a claim.

    Read-only adoption: this parses what CONSTRAINTS.md already writes, so
    the file needs no migration to be covered. A claim opts in to being
    checked by adding an inline `<!-- verify: ... -->`; until it does it is
    counted as unfalsifiable, which is the honest description of a status
    word nothing can contradict.

    A claim's predicates are those appearing between its own tag and the next
    one, so predicates attach to the entry that declares them."""
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(root).as_posix()
    spans = fenced_spans(text)

    def fenced(pos: int) -> bool:
        return any(start <= pos < end for start, end in spans)

    tags = [m for m in BRACKET_TAG_RE.finditer(text) if not fenced(m.start())]
    claims: List[Claim] = []
    for index, match in enumerate(tags):
        end = tags[index + 1].start() if index + 1 < len(tags) else len(text)
        body = text[match.end():end]
        predicates = tuple(
            part.strip()
            for found in INLINE_VERIFY_RE.finditer(body)
            for part in found.group(1).split(";")
            if part.strip()
        )
        status = match.group(1).split(",")[0].strip()
        line = text.count("\n", 0, match.start()) + 1
        # Keyed on status + ordinal rather than line: the fingerprint must
        # survive a paragraph moving, for the same reason Finding's does.
        claims.append(Claim("constraints", rel, line, status, predicates,
                            f"{rel}#{index}:{status}"))
    return claims


CLAIM_CORPORA: Tuple[Tuple[str, str, object], ...] = (
    ("steering-prompts", "claude/steering-prompts/[0-9][0-9]-*.md",
     extract_frontmatter_claims),
    ("constraints", "CONSTRAINTS.md", extract_bracket_tag_claims),
)


def collect_claims(root: Path) -> List[Claim]:
    """Every claim in every registered corpus. Adding a corpus is a row in
    CLAIM_CORPORA, not a new function in the check below."""
    claims: List[Claim] = []
    for _name, pattern, extract in CLAIM_CORPORA:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                claims.extend(extract(root, path))  # type: ignore[operator]
    return claims


# Prompts 00-06 have a canonical copy in the Claude project; 07+ do not.
# Editing one of the first seven creates an obligation to copy the change
# back, and this session cannot discharge it -- a CLI session has git and no
# project access, a Cowork session has the reverse. That obligation has been
# carried in prose in claude/session-log.md, which means it is only as
# reliable as someone reading the log.
MIRRORED_PROMPT_GLOB = "claude/steering-prompts/0[0-6]-*.md"
MIRROR_STATE = Path("claude") / "steering-prompts" / "mirror-state.json"


def mirror_debt(root: Path) -> List[str]:
    """Mirrored prompts edited since they were last copied to the project.

    Deliberately NOT wired to unchanged_since:/--affirm, though the mechanism
    is the same. Affirming means "I re-read this claim"; mirroring means "I
    copied this file to the Claude project." Those are different acts, and
    sharing one verb would let a routine --affirm silently clear real mirror
    debt -- the reported number would then be lowest exactly when someone had
    been most casual.

    Measures debt, it does not confirm sync: nothing here can see the project
    copy. A prompt absent from the state file has never been recorded, which
    is reported as debt rather than assumed clean."""
    state: Dict[str, str] = {}
    state_path = root / MIRROR_STATE
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8")).get("mirrored", {})
    stale: List[str] = []
    for path in sorted(root.glob(MIRRORED_PROMPT_GLOB)):
        rel = path.relative_to(root).as_posix()
        if state.get(rel) != _ast_signature.signature(path, "raw"):
            stale.append(rel)
    return stale


def write_mirror_state(root: Path) -> int:
    """Record every mirrored prompt's current signature. Run this *after*
    copying the changes into the Claude project, never instead of it."""
    recorded = {
        path.relative_to(root).as_posix(): _ast_signature.signature(path, "raw")
        for path in sorted(root.glob(MIRRORED_PROMPT_GLOB))
    }
    payload = {
        "$comment": ("Signatures of the steering prompts that have a canonical copy "
                     "in the Claude project, as of the last time they were mirrored "
                     "back. Regenerate with check_repo_claims.py --mirrored AFTER "
                     "copying the changes across. This records debt; it cannot see "
                     "the project and does not confirm the copies match."),
        "mirrored": recorded,
    }
    (root / MIRROR_STATE).write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    return len(recorded)


CLAIM_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

# Everything that ends a status word. Statuses are written freehand -- a
# steering prompt's begins "[Resolved — CI part; ...", a CONSTRAINTS.md tag
# "Partially resolved, 2026-07-24" -- so the bucket is the leading phrase up
# to the first separator. Without this the counts split "Resolved" across
# "[Resolved", "Resolved (2026-07-23" and "resolved", which is noise that
# hides the very sprawl the metric exists to show.
STATUS_SEPARATORS = re.compile(r"[—(,;:]")


def normalize_status(status: str) -> str:
    """The bucket a freehand status belongs to. Case-folded leading phrase,
    with punctuation and any date removed.

    The date is stripped *before* splitting: "Corrected 2026-07-24" and
    "Reopened 2026-07-25" are the same kind of claim as an undated
    "Corrected", and bucketing them apart would report the vocabulary as
    wider than it is -- which is the opposite of this metric's job."""
    cleaned = CLAIM_DATE_RE.sub("", status).strip().lstrip("[*").strip()
    head = STATUS_SEPARATORS.split(cleaned, 1)[0].strip()
    return head.lower()[:40] or "(none)"


class ClaimMetrics(NamedTuple):
    """Counts over the claim store. Reported, deliberately not gated.

    A ratio nobody has looked at is not a threshold anybody can defend --
    the same lesson check_code_quality.py's USAGE_WITHIN_LINES records. Print
    these for a while, then ratchet against a measured baseline if it earns
    it."""
    total: int
    falsifiable: int
    predicates: int
    failing: int
    by_status: Tuple[Tuple[str, int], ...]
    dated: int
    oldest: str


def claim_metrics(root: Path) -> ClaimMetrics:
    """Measure the claim store at one row per claim.

    The grain is the whole point: divide by claims, never by files. A file
    carrying nine claims and a file carrying one are not comparable units,
    and a ratio that mixes them reads as precise while meaning nothing."""
    claims = collect_claims(root)
    counts: Dict[str, int] = {}
    dates: List[str] = []
    predicates = 0
    failing = 0
    for claim in claims:
        status = normalize_status(claim.status)
        counts[status] = counts.get(status, 0) + 1
        found = CLAIM_DATE_RE.search(claim.status)
        if found:
            dates.append(found.group(1))
        for predicate in claim.predicates:
            predicates += 1
            passed, _ = evaluate_predicate(root, predicate)
            if not passed:
                failing += 1
    return ClaimMetrics(
        total=len(claims),
        falsifiable=sum(1 for c in claims if c.predicates),
        predicates=predicates,
        failing=failing,
        # Sorted for byte-stable output: this gets printed into CI logs that
        # get diffed, and an unstable dict order makes every run look changed.
        by_status=tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        dated=len(dates),
        oldest=min(dates) if dates else "-",
    )


def format_metrics(metrics: ClaimMetrics) -> str:
    """Human-readable, and honest about the denominator of every ratio."""
    total = metrics.total or 1
    unfalsifiable = metrics.total - metrics.falsifiable
    lines = [
        f"claims                {metrics.total}",
        f"  falsifiable         {metrics.falsifiable} "
        f"({100 * metrics.falsifiable // total}% carry a verify: predicate)",
        f"  unfalsifiable       {unfalsifiable} "
        f"({100 * unfalsifiable // total}% assert something nothing can contradict)",
        f"predicates evaluated  {metrics.predicates}, failing {metrics.failing}",
        f"claims carrying a date {metrics.dated}, oldest {metrics.oldest}",
        "by status:",
    ]
    lines += [f"  {count:>3}  {status}" for status, count in metrics.by_status]
    return "\n".join(lines)


def format_mirror_debt(stale: Sequence[str], total: int) -> str:
    """Reported, never gated. Nothing here can see the project copy, so this
    is a prompt to go and check, not a verdict that anything is wrong."""
    if not stale:
        return f"mirror debt          0 of {total} mirrored prompts edited since last sync"
    lines = [f"mirror debt          {len(stale)} of {total} edited since last mirrored "
             f"to the Claude project:"]
    lines += [f"  {rel}" for rel in stale]
    lines.append("  -> copy these across, then run --mirrored to record it")
    return "\n".join(lines)


def check_verify_predicates(root: Path) -> Tuple[List[Finding], List[Finding]]:
    """Returns (failures, missing). Missing verify: blocks are reported
    separately because they ride the baseline -- a claim with no predicate
    is an unchecked claim, not yet a wrong one."""
    failures: List[Finding] = []
    missing: List[Finding] = []
    for claim in collect_claims(root):
        if not claim.predicates:
            missing.append(Finding(
                "C", claim.path, claim.line,
                "declares a status with no verify: predicates, so nothing "
                "checks it", f"C-missing:{claim.key}"))
            continue
        for predicate in claim.predicates:
            passed, explanation = evaluate_predicate(root, predicate)
            if not passed:
                failures.append(Finding(
                    "C", claim.path, claim.line,
                    f"status {claim.status!r} is contradicted: {explanation}",
                    f"C:{claim.key}:{predicate}"))
    return failures, missing


# --------------------------------------------------------------------------
# Check D -- every test suite is wired into CI
# --------------------------------------------------------------------------

def check_ci_suite_coverage(root: Path) -> List[Finding]:
    workflow = root / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        return []
    text = workflow.read_text(encoding="utf-8")
    findings: List[Finding] = []
    for path in _test_suite_paths(root):
        name = path.name
        if name in CI_EXEMPT_SUITES:
            continue
        if f"scripts/{name}" not in text:
            findings.append(Finding(
                "D", ".github/workflows/ci.yml", 1,
                f"scripts/{name} is never run by CI. ci.yml enumerates suites "
                f"individually, so a new one silently never runs. Add a step, "
                f"or add it to CI_EXEMPT_SUITES with a reason.",
                f"D:{name}"))
    return findings


# --------------------------------------------------------------------------
# Check E -- a step named as a gate must be able to fail
# --------------------------------------------------------------------------

def check_gate_honesty(root: Path) -> List[Finding]:
    """ci.yml already states this rule in a comment; nothing enforced it.
    A non-enforcing script is fine. A non-enforcing script whose step name
    reads like a gate is not, because it looks like enforcement to anyone
    scanning the workflow."""
    workflow = root / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        return []
    lines = workflow.read_text(encoding="utf-8").splitlines()
    findings: List[Finding] = []
    for script in sorted((root / "scripts").glob("*.py")):
        source = script.read_text(encoding="utf-8")
        if not re.search(r"^ENFORCE\s*=\s*False", source, re.MULTILINE):
            continue
        for index, line in enumerate(lines):
            if not line.lstrip().startswith("- name:"):
                continue
            step_name = line.split("- name:", 1)[1]
            # `test_check_llms_coverage.py` contains `check_llms_coverage.py`.
            # Matching on substring alone flags the *suite's* step, which is
            # a unit-test run and makes no enforcement claim at all.
            if not re.search(rf"(?<![\w.]){re.escape(script.name)}", step_name):
                continue
            if "non-blocking" not in step_name.lower():
                findings.append(Finding(
                    "E", ".github/workflows/ci.yml", index + 1,
                    f"step names {script.name}, which sets ENFORCE = False, "
                    f"without saying 'non-blocking'. A step named as a gate "
                    f"that cannot fail is worse than no gate.",
                    f"E:{script.name}"))
    return findings


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------

def load_baseline(path: Path) -> Optional[Dict[str, object]]:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(path: Path, findings: Sequence[Finding]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "$comment": (
            "Findings present when check_repo_claims.py was adopted. The gate "
            "fails only on findings NOT listed here, the same ratchet "
            "code_quality_baseline.json uses. Shrinking this file is always "
            "correct; growing it needs a reason in the PR that does it."
        ),
        "accepted": sorted({f.fingerprint: f.message for f in findings}.items()),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def accepted_fingerprints(baseline: Optional[Dict[str, object]]) -> Set[str]:
    if not baseline:
        return set()
    entries = baseline.get("accepted", [])
    if not isinstance(entries, list):
        return set()
    return {entry[0] for entry in entries if isinstance(entry, list) and entry}


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def collect_all(root: Path) -> Tuple[List[Finding], List[Finding]]:
    """Returns (hard, baseline_eligible). Checks A, D and E are exact and
    never ride the baseline: a wrong derived number, an unrun suite, and a
    mislabelled gate are all unambiguous and all cheap to fix on the spot."""
    markdown = tracked_markdown(root)
    verify_failures, verify_missing = check_verify_predicates(root)
    hard = (check_derived_blocks(root, markdown)
            + check_ci_suite_coverage(root)
            + check_gate_honesty(root)
            + verify_failures)
    soft = check_references(root, markdown) + verify_missing
    return hard, soft


def exit_code(issues: Sequence[Finding]) -> int:
    return 1 if issues else 0


def report(hard: Sequence[Finding], new_soft: Sequence[Finding],
           accepted_count: int) -> None:
    issues = list(hard) + list(new_soft)
    if not issues:
        print(f"OK: no new state-claim violations "
              f"({accepted_count} pre-existing finding(s) held by the baseline).")
        return
    print(f"repo-claims check failed ({len(issues)} new issue(s)):", file=sys.stderr)
    for finding in issues:
        print(f"  [{finding.check}] {finding.path}:{finding.line} — {finding.message}",
              file=sys.stderr)
    print("\nA claim about repo state has to name what would falsify it: a "
          "derived: block, a verify: predicate, or a path that resolves.",
          file=sys.stderr)


def run_action_mode(args: argparse.Namespace, root: Path) -> Optional[int]:
    """Handle the flags that *do* something and exit, rather than checking.

    Returns an exit code when one applied, or None to fall through to the
    check. Split out of main() because main() grew to 49 statements as these
    accumulated and the ratchet said so -- which is the ratchet working, so
    the answer was to shrink it rather than re-baseline."""
    if args.mirrored:
        count = write_mirror_state(root)
        print(f"mirror state recorded for {count} prompt(s). This says they were "
              f"copied to the Claude project — it cannot verify that they were.")
        return 0
    if args.metrics:
        # Exits 0 regardless: measurements, not verdicts. Gating on a number
        # before anyone has watched it move is how a threshold gets picked
        # that nobody can defend.
        print(format_metrics(claim_metrics(root)))
        print()
        print(format_mirror_debt(mirror_debt(root),
                                 len(list(root.glob(MIRRORED_PROMPT_GLOB)))))
        return 0
    if args.affirm:
        changed = apply_affirm(root, tracked_markdown(root))
        print(f"unchanged_since: signatures stamped in {len(changed)} file(s)"
              + (": " + ", ".join(changed) if changed else ""))
        return 0
    if args.fix:
        changed = apply_fix(root, tracked_markdown(root))
        print(f"derived blocks rewritten in {len(changed)} file(s)"
              + (": " + ", ".join(changed) if changed else ""))
        return 0
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--root", default=str(REPO_ROOT),
                        help="repository root to check")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE),
                        help="committed baseline of accepted pre-existing findings")
    parser.add_argument("--fix", action="store_true",
                        help="rewrite derived blocks to their recomputed values")
    parser.add_argument("--update", action="store_true",
                        help="re-baseline instead of checking")
    parser.add_argument("--affirm", action="store_true",
                        help="stamp every unchanged_since: predicate with its "
                             "subject's current signature (do this after re-reading "
                             "the claim, not instead of it)")
    parser.add_argument("--mirrored", action="store_true",
                        help="record that prompts 00-06 have been copied back to the "
                             "Claude project (run AFTER copying, not instead of it)")
    parser.add_argument("--metrics", action="store_true",
                        help="report claim-store metrics and exit without checking")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print(f"error: {root} is not a git repository", file=sys.stderr)
        return 2

    handled = run_action_mode(args, root)
    if handled is not None:
        return handled

    hard, soft = collect_all(root)

    if args.update:
        write_baseline(Path(args.baseline), soft)
        print(f"baseline written: {args.baseline} ({len(soft)} finding(s) accepted)")
        if hard:
            print("note: exact checks (A/D/E and failed verify: predicates) are "
                  "never baselined; the following still fail:", file=sys.stderr)
            for finding in hard:
                print(f"  [{finding.check}] {finding.path}:{finding.line} — "
                      f"{finding.message}", file=sys.stderr)
        return exit_code(hard)

    baseline = load_baseline(Path(args.baseline))
    if baseline is not None and baseline.get("schema_version") != SCHEMA_VERSION:
        print(f"error: baseline schema_version {baseline.get('schema_version')} "
              f"!= {SCHEMA_VERSION}; regenerate with --update.", file=sys.stderr)
        return 2

    accepted = accepted_fingerprints(baseline)
    new_soft = [f for f in soft if f.fingerprint not in accepted]
    report(hard, new_soft, len(accepted))
    return exit_code(list(hard) + new_soft)


if __name__ == "__main__":
    sys.exit(main())
