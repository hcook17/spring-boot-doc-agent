#!/usr/bin/env python3
"""
partition_repo.py — adaptive, token-bounded, DFS-ordered file grouping with overlap.

Implements the grouping scheme described in Pan, Mao, Ma & Ling,
"ArchAgent: Scalable Legacy Software Architecture Recovery with LLMs"
(arXiv:2601.13007), Section 3 ("Adaptive Grouping"):

    1. Calculate total token count T of the repository.
    2. Define a maximum token threshold M (bounded by the target model's
       context window).
    3. Partition into G = ceil(T / M) groups.
    4. Traverse the file tree via DFS, maintaining ~10% overlap between
       adjacent groups so the merge stage has shared context to stitch on.

Token counts here are estimated with a cheap heuristic (chars / N) rather
than a real tokenizer, since this only needs to be "close enough" to size
groups sensibly — it is not used for anything that requires exact counts.
No third-party dependencies, so it runs anywhere Python 3 does.

N depends on content density rather than being a flat 4 for everything —
see CHARS_PER_TOKEN_DEFAULT / CHARS_PER_TOKEN_DENSE below for what that's
based on and why. G itself is also only a planning estimate, not a hard
cap: build_groups() will emit more than G groups if the actual content
needs it rather than let a group silently exceed max_tokens (see the
is_last_group_being_filled comment there).

Two bugs in build_groups() were found and fixed by validating this script
against a real repository's actual file tree rather than only synthetic
scenarios (a small, uniform hand-built file list doesn't expose either
one — both need genuinely lopsided real-world file sizes to surface):
the final group had no size ceiling at all (is_last_group_being_filled
used to suppress it unconditionally), and separately, the overlap-carry
step could duplicate a single oversized file into several consecutive
groups instead of carrying a small trailing slice (see the long comment
above the `carried + tok2 >= max_tokens` check inside build_groups()).
Both have permanent regression tests in test_partition_repo.py
(test_final_group_no_longer_unbounded, test_overlap_skips_oversized_
trailing_file) using small synthetic repros, plus an opt-in real-world
validation pass in test_partition_repo_real_world.py that is what
actually surfaced the second bug in the first place.

Usage:
    python3 partition_repo.py <repo_path> [--max-tokens 120000] [--overlap 0.10]
                               [--out groups.json] [--exclude-dir NAME ...]
                               [--max-file-bytes 2000000]
"""

import argparse
import json
import math
import os
import sys

DEFAULT_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "target",
    "venv", ".venv", "env", "__pycache__", ".next", ".nuxt", ".gradle",
    ".idea", ".vscode", "vendor", "coverage", ".pytest_cache", ".mypy_cache",
    "out", "bin", "obj",
}

DEFAULT_EXCLUDED_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar", ".jar", ".war", ".class",
    ".so", ".dll", ".dylib", ".exe", ".bin", ".woff", ".woff2", ".ttf",
    ".eot", ".mp3", ".mp4", ".mov", ".avi", ".lock",
}

DEFAULT_EXCLUDED_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Gemfile.lock",
    "poetry.lock", "Cargo.lock", "composer.lock",
}

# Chars-per-token divisors, calibrated against a real BPE tokenizer
# (tiktoken's cl100k_base — used only offline to pick these constants, not
# a runtime dependency of this script) run against real and synthetic Java,
# Python, YAML, JSON, and .properties files.
#
# What that measurement actually found, char-weighted:
#   Java (6 real production files):        ~5.0 chars/token
#   Python:                                 ~4.1-4.5 chars/token
#   YAML (7 files, real configs):           ~2.4 chars/token
#   JSON (3 files):                         ~3.6 chars/token
#   YAML+JSON+.properties combined:         ~2.9 chars/token
#
# That does NOT support "code under-counts relative to prose" as a general
# rule — Java/Python came out at or above 4 chars/token, meaning the old
# flat chars/4 already over-estimates their token cost, which is the safe
# direction for a budget this heuristic exists to protect. The real,
# measured gap is specifically in dense structured-data formats
# (YAML/JSON/properties): chars/4 under-counts those by roughly a third,
# which is the risky direction — it makes a config-heavy group look
# cheaper than it actually is. This divisor split targets that specific,
# measured gap rather than a blanket code-vs-prose adjustment.
#
# Caveat worth keeping in mind if you revisit this: cl100k_base is a proxy
# for "a real modern BPE tokenizer's behavior," not Claude's own tokenizer
# — there's no offline Claude tokenizer available to calibrate against
# directly. The relative ordering (structured data denser than code or
# prose) is a robust, general property of BPE tokenization and not
# specific to one vocabulary, but the exact divisor values are an
# approximation, not a guarantee.
CHARS_PER_TOKEN_DEFAULT = 4
CHARS_PER_TOKEN_DENSE = 3
DENSE_EXTS = {".yml", ".yaml", ".json", ".properties", ".xml", ".toml"}


