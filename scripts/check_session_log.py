#!/usr/bin/env python3
"""
check_session_log.py — validates the two one-file-per-entry append-only logs,
`claude/session-log/` and `claude/tool-quirks/`.

WHY THIS EXISTS
Both logs used to be single append-only markdown files. Every qualifying PR
appended to `claude/session-log.md`, which made it a guaranteed merge-conflict
point: two concurrent PRs always touched the same tail of the same file, and
an append-only log has no legitimate "theirs wins" resolution, so every
collision had to be reconciled by hand. Splitting to one file per entry
removes the shared append point entirely.

That split needs a validator, because the session log was the least
mechanically defended of this repo's three conventions — no parser, no test,
no CI step, and its one integrity property ever checked (that `Commit:` SHAs
resolve) was verified by hand exactly once. `claude/llms/` has had
`verify_llms_docs.py` and `check_llms_coverage.py` for a while; this is the
equivalent for the other two.

DELIBERATELY NOT CHECKED
Three things look like defects and are not. Do not "fix" them:

1. Heading date vs. the commit's own author date. A batch of entries was
   written a day ahead of the commits they describe (`STATUS.md`'s date
   convention note records this, and says historical entries stay as
   written). Enforcing agreement would fail more than half the corpus.
2. Tag *presence*. Many bullets under `Assumptions affected:` are context or
   commentary, not assumptions, and one entire entry has four bullets and no
   tags. This checks the grammar of a tag when one is present, never that one
   must be — the same posture `test_pipeline_stages.py` takes toward the
   doc-writer tag grammar.
3. Chronological ordering. One entry sits out of order for a reason recorded
   in the log itself. Post-split, ordering is a filename sort anyway.

NO `ENFORCE` TOGGLE
`check_llms_coverage.py` ships with `ENFORCE = False` because it needs a live
`gh` call and merged out of order during a fast-merge burst. This script is
local, deterministic, and needs no network, so it blocks from day one. The
one deliberate softening is `kind:` — see KINDS below — which warns rather
than fails because that vocabulary is explicitly provisional. Warnings are
always printed; if one is ever swallowed, that is the bug.

Run with:
    python3 scripts/check_session_log.py
    python3 scripts/check_session_log.py --group-by kind
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

SESSION_LOG = "session-log"
TOOL_QUIRKS = "tool-quirks"

DEFAULT_DIRS = {
    SESSION_LOG: REPO_ROOT / "claude" / "session-log",
    TOOL_QUIRKS: REPO_ROOT / "claude" / "tool-quirks",
}

EM_DASH = "—"

FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) " + EM_DASH + r" (.+)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BACKTICK_RE = re.compile(r"`[^`]*`")
SHA_RE = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")
TICKET_ID_RE = re.compile(r"^[A-Z]+-\d+$")

# Closed sets. `ticket:` and `pr:` take a real ID or a sentinel — never a bare
# `null`, which would collapse genuinely different situations into one bucket
# under --group-by. The sentinels distinguish "no tracker exists yet" from
# "this predates the tracker" from "should have one, nobody knows which".
TICKET_SENTINELS = ("UNASSIGNED-NO-TRACKER", "UNASSIGNED-PREDATES", "UNASSIGNED-UNKNOWN")
PR_SENTINELS = ("PR-OPEN", "NO-PR-DIRECT-COMMIT", "NO-PR-UNCOMMITTED")
TEAMS = ("platform",)
EPICS = (
    "repo-hygiene",
    "testability",
    "constraints",
    "secret-redaction",
    "dependency-pinning",
    "drift-check",
    "jpql-provenance",
    "llms-coverage",
    "pipeline-telemetry",
    "tool-quirks",
)

# Provisional, and warning-only for exactly that reason: this vocabulary was
# fitted to six historical entries, and the first genuinely new entry after
# the split already needed a seventh value (`sandbox-env` — a container that
# can clone but cannot push, where neither `git` nor the GitHub API is
# misbehaving). Review when steering prompt 09 is picked up, or at 15 entries,
# whichever comes first. Adding a value means editing this constant AND
# skills/tool-quirks/SKILL.md in the same commit as the entry that needs it.
KINDS = (
    "gh-cli",
    "github-api",
    "git",
    "shell-windows",
    "mcp-tool",
    "process-gap",
    "sandbox-env",
)

SCHEMAS = {
    SESSION_LOG: {
        "frontmatter": ("team", "epic", "ticket", "pr", "session", "date"),
        "fields": ("Commit:", "Tests:", "Assumptions affected:", "Files touched:"),
        # Fields that belong to the *other* log. Their presence means an entry
        # was filed in the wrong directory.
        "foreign_fields": ("Tools/commands involved:", "Symptom:", "Resolution / workaround:"),
        # Anchored on em-dash-space-bracket. Without the anchor, prose brackets
        # like `[dotted.key.path, ...]` register as tags.
        "tag_anchor": re.compile(r"" + EM_DASH + r" \[([^\]" + EM_DASH + r"]{1,90})"),
        "tags": ("Resolved", "Still accurate", "New info"),
    },
    TOOL_QUIRKS: {
        "frontmatter": ("team", "epic", "ticket", "kind", "session", "date"),
        "fields": (
            "Tools/commands involved:",
            "Status:",
            "Symptom:",
            "Diagnostic steps taken (re-runnable):",
            "Resolution / workaround:",
        ),
        "foreign_fields": ("Commit:", "Assumptions affected:"),
        # A DIFFERENT anchor, and this is load-bearing: every tag here follows
        # `Status: `, not an em dash. Reusing session-log's anchor matches zero
        # lines in this directory and reports "0 violations" over an empty set,
        # letting any invented tag through silently — in the one directory
        # where vocabulary drift has actually happened.
        "tag_anchor": re.compile(r"^Status: \[([^\]" + EM_DASH + r"]{1,90})"),
        "tags": ("Resolved", "Diagnosed", "Partially diagnosed", "Unresolved"),
    },
}


class Entry(NamedTuple):
    path: Path
    kind: str
    frontmatter: Dict[str, str]
    body: List[str]          # lines after the frontmatter block
    heading_date: str        # "" if no parseable heading
    heading_text: str
    raw: str


def strip_backticks(line: str) -> str:
    """Backtick-quoted spans are quotations, not assertions — a documented
    `[Evidenced — path:line]` example inside backticks is not this entry's own
    tag. Strip them before any tag matching."""
    return BACKTICK_RE.sub("", line)


def split_frontmatter(text: str) -> Tuple[Dict[str, str], List[str]]:
    """Returns (frontmatter dict, body lines).

    Deliberately the same flat, line-oriented `key: value` parse
    `check_llms_coverage.py` uses — no YAML dependency. The flatness is a
    constraint, not an oversight: a nested value would be silently mangled
    (its child keys promoted to top level, the parent left empty, no error),
    which is exactly why `ticket:`/`pr:` use flat sentinel strings instead of
    a nested {id, reason} object.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fields = {}
            for line in lines[1:i]:
                if ":" in line:
                    key, _, value = line.partition(":")
                    fields[key.strip()] = value.strip()
            return fields, lines[i + 1:]
    return {}, lines


