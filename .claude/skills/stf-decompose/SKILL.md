---
name: stf-decompose
description: Planner stage — SPEC → dependency-ordered TASKS.json with waves/T0. Runs nothing. Must pass python -m stf validate and plan-gate before done.
disable-model-invocation: true
---

# stf-decompose (Planner)

Produces `specs/(target)/TASKS.json` (SoR). Markdown projection optional.

## Rules

- Define T0 Wave 0 probes with `gates:` task ids.
- SPOQ waves via depends DAG; do not reorder without updating why_this_order.
- Cold-executable task blocks (goal, inputs, phases, verify, acceptance).
- Code locate: **ast-grep only** — never Grep/rg.
- Before DONE: `python -m stf validate --target-dir specs/<target>` and `python -m stf plan-gate --target-dir specs/<target>` must exit 0.

Repair: open blockers of class decision|assumption|dag-collision — amend blast radius only.
