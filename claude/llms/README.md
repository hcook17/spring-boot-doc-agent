# PR verification index

One file per pull request (`pr-N.md`), each pairing that PR's summary with **deterministic search heuristics** — literal `git`/`grep` commands, pinned to that PR's actual commit(s) — a reader (human or another Claude session) can run to confirm each claim directly, instead of re-reading the full diff or trusting the prose alone. Same discipline `CONTRIBUTING.md`'s write-then-verify rule and this pipeline's own `[Evidenced — path:line]` tagging already apply elsewhere in this repo, turned outward on this repo's own PR history.

Every command is pinned to a commit SHA (or, for a still-open PR, its head branch), not to `HEAD`/`main` — so a command in `pr-3.md` still resolves correctly even after ten more PRs land. Run them with `git show <ref>:<path>`, not by checking out the branch — that works from whatever's currently checked out, without disturbing your working tree.

> **These commands are for a human to run. CI does not execute them.** `scripts/verify_llms_docs.py` used to re-run all of them on every PR; it was deleted, along with its CI step, in the change closing [#35](https://github.com/hcook17/spring-boot-doc-agent/issues/35). It passed backtick-fenced spans from this markdown to `bash -c` with `GH_TOKEN` in scope, and matched on prefix — so any `;` in a span was arbitrary code execution (reproduced: `git log -1; echo X > file` graded PASS and wrote the file). Because these files are LLM-authored, the realistic path was an agent writing a doc that CI then executed, which is how it actually fired. Hardening the parser was rejected because telling a command from the *name* of a command in prose is undecidable; see `claude/10-architecture-maturation-plan.md` scrap item 2 and 0.1.3.
>
> Two consequences for readers. **Run these yourself, from a trusted checkout, when you want to verify a claim** — that was always their real value. And **do not treat an `Expect:` value as machine-verified**: even while the harness existed it graded on exit status alone and never compared the stated value, so `grep -c` returning `7` passed a claim that said `1`. Around 20 commands in this index end in a stage that cannot fail at all (bare `git show`, `git log`, `git rev-parse`, `git diff` without `--exit-code`), asserting only that a SHA resolved.

**Convention: write a PR's own `pr-N.md` in the same PR when possible.** For any PR touching `scripts/`/`agents/`/`skills/`/`references/`, add its `pr-N.md` (pinned to the PR's own head commit, per the still-open-PR case above — `pr-13.md` is the original precedent) as part of that same PR, using the PR number `gh pr create` returns once the PR is opened. `scripts/check_llms_coverage.py` (CI-wired) fails the build if a merged PR has no corresponding `pr-N.md`, or one with a stale `state:` frontmatter field — but a PR can never document its own merge commit before that commit exists, so the single most-recently-merged PR is always exempt from both checks. Following this convention keeps that exemption rarely exercised in practice, rather than relying on it as the default path.

> **The grace window did not hold, and the table below records where.** This paragraph used to claim the exemption was "a bounded grace window, not a hole: the exemption shifts to whichever PR merges next, so nothing stays undocumented past one PR cycle." That reasoning only holds while the check can actually fail. `scripts/check_llms_coverage.py` has `ENFORCE = False` (set during a fast-merge burst and never flipped back), so the findings print and the build stays green — and **PRs #21–#27 merged with no `pr-N.md` at all**, seven PRs rather than one. Run `python3 scripts/check_llms_coverage.py` to see the current list. The exemption is sound in principle; what failed is that nothing enforced the window's closing. Either backfill #21–#27 and set `ENFORCE = True`, or drop the convention deliberately — but the CI step is currently named "fails on a merged PR with no `claude/llms/pr-N.md`" and cannot fail, which is the worst of the three options.

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
| #36 | Execute the mirror-back; correct the manifest's two wrong rows; fix `06`'s stale `status:` | merged (`a62a99c`) — **no `pr-36.md`** |
| [#47](pr-47.md) | Kitchen-sink suite, a code-quality ratchet, and five real bugs | merged (`1539d0c`) — branch history was rewritten before merge; see the file |
| [#48](pr-48.md) | Verified testing/security anchors, cited from steering prompt 10 | merged (`8b1138a`) |
| [#49](pr-49.md) | Order module docstrings reference-first, and enforce it | merged (`56e9a74`) |
| [#50](pr-50.md) | Measure tier 2's false-positive rate before adding anything to it | merged (`57d8e63`) |
| [#51](pr-51.md) | Make agents search structurally, and build the tests that keep it honest | open (`c7426b3`) |

> **#37–#46 have no `pr-N.md`.** They are not listed above either, so the gap is invisible in this table rather than merely undocumented — worth stating here rather than leaving a reader to infer it from the jump between #36 and #47. `python3 scripts/check_llms_coverage.py` prints the authoritative current list; it reports rather than fails, because `ENFORCE = False`.

Cross-linked from `STATUS.md` and `README.md`. See `claude/session-log.md` for the append-only history of which steering-prompt assumptions each of these PRs affected — this index is about verifying *what a PR did*, the session log is about *what it means for the steering prompts*. Different axis, same underlying discipline.