def parse_entry(path: Path, kind: str) -> Entry:
    raw = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(raw)
    heading_date, heading_text = "", ""
    for line in body:
        if line.startswith("## "):
            m = HEADING_RE.match(line)
            if m:
                heading_date, heading_text = m.group(1), m.group(2)
            break
    return Entry(path, kind, frontmatter, body, heading_date, heading_text, raw)


def _check_frontmatter(entry: Entry, schema: dict) -> Tuple[List[str], List[str]]:
    issues: List[str] = []
    warnings: List[str] = []
    fm = entry.frontmatter
    required = schema["frontmatter"]

    if not fm:
        issues.append("no parseable frontmatter block")
        return issues, warnings

    for key in required:
        if key not in fm:
            issues.append(f"frontmatter is missing required key `{key}:`")
    # Typo guard: `tickets:` next to `ticket:` would otherwise be invisible.
    for key in fm:
        if key not in required:
            issues.append(f"frontmatter has unrecognized key `{key}:`")

    def closed(key: str, allowed: Sequence[str]) -> None:
        value = fm.get(key)
        if value is not None and value not in allowed:
            issues.append(
                f"`{key}: {value}` is not in the declared set ({', '.join(allowed)})"
            )

    closed("team", TEAMS)
    closed("epic", EPICS)

    ticket = fm.get("ticket")
    if ticket is not None and ticket not in TICKET_SENTINELS and not TICKET_ID_RE.match(ticket):
        issues.append(
            f"`ticket: {ticket}` is neither an ID matching [A-Z]+-<digits> nor one of "
            f"({', '.join(TICKET_SENTINELS)})"
        )

    if "pr" in required:
        pr_value = fm.get("pr")
        if pr_value is not None and pr_value not in PR_SENTINELS and not pr_value.isdigit():
            issues.append(
                f"`pr: {pr_value}` is neither a PR number nor one of ({', '.join(PR_SENTINELS)})"
            )

    if "kind" in required:
        kind_value = fm.get("kind")
        # Warning, not an issue — the vocabulary is provisional by design.
        if kind_value is not None and kind_value not in KINDS:
            warnings.append(
                f"`kind: {kind_value}` is not in the provisional set ({', '.join(KINDS)}) "
                f"— add it there and to skills/tool-quirks/SKILL.md, or rename the value"
            )

    date = fm.get("date", "")
    if date and not DATE_RE.match(date):
        issues.append(f"`date: {date}` is not YYYY-MM-DD")

    return issues, warnings


