# Implementation handoff: spring-boot-doc-agent, six agreed fixes

> **Historical (completed).** All six items landed (PR #1 era). This file is the origin story for write-then-verify and the six fixes — not live product instructions. Current product layout: [`docs/product-architecture.md`](docs/product-architecture.md). Agents live under `adapters/claude/agents/`; Stage 0 tools under `src/doc_engine/tools/`. Do not recreate `baseline-reference/`.

*Prepared 2026-07-23 by a Cowork session, for a Claude Code CLI session running directly against this repo on disk. Read this whole file before making any changes — items are ordered so later ones don't depend on earlier ones being incomplete, but Step 0 is a hard prerequisite for all of them.*

## Why this document exists, and why you (not the Cowork session that wrote it) are implementing it

This plugin went through six rounds of review and fixes in a cloud sandbox session that could only reach this repo through a device-file-bridge tool. That bridge repeatedly reported a file as "written" when the live copy on disk hadn't actually changed — confirmed multiple times by re-reading the file's actual bytes after a "success" response. Some fixes landed; some didn't, silently, until directly re-checked. The full history is in this repo's own commit history and, if this repo happens to be attached to a Claude project on claude.ai, in `claude/spring-boot-doc-agent-review.md`'s "Resolution, part 4" through "part 6" — but don't assume you can reach that; this document is written to be fully self-contained and not depend on it.

You (running as Claude Code directly on the machine that has this repo checked out) read and write these files with normal filesystem calls. There is no bridge in this path, so that specific failure mode — "reported written, wasn't" — cannot happen here. That's the main reason this implementation work is happening in a Claude Code session rather than continuing in the cloud one.

It does mean, however, that the *current* state of a few specific files on disk right now is not guaranteed to already reflect every fix described in that review history — some fixes might genuinely never have landed. **Do not assume the baseline is correct. Step 0 below makes it verifiable instead of assumed.**

## Step 0 — Reconcile against the known-good baseline (historical)

**Completed in PR #1 (2026-07-23).** The five-file `baseline-reference/` tree that used to ship beside this document was deleted in a later hygiene pass — those snapshots lived only to reconcile a device-bridge write-without-verify incident and had no sync mechanism against live SoT under `src/doc_engine/` / `adapters/`. Recover them from git history if needed (`git show <pre-delete-sha>:baseline-reference/...`).

Do **not** recreate `baseline-reference/`. Verify the live tree with `pytest tests/` and `python scripts/ci/check_repo_claims.py` instead of diffing against frozen forks.

~~Original Step 0 instructions (kept as record of what the implementing session was told to do):~~

<details>
<summary>Original Step 0 text (obsolete)</summary>

Bundled alongside this document, under `baseline-reference/`, were five files confirmed correct as of 2026-07-23. For each: diff against the live path, overwrite on mismatch, then run:

```bash
pytest tests/test_partition_repo.py -v
pytest tests/test_spring_signal_scan.py -v
```

</details>

Two other files were, per the review history, correctly delivered already and don't need reconciliation, but it costs nothing to sanity-check them along the way since you'll have both scripts' test suites running anyway: `adapters/claude/agents/architect-merge.md` and `adapters/claude/agents/architect-segment.md` should each have complete YAML frontmatter (`name`, `description`, `tools: Read, Grep, Glob`) and zero occurrences of the literal strings `{README}` or `{REPO}`. If either check fails, treat it as a new problem worth flagging, not something to silently patch over while you're in there for something else.

## A note on how literally to follow the six items below

They are not all the same kind of instruction:

- **Items 1, 3, and 4** come with exact target code, verified before this document was written — item 4's replacement function was actually executed against seven scenarios (output included below), not just reasoned about. Apply these close to as-written; if something doesn't fit the live file exactly (a line number shifted, a variable got renamed since this was written), adapt the mechanics but keep the same end state.
- **Item 2** comes with an exact before/after text diff, taken from the same verified baseline files in Step 0.
- **Items 5 and 6** are precise about the *what* and *why* and come with an illustrative sketch of the *how*, but the exact code/YAML needs to be written against the live files as they actually are (particularly `scripts/spring_ast_grep_rules.yml`, which isn't bundled here — it was never checked into the location this document was prepared from, so its exact current content has to come from your own read of the live file, not from this document). Treat the sketches in items 5 and 6 as a strong starting draft, not a diff to apply verbatim.

Whichever category, the standing rule for this whole codebase (visible throughout its own commit history) is **verify by running, not by reading**. Every one of the bugs this plugin has fixed so far was found by executing something — a real test suite, a real repo, a real reproduction script — not by inspection alone. Follow that same discipline for these six: run the test suites after each item, not just at the end.

## Suggested order

1. Delete the orphaned `doc-taxonomy.md` copy (trivial, do it first, gets it out of the way)
2. Shared exclude-dir module (touches both scripts' constants)
3. Opt-in `.gitignore` union (builds on the module from #2)
4. doc-writer.md / doc-taxonomy.md rule-text dedup (independent of the Python changes)
5. `build_groups()` strict-mode swap (independent function in `partition_repo.py`)
6. Generic import/package ast-grep rule + file-summarizer seam (most involved, do last so problems here don't block the other five)

(Numbering below matches the six agreed action items as discussed with the user, not this suggested execution order — cross-references say which is which.)

---

## Item 1 — Delete the orphaned `references/doc-taxonomy.md`

**What and why:** Two on-disk copies of this file exist — the plugin-root `references/doc-taxonomy.md` and `skills/document-spring-repo/references/doc-taxonomy.md`. As of the last check they were byte-identical, but only the second path is ever actually read: `SKILL.md`, `doc-writer.md`, and `gap-analyzer.md` all resolve `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md` exclusively. The root copy is a second source of truth with zero readers — a latent trap for whoever edits the wrong one later.

**Before deleting:** re-verify this yourself rather than trusting this document's claim blind — `grep -rn "references/doc-taxonomy" --include="*.md" .` from the repo root (excluding the file itself) and confirm every hit resolves through the `skills/document-spring-repo/` path, not the root one.

**Change:** `rm references/doc-taxonomy.md` (repo-root relative path). Leave `skills/document-spring-repo/references/doc-taxonomy.md` untouched by this item — item 4 below edits that one.

**Acceptance:** the grep above shows zero references to the root path anywhere in the repo (agents, skills, README, tests). No test suite covers this directly; the check is the grep, run before and treated as the gate.

---

## Item 2 — Shared exclude-dir module

**What and why:** `partition_repo.py`'s `DEFAULT_EXCLUDED_DIRS` and `spring_signal_scan.py`'s `EXCLUDED_DIRS` are two independently-maintained sets that have already drifted: `spring_signal_scan.py`'s set is missing `vendor`, `venv`, `.venv`, `env`, and `coverage`. That's not cosmetic — `run_ast_grep()` in `spring_signal_scan.py` shells out to the `ast-grep` binary directly against the repo root, with ast-grep's own default ignoring explicitly disabled (`--no-ignore hidden/dot/vcs/parent/global/exclude`), so the `--globs` list built from `EXCLUDED_DIRS` is the *only* thing standing between ast-grep and any given directory. A top-level `vendor/` or `venv/` directory containing Java (not unusual in enterprise brownfield repos, which is this plugin's target population) currently gets scanned, and anything in it — a stray `@Entity`, a `@PreAuthorize` — gets cited into `spring_signals.json` and downstream `[Evidenced — ...]` tags as if it were the repo's own code. Confirmed by direct reproduction with a synthetic `vendor/Vendored.java` during the review that led to this document.

The current two sets, diffed:
```
partition_repo.py DEFAULT_EXCLUDED_DIRS only: .mypy_cache, .next, .nuxt, .pytest_cache,
    .venv, __pycache__, coverage, env, vendor, venv
spring_signal_scan.py EXCLUDED_DIRS only:     .mvn
```
Everything else (`.git`, `.hg`, `.svn`, `node_modules`, `target`, `build`, `.gradle`, `.idea`, `.vscode`, `out`, `bin`, `obj`, `dist`) is already common to both.

**Change:** new file `scripts/_shared_excludes.py`:

```python
"""Shared default excluded-directory set for the deterministic scan/partition
stage. Single source of truth for both spring_signal_scan.py and
partition_repo.py — previously each maintained its own independent copy,
which had already drifted (spring_signal_scan.py's EXCLUDED_DIRS was
missing vendor/venv/.venv/env/coverage, which meant run_ast_grep()'s
--globs exclusion list — the only thing standing between ast-grep and
those directories, since run_ast_grep's own traversal is Rust-internal and
never goes through this module's dot-guard — let a top-level vendor/ or
venv/ directory's Java get scanned and cited as if it were the repo's own
code).

This is the union of the two sets as they stood on 2026-07-23 (diffed
programmatically, not merged by eye), plus no new entries.
"""

DEFAULT_EXCLUDED_DIRS = frozenset({
    ".git", ".gradle", ".hg", ".idea", ".mvn", ".mypy_cache", ".next",
    ".nuxt", ".pytest_cache", ".svn", ".venv", ".vscode", "__pycache__",
    "bin", "build", "coverage", "dist", "env", "node_modules", "obj",
    "out", "target", "vendor", "venv",
})
```

In `partition_repo.py`: delete the inline `DEFAULT_EXCLUDED_DIRS = {...}` block (currently near the top, right after the imports) and replace it with:
```python
from _shared_excludes import DEFAULT_EXCLUDED_DIRS
```
Nothing else in `partition_repo.py` needs to change — `main()` already does `DEFAULT_EXCLUDED_DIRS | set(args.exclude_dir)`, and the name is unchanged.

In `spring_signal_scan.py`: delete the inline `EXCLUDED_DIRS = {...}` block and replace it with:
```python
from _shared_excludes import DEFAULT_EXCLUDED_DIRS as EXCLUDED_DIRS
```
This keeps the local name `EXCLUDED_DIRS` so `dfs_walk()` and `run_ast_grep()` need no other changes.

**Risk worth checking, not assuming:** both scripts are invoked as `python3 scripts/spring_signal_scan.py ...` / `python3 scripts/partition_repo.py ...` (per `SKILL.md`'s Stage 0), which means Python auto-adds `scripts/` to `sys.path`, so a plain sibling import (`from _shared_excludes import ...`, no package prefix) should resolve. This should just work but hasn't been executed as of this document being written — the test run below is the actual check, not this paragraph's reasoning.

**Acceptance:**
```bash
python3 scripts/test_partition_repo.py -v
python3 scripts/test_spring_signal_scan.py -v
```
Both suites green. Additionally, spot-check the fix actually closes the gap it's meant to close — create a throwaway `vendor/Probe.java` containing `@Entity` in a scratch test repo, run `spring_signal_scan.py` against it, and confirm `vendor/Probe.java` produces zero entries anywhere in the output (it did produce entries before this change).

---

## Item 3 — Opt-in `.gitignore` union

**What and why:** `spring_signal_scan.py`'s `run_ast_grep()` deliberately ignores `.gitignore` — a legitimate, documented, reproducibility-motivated choice (the comment right above the `--no-ignore` flags says so directly), not a bug. But the two comparator tools this plugin was benchmarked against (repomix, gitingest) both showed a more complete pattern worth adding as an *option*: keep a hardcoded exclude floor unconditionally, but let it additionally consult the repo's own `.gitignore` when a caller wants "stay in sync with what this repo's maintainers already flagged as noise" more than "identical behavior regardless of checkout." Default behavior must not change — this is additive only.

**Design, worked out precisely while preparing this document (more precise than earlier framing that suggested a uniform `pathspec` shim everywhere):**

- The **Python-side traversals** (`dfs_walk` in `spring_signal_scan.py`, `dfs_file_list` in `partition_repo.py`) have no native gitignore support at all — these do need the `pathspec` library (`pip install pathspec`; `gitwildmatch` syntax — the same real, well-trodden library gitingest itself uses for this, not a hand-rolled parser).
- The **ast-grep subprocess call** (`run_ast_grep`) is different: ast-grep already has its own native, battle-tested `.gitignore` handling built in — that's precisely what the existing `--no-ignore vcs` flag is turning *off*. There's no need to reimplement gitignore matching for that call; just don't pass `--no-ignore vcs` when the opt-in flag is set, and let ast-grep's own logic take over for that one category. Leave `hidden`/`dot`/`parent`/`global`/`exclude` disabled either way — `parent` and `global` are about gitignore state outside this repo (parent directories, the invoking user's personal global gitignore config), which has nothing to do with "sync with what this repo's own maintainers flagged" and would reintroduce a different, per-machine kind of non-reproducibility if left enabled.

**Change:**

1. Add to `scripts/_shared_excludes.py` (from item 2):
```python
def load_gitignore_spec(repo_path):
    """Return a pathspec.PathSpec built from repo_path/.gitignore, or None
    if there is no .gitignore or the pathspec library isn't installed.
    Soft dependency, same pattern as spring_signal_scan.py's existing
    sqllineage handling — a missing install degrades this one feature,
    it doesn't fail the whole scan."""
    import os
    gitignore_path = os.path.join(repo_path, ".gitignore")
    if not os.path.isfile(gitignore_path):
        return None
    try:
        import pathspec
    except ImportError:
        return None
    with open(gitignore_path) as f:
        return pathspec.PathSpec.from_lines("gitwildmatch", f)
```

2. `partition_repo.py`: add `--respect-gitignore` (store_true, default False) to the argparse block. When set, load the spec once in `main()` and thread it into `dfs_file_list`'s `_walk` closure so a path matched by the spec is skipped the same way an excluded dir/ext/file already is today. Match against the path relative to `repo_path` (pathspec matches relative, POSIX-style paths).

3. `spring_signal_scan.py`: add `--respect-gitignore` to its argparse block too.
   - In `dfs_walk`, when the flag is set, also skip any file/dir matched by the loaded spec (same relative-path matching as above).
   - In `run_ast_grep`, accept a `respect_gitignore` parameter; when True, omit `"--no-ignore", "vcs"` from the `cmd` list (keep every other `--no-ignore` pair as-is).

4. Update `SKILL.md`'s Stage 0 command block with a one-line note that both scripts accept an optional `--respect-gitignore` flag, off by default.

**Acceptance:** default behavior (flag omitted) must be byte-identical to before this change — run both existing test suites unmodified and confirm they still pass with no changes to expected output. Then add one new test per script (or extend the real-world fixture test) that creates a scratch repo with a `.gitignore` excluding some directory the hardcoded set does *not* cover, runs the scanner/partitioner twice (with and without `--respect-gitignore`), and confirms that directory is included in the first run and excluded in the second.

---

## Item 4 — doc-writer.md / doc-taxonomy.md rule-text deduplication

**What and why:** `doc-writer.md`'s Rule 1 and `doc-taxonomy.md`'s "General rule across all fourteen" section currently both fully restate the same five-tag evidence rule, verbatim, with a comment in `doc-taxonomy.md` acknowledging the duplication ("the two must stay in sync; if you edit one, edit the other") but no actual enforcement. Same "two sources of truth" pattern as item 1, in prose instead of code. Fix: keep the full statement in exactly one place — `doc-taxonomy.md`, since it's the fuller spec with the taxonomy context around it — and have `doc-writer.md` point at it instead of restating it.

**Exact current text, `agents/doc-writer.md`** (numbered list item 1, verified against the baseline bundle):
```
1. Every substantive claim ends with a bracketed tag, in exactly one of these forms — this is a required format, not a category to paraphrase in your own words, so tags read identically across all fourteen files no matter which of you writes which one:
   - `[Evidenced — path/File.java:42]` — the specific file (and line, for a claim about one spot in it) the claim comes from. A whole-file claim just cites the file: `[Evidenced — build.gradle]`.
   - `[Confirmed — interview, <date from interview_answers.json>]`.
   - `[Unknown — not evidenced in code, not covered in interview]`. Do not write a guess and dress it up as either of the other tags.
   - `[Evidenced — path/File.java:42; inference avoided beyond this]` — optional. Use it when there's real signal but you're deliberately not stretching it into a claim the signal doesn't actually support. A reader can't tell "no signal at all" from "signal, deliberately not extrapolated" unless you say which.

   Read `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md`'s "What counts as code evidence" section before tagging anything `[Evidenced — ...]` — not everything that's technically text in the repo (generated output, an existing README, a comment) carries the same weight, and that section defines a fifth tag, `[Per existing docs — ...]`, for claims sourced from documentation that predates this pipeline rather than from the code itself.
```

**Replace with:**
```
1. Every substantive claim ends with a bracketed tag. Read `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md`'s "General rule across all fourteen" section for the exact required wording of all five tag forms (Evidenced / Confirmed / Unknown / Evidenced-with-inference-avoided / Per existing docs) — use that wording exactly, do not restate or paraphrase it here, so this file and that one can't drift out of sync the way they already have once.

   That same file's "What counts as code evidence" section (just above the general rule) matters just as much — not everything that's technically text in the repo (generated output, an existing README, a comment) carries the same evidentiary weight. Read both sections before writing anything, not just the numbered entry for the file you're writing.
```

**Exact current text, `skills/document-spring-repo/references/doc-taxonomy.md`** ("General rule across all fourteen" section, first sentence):
```
This is the same rule as `doc-writer.md`'s Rule 1, stated here for reference — the two must stay in sync; if you edit one, edit the other.
```

**Replace with:**
```
This is the canonical statement of the tag rule — `doc-writer.md`'s Rule 1 points here rather than restating it, so there is exactly one copy of the wording to keep current.
```
(Leave the five numbered tag forms immediately below that sentence untouched — they remain the one authoritative copy.)

**Acceptance:** no automated test covers prose content directly. Manually confirm: `doc-writer.md` no longer contains the literal strings `[Confirmed —` or `[Unknown —` (the restated tag examples) outside of the one pointer sentence; `doc-taxonomy.md` still contains all five tag forms exactly once each. Re-run both test suites to confirm this text-only change didn't touch anything they check (it shouldn't — flag it if it somehow does).

---

## Item 5 — `build_groups()` strict-mode swap (check-before-append)

**What and why:** the current `build_groups()` in `partition_repo.py` appends a file, *then* checks whether the cap was hit ("check-after-append") — so its actual bound is `max_tokens + (whatever single file closed the group)`, not `max_tokens`. A "check-before-append" version (peek at the next file, close the current group *without* it if adding it would breach the cap, then retry) was implemented and run against five scenarios plus two edge cases as part of the review that produced this document. Real output, from actually executing both the scenarios and a deliberate infinite-loop trigger case, not reasoning about them:

```
Scenario A (6×20-tok + 12×90-tok files, max_tokens=100):
  strict groups = 15, sizes = [100,40,20,90,90,90,90,90,90,90,90,90,90,90,90], max = 100
  (current check-after-append algorithm produces 14 groups, largest 180 — i.e. 80 over cap)

Scenario B (50, 900, 30 tok files, max_tokens=100):
  strict groups = 3, sizes = [50, 900, 30], contents = [['f1'], ['f2'], ['f3']]
  (current algorithm produces 2 groups, [950, 30] — the unrelated 50-tok file gets
  dragged into the 900-tok file's group)

Scenario C (20 uniform 10-tok files, max_tokens=100):
  strict groups = 3, sizes = [100, 100, 20]  (identical to current algorithm)

Scenario D (5×60-tok files, max_tokens=100):
  strict groups = 5, sizes = [60,60,60,60,60]
  (current algorithm also produces 5 groups, but [120,120,120,120,60] — 20 over cap on 4 of 5;
  strict costs nothing extra here and removes all overshoot)

Scenario E (10-tok + 5000-tok files, max_tokens=100):
  strict groups = 2, sizes = [10, 5000], contents = [['small'], ['huge']]
  (current algorithm produces 1 group, [5010] — the small file dragged into the huge one)

Overlap-duplication regression (40, 40, 900, 20, 20 tok files, max_tokens=100):
  strict groups = 4, sizes = [80, 40, 900, 40]; the 900-tok file appears in exactly 1 group
  (confirms the strict swap doesn't reintroduce the already-fixed oversized-trailing-file
  duplication bug documented elsewhere in this file's own history)

Infinite-loop trigger case (90-tok file, then a 95-tok file, max_tokens=100):
  completed without hanging, groups = 2, sizes = [90, 95]
  (this is the exact shape that hung a naive first attempt at this swap: a group whose
  entire content gets carried forward unchanged, followed by a file that still doesn't
  fit even against that full carry — see the zero-progress guard below)

All bound checks pass: every group's total is <= max_tokens, except a group forced to
open with a single file whose own token count alone exceeds max_tokens (unavoidable —
groups are atomic at the file level, so "a group containing that file is at least that
file's size" is a floor no partitioning algorithm can beat).
```

**Exact replacement for `build_groups()`** (drop this in place of the current function body in `partition_repo.py`; the function signature and return shape are unchanged, so nothing calling it needs to change):

```python
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
    total_tokens = sum(t for _, t in file_tokens)
    if total_tokens == 0 or not file_tokens:
        return []

    num_groups = max(1, math.ceil(total_tokens / max_tokens))
    target_per_group = total_tokens / num_groups

    def carry_forward(closed_group, closed_tokens):
        """Build ~overlap_ratio worth of trailing tokens from a just-closed
        group to seed the next one. Same oversized-trailing-file guard as
        the previous check-after-append version: a candidate is never
        added to the carry if doing so would, by itself, already reach
        max_tokens."""
        overlap_budget = closed_tokens * overlap_ratio
        carry, carried = [], 0
        for relpath2, tok2 in reversed(closed_group):
            if carried >= overlap_budget:
                break
            if carried + tok2 >= max_tokens:
                break
            carry.append((relpath2, tok2))
            carried += tok2
        carry.reverse()
        return carry, carried

    groups = []
    current = []
    current_tokens = 0
    i = 0
    n = len(file_tokens)

    while i < n:
        relpath, tok = file_tokens[i]
        is_last_group_being_filled = len(groups) == num_groups - 1

        would_exceed_hard_cap = bool(current) and (current_tokens + tok > max_tokens)
        would_exceed_soft_target = (
            bool(current)
            and not is_last_group_being_filled
            and current_tokens >= target_per_group
        )

        if would_exceed_hard_cap or would_exceed_soft_target:
            groups.append(current)
            carry, carried = carry_forward(current, current_tokens)

            # Zero-progress guard: if the entire just-closed group got
            # carried forward unchanged (carried == current_tokens, i.e.
            # nothing was dropped) and the same triggering file still
            # wouldn't fit even against that unchanged carry, retrying
            # as-is would reproduce the exact same state forever — this is
            # the exact infinite loop a naive first port of this swap hit.
            # Force the carry empty instead: better to lose the overlap at
            # this one seam than to hang.
            if carried == current_tokens and carried + tok > max_tokens:
                carry, carried = [], 0

            current, current_tokens = list(carry), carried
            continue  # re-evaluate the same file against the new group

        current.append((relpath, tok))
        current_tokens += tok
        i += 1

    if current:
        groups.append(current)

    return groups
```

**New regression test** — add to `scripts/test_partition_repo.py`, matching the existing file's style (it already has `test_final_group_no_longer_unbounded` and `test_overlap_skips_oversized_trailing_file` for the two previous bugs in this same function; read those first for exact conventions to match):

```python
def test_strict_mode_zero_progress_guard_prevents_infinite_loop(self):
    """A group whose entire content gets carried forward unchanged,
    followed by a file that still doesn't fit even against that full
    carry, must not retry against unchanged state forever. Regression
    for the infinite loop found while porting build_groups() to
    check-before-append (strict) semantics."""
    file_tokens = [("only.txt", 90), ("trigger.txt", 95)]
    groups = build_groups(file_tokens, max_tokens=100, overlap_ratio=0.10)
    all_files = [f for g in groups for f, _ in g]
    self.assertIn("only.txt", all_files)
    self.assertIn("trigger.txt", all_files)
    for g in groups:
        total = sum(t for _, t in g)
        if total > 100:
            self.assertEqual(len(g), 1, f"group exceeds max_tokens with more than one file: {g}")
```

Also re-run the two *existing* regression tests for the previous two bugs in this function against the new implementation — they must still pass unmodified; if either needs its assertions changed to accommodate the strict swap, that's a signal the swap regressed something the old tests were protecting, not that the old test was wrong.

**Acceptance:**
```bash
python3 scripts/test_partition_repo.py -v
```
All tests green, including the new one and both pre-existing regression tests. If a real-world fixture is configured, also re-run `test_partition_repo_real_world.py` and expect it to still pass (strict mode should only ever produce equal-or-more groups with equal-or-less overshoot than before, never break an assertion that was about *content*, only ones that were specifically about the old bound).

---

## Item 6 — Generic import/package ast-grep rule, closing the file-summarizer group-boundary seam

**What and why, in full:** `file-summarizer.md` (Stage 1) only ever sees its own group's files — its step 3 scopes relationship-finding to "any other file in your group." A controller in group 1 and the service it calls in group 16 of a large repo have no mechanism to be linked; the ~10% DFS overlap only rescues relationships that happen to straddle *adjacent* groups. `entity_table_map` (already computed, free) only covers shared-*table* relationships, not this call-graph case. The actual gap is specifically *cross-package* references — same-package files are already DFS-adjacent by construction (`dfs_file_list`'s `_walk` appends every file in a directory before recursing into subdirectories), so the existing overlap already has a shot at those.

The fix: one more ast-grep rule — a plain `import_declaration` capture (no narrowing regex to one specific type), alongside `package_declaration` — since ast-grep already parses every file's full AST for the other 21 rules in `spring_ast_grep_rules.yml`, so this is marginal cost, not a new pass. That produces a repo-wide reference index, independent of group boundaries, that `file-summarizer` can consult for cross-group relationships the same way it already consults its group's `spring_signals.json` slice today.

**Honest limits, worth keeping in the final prose rather than dropping:** same-package references need no import statement at all (Java doesn't require importing a same-package class) — DFS locality already covers the case where both files are in the same group, but a same-package file that landed in a *different* group (large repo, package split across groups) is a case this rule alone won't catch; flag it as a known residual gap rather than silently pretending it's solved. Wildcard imports (`import com.foo.*`) resolve to a package, not a specific class. Interface-mediated dependency injection (`@Autowired` on an interface type) needs matching `@Service`/`@Component` implementers against the interface — an import graph alone won't give you that. This closes the specific controller-calls-service gap that motivated it; it is not a complete call graph.

**Pieces this touches — all four are needed for the fix to actually do anything, not just the rule file:**

1. **`scripts/spring_ast_grep_rules.yml`** — add the new rule(s). This file is not bundled with this handoff (it wasn't checked into wherever this document was assembled from) — read it live first and match its existing conventions exactly (rule id naming like `bucket__subkind`, the YAML structure the other 21 rules use, its header comment about the rule-id convention and past matching-adjacency bugs). Illustrative sketch of what's needed, **not** verified YAML syntax — confirm against the real file's own patterns before trusting this shape:
   ```yaml
   # ILLUSTRATIVE — verify against this file's actual existing rule syntax
   # before using verbatim; the other rules in this file are the source of
   # truth for exact ast-grep YAML shape, not this sketch.
   - id: references__import
     language: java
     rule:
       kind: import_declaration
   - id: references__package
     language: java
     rule:
       kind: package_declaration
   ```

2. **`scripts/spring_signal_scan.py`'s `scan()` function** — the `buckets` dict initialized at the top of `scan()` currently has exactly eleven keys (`api_surface`, `outbound_clients`, `messaging`, `persistence`, `raw_queries`, `security`, `configuration`, `error_handling`, `observability`, `deployment`, `testing`). A rule id like `references__import` produces a bucket name of `references` via `rule_id.partition("__")` — **that key does not exist yet**. Without adding it, the existing code path (`if bucket not in buckets: print(warning...); continue`) will silently drop every match from the new rule with just a stderr warning — an easy way for this whole item to compile cleanly and produce nothing. Add `"references": []` to the `buckets` dict. The generic entry-construction path (`entry = {"file": rel, "line": line, "match": match_str, "rule_id": rule_id}` then `buckets[bucket].append(entry)`) needs no other changes — this rule doesn't need special extraction like `persistence__entity` or `raw_queries__query` get. Also update the module docstring's "Output buckets map directly to documentation categories" comment block with a line for the new bucket (something like `references -> consumed by file-summarizer for cross-group relationship-finding; not written directly into any of the 14 output files`), so the docstring doesn't go stale the moment this ships.

3. **`skills/document-spring-repo/SKILL.md`'s Stage 1** — currently says to give each `file-summarizer` dispatch "the relevant slice of `spring_signals.json` (matches whose `file` field falls in that group)." The new `references` bucket needs to be passed *in full, repo-wide*, not scoped to the group — the entire point is giving file-summarizer visibility outside its own group. It's cheap (file/line/package-or-import-text triples, not source), so passing all of it to every dispatch should be inexpensive regardless of repo size, but confirm that assumption against a real repo's actual `references` bucket size rather than just asserting it.

4. **`agents/file-summarizer.md`** — step 3 currently reads: *"Check whether it clearly relates to any other file in your group — shared types, direct imports, shared table/queue/topic names. Use Grep within the group's files if it's not obvious from imports."* This needs to generalize beyond "in your group" now that the repo-wide `references` slice is available: for each file, cross-check its own package/import lines (visible from the file-summarizer's own read of the file) against the `references` bucket's package/import entries for files *outside* the group, and name a cross-group relationship when there's a match — while still doing the existing in-group check via Grep for cases the import graph alone won't show. Also extend the returned JSON shape: the existing `relationships` field is documented as in-group only ("other in-group files with a load-bearing relationship") — add a parallel field (e.g. `cross_group_relationships`) for relationships found via the new repo-wide slice, rather than silently mixing two different confidence levels into one field. Write the exact final wording against the live file's actual current text and tone, not by guessing at it blind — the current exact text is quoted above precisely so you can find and edit it directly.

**Acceptance:**
```bash
python3 scripts/test_spring_signal_scan.py -v
```
Green, plus a new assertion (add to that file, matching its existing conventions) that scans a small fixture with two files in different fictional "groups" — one importing the other — and confirms the `references` bucket contains an entry for the import. Since `file-summarizer.md`/`SKILL.md` changes aren't covered by the Python test suite at all, the acceptance for those two is a live pipeline run against a real small repo, checking by hand that at least one cross-group relationship shows up in a `file-summarizer` result that would have been invisible under the old group-scoped-only step 3 — this is the one item in this whole list where "run the actual pipeline once against a real target" is the only real verification available, so budget time for that rather than treating a clean test-suite run alone as sufficient sign-off.

---

## After all six items

Re-run both full test suites one more time end to end:
```bash
python3 scripts/test_partition_repo.py -v
python3 scripts/test_spring_signal_scan.py -v
```

This repo doesn't appear to enforce a specific commit-message or branch-naming convention of its own (no `CLAUDE.md`/`CONTRIBUTING.md` was found describing one as of this document being written — check again yourself in case that's changed). Absent one, plain hygiene: do this work on its own branch, and keep each of the six items as its own commit so a reviewer (or a future you) can bisect if one of them turns out to need a follow-up fix, the same way this plugin's own history has needed several already.
