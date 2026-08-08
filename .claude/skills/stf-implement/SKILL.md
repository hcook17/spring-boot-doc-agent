---
name: stf-implement
description: Executor stage — run TASKS waves with T0 first. Cannot mark DONE without Reviewer validation token (2+N SoD). ast-grep only for Locate.
disable-model-invocation: true
---

# stf-implement (Executor)

## Gates

1. `python -m stf plan-gate --target-dir specs/<target>`
2. `python -m stf implement --target-dir specs/<target> --plan-gate`
3. Per-task Verify commands (own tests; full suite only at final / edit tasks).
4. `python -m stf verify-gate --cmd "<verify>"`
5. Reviewer issues token: `python -m stf reviewer-token --target-dir specs/<target>`
6. Mark done: `python -m stf mark-done --target-dir specs/<target> --token <token>`

**You must not invent a validation token.** Self-approval is forbidden.

## Locate

ast-grep only for structural citations. Never Grep/rg.

## Blockers

On falsified plan facts, append blocker via store (class + evidence + blast radius) and stall; do not guess.