def _check_heading_and_dates(entry: Entry) -> List[str]:
    issues: List[str] = []

    headings = [line for line in entry.body if line.startswith("## ")]
    if len(headings) != 1:
        issues.append(f"expected exactly one `## ` heading, found {len(headings)}")
        return issues
    if not entry.heading_date:
        issues.append(
            f"heading does not match `## YYYY-MM-DD {EM_DASH} <description>` "
            f"(an em dash, U+2014, not a hyphen): {headings[0][:60]!r}"
        )
        return issues

    # The heading must be the first thing after the frontmatter — otherwise
    # content can hide above it and never be read as part of any entry.
    for line in entry.body:
        if not line.strip():
            continue
        if not line.startswith("## "):
            issues.append(f"content appears before the `## ` heading: {line[:60]!r}")
        break

    filename_date = entry.path.name[:10]
    fm_date = entry.frontmatter.get("date", "")
    # Three-way agreement. Two-way would pass a file copied from a neighbour
    # and renamed, which is the realistic mistake.
    if fm_date and fm_date != filename_date:
        issues.append(f"`date: {fm_date}` disagrees with the filename date {filename_date}")
    if entry.heading_date != filename_date:
        issues.append(
            f"heading date {entry.heading_date} disagrees with the filename date {filename_date}"
        )
    return issues


def _check_fields(entry: Entry, schema: dict) -> List[str]:
    """Required fields present exactly once, as labels at column 0.

    Two scoping rules, both learned from real entries:
      - "column 0" applies to the *label*, never to its content. The
        tool-quirks template indents its diagnostic command block four spaces
        by design.
      - a field's value may sit inline on the label line rather than in a
        following block ("Diagnostic steps taken (re-runnable): none needed
        beyond ..." is legal).
    Fields need not be contiguous or exhaustive either: interleaved prose,
    bolded paragraphs, markdown tables and extra fields are all legal.
    """
    issues: List[str] = []
    for field in schema["fields"]:
        count = sum(1 for line in entry.body if line.startswith(field))
        if count == 0:
            indented = any(line.strip().startswith(field) for line in entry.body)
            if indented:
                issues.append(f"field `{field}` is indented; field labels must start at column 0")
            else:
                issues.append(f"missing required field `{field}`")
        elif count > 1:
            issues.append(f"field `{field}` appears {count} times, expected once")

    for field in schema["foreign_fields"]:
        if any(line.startswith(field) for line in entry.body):
            issues.append(
                f"field `{field}` belongs to the other log — this entry looks filed "
                f"in the wrong directory"
            )
    return issues


def _tag_leading_word(captured: str, vocabulary: Sequence[str]) -> Optional[str]:
    """Match on the leading word plus a boundary, not the whole tag.

    Qualified forms are common and legal — `[Resolved, heuristically ...]`,
    `[Resolved for the bounded common case ...]`, `[Still accurate, with one
    small, deliberately-scoped exception ...]`. Longest vocabulary entry first
    so "Partially diagnosed" is not swallowed by "Diagnosed".
    """
    text = captured.strip()
    for word in sorted(vocabulary, key=len, reverse=True):
        if text == word or text.startswith(word + " ") or text.startswith(word + ","):
            return word
    return None


def count_tags(entry: Entry, schema: dict) -> Tuple[int, List[str]]:
    """Returns (tags found, issues). Grammar of a tag when present — never
    that a tag must be present."""
    issues: List[str] = []
    found = 0
    for line in entry.body:
        for captured in schema["tag_anchor"].findall(strip_backticks(line)):
            found += 1
            if _tag_leading_word(captured, schema["tags"]) is None:
                issues.append(
                    f"tag `[{captured.strip()}]` is not in the vocabulary "
                    f"({', '.join(schema['tags'])})"
                )
    return found, issues


