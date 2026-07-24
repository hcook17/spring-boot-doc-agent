# PR verification index

One file per pull request (`pr-N.md`), each pairing that PR's summary with **deterministic search heuristics** — literal `git`/`grep` commands, pinned to that PR's actual commit(s) — a reader (human or another Claude session) can run to confirm each claim directly, instead of re-reading the full diff or trusting the prose alone. Same discipline `CONTRIBUTING.md`'s write-then-verify rule and this pipeline's own `[Evidenced — path:line]` tagging already apply elsewhere in this repo, turned outward on this repo's own PR history.

Every command is pinned to a commit SHA (or, for a still-open PR, its head branch), not to `HEAD`/`main` — so a command in `pr-3.md` still resolves correctly even after ten more PRs land. Run them with `git show <ref>:<path>`, not by checking out the branch — that works from whatever's currently checked out, without disturbing your working tree.

**Convention: write a PR's own `pr-N.md` in the same PR when possible.** For any PR touching `scripts/`/`agents/`/`skills/`/`references/`, add its `pr-N.md` (pinned to the PR's own head commit, per the still-open-PR case above — `pr-13.md` is the original precedent) as part of that same PR, using the PR number `gh pr create` returns once the PR is opened. `scripts/check_llms_coverage.py` (CI-wired) fails the build if a merged PR has no corresponding `pr-N.md`, or one with a stale `state:` frontmatter field — but a PR can never document its own merge commit before that commit exists, so the single most-recently-merged PR is always exempt from both checks (a bounded grace window, not a hole: the exemption shifts to whichever PR merges next, so nothing stays undocumented past one PR cycle). Following this convention keeps that exemption rarely exercised in practice, rather than relying on it as the default path.

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

Cross-linked from `STATUS.md` and `README.md`. See `claude/session-log.md` for the append-only history of which steering-prompt assumptions each of these PRs affected — this index is about verifying *what a PR did*, the session log is about *what it means for the steering prompts*. Different axis, same underlying discipline.
