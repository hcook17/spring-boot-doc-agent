# PR verification index

One file per pull request (`pr-N.md`), each pairing that PR's summary with **deterministic search heuristics** — literal `git`/`grep` commands, pinned to that PR's actual commit(s) — a reader (human or another Claude session) can run to confirm each claim directly, instead of re-reading the full diff or trusting the prose alone. Same discipline `CONTRIBUTING.md`'s write-then-verify rule and this pipeline's own `[Evidenced — path:line]` tagging already apply elsewhere in this repo, turned outward on this repo's own PR history.

Every command is pinned to a commit SHA (or, for a still-open PR, its head branch), not to `HEAD`/`main` — so a command in `pr-3.md` still resolves correctly even after ten more PRs land. Run them with `git show <ref>:<path>`, not by checking out the branch — that works from whatever's currently checked out, without disturbing your working tree.

**Convention: write a PR's own `pr-N.md` in the same PR when possible.** For any PR touching `scripts/`/`agents/`/`skills/`/`references/`, add its `pr-N.md` (pinned to the PR's own head commit, per the still-open-PR case above — `pr-13.md` is the original precedent) as part of that same PR, using the PR number `gh pr create` returns once the PR is opened. `scripts/check_llms_coverage.py` (CI-wired) fails the build if a merged PR has no corresponding `pr-N.md`, or one with a stale `state:` frontmatter field — but a PR can never document its own merge commit before that commit exists, so the single most-recently-merged PR is always exempt from both checks. Following this convention keeps that exemption rarely exercised in practice, rather than relying on it as the default path.

> **The grace window did not hold, and the table below records where.** This paragraph used to claim the exemption was "a bounded grace window, not a hole: the exemption shifts to whichever PR merges next, so nothing stays undocumented past one PR cycle." That reasoning only holds while the check can actually fail. `scripts/check_llms_coverage.py` has `ENFORCE = False` (set during a fast-merge burst and never flipped back), so the findings print and the build stays green — and **PRs #21–#27 merged with no `pr-N.md` at all**, seven PRs rather than one. Run `python3 scripts/check_llms_coverage.py` to see the current list. The exemption is sound in principle; what failed is that nothing enforced the window's closing. Either backfill #21–#27 and set `ENFORCE = True`, or drop the convention deliberately — but the CI step is currently named "fails on a merged PR with no `claude/llms/pr-N.md`" and cannot fail, which is the worst of the three options.

## Writing the commands

Two rules that are requirements of `scripts/verify_llms_docs.py`, not style. Both were found the same way — by writing a `pr-N.md`, running the verifier, and having it reject correct-looking claims — so they are recorded here, where the next author looks, rather than in the file where they happened to surface.

1. **A command may not contain a backtick.** `parse_commands()` extracts single-backtick-fenced text, so wrapping a command in double backticks to let its grep pattern contain backticks does not work: the parser truncates at the first inner backtick and runs a fragment. Choose a distinctive backtick-free substring to grep for instead.
2. **An expected-empty result must say "no output", not a count of `0`.** `evaluate()` grades a non-zero exit as failure unless the `Expect:` line matches "no output" or "empty output" — and `grep -c` exits 1 whenever the count is zero. So `grep -c ...` with `Expect: 0` fails the harness while being factually right. Use `grep -n ...` with `Expect: no output`.

The reason to run the verifier before committing is not really the harness, though. Doing so on `pr-31.md` also surfaced a claim whose own commands did not support it — a summary asserting a three-way split where the file states a two-way one. A verification doc that asserts more than it checks is the exact failure this index exists to prevent, and only running it finds that.