def commit_shas(entry: Entry) -> Tuple[bool, List[str]]:
    """Returns (entry declares itself uncommitted, SHA tokens in order)."""
    for line in entry.body:
        if line.startswith("Commit:"):
            value = line[len("Commit:"):].strip()
            first = value.split()[0].rstrip(",;") if value.split() else ""
            if first.lower() == "uncommitted":
                return True, []
            return False, SHA_RE.findall(value)
    return False, []


def _check_commit(entry: Entry, known_shas: Optional[Set[str]]) -> Tuple[List[str], List[str]]:
    issues: List[str] = []
    warnings: List[str] = []
    uncommitted, shas = commit_shas(entry)
    if uncommitted:
        return issues, warnings
    if not shas:
        if any(line.startswith("Commit:") for line in entry.body):
            issues.append("`Commit:` has neither a SHA nor `uncommitted`")
        return issues, warnings
    if known_shas is None:
        return issues, warnings

    # First token hard, the rest soft. Later tokens come from free prose, and
    # a prose word can be valid hex ("facade", "deadbeef") — failing the build
    # over one would be a false positive nobody could act on. The first token
    # is the entry's own commit and must resolve.
    if shas[0] not in known_shas:
        issues.append(f"`Commit:` SHA {shas[0]} does not resolve to a commit")
    for token in shas[1:]:
        if token not in known_shas:
            warnings.append(
                f"referenced SHA {token} in `Commit:` does not resolve "
                f"(may be prose, not a commit)"
            )
    return issues, warnings


def _check_body_shape(entry: Entry) -> List[str]:
    issues: List[str] = []
    # A bare `---` in the body means the splitter left a separator behind, or
    # two entries got fused into one file. Markdown table rules (`|---|---|`)
    # are not bare and are unaffected.
    for line in entry.body:
        if line.strip() == "---":
            issues.append("body contains a bare `---` separator (leftover from the split?)")
            break
    if not entry.raw.endswith("\n"):
        issues.append("file does not end with a newline")
    elif entry.raw.endswith("\n\n"):
        issues.append("file ends with more than one trailing newline")
    return issues


def check_entry(entry: Entry, known_shas: Optional[Set[str]] = None) -> Tuple[List[str], List[str]]:
    """Pure apart from the already-read file contents. Returns
    (issues, warnings), each a list of human-readable strings."""
    schema = SCHEMAS[entry.kind]
    issues: List[str] = []
    warnings: List[str] = []

    if not FILENAME_RE.match(entry.path.name):
        issues.append("filename does not match YYYY-MM-DD-<lowercase-kebab-slug>.md")

    fm_issues, fm_warnings = _check_frontmatter(entry, schema)
    issues += fm_issues
    warnings += fm_warnings

    issues += _check_heading_and_dates(entry)
    issues += _check_fields(entry, schema)

    _, tag_issues = count_tags(entry, schema)
    issues += tag_issues

    if entry.kind == SESSION_LOG:
        commit_issues, commit_warnings = _check_commit(entry, known_shas)
        issues += commit_issues
        warnings += commit_warnings

    issues += _check_body_shape(entry)
    return issues, warnings


def load_entries(dir_path: Path, kind: str) -> List[Entry]:
    return [parse_entry(p, kind) for p in sorted(dir_path.glob("*.md"))]


def check_dir(
    dir_path: Path, kind: str, known_shas: Optional[Set[str]] = None
) -> Tuple[List[str], List[str]]:
    """Pure-ish core (reads the directory, makes no git calls). Returns
    (issues, warnings) prefixed with each entry's filename."""
    issues: List[str] = []
    warnings: List[str] = []
    entries = load_entries(dir_path, kind)

    # Case-only collisions are invisible on Windows, where this repo is
    # developed, and fatal on the ubuntu-latest runner it is tested on.
    seen: Dict[str, str] = {}
    for entry in entries:
        lowered = entry.path.name.lower()
        if lowered in seen:
            issues.append(
                f"{entry.path.name}: collides with {seen[lowered]} except for letter case"
            )
        seen[lowered] = entry.path.name

    for entry in entries:
        entry_issues, entry_warnings = check_entry(entry, known_shas)
        issues += [f"{entry.path.name}: {i}" for i in entry_issues]
        warnings += [f"{entry.path.name}: {w}" for w in entry_warnings]

    return issues, warnings


