#!/usr/bin/env python3
"""Read the agent prompts' output contracts back out of the prompts themselves.

Usage:
    python3 scripts/ci/prompt_contracts.py          # print every parsed contract

WHY THIS EXISTS

`test_pipeline_stages.py` validates Stage-1/2/3 output against contracts that
are stated in `agents/*.md` -- the `spring_role` enumeration, the per-file JSON
keys, the fourteen documentation filenames. It enforced those by holding a
hand-copied duplicate of each one, with nothing asserting the copy still
matched the prompt. Editing a prompt therefore left the validators silently
enforcing the previous contract, and the suite would stay green while checking
something the pipeline no longer produces.

That is the same two-sources-of-truth failure this repo has already hit and
written up more than once: `test_pipeline_stages.py:36-38` warns about it for
fixtures, `VALID_DOC_FILES` was moved into `doc_tag_utils.py` to avoid it
(`:58-63`), and `drift_match_normalizers.py:21` re-derives its comparison
table for the same reason -- "a table in a comment goes stale silently".

This module closes it for the prompts. The prompt is the source of truth; the
constants become assertions about it rather than second originals.

DELIBERATELY STRICT

Every parser raises `ContractParseError` unless it finds exactly what it
expects. A lenient parser that returned an empty set on a reformatted prompt
would turn the equality tests into a comparison of two empty sets somewhere
down the line, which is precisely the vacuous pass they exist to prevent.
Failing loudly on a reformat is the cheaper error: it costs one regex edit,
and it cannot be mistaken for agreement.

This reads prompts; it never writes them, and nothing here executes anything a
prompt says. The prompts are data.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import FrozenSet

from doc_engine.paths import repo_root

_root = repo_root()
AGENTS_DIR = _root / "adapters" / "claude" / "agents"
if not AGENTS_DIR.is_dir():
    AGENTS_DIR = _root / "agents"

# "**Spring role** -- one of: controller, service, ... -- pulled from ..."
# Anchored on the bolded label so a prose mention elsewhere cannot match, and
# stopping at the em dash that ends the list.
_SPRING_ROLE_RE = re.compile(
    r"\*\*Spring role\*\*\s*[—-]\s*one of:\s*(?P<roles>[^—\n]+?)\s*[—-]\s")

# The top-level keys of the single JSON example block in file-summarizer.md.
_JSON_BLOCK_RE = re.compile(r"```json\s*(?P<body>.*?)```", re.DOTALL)
_TOP_LEVEL_KEY_RE = re.compile(r'^\s{6}"(?P<key>\w+)"\s*:', re.MULTILINE)

# doc-writer.md's frontmatter description enumerates the fourteen files.
_DOC_FILES_RE = re.compile(
    r"fourteen-file documentation set\s*\((?P<files>[^)]+)\)")


class ContractParseError(RuntimeError):
    """A prompt no longer states its contract in the shape this module reads.

    Raised rather than returning a partial answer: a contract this module
    cannot find is not a contract that changed, it is one nobody is checking.
    """


def _read(name: str) -> str:
    path = AGENTS_DIR / name
    if not path.is_file():
        raise ContractParseError(f"{name} is missing from {AGENTS_DIR}")
    return path.read_text(encoding="utf-8")


def _split_list(text: str) -> FrozenSet[str]:
    """Split a prose list like `a, b, or c` into its members."""
    parts = [p.strip().strip("`") for p in text.replace(" or ", ", ").split(",")]
    return frozenset(p for p in parts if p)


def spring_roles() -> FrozenSet[str]:
    """The `spring_role` enumeration, from agents/file-summarizer.md step 4."""
    match = _SPRING_ROLE_RE.search(_read("file-summarizer.md"))
    if not match:
        raise ContractParseError(
            "file-summarizer.md no longer states '**Spring role** — one of: ...'; "
            "the enumeration test cannot check anything until this parser is "
            "updated to match the new wording")
    roles = _split_list(match.group("roles"))
    if len(roles) < 2:
        raise ContractParseError(f"parsed an implausible spring_role list: {sorted(roles)}")
    return roles


def file_summary_keys() -> FrozenSet[str]:
    """Top-level keys of the per-file object in file-summarizer.md's example."""
    text = _read("file-summarizer.md")
    blocks = _JSON_BLOCK_RE.findall(text)
    if len(blocks) != 1:
        raise ContractParseError(
            f"expected exactly one ```json block in file-summarizer.md, found "
            f"{len(blocks)}; this parser keys off there being one canonical example")
    keys = frozenset(_TOP_LEVEL_KEY_RE.findall(blocks[0]))
    if not keys:
        raise ContractParseError(
            "the ```json block in file-summarizer.md yielded no top-level keys; "
            "its indentation probably changed (this parser matches six spaces)")
    return keys


def doc_files() -> FrozenSet[str]:
    """The fourteen documentation filenames, from doc-writer.md's description."""
    match = _DOC_FILES_RE.search(_read("doc-writer.md"))
    if not match:
        raise ContractParseError(
            "doc-writer.md's description no longer enumerates the fourteen-file set")
    return _split_list(match.group("files"))


CONTRACTS = {
    "spring_roles": spring_roles,
    "file_summary_keys": file_summary_keys,
    "doc_files": doc_files,
}


def main(argv=None) -> int:
    for name, parser in CONTRACTS.items():
        try:
            values = sorted(parser())
        except ContractParseError as exc:
            print(f"{name}: UNPARSEABLE — {exc}", file=sys.stderr)
            return 1
        print(f"{name} ({len(values)}): {', '.join(values)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