| PR | Title | State |
|----|-------|-------|
| [#1](pr-1.md) | Implement six agreed fixes from IMPLEMENTATION_HANDOFF.md | merged (`0b7b7de`) |
| [#2](pr-2.md) | New prompts and skill update | merged (`bcd339b`) |
| [#3](pr-3.md) | Document and wire spring_drift_check.py into pipeline docs | merged (`274c6d3`) |
| [#4](pr-4.md) | Add CONSTRAINTS.md | merged (`7751322`) |
| [#5](pr-5.md) | Fix README.md merge artifact from PR #3/#4 | merged (`79e0b7d`) |
| [#6](pr-6.md) | License and version update | merged (`08a588e`) |
| [#7](pr-7.md) | Add CONTRIBUTING.md (write-then-verify rule) and STATUS.md | merged (`bfcb324`) |
| [#8](pr-8.md) | Add structural tests for the four LLM pipeline stages | merged (`a0acc76`) |
| [#9](pr-9.md) | Add claude/llms/: deterministic-verification index for this repo's PR history | merged (`3454c4c`) |
| [#10](pr-10.md) | Log PR #9 review findings; scaffold task prompt for repo's first CI job | merged (`19714dd`) |
| [#11](pr-11.md) | Add this repo's first CI workflow and a claude/llms/ meta-verification script | merged (`6ea8ba5`) |
| [#12](pr-12.md) | Add a heuristic secret-redaction layer for the doc-generation pipeline | merged (`52e3e87`) |
| [#13](pr-13.md) | Add semantic-pipeline-eval and capacity-preflight skills, plus a maturity assessment | merged (`e8dbe89a`) |
| [#14](pr-14.md) | Land two commits stranded after PR #13 merged early | merged (`b8d07f9`) |
| [#15](pr-15.md) | Pin ast-grep-cli, sqllineage, pathspec via requirements.txt | merged (`9a517e3`) |
| [#16](pr-16.md) | Add claude/llms/ coverage check; backfill pr-9..15.md; fix stale pr-13.md | merged (`1e6467b`) |
| [#17](pr-17.md) | Add claude/llms/pr-16.md (closes the recursive coverage gap) | merged (`85290ee`) |
| [#18](pr-18.md) | Fix infinite-regress bug in claude/llms/ coverage enforcement | merged (`5726135`) |
| [#19](pr-19.md) | CONSTRAINTS.md: add solo-context note; flag coverage-exemption heuristic as provisional | merged (`0d7f727`) |
| [#20](pr-20.md) | Add claude/llms/pr-18.md (grace window shifted forward as designed) | merged (`99804af`) |
| #21 | Add claude/llms/pr-19.md (grace window shifted forward again) | merged (`bd66860`) — **no `pr-21.md`** |
| #22 | CONSTRAINTS.md: sketch future-team review workflow using claude/llms/pr-N.md | merged (`d8ce31c`) — **no `pr-22.md`** |
| #23 | check_llms_coverage.py: add ENFORCE toggle, default False for now | merged (`958aaa2`) — **no `pr-23.md`** |
| #24 | Add scripts/run_manifest.py: run-level telemetry for document-spring-repo | merged (`9d54efd`) — **no `pr-24.md`** |
| #25 | test_run_manifest.py: derive required-key sets from run_manifest.schema.json | merged (`569785f`) — **no `pr-25.md`** |
| #26 | spring_drift_check.py: add --manifest to use run_manifest.json's file_signatures as the tier-1 baseline | merged (`9620e27`) — **no `pr-26.md`** |
| #27 | spring_drift_check.py: follow-ups to PR #26 (manifest empty-repo edge case, research note) | merged (`40910bc`) — **no `pr-27.md`** |
| [#28](pr-28.md) | Sync status docs, fix ast-grep test-killing bug, resolve bounded JPQL lineage | merged (`03c16dd`) |
| #29 | Fix broken doc references and sweep stale numbers out of the living snapshots | merged (`add3083`) — exempt as most-recently-merged when opened; `pr-29.md` still owed |
| [#30](pr-30.md) | Fix two JPQL-provenance gate misses in spring_drift_check.py | merged (`a677279`) |
| [#31](pr-31.md) | Correct the mirror-back scope and annotate the maturation plan's stale items | merged (`6f04332`) |

Cross-linked from `STATUS.md` and `README.md`. See `claude/session-log.md` for the append-only history of which steering-prompt assumptions each of these PRs affected — this index is about verifying *what a PR did*, the session log is about *what it means for the steering prompts*. Different axis, same underlying discipline.
