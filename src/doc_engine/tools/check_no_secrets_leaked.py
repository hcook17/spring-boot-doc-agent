#!/usr/bin/env python3
"""

Run with: python -m doc_engine.tools.check_no_secrets_leaked

check_no_secrets_leaked.py — deterministic defense-in-depth check for
CONSTRAINTS.md's "Secret/credential leakage" gap.

WHY THIS EXISTS ON TOP OF THE agents/*.md INSTRUCTION
spring_signal_scan.py now flags `redaction_zones` (line + heuristic, never
the value) for configuration/deployment files, and agents/file-summarizer.md
+ doc-writer.md are instructed not to transcribe a flagged line's literal
value. But an instruction to an LLM subagent is not a guarantee — this
project's own standing posture (spring_drift_check.py, verify_llms_docs.py,
test_pipeline_stages.py's citation-resolution check) is to mechanically
re-verify a claim rather than trust that a prompt was followed. This script
is that same "trust but verify" pattern applied to confidentiality instead
of correctness: it re-applies the exact same heuristics from
_secret_heuristics.py to a completed pipeline run's own OUTPUT (Stage 1's
summaries.json and/or the final docs/*.md files) and fails loudly if a
credential-shaped value made it through anyway.

WHAT IT DOES NOT DO
Same heuristic-only scope as _secret_heuristics.py itself: this catches
values shaped like the patterns that module knows about, not every
possible secret. A clean run here is evidence the known leak vectors
didn't fire, not a guarantee nothing sensitive is present. Not wired into
CI (unlike verify_llms_docs.py) because CI has no target-repo pipeline
output to check against — this repo's CI runs this repo's own test
suites, not a document-spring-repo run against a real Spring Boot repo.
Documented in SKILL.md as an optional post-run check instead, the same
posture spring_drift_check.py itself already has there.

Run with:
    python -m doc_engine.tools.check_no_secrets_leaked <path-to-summaries.json-or-docs-dir> [more paths...]
"""

import argparse
import os
import sys

from doc_engine.scanning.support._secret_heuristics import scan_text_for_secrets  # noqa: E402

CHECKED_EXTENSIONS = {".json", ".md"}


def _checked_names(names):
    return [
        name for name in names if os.path.splitext(name)[1] in CHECKED_EXTENSIONS
    ]


def _files_under_dir(directory: str):
    for root, _, names in os.walk(directory):
        for name in _checked_names(names):
            yield os.path.join(root, name)


def _iter_one_path(path: str):
    if os.path.isdir(path):
        yield from _files_under_dir(path)
        return
    if os.path.isfile(path):
        yield path
        return
    print(f"warning: not a file or directory, skipping: {path}", file=sys.stderr)


def iter_files(paths):
    for path in paths:
        yield from _iter_one_path(path)


def check(paths):
    """Returns a {file: [{"line", "heuristic"}, ...]} map of hits, empty if
    nothing flagged. Never returns the matched value, same as
    _secret_heuristics.scan_text_for_secrets itself.
    """
    findings = {}
    for path in iter_files(paths):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError as e:
            print(f"warning: could not read '{path}': {e}", file=sys.stderr)
            continue
        hits = scan_text_for_secrets(text)
        if hits:
            findings[path] = hits
    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="files and/or directories to scan (e.g. summaries.json, docs/)")
    args = ap.parse_args()

    findings = check(args.paths)
    if not findings:
        print("No credential-shaped values found in the checked output.")
        return 0

    for path, hits in sorted(findings.items()):
        for hit in hits:
            print(f"{path}:{hit['line']}: flagged by heuristic '{hit['heuristic']}'", file=sys.stderr)
    total = sum(len(hits) for hits in findings.values())
    print(
        f"\n{total} credential-shaped value(s) found across {len(findings)} file(s) in "
        "generated output. Review and redact before sharing this output.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
