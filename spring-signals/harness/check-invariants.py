#!/usr/bin/env python3
"""
Static invariants for the spring-signals pack. Runs without a CodeQL CLI.

WHY THIS EXISTS
Successive drafts quoted a "framework references in Catalog.qll" figure, each a
different value, none reproducible. The figure was doing rhetorical work in an
architectural rationale while nobody could re-derive it. A fresh hand-count would
have been the same defect with a new value.

So the numbers are computed here, the patterns are pinned in code, and the docs
cite this script rather than hardcoding results.

THEN IT HAPPENED AGAIN. This docstring itself quoted the measured figures, and a
later edit to a *comment* in Catalog.qll moved the comment-inclusive count -- so
the prose went stale against the code it was documenting, in the very file
written to prevent that. Two lessons, both now enforced:

  - The comment-inclusive count is NOT an invariant. It moves whenever anyone
    edits prose. Only the code-only count means anything, and even that should
    be read from output rather than quoted.
  - "Cite the script, do not hardcode" is a rule, and an unenforced rule decays.
    Check 6 greps the docs and QL comments for count claims and fails on them.

CHECKS
  1  or-or      no empty disjuncts (comments AND string literals stripped)
  2  layering   zero framework literals in java-signals-lib code
  3  location   Catalog.qll is not in the library pack
  4  wiring     MetaAnnotationEdges has a contributor in the query pack's
                import closure -- STRUCTURAL ONLY, see caveat below
  5  counts     measured framework-reference figures, both patterns
  6  no-quotes  no document or QL comment hardcodes a count claim

Exit 0 if all pass, 1 otherwise.

Usage:
    python3 check-invariants.py [--root PATH]

The pack root is discovered by searching for `codeql/packs/java-signals-lib`,
so the script works from the harness directory, from the pack root, from an
overlay mirror sitting beside an extracted pack, or from anywhere with --root.

CAVEAT ON CHECK 4: this confirms the import and the subclass exist in source.
It cannot prove the contribution reaches `declaredMetaEdge` at evaluation time.
Only Probe.ql's `closed_state_restcontroller_is_controller > 0` proves that, and
it needs a database. A missing contribution produces NO compile error -- it
silently degrades `isOrMeta` to exact matching and reopens the @RestController
recall regression. Do not read a green check 4 as a closed gate.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKER = Path("codeql") / "packs" / "java-signals-lib"


def find_root(explicit: str | None = None) -> Path:
    """
    Locate the pack root by SEARCHING for it, not by relative arithmetic.

    The previous form was `Path(__file__).resolve().parent.parent`, which
    silently assumed the script sits at `<root>/harness/`. Review packaging
    mirrors this file to the top level of an overlay archive that has no
    `codeql/` sibling, so the mirror died with a bare FileNotFoundError from
    inside check 2 -- an error that says nothing about the actual problem.

    That is the third instance in this project of verification machinery failing
    for an environmental reason unrelated to what it verifies (Probe.ql could not
    resolve pack imports from `harness/`; run.sh aborted on a comment line before
    its first assertion). A checker that dies on its own setup reports nothing,
    and reporting nothing is indistinguishable from passing if the exit code is
    not read carefully.

    Resolution order: explicit --root, then upward from the script, then downward
    one level (the overlay-mirror case, where an extracted `spring-signals/` sits
    beside the script), then the current working directory.
    """
    if explicit:
        root = Path(explicit).resolve()
        if (root / MARKER).is_dir():
            return root
        sys.exit(f"--root {root} does not contain {MARKER}")

    here = Path(__file__).resolve()
    for cand in [here.parent, *here.parents]:
        if (cand / MARKER).is_dir():
            return cand
    # Downward search. Deterministic (sorted), but ambiguity is REPORTED rather
    # than silently resolved: two extracted packs side by side would otherwise
    # make a green run attributable to the alphabetically first one by accident.
    # Search a few levels deep to tolerate nested archives (e.g. extracted
    # overlay/v1/spring-signals/...).
    def _downward(start: Path, depth: int) -> list[Path]:
        if depth <= 0:
            return []
        found: list[Path] = []
        for cand in sorted(start.glob("*/")):
            if (cand / MARKER).is_dir():
                found.append(cand.resolve())
            else:
                found.extend(_downward(cand, depth - 1))
        return found

    found = sorted(
        set(_downward(here.parent, 4) + _downward(Path.cwd(), 4))
    )
    if len(found) > 1:
        print(
            "WARNING: multiple pack roots found; using the first. Pass --root to "
            "disambiguate.\n  " + "\n  ".join(str(f) for f in found),
            file=sys.stderr,
        )
    if found:
        return found[0]
    if (Path.cwd() / MARKER).is_dir():
        return Path.cwd()

    sys.exit(
        "Could not locate the pack root.\n"
        f"Looked for a directory containing {MARKER}, searching upward from\n"
        f"  {here}\n"
        "and one level down from there and from the current directory.\n\n"
        "If you extracted an overlay archive, the pack is inside the nested\n"
        "spring-signals.zip -- extract it first, or pass --root explicitly:\n"
        "  python3 check-invariants.py --root path/to/spring-signals"
    )


def _root_arg(argv: list[str]) -> str | None:
    for i, a in enumerate(argv):
        if a.startswith("--root="):
            val = a.split("=", 1)[1]
            if not val:
                sys.exit("--root= requires a value")
            return val
        if a == "--root":
            if i + 1 >= len(argv):
                sys.exit("--root requires a value: --root path/to/spring-signals")
            return argv[i + 1]
    return None


ROOT = find_root(_root_arg(sys.argv[1:]))
LIB = ROOT / "codeql" / "packs" / "java-signals-lib"
PACK = ROOT / "codeql" / "packs" / "spring-signals"

# PINNED PATTERNS. Changing either changes every published figure, so change
# them in the same commit that updates the docs, and say so in the message.
#
# NARROW reproduces the four packages used in review verification, kept so
# figures stay comparable across reviews.
NARROW = re.compile(r"org\.springframework|javax\.persistence|org\.hibernate|io\.swagger")
# BROAD is the invariant pattern: anything naming a framework namespace.
BROAD = re.compile(
    r"org\.springframework|javax\.|jakarta\.|org\.hibernate|io\.swagger"
    r"|com\.fasterxml|tools\.jackson|com\.vladmihalcea|redis\.clients|io\.micrometer"
)


def strip_comments(text: str) -> str:
    """Remove QL block and line comments, preserving line structure."""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def strip_strings(text: str) -> str:
    """Remove double-quoted QL string literals, honouring backslash escapes."""
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


def extract_comments(text: str) -> str:
    """Return all QL block and line comments, with strings stripped first."""
    text = strip_strings(text)
    parts = re.findall(r"//[^\n]*", text)
    parts += re.findall(r"/\*.*?\*/", text, flags=re.S)
    return "\n".join(parts)


def ql_files(base: Path):
    return sorted(p for p in base.rglob("*.q*") if p.suffix in {".ql", ".qll"})


def check_or_or() -> list[str]:
    """
    Flag malformed `or` separators.

    Two failure modes:
      - adjacent `or` tokens (empty disjunct)
      - dangling `or` immediately before a closing brace, parenthesis, bracket,
        or end of file (the branch was removed but its separator was not)

    Comments AND string literals must both go first. A raw `or\\s*//.*\\n\\s*or`
    regex false-positives on the ~20 legitimate `or` + explanatory-comment forms
    in this pack, and a comment-only strip still trips over `or` inside a regex
    literal. Tokenise, then inspect the token following every `or`.
    """
    bad = []
    terminators = {"}", ")", "]"}
    for f in ql_files(ROOT / "codeql"):
        # Strip strings BEFORE comments so a string containing "//" is not
        # mangled by the comment stripper. Tokenise numbers and punctuation so
        # tokens like "1 or 2 or y" are not collapsed into adjacent "or" tokens.
        text = strip_comments(strip_strings(f.read_text()))
        toks = re.findall(
            r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[(){}\[\]]|[^\sA-Za-z0-9_(){}\[\]]+", text
        )
        for i in range(1, len(toks)):
            if toks[i] == "or" and toks[i - 1] == "or":
                bad.append(f"{f.relative_to(ROOT)}: adjacent 'or' at token {i}")
        # dangling or before a closing delimiter or EOF
        for i in range(len(toks)):
            if toks[i] == "or" and (i + 1 == len(toks) or toks[i + 1] in terminators):
                bad.append(f"{f.relative_to(ROOT)}: dangling 'or' before '{toks[i + 1] if i + 1 < len(toks) else 'EOF'}'")
    return bad


def framework_hits(path: Path, pattern: re.Pattern, code_only: bool):
    text = strip_comments(path.read_text()) if code_only else path.read_text()
    occurrences = len(pattern.findall(text))
    lines = sum(1 for ln in text.splitlines() if pattern.search(ln))
    return occurrences, lines


# A count claim is a number adjacent -- in EITHER order -- to count vocabulary.
# Prose must cite the script instead; see the docstring for why an unenforced
# "cite, don't hardcode" rule decayed within two edits.
#
# THREAT MODEL: this defends against DECAY, not EVASION. The failure it exists to
# stop is someone copying a figure out of the output in good faith, or leaving one
# behind after an edit moves it. Both are accidents, and accidents follow a small
# number of natural phrasings, so a targeted pattern catches them.
#
# Someone determined to state a count in prose the check does not match will
# succeed. That is accepted, not overlooked. Chasing evasion-proofing turns a
# convention enforcer into a regex arms race whose failures are silent, and a
# reviewer who wants to hardcode a number after reading three comments explaining
# why not has made a decision no lint should be arbitrating.
#
# What is NOT accepted is a phrasing a careful writer would reach for by default.
# "framework references: 37" was one such gap -- keyword before number -- found in
# review. The alternation is symmetric now.
# What counts as a count claim: the figure this script owns (framework /
# namespace references and literals) plus the two ways the code-only /
# comment-inclusive split is usually phrased. It does not claim to police every
# prediction in the pack; those are intentionally labelled as falsifiable
# hypotheses in CAMPAIGN.md and belong to runtime verification, not a static
# lint. The threat-model comment below still applies.
_VOCAB = (
    r"code-only|comment-inclusive|framework (?:references|literals)|namespace literals"
)
COUNT_CLAIM = re.compile(
    rf"~?\d+\s*(?:{_VOCAB})"          # 37 code-only
    rf"|(?:{_VOCAB})[^.\n]{{0,20}}?~?\d+"  # framework references: 37
    r"|measurement says\s*~?\d+",
    re.I,
)


def check_no_count_claims() -> list[str]:
    """Fail if any doc or QL comment hardcodes a framework-/namespace-reference count."""
    targets = [
        *(ROOT / "docs").glob("*.md"),
        ROOT / "README.md",
        *ql_files(ROOT / "codeql"),
    ]
    offenders = []
    for f in targets:
        if not f.exists():
            continue
        text = f.read_text()
        # QL: only comments are prose (including trailing comments after code).
        # Markdown: all of it is.
        prose = text if f.suffix == ".md" else extract_comments(text)
        for m in COUNT_CLAIM.finditer(prose):
            line = prose[: m.start()].count("\n") + 1
            offenders.append(
                f"{f.relative_to(ROOT)}: count claim {m.group(0)!r} (prose line ~{line})"
            )
    return offenders


def main() -> int:
    failures: list[str] = []
    print(f"pack root: {ROOT}\n")

    print("1. or-or (empty disjuncts)")
    bad = check_or_or()
    if bad:
        failures += bad
        for b in bad:
            print("   FAIL", b)
    else:
        print("   PASS  0 adjacent 'or' tokens across all .ql/.qll")

    print("2. layering: framework literals in java-signals-lib code")
    total = 0
    for f in ql_files(LIB):
        occ, _ = framework_hits(f, BROAD, code_only=True)
        total += occ
        if occ:
            failures.append(f"{f.relative_to(ROOT)}: {occ} framework literals")
            print(f"   FAIL  {f.name}: {occ}")
    if not total:
        print("   PASS  0 (broad pattern, comments excluded)")

    print("3. location: Catalog.qll not in the library pack")
    if (LIB / "signals" / "Catalog.qll").exists():
        failures.append("Catalog.qll is in java-signals-lib")
        print("   FAIL  Catalog.qll found under java-signals-lib")
    else:
        print("   PASS  Catalog.qll lives in spring-signals")

    print("4. wiring (STRUCTURAL ONLY -- not a proof, see module docstring)")
    common = strip_comments((PACK / "Common.qll").read_text())
    edges = strip_comments((PACK / "SpringMetaEdges.qll").read_text())
    probe = strip_comments((PACK / "Probe.ql").read_text())
    for label, ok in [
        ("Common imports SpringMetaEdges", "import SpringMetaEdges" in common),
        ("SpringMetaEdges extends MetaAnnotationEdges", "extends MetaAnnotationEdges" in edges),
        ("edge RestController -> Controller present", '"RestController"' in edges),
        ("Probe defines closed-state gate", "closed_state_restcontroller_is_controller" in probe),
    ]:
        print(f"   {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            failures.append(label)
    print("   NOTE  runtime proof is Probe.ql on a real database; still unrun")

    print("5. measured framework references (pinned patterns)")
    print(f"   {'file':<26} {'narrow occ/line':>16} {'broad occ/line':>16}  (comments excluded)")
    for f in [PACK / "Catalog.qll", PACK / "SpringMetaEdges.qll"]:
        n_occ, n_ln = framework_hits(f, NARROW, code_only=True)
        b_occ, b_ln = framework_hits(f, BROAD, code_only=True)
        print(f"   {f.name:<26} {f'{n_occ}/{n_ln}':>16} {f'{b_occ}/{b_ln}':>16}")
    for f in [PACK / "Catalog.qll"]:
        n_occ, n_ln = framework_hits(f, NARROW, code_only=False)
        print(f"   {f.name + ' (with comments)':<26} {f'{n_occ}/{n_ln}':>16}  <- DIAGNOSTIC ONLY")
    print("   The comment-inclusive figure is not an invariant: it moves whenever")
    print("   anyone edits a comment. Do not quote it. Do not quote any of these.")

    print("6. no hardcoded framework-/namespace-reference count claims")
    offenders = check_no_count_claims()
    if offenders:
        failures += offenders
        for o in offenders:
            print("   FAIL", o)
    else:
        print("   PASS  no doc or QL comment quotes a framework-/namespace-reference count")

    print()
    if failures:
        print(f"FAILED: {len(failures)} invariant violation(s)")
        return 1
    print("All static invariants hold. Wave 0 items 2-4 remain blocked on CodeQL CLI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