def is_shallow() -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def resolve_shas(shas: Sequence[str]) -> Set[str]:
    """One `git cat-file --batch-check` for every SHA in the run, rather than
    a subprocess per entry."""
    if not shas:
        return set()
    proc = subprocess.run(
        ["git", "cat-file", "--batch-check"],
        cwd=str(REPO_ROOT),
        input="\n".join(f"{s}^{{commit}}" for s in shas) + "\n",
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git cat-file failed: {proc.stderr.strip()}")
    # One output line per input line. A resolvable ref prints
    # "<full-oid> commit <size>"; anything else is "<input> missing" or
    # "<input> ambiguous".
    resolved = set()
    for sha, line in zip(shas, proc.stdout.splitlines()):
        parts = line.split()
        if len(parts) == 3 and parts[1] == "commit":
            resolved.add(sha)
    return resolved


def collect_shas(entries: Sequence[Entry]) -> List[str]:
    out: List[str] = []
    for entry in entries:
        _, shas = commit_shas(entry)
        out += shas
    return out


def group_entries(entries: Sequence[Entry], field: str) -> Dict[str, List[Entry]]:
    buckets: Dict[str, List[Entry]] = {}
    for entry in entries:
        buckets.setdefault(entry.frontmatter.get(field, "") or "", []).append(entry)
    for bucket in buckets.values():
        bucket.sort(key=lambda e: (e.frontmatter.get("date", ""), e.path.name))
    return buckets


def print_groups(buckets: Dict[str, List[Entry]], field: str) -> None:
    def sort_key(value: str) -> Tuple[int, str]:
        return (1, "") if value == "" else (0, value)

    for value in sorted(buckets, key=sort_key):
        label = "(unset)" if value == "" else value
        print(f"{field}: {label}")
        for entry in buckets[value]:
            print(f"  {entry.path.name}  {EM_DASH} {entry.heading_text[:70]}")


def exit_code(issues: Sequence[str]) -> int:
    """Split out so the blocking behavior is unit-testable. There is no
    ENFORCE toggle by design — see the module docstring."""
    return 1 if issues else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--kind", choices=[SESSION_LOG, TOOL_QUIRKS, "both"], default="both")
    ap.add_argument("--session-log-dir", default=str(DEFAULT_DIRS[SESSION_LOG]))
    ap.add_argument("--tool-quirks-dir", default=str(DEFAULT_DIRS[TOOL_QUIRKS]))
    ap.add_argument("--no-git", action="store_true", help="skip Commit: SHA resolution")
    ap.add_argument(
        "--group-by", metavar="FIELD",
        help="list entries bucketed by a frontmatter field instead of validating",
    )
    args = ap.parse_args()

    kinds = [SESSION_LOG, TOOL_QUIRKS] if args.kind == "both" else [args.kind]
    dirs = {SESSION_LOG: Path(args.session_log_dir), TOOL_QUIRKS: Path(args.tool_quirks_dir)}

    for kind in kinds:
        if not dirs[kind].is_dir():
            print(f"error: {dirs[kind]} is not a directory", file=sys.stderr)
            return 2

    entries: List[Entry] = []
    for kind in kinds:
        entries += load_entries(dirs[kind], kind)

    if args.group_by:
        valid = sorted({k for kind in kinds for k in SCHEMAS[kind]["frontmatter"]})
        if args.group_by not in valid:
            print(
                f"error: --group-by {args.group_by} is not a frontmatter field; "
                f"available: {', '.join(valid)}",
                file=sys.stderr,
            )
            return 2
        print_groups(group_entries(entries, args.group_by), args.group_by)
        # A query, not a gate: always 0, even when entries have real issues.
        return 0

    known_shas: Optional[Set[str]] = None
    shallow = False
    if not args.no_git:
        shallow = is_shallow()
        if not shallow:
            try:
                known_shas = resolve_shas(collect_shas(entries))
            except RuntimeError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2

    issues: List[str] = []
    warnings: List[str] = []
    counts = []
    for kind in kinds:
        kind_issues, kind_warnings = check_dir(dirs[kind], kind, known_shas)
        issues += kind_issues
        warnings += kind_warnings
        counts.append(f"{len(list(dirs[kind].glob('*.md')))} {kind}")

    if shallow:
        warnings.append("shallow clone detected — `Commit:` SHA resolution was skipped")

    if warnings:
        print(f"warnings ({len(warnings)}):", file=sys.stderr)
        for warning in warnings:
            print(f"  - {warning}", file=sys.stderr)

    if issues:
        print(f"check failed ({len(issues)} issue(s)):", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
    else:
        print(f"OK: {', '.join(counts)} entries valid.")

    return exit_code(issues)


if __name__ == "__main__":
    sys.exit(main())
