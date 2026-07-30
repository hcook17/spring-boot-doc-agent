---
name: verify-state-claims
description: Read before writing or editing any claim about this repo's own current state — a count, a `status:` field, a `[Resolved]` tag, a path or symbol reference, or a CI step name. Also read when a session is about to assert that something is done, fixed, absent, or unaffected. Run `python3 scripts/ci/check_repo_claims.py` before the final commit of any session touching scripts/, agents/, or skills/. Covers the failure this repo calls the assume-spiral: a claim gets written, nothing reads it back, and later work compounds it. Distinct from claude/tool-quirks.md (ambient tool behavior) and claude/session-log.md (steering-prompt impact) — this is about the claims themselves.
---

# Verifying claims about this repo's own state

## The one rule

**A claim about repo state has to name what would falsify it.**

Three forms, in order of preference:

1. **The command that recomputes it.** `MATURITY_ASSESSMENT.md` does this: "for the
   current inventory run `ls tests/test_*.py`" instead of a number.
2. **A `derived:` block**, when a number genuinely has to sit in prose. Add the key to
   `DERIVATIONS` in `scripts/ci/check_repo_claims.py` first.
3. **A `verify:` predicate** in frontmatter, when the claim is a status.

If a claim fits none of these, that is the signal it is a *judgment*, not a fact. Tag it
and give the reasoning, using the vocabulary already in `CLAUDE.md` — `[Resolved — ...]`,
`[Still accurate]`, `[New info — ...]`. Do not invent new status words.

## Why this exists, in this repo specifically

Not a hypothetical. This repo's record is excellent — an append-only `session-log.md`, a
`tool-quirks.md` index, a bracket-tagged `CONSTRAINTS.md`. Every failure below happened
anyway, with the record right there:

| What happened | The tell |
|---|---|
| `06-wiredrift-check-task-prompt.md` said `status: not started` after the work landed | The session log **flagged it three separate times before anyone edited the field**. Its own `note:` records this. Logging caught it three times and fixed it zero times. |
| `CLAUDE.md`'s rule *against* hardcoded counts carried three wrong numbers of its own | It quoted a sentence that had already been corrected, and stamped its replacement "as of" a date it was wrong on. |
| `12-review-session-launcher.md` sent fresh sessions to two prompt files that did not exist | A renumbering moved them. Nothing resolved the paths. |
| `CONSTRAINTS.md` cited `verify_llms_docs.py` after it was deleted | In two places, so the file contradicted itself. |
| A `[Resolved]` was written for a `sys.exit` fix true of one function | It was generalized to the file; the CodeQL runner still had two analogous exits. |
| `capacity_preflight.py` measured a broadcast removed three commits earlier | Over-reported by ~21x, in the direction of alarm. |
| `ls docs/*.md \| wc -l` was added to catch a duplicate-write bug | Counting to fourteen *passes* that exact failure. |

**Zero of these were caught by CI.** They were caught by a direct `git status`, a
reviewer's fresh-environment run, a user's question, the owner's own read, and the first
real end-to-end run.

## Before your final commit

```
python3 scripts/ci/check_repo_claims.py
python3 scripts/ci/check_repo_claims.py --fix    # if a derived: block drifted
```

It resolves `verify:` predicates, recomputes `derived:` blocks, resolves backticked repo
paths and `symbol()` references in current-state docs, checks every test suite is wired
into CI, and checks no step is named as a gate it cannot be.

**It is the floor, not the ceiling.** It decides whether a claim is *well-formed and
resolvable* — never whether it is *true*. A `[Resolved]` pointing at a file that exists
passes while being wrong about what the file does. That judgment is still yours, and it
is why `CLAUDE.md` still asks for a human pass.

## The three drift directions

A claim does not only go stale by becoming false. Say which one happened rather than
quietly restating the claim.

1. **It became false.** The ordinary case. Code moved; the sentence didn't.
2. **It was written ahead of the code.** A `[Resolved]` describing intent rather than
   merged behavior. `CONSTRAINTS.md` carries a worked example of correcting one.
3. **It was silently narrowed.** Scope dropped between plan and implementation, and the
   docs then described the narrower thing as if it were always the intent.
   `check_mermaid_syntax()` lost its undefined-node-ref check this way, with `SKILL.md`,
   `eval-rubric.md`, and the docstring all independently describing only the three checks
   that shipped.

## Do not

- **Do not certify your own blast radius.** "Nothing downstream depended on it" is not
  yours to assert — it is asserted by the same process that produced the error. State what
  you checked and how.
- **Do not report a log entry as the fix.** A log entry documents a failure; it does not
  prevent it. For anything that has now happened twice, build the control.
- **Do not tag `[Resolved]` from one call site.** Check every reachable path, or say which
  one you checked.
- **Do not name a step a gate if it cannot fail.** `check_llms_coverage.py` ships
  `ENFORCE = False`, and its CI step name says "non-blocking" for exactly this reason.
  Check E now enforces that pairing.
- **Do not trust a tool's success report.** Six of the seven entries in
  `claude/tool-quirks.md` are this bug: `git clone` printing "Clone succeeded" over a
  15-of-49-file checkout, `gh pr list` returning `[]` for a PR that exists, `pip`
  reporting an upgrade a shadowed `PATH` binary ignored. Read the resulting state.
- **Do not widen a claim during a sweep.** A tidy-up pass once widened "mirrored `01`–`05`"
  to `01`–`12` without re-checking; the correction's own manifest was then wrong in two
  rows. Four commits to land one true sentence.
- **Do not assert a number.** Prefer the command. If you must, use a `derived:` block.

## Fix the class, not the instance

Path-separator normalization was fixed in `spring_signal_scan.py`, then
`spring_drift_check.py`, then `partition_repo.py`, then `capacity_preflight.py` — four
sites, three point fixes, before it was extracted into `partition_repo.to_posix()`. From
the session log: *"A bug fixed three times in three places is the signal that the fix
belonged in one place."*

The same applies to checks. A probe is weaker than an invariant: a re-run-and-diff
determinism probe **passed against the unfixed scanner**, while `keys == sorted(keys)`
caught it on a single run. Name the invariant when one exists.

## Related, and deliberately separate

- `claude/tool-quirks.md` — ambient tool/environment behavior. Check it *first* when
  something looks like a tool bug.
- `claude/session-log.md` — steering-prompt impact, per `CLAUDE.md`'s trigger.
- `claude/llms/pr-N.md` — hand-verified, re-runnable PR verification commands.
- `skills/citation-coverage/` — the same discipline applied to *generated* docs rather than
  this repo's own.
- `branch parked-session-log-validator` — 620 lines and 70 passing tests for a
  one-file-per-entry log split that was never built. Prior art if that split is revisited;
  it validates nothing today.
