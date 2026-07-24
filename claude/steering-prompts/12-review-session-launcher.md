# 12 — Review session launcher

The paste-able template for a fresh Claude Code session. Everything durable lives in the repo;
this file exists so a new session bootstraps from **disk, not from a pasted wall of context**.

Copy §A verbatim into a new terminal session, filling the three bracketed slots. Nothing else needs
to be pasted — no history, no prior findings, no summary of what happened before.

---

## §A — The launcher (copy this)

```
Read, in this order, before doing anything else:
  claude/steering-prompts/00-shared-research-standards.md
  claude/steering-prompts/10-review-persona-and-standards.md
  claude/steering-prompts/11-context-traversal-protocol.md

Then read the current state, and nothing beyond it unless traversal leads you there:
  STATUS.md
  CONSTRAINTS.md
  [TARGET — the document or subsystem under review]

TASK: [ONE question or one artifact. Not a list.]

Run the file-11 interleave (BFS to discover, DFS to ground) with the concept set seeded from
the target. Hold the file-10 evidence tiers and verdict vocabulary throughout.

Stop when at least two of S1–S4 hold. If you stop on budget instead, say TRUNCATED, not done.

Write your output to [OUTPUT PATH] incrementally as you go — do not hold findings in context and
write at the end. Follow the §B contract below.

Do not: summarize this conversation into the output; re-derive anything already recorded in
claude/session-log.md or claude/tool-quirks.md; read more than 10 files before writing your first
finding; or expand scope beyond TASK. If you find something important but out of scope, record it
under "Adjacent findings" and keep going.
```

---

## §B — Output contract

Every review session emits one document with these sections. The next session reads *this*, not a
transcript.

1. **Verdict line.** One sentence. What is the answer to TASK.
2. **Claims table.** `claim | verdict | tier | source (path or URL) | version checked | date`.
   One row per claim that moved a conclusion. No row without a source.
3. **Findings**, most severe first. Each carries: the defect stated as a proposition, a concrete
   witness (inputs → wrong output), blast radius, and the cheapest thing that would refute it.
4. **Contradictions** — pairs that forced a `contested`, with both sources named.
5. **Open frontier** — unexpanded nodes with scores, so the next session resumes mid-traversal.
6. **Bounds applied** — every cap, drop, and skip with counts. If none, say "none."
7. **What would change this** — the trigger conditions that would invalidate the conclusion. This
   repo already uses this convention in `claude/10-architecture-maturation-plan.md`; match it.

Filename convention: `claude/<topic>-<review|research|scoping>-<YYYY-MM-DD>.md`, kebab-case, matching
the existing `claude/drift-check-manifest-baseline-research-2026-07-25.md` shape.

---

## §C — Tactical weighing (only after §B is written)

Review first, decide second — never interleave them, because a half-grounded finding will pull the
decision toward whatever was investigated most recently rather than what matters most.

Score each candidate direction on:

- **Reversibility.** One-way or two-way door? A schema change the drift checker will refuse to
  compare across is a one-way door and must be paid for up front.
- **Blast radius if wrong**, weighted by *detectability*. A silent wrong answer costs more than a
  loud failure of the same size.
- **Cost to verify vs cost to be wrong.** If verification is cheap, verify; stop debating.
- **Option value.** Does it close doors or keep them open? Prefer the one that keeps them open at
  equal cost.
- **Ordering.** What does it block, and what blocks it? A cheap item that unblocks three others
  outranks an expensive item that unblocks none.

Then output exactly this, and no more:

- **The recommendation**, one paragraph, with the mechanism spelled out concretely enough to start.
- **The runner-up**, one sentence, and *why it lost* — not just that it did.
- **The trigger that flips the choice.** A named, observable condition. If you cannot name one, the
  recommendation is not yet grounded; say so rather than inventing a trigger.

Prefer the elegant solution — the one that closes a failure *class* rather than an instance, or that
makes a defect structurally impossible rather than caught by a check. But state its cost honestly.
Elegance that costs three weeks against a patch that costs a day is a trade to be *priced*, not a
verdict to be assumed.

---

## §D — Session hygiene

- **One TASK per session.** If it splits, write the split into "Adjacent findings" and start a new
  session per branch. Do not chain three reviews into one context window.
- **Write early, write often.** The output file is the durable artifact; context is not. A session
  that dies with findings only in context has produced nothing.
- **Never paste prior findings forward.** Point at the file path instead. If a fact matters enough
  to carry between sessions, it belongs in a repo document, not in a prompt.
- **Re-verify version-sensitive claims** rather than inheriting them. `claude/hibernate-jakarta-
  fact-verification-2026-07-24.md` is dated for exactly this reason — check the date before trusting
  the values.
- **Record tool surprises** in `claude/tool-quirks.md`, not in the review output. Two known ones
  already: a project-doc write to a bare filename gets namespaced rather than replacing, and a
  delete against duplicate paths removed the *newest* copy first.
