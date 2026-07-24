# PR verification index

One file per pull request (`pr-N.md`), each pairing that PR's summary with **deterministic search heuristics** — literal `git`/`grep` commands, pinned to that PR's actual commit(s) — a reader (human or another Claude session) can run to confirm each claim directly, instead of re-reading the full diff or trusting the prose alone. Same discipline `CONTRIBUTING.md`'s write-then-verify rule and this pipeline's own `[Evidenced — path:line]` tagging already apply elsewhere in this repo, turned outward on this repo's own PR history.

Every command is pinned to a commit SHA (or, for a still-open PR, its head branch), not to `HEAD`/`main` — so a command in `pr-3.md` still resolves correctly even after ten more PRs land. Run them with `git show <ref>:<path>`, not by checking out the branch — that works from whatever's currently checked out, without disturbing your working tree.

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
| [#13](pr-13.md) | Add semantic-pipeline-eval and capacity-preflight skills, plus a maturity assessment | open (`3254d67`) |

Cross-linked from `STATUS.md` and `README.md`. See `claude/session-log.md` for the append-only history of which steering-prompt assumptions each of these PRs affected — this index is about verifying *what a PR did*, the session log is about *what it means for the steering prompts*. Different axis, same underlying discipline.