def estimate_tokens(path, max_file_bytes):
    """Cheap token estimate: chars / N, where N is CHARS_PER_TOKEN_DENSE for
    structured-data extensions (DENSE_EXTS) and CHARS_PER_TOKEN_DEFAULT
    otherwise. Skips files that look binary or are too large; returns
    (tokens, skipped_reason_or_None)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return 0, "stat-failed"
    if size > max_file_bytes:
        return 0, f"too-large ({size} bytes)"
    try:
        with open(path, "rb") as f:
            chunk = f.read(size)
    except OSError:
        return 0, "read-failed"
    if b"\x00" in chunk[:8000]:
        return 0, "binary"
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = chunk.decode("latin-1")
        except Exception:
            return 0, "undecodable"
    _, ext = os.path.splitext(path)
    divisor = CHARS_PER_TOKEN_DENSE if ext.lower() in DENSE_EXTS else CHARS_PER_TOKEN_DEFAULT
    return max(1, len(text) // divisor), None


def dfs_file_list(repo_path, excluded_dirs, excluded_exts, excluded_files):
    """Depth-first, deterministically-ordered walk of the repo, yielding
    relative file paths. Directories and files are sorted at each level so
    the ordering is stable across runs (important since overlap depends on
    a consistent DFS order)."""
    files = []

    def _walk(dir_path):
        try:
            entries = sorted(os.listdir(dir_path))
        except OSError:
            return
        dirs, regular = [], []
        for name in entries:
            full = os.path.join(dir_path, name)
            if os.path.isdir(full):
                if name not in excluded_dirs and not name.startswith("."):
                    dirs.append(full)
            else:
                regular.append((name, full))
        for name, full in regular:
            if name in excluded_files:
                continue
            _, ext = os.path.splitext(name)
            if ext.lower() in excluded_exts:
                continue
            files.append(full)
        for d in dirs:
            _walk(d)

    _walk(repo_path)
    return files


def build_groups(file_tokens, max_tokens, overlap_ratio):
    """file_tokens: list of (relpath, tokens) in DFS order.
    Returns list of groups: each a list of (relpath, tokens)."""
    total_tokens = sum(t for _, t in file_tokens)
    if total_tokens == 0 or not file_tokens:
        return []

    num_groups = max(1, math.ceil(total_tokens / max_tokens))
    target_per_group = total_tokens / num_groups

    groups = []
    current = []
    current_tokens = 0
    i = 0
    n = len(file_tokens)

    while i < n:
        relpath, tok = file_tokens[i]
        current.append((relpath, tok))
        current_tokens += tok
        i += 1

        is_last_group_being_filled = len(groups) == num_groups - 1
        # target_per_group is a *planning* number (total / num_groups) used
        # to spread files evenly across the groups we expect to need. The
        # last group skips that even-distribution target on purpose, so a
        # small remainder doesn't spin up its own near-empty straggler
        # group — but it must still respect max_tokens, the actual
        # context-window constraint this whole scheme exists to protect.
        # Every group, last or not, closes the instant it hits that hard
        # ceiling; only the softer target_per_group threshold is skipped
        # for the presumed-last one. Since num_groups was computed from a
        # heuristic token *estimate*, real content can legitimately need
        # more groups than planned (e.g. DFS order happens to put a large
        # cluster of files at the tail) — this lets that happen rather than
        # silently producing one oversized final group, which is what the
        # unconditional "never close the last group" version used to do.
        hit_hard_cap = current_tokens >= max_tokens
        hit_soft_target = current_tokens >= target_per_group and not is_last_group_being_filled
        if hit_hard_cap or hit_soft_target:
            groups.append(current)
            # Build ~overlap_ratio worth of trailing tokens from this group
            # to seed the front of the next one, per the paper's DFS +
            # 10%-overlap scheme.
            #
            # The `carried + tok2 >= max_tokens` guard below exists because
            # of a real bug found by validating against a real repo's file
            # tree (see test_overlap_skips_oversized_trailing_file in
            # test_partition_repo.py and the module docstring's "overlap
            # carry" note): the loop below walks BACKWARD through the
            # group that just closed, and its stopping condition
            # (`carried >= overlap_budget`) is checked using the value of
            # `carried` from BEFORE the candidate item is added. If the
            # small items scanned so far still leave `carried` under
            # budget, the loop takes one more step back and includes
            # whatever's there next — even if that's a single file far
            # bigger than the entire next group's budget. When that
            # happens, the "carry" isn't a sliver of trailing context
            # anymore, it's a wholesale duplicate of a huge file, and the
            # new group it seeds is stillborn: current_tokens already
            # meets max_tokens before a single new file is considered, so
            # hit_hard_cap fires on the very next iteration and the same
            # huge file (now still the most-recent item in that
            # freshly-closed group) gets walked back into the carry again.
            # Left unguarded, this can repeat for several groups in a row
            # — observed in practice as one large file (plus whichever
            # small files happened to ride along beside it) appearing in
            # 3-4 separate groups' file lists. The fix: never let a
            # candidate join the carry if doing so would already fill (or
            # exceed) max_tokens by itself — better to under-carry at that
            # seam, or even carry nothing, than to chain-duplicate a huge
            # file across a run of groups.
            overlap_budget = current_tokens * overlap_ratio
            carry = []
            carried = 0
            for relpath2, tok2 in reversed(current):
                if carried >= overlap_budget:
                    break
                if carried + tok2 >= max_tokens:
                    break
                carry.append((relpath2, tok2))
                carried += tok2
            carry.reverse()
            current = list(carry)
            current_tokens = carried
    if current:
        groups.append(current)

    return groups


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_path", help="Path to the repository root")
    ap.add_argument("--max-tokens", type=int, default=120000,
                    help="Target max tokens per group (default: 120000; leave headroom under the model's context window)")
    ap.add_argument("--overlap", type=float, default=0.10,
                    help="Fraction of a group's trailing tokens carried into the next group (default: 0.10)")
    ap.add_argument("--out", default="groups.json", help="Output JSON path (default: groups.json)")
    ap.add_argument("--exclude-dir", action="append", default=[],
                    help="Additional directory name to exclude (repeatable)")
    ap.add_argument("--max-file-bytes", type=int, default=2_000_000,
                    help="Skip files larger than this many bytes (default: 2,000,000)")
    args = ap.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"error: not a directory: {repo_path}", file=sys.stderr)
        sys.exit(1)

    excluded_dirs = DEFAULT_EXCLUDED_DIRS | set(args.exclude_dir)

    all_files = dfs_file_list(repo_path, excluded_dirs, DEFAULT_EXCLUDED_EXTS, DEFAULT_EXCLUDED_FILES)

    file_tokens = []
    skipped = []
    for full in all_files:
        rel = os.path.relpath(full, repo_path)
        tokens, reason = estimate_tokens(full, args.max_file_bytes)
        if reason:
            skipped.append({"file": rel, "reason": reason})
            continue
        file_tokens.append((rel, tokens))

    groups_raw = build_groups(file_tokens, args.max_tokens, args.overlap)

    output = {
        "repo_path": repo_path,
        "max_tokens_per_group": args.max_tokens,
        "overlap": args.overlap,
        "total_files_considered": len(file_tokens),
        "total_files_skipped": len(skipped),
        "skipped": skipped,
        "num_groups": len(groups_raw),
        "groups": [
            {
                "id": idx,
                "files": [f for f, _ in g],
                "est_tokens": sum(t for _, t in g),
            }
            for idx, g in enumerate(groups_raw)
        ],
    }

    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {args.out}: {output['num_groups']} groups, "
          f"{output['total_files_considered']} files considered, "
          f"{output['total_files_skipped']} skipped.")


if __name__ == "__main__":
    main()