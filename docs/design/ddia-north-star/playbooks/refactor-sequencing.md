---
id: refactor-sequencing
kind: playbook
completeness: operational
tags: [refactor, sequencing, blast-radius]
related: [maintainability-operability-evolvability, schema-evolution-and-data-outlives-code, coverage-gates]
last_refined: 2026-07-30
path: playbooks/refactor-sequencing.md

---

# Playbook: refactor sequencing

## Intent

Sequence refactors so each step is reversible, verifiable, and does not mint a new stale derived view.

## Decision procedure

1. Name the failure class (not only the instance).
2. Prefer derive-before-merge; prefer hermetic gates before client corpora.
3. Land doc/`verify:` corrections in the same PR as SoR moves when cheap; else queue with id (L6…).
4. One focused PR theme; do not fold branch protection / claim-symbol redesign into coverage work.
5. Update STATUS/queue as derived views of the new SoR.

## Review procedure
- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

1. Is there a rollback story?
2. Does CI prove the new invariant, or only change prose?
3. Are polarities/baselines versioned explicitly?
4. Cite `refactor-sequencing` + relevant concept ids.

## Do not

- Big-bang “fix all coverage docs + invent recall baseline + retarget metamorphic” in one PR.
- Delete metamorphic corpora because a different gate moved.

## Worked example (this repo)

- Order: north-star under `docs/design/` → L1 FP ratchet (**done**) → **L2** capacity Stage-4 SoR align (`rel-sor-feeds-views`, `claims-and-status-drift`) → L6 coverage baseline hygiene / L5 drift schema; L4 branch protection stays parallel human; L3 claim-symbol stays later.
- Cite `refactor-sequencing` + the queue item’s DDIA card ids in the PR body.

## See also

- `architecture-decision-review`, adoption-blockers queue
