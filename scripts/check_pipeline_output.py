#!/usr/bin/env python3
"""
check_pipeline_output.py — gate a completed document-spring-repo run's own
output, mechanically, before anyone reads it.

WHY THIS EXISTS
Three of Stage 4's guarantees were carried only by instructions in
agents/doc-writer.md — that is, by asking an LLM nicely:

  1. "write to exactly the path given and nowhere else"  (fourteen writers
     run concurrently against one docs/ directory; a duplicated or wrong
     path silently destroys a sibling's file)
  2. every claim carries a well-formed evidence tag
  3. an [Evidenced — path:line] citation points at something real

A prompt instruction is the weakest available control, and this repo has
already learned that twice: claude/llms/README.md's authoring rules did not
prevent the failure they described, and CONSTRAINTS.md item 4 records a
convention that silently stopped holding. The same reasoning that deleted
verify_llms_docs.py rather than hardening it applies here — so these three
become checks that run, rather than sentences a subagent may or may not
have honored.

Check 1 is the one that needs the target repo: a clean checkout before the
run means `git status --porcelain` afterwards is an exact record of what
the fan-out actually wrote. A writer that wandered outside docs/ shows up
as a path this script does not expect, with no cooperation from the agent
required.

WHAT THIS DOES NOT DO
It does not judge whether the documentation is any good, or whether a
resolvable citation actually *supports* the sentence it is attached to.
That is skills/semantic-pipeline-eval/'s job, and it needs a model. This
script is the mechanical half: shape, completeness, and whether the things
being pointed at exist. Same boundary test_pipeline_stages.py already draws
around itself.

Not CI-wired, for the same reason check_no_secrets_leaked.py isn't: this
repo's CI has no target-repo pipeline run to check the output of. Run it by
hand after a real run, or from the pipeline's own Output stage.

Run with:
    python3 scripts/check_pipeline_output.py <docs_dir> --target-repo <repo>
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from doc_tag_utils import (  # noqa: E402
    VALID_DOC_FILES, find_malformed_tags, count_tags_by_kind,
    resolve_evidenced_citations,
)


def check_file_set(docs_dir: Path) -> List[str]:
    """Exactly the fourteen taxonomy files, no more and no fewer.

    Counting to fourteen is not enough: two writers given the same
    output_path produce fourteen names with one duplicated and one missing,
    which a count check passes and this one does not."""
    issues = []
    present = {p.stem for p in docs_dir.glob("*.md")}
    missing = sorted(VALID_DOC_FILES - present)
    extra = sorted(present - VALID_DOC_FILES)
    for name in missing:
        issues.append(f"missing expected doc: {name}.md")
    for name in extra:
        issues.append(f"unexpected file in docs dir: {name}.md (not one of the fourteen)")
    return issues


def check_tags_and_citations(docs_dir: Path, target_repo: Optional[Path]) -> List[str]:
    """Malformed tags anywhere, plus citation resolution when a target repo
    is available to resolve against."""
    issues = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for bad in find_malformed_tags(text):
            issues.append(f"{path.name}: malformed evidence tag {bad!r}")
        if target_repo is not None:
            for citation, reason in resolve_evidenced_citations(text, str(target_repo)):
                issues.append(f"{path.name}: unresolvable citation {citation!r} — {reason}")
    return issues


def parse_porcelain(output: str) -> List[str]:
    """Paths from `git status --porcelain`, handling renames (`R  old -> new`)
    and quoted paths with spaces."""
    paths = []
    for line in output.splitlines():
        if not line.strip():
            continue
        entry = line[3:] if len(line) > 3 else ""
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        paths.append(entry.strip().strip('"'))
    return paths


def check_target_repo_writes(target_repo: Path, docs_dir: Path) -> List[str]:
    """The structural replacement for "write only where you were told."

    The target repo is expected clean before a run, so anything git reports
    afterwards is exactly what the fan-out wrote. Only paths under the docs
    directory are expected; anything else is a writer that went somewhere it
    should not have."""
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(target_repo), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return [f"target repo is not a git checkout, cannot verify write scope: {proc.stderr.strip()}"]

    try:
        docs_rel = docs_dir.resolve().relative_to(target_repo.resolve()).as_posix()
    except ValueError:
        docs_rel = None  # docs written outside the repo; then NOTHING in it should have changed

    issues = []
    for path in parse_porcelain(proc.stdout):
        norm = path.replace("\\", "/").rstrip("/")
        if docs_rel is not None and (norm == docs_rel or norm.startswith(docs_rel + "/")):
            continue
        where = "outside the docs directory" if docs_rel else "in the target repo (docs were written elsewhere)"
        issues.append(f"unexpected write {where}: {path}")
    return issues


def summarize_tags(docs_dir: Path) -> dict:
    totals = {}
    for path in sorted(docs_dir.glob("*.md")):
        for kind, n in count_tags_by_kind(path.read_text(encoding="utf-8")).items():
            totals[kind] = totals.get(kind, 0) + n
    return totals


def check_all(docs_dir: Path, target_repo: Optional[Path], check_writes: bool) -> List[str]:
    """Pure-ish core (reads the two directories, one git call). Returns a
    list of human-readable issue strings; empty means clean."""
    issues = check_file_set(docs_dir)
    issues += check_tags_and_citations(docs_dir, target_repo)
    if target_repo is not None and check_writes:
        issues += check_target_repo_writes(target_repo, docs_dir)
    return issues


def exit_code(issues: List[str]) -> int:
    """Split out so the blocking behavior is unit-testable. No ENFORCE
    toggle — this is local and deterministic, so it has none of the reasons
    check_llms_coverage.py has one."""
    return 1 if issues else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("docs_dir", help="the run's docs/ output directory")
    ap.add_argument("--target-repo", help="repo the docs describe; needed to resolve citations "
                                          "and to verify nothing was written outside docs/")
    ap.add_argument("--no-write-check", action="store_true",
                    help="skip the git write-scope check (use when the target repo was already dirty)")
    args = ap.parse_args()

    docs_dir = Path(args.docs_dir)
    if not docs_dir.is_dir():
        print(f"error: {docs_dir} is not a directory", file=sys.stderr)
        return 2

    target_repo = Path(args.target_repo) if args.target_repo else None
    if target_repo is not None and not target_repo.is_dir():
        print(f"error: {target_repo} is not a directory", file=sys.stderr)
        return 2
    if target_repo is None:
        print("note: --target-repo not given; citations and write scope are NOT checked",
              file=sys.stderr)

    issues = check_all(docs_dir, target_repo, check_writes=not args.no_write_check)

    if issues:
        print(f"pipeline output check failed ({len(issues)} issue(s)):", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
    else:
        tags = summarize_tags(docs_dir)
        shown = ", ".join(f"{k}={v}" for k, v in sorted(tags.items())) or "no tags found"
        print(f"OK: all 14 docs present, tags well-formed, citations resolve. Tag totals: {shown}")

    return exit_code(issues)


if __name__ == "__main__":
    sys.exit(main())
