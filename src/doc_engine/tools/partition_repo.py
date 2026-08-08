#!/usr/bin/env python3
"""

Run with: python -m doc_engine.tools.partition_repo

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
No third-party dependencies for default behavior, so it runs anywhere
Python 3 does. The optional --respect-gitignore flag is the one exception:
it needs the `pathspec` library installed, and degrades to a no-op (with
default exclude behavior unchanged) if that library isn't available.

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
    python -m doc_engine.tools.partition_repo <repo_path> [--max-tokens 120000] [--overlap 0.10]
                               [--out groups.json] [--exclude-dir NAME ...]
                               [--max-file-bytes 2000000]
"""

import argparse
import json
import math
import os
import sys

from doc_engine.core.excludes import DEFAULT_EXCLUDED_DIRS, load_gitignore_spec

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


def _decode_file_bytes(chunk: bytes):
    """Return (text, skip_reason). skip_reason is set when undecodable."""
    if b"\x00" in chunk[:8000]:
        return None, "binary"
    try:
        return chunk.decode("utf-8"), None
    except UnicodeDecodeError:
        try:
            return chunk.decode("latin-1"), None
        except Exception:
            return None, "undecodable"


def _read_file_bytes(path: str, size: int):
    try:
        with open(path, "rb") as handle:
            return handle.read(size), None
    except OSError:
        return None, "read-failed"


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
    chunk, read_error = _read_file_bytes(path, size)
    if read_error:
        return 0, read_error
    text, decode_error = _decode_file_bytes(chunk)
    if decode_error:
        return 0, decode_error
    _, extension = os.path.splitext(path)
    divisor = (
        CHARS_PER_TOKEN_DENSE
        if extension.lower() in DENSE_EXTS
        else CHARS_PER_TOKEN_DEFAULT
    )
    return max(1, len(text) // divisor), None


def to_posix(path: str) -> str:
    """Backslashes to forward slashes. Trivial, and deliberately its own
    named function rather than an inline .replace() repeated at each site.

    Every artifact this pipeline writes keys on relative paths, and separate
    scripts' outputs are then joined by those paths -- groups.json against
    spring_signals.json, spring_signals.json against a doc's [Evidenced —
    path:line] citation. A backslash on one side of that join and a forward
    slash on the other matches nothing and raises no error; the consumer just
    receives an empty slice. That failure has now been found and fixed three
    separate times (spring_drift_check.py's tier1_scan(), partition_repo's own
    main(), and capacity_preflight.py's compute_preflight() on 2026-07-25),
    which is the signal that the fix belonged in one named place rather than
    in a comment telling the next author to remember."""
    return path.replace("\\", "/")


def relpath_posix(full: str, root: str) -> str:
    """os.path.relpath, normalized. The pairing above is the whole point:
    os.path.relpath is the thing that introduces the platform separator, so
    the normalization belongs immediately next to it."""
    return to_posix(os.path.relpath(full, root))


def _relpath_under_repo(full_path: str, repo_path: str) -> str:
    return os.path.relpath(full_path, repo_path).replace("\\", "/")


def _should_descend_directory(
    name: str,
    full_path: str,
    repo_path: str,
    excluded_dirs,
    gitignore_spec,
) -> bool:
    if name in excluded_dirs or name.startswith("."):
        return False
    if gitignore_spec is None:
        return True
    return not gitignore_spec.match_file(_relpath_under_repo(full_path, repo_path) + "/")


def _should_include_file(
    name: str,
    full_path: str,
    repo_path: str,
    root: str,
    excluded_files,
    excluded_exts,
    gitignore_spec,
    is_path_inside_root,
) -> bool:
    if name in excluded_files:
        return False
    _, extension = os.path.splitext(name)
    if extension.lower() in excluded_exts:
        return False
    if gitignore_spec is not None and gitignore_spec.match_file(
        _relpath_under_repo(full_path, repo_path)
    ):
        return False
    return is_path_inside_root(full_path, root)


def _classify_dir_entry(name: str, full_path: str):
    """Return 'directory', 'file', or None for ignored entry kinds."""
    if os.path.isdir(full_path) and not os.path.islink(full_path):
        return "directory"
    if os.path.isfile(full_path) or os.path.islink(full_path):
        return "file"
    return None


def _partition_dir_entries(dir_path: str):
    """Split sorted directory entries into real dirs vs files/symlinks."""
    try:
        entries = sorted(os.listdir(dir_path))
    except OSError:
        return [], []
    directories, regular_files = [], []
    for name in entries:
        full_path = os.path.join(dir_path, name)
        kind = _classify_dir_entry(name, full_path)
        if kind == "directory":
            directories.append((name, full_path))
        elif kind == "file":
            regular_files.append((name, full_path))
    return directories, regular_files


def _collect_descendable_dirs(
    directories,
    repo_path: str,
    excluded_dirs,
    gitignore_spec,
):
    return [
        full_path
        for name, full_path in directories
        if _should_descend_directory(
            name, full_path, repo_path, excluded_dirs, gitignore_spec
        )
    ]


def _append_included_files(
    files: list,
    regular_files,
    *,
    repo_path: str,
    root: str,
    excluded_files,
    excluded_exts,
    gitignore_spec,
    is_path_inside_root,
) -> None:
    for name, full_path in regular_files:
        if _should_include_file(
            name,
            full_path,
            repo_path,
            root,
            excluded_files,
            excluded_exts,
            gitignore_spec,
            is_path_inside_root,
        ):
            files.append(full_path)


def _walk_repo_collecting_files(
    dir_path: str,
    files: list,
    *,
    repo_path: str,
    root: str,
    excluded_dirs,
    excluded_exts,
    excluded_files,
    gitignore_spec,
    is_path_inside_root,
) -> None:
    directories, regular_files = _partition_dir_entries(dir_path)
    descendable = _collect_descendable_dirs(
        directories, repo_path, excluded_dirs, gitignore_spec
    )
    _append_included_files(
        files,
        regular_files,
        repo_path=repo_path,
        root=root,
        excluded_files=excluded_files,
        excluded_exts=excluded_exts,
        gitignore_spec=gitignore_spec,
        is_path_inside_root=is_path_inside_root,
    )
    for full_path in descendable:
        _walk_repo_collecting_files(
            full_path,
            files,
            repo_path=repo_path,
            root=root,
            excluded_dirs=excluded_dirs,
            excluded_exts=excluded_exts,
            excluded_files=excluded_files,
            gitignore_spec=gitignore_spec,
            is_path_inside_root=is_path_inside_root,
        )


def dfs_file_list(repo_path, excluded_dirs, excluded_exts, excluded_files, gitignore_spec=None):
    """Depth-first, deterministically-ordered walk of the repo, yielding
    absolute file paths. Directories and files are sorted at each level so
    the ordering is stable across runs (important since overlap depends on
    a consistent DFS order).

    File symlinks that resolve outside ``repo_path`` are skipped (untrusted
    trees). Directory symlinks are not followed (``os.path.isdir`` on the
    link itself without walking through it via ``os.listdir`` of the target
    as a root — we only recurse into real directories under the walk).

    gitignore_spec, if given, is a pathspec.PathSpec (see
    _shared_excludes.load_gitignore_spec) additionally consulted against
    each entry's path relative to repo_path — opt-in, off by default, on
    top of the hardcoded excluded_dirs/excluded_exts/excluded_files floor,
    not a replacement for it."""
    from doc_engine.core.walk import is_path_inside_root

    files = []
    root = os.path.abspath(repo_path)
    _walk_repo_collecting_files(
        repo_path,
        files,
        repo_path=repo_path,
        root=root,
        excluded_dirs=excluded_dirs,
        excluded_exts=excluded_exts,
        excluded_files=excluded_files,
        gitignore_spec=gitignore_spec,
        is_path_inside_root=is_path_inside_root,
    )
    return files


def _should_skip_carry_candidate(
    relpath: str,
    tokens: int,
    *,
    carried: int,
    overlap_budget: float,
    max_tokens: int,
    carried_in_paths,
) -> str | None:
    """Return 'break', 'continue', or None to accept the candidate."""
    if carried >= overlap_budget:
        return "break"
    if relpath in carried_in_paths:
        return "continue"
    if carried + tokens >= max_tokens:
        return "break"
    return None


def _carry_forward_overlap(closed_group, closed_tokens, overlap_ratio, max_tokens, carried_in_paths=frozenset()):
    """Build ~overlap_ratio worth of trailing tokens from a just-closed
    group to seed the next one. Files that entered the closed group only
    via overlap from the prior group are not re-carried — that prevents
    overlap cascading into three or more consecutive groups."""
    overlap_budget = closed_tokens * overlap_ratio
    carry, carried = [], 0
    for relpath, tokens in reversed(closed_group):
        decision = _should_skip_carry_candidate(
            relpath,
            tokens,
            carried=carried,
            overlap_budget=overlap_budget,
            max_tokens=max_tokens,
            carried_in_paths=carried_in_paths,
        )
        if decision == "break":
            break
        if decision == "continue":
            continue
        carry.append((relpath, tokens))
        carried += tokens
    carry.reverse()
    return carry, carried


def _should_close_group(
    current,
    current_tokens,
    candidate_tokens,
    *,
    is_last_group_being_filled: bool,
    max_tokens: int,
    target_per_group: float,
) -> bool:
    would_exceed_hard_cap = bool(current) and (current_tokens + candidate_tokens > max_tokens)
    would_exceed_soft_target = (
        bool(current)
        and not is_last_group_being_filled
        and current_tokens >= target_per_group
    )
    return would_exceed_hard_cap or would_exceed_soft_target


def _guard_zero_progress_carry(
    carry,
    carried,
    current_tokens,
    candidate_tokens,
    *,
    groups_closed_so_far: int,
    num_groups: int,
    max_tokens: int,
    target_per_group: float,
):
    """Clear carry when it would re-trigger the same close decision forever."""
    if carried != current_tokens:
        return carry, carried
    re_triggers_hard_cap = carried + candidate_tokens > max_tokens
    re_triggers_soft_target = (
        groups_closed_so_far != num_groups - 1 and carried >= target_per_group
    )
    if re_triggers_hard_cap or re_triggers_soft_target:
        return [], 0
    return carry, carried


def _close_group_and_seed_next(
    groups,
    current,
    current_tokens,
    candidate_tokens,
    *,
    overlap_ratio,
    max_tokens,
    carried_in_paths,
    num_groups,
    target_per_group,
):
    groups.append(current)
    carry, carried = _carry_forward_overlap(
        current, current_tokens, overlap_ratio, max_tokens, carried_in_paths,
    )
    carry, carried = _guard_zero_progress_carry(
        carry,
        carried,
        current_tokens,
        candidate_tokens,
        groups_closed_so_far=len(groups),
        num_groups=num_groups,
        max_tokens=max_tokens,
        target_per_group=target_per_group,
    )
    return list(carry), carried, frozenset(path for path, _ in carry)


def _step_group_assignment(
    file_tokens,
    index,
    *,
    groups,
    current,
    current_tokens,
    carried_in_paths,
    num_groups,
    max_tokens,
    overlap_ratio,
    target_per_group,
):
    """Advance one file into the current group, or close and re-evaluate."""
    relpath, tokens = file_tokens[index]
    is_last_group_being_filled = len(groups) == num_groups - 1
    if _should_close_group(
        current,
        current_tokens,
        tokens,
        is_last_group_being_filled=is_last_group_being_filled,
        max_tokens=max_tokens,
        target_per_group=target_per_group,
    ):
        current, current_tokens, carried_in_paths = _close_group_and_seed_next(
            groups,
            current,
            current_tokens,
            tokens,
            overlap_ratio=overlap_ratio,
            max_tokens=max_tokens,
            carried_in_paths=carried_in_paths,
            num_groups=num_groups,
            target_per_group=target_per_group,
        )
        return index, current, current_tokens, carried_in_paths
    current.append((relpath, tokens))
    return index + 1, current, current_tokens + tokens, carried_in_paths


def build_groups(file_tokens, max_tokens, overlap_ratio):
    """file_tokens: list of (relpath, tokens) in DFS order.
    Returns list of groups: each a list of (relpath, tokens).

    Check-before-append ("strict"): a candidate file is only added to the
    current group if doing so would not exceed max_tokens (unless the
    current group is still empty, in which case the file is added
    regardless — a single file larger than max_tokens has nowhere else to
    go; groups are atomic at the file level, so "a group containing that
    file is at least that file's size" is an unavoidable floor, not a bug).
    This bounds every group's total to at most max_tokens, except a group
    forced to open with a single oversized file — versus the previous
    check-after-append behavior's max_tokens + (whatever file closed the
    group) bound. Verified by direct execution against five scenarios plus
    an overlap-duplication regression and a deliberate infinite-loop
    trigger case — see the module's accompanying handoff notes / commit
    message for the exact scenarios and output, so nobody has to re-derive
    this from scratch if it's questioned later.
    """
    total_tokens = sum(tokens for _, tokens in file_tokens)
    if total_tokens == 0 or not file_tokens:
        return []

    num_groups = max(1, math.ceil(total_tokens / max_tokens))
    target_per_group = total_tokens / num_groups

    groups = []
    current = []
    current_tokens = 0
    carried_in_paths: frozenset[str] = frozenset()
    index = 0
    file_count = len(file_tokens)

    while index < file_count:
        index, current, current_tokens, carried_in_paths = _step_group_assignment(
            file_tokens,
            index,
            groups=groups,
            current=current,
            current_tokens=current_tokens,
            carried_in_paths=carried_in_paths,
            num_groups=num_groups,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
            target_per_group=target_per_group,
        )

    if current:
        groups.append(current)

    return groups


def _collect_file_tokens(repo_path, all_files, max_file_bytes):
    file_tokens = []
    skipped = []
    for full_path in all_files:
        rel = relpath_posix(full_path, repo_path)
        tokens, reason = estimate_tokens(full_path, max_file_bytes)
        if reason:
            skipped.append({"file": rel, "reason": reason})
            continue
        file_tokens.append((rel, tokens))
    return file_tokens, skipped


def _groups_output_payload(repo_path, max_tokens, overlap, file_tokens, skipped, groups_raw):
    return {
        "repo_path": repo_path,
        "max_tokens_per_group": max_tokens,
        "overlap": overlap,
        "total_files_considered": len(file_tokens),
        "total_files_skipped": len(skipped),
        "skipped": skipped,
        "num_groups": len(groups_raw),
        "groups": [
            {
                "id": index,
                "files": [path for path, _ in group],
                "est_tokens": sum(tokens for _, tokens in group),
            }
            for index, group in enumerate(groups_raw)
        ],
    }


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
    ap.add_argument("--respect-gitignore", action="store_true", default=False,
                    help="Additionally exclude paths matched by the repo's own .gitignore, "
                         "on top of the hardcoded exclude list (default: off; requires the "
                         "pathspec library)")
    args = ap.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"error: not a directory: {repo_path}", file=sys.stderr)
        sys.exit(1)

    excluded_dirs = DEFAULT_EXCLUDED_DIRS | set(args.exclude_dir)
    gitignore_spec = load_gitignore_spec(repo_path) if args.respect_gitignore else None
    all_files = dfs_file_list(
        repo_path,
        excluded_dirs,
        DEFAULT_EXCLUDED_EXTS,
        DEFAULT_EXCLUDED_FILES,
        gitignore_spec=gitignore_spec,
    )
    file_tokens, skipped = _collect_file_tokens(repo_path, all_files, args.max_file_bytes)
    groups_raw = build_groups(file_tokens, args.max_tokens, args.overlap)
    output = _groups_output_payload(
        repo_path, args.max_tokens, args.overlap, file_tokens, skipped, groups_raw
    )

    with open(args.out, "w") as handle:
        json.dump(output, handle, indent=2)

    print(
        f"Wrote {args.out}: {output['num_groups']} groups, "
        f"{output['total_files_considered']} files considered, "
        f"{output['total_files_skipped']} skipped."
    )


if __name__ == "__main__":
    main()
