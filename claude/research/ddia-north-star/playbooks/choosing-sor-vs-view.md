---
id: choosing-sor-vs-view
kind: playbook
completeness: operational
tags: [sor, derived, decision]
related: [sor-vs-derived, replication-lag-and-lww, materialized-views-and-caches]
last_refined: 2026-07-30
---

# Playbook: choosing SoR vs view

## Intent

Decide whether a new artifact is written as system of record or maintained as a derived view.

## Decision procedure

1. What is the user/agent input that must not be lost? → that lands in SoR.
2. Can another representation be rebuilt from SoR alone? → prefer derived view.
3. Multiple readers need different shapes? → multiple views, one SoR (not dual SoRs).
4. Tempted to LWW-merge two writers? → stop; pick one SoR or define a fold (see B2.5).
5. Document the writer and the rebuild command in the same PR.

## Review procedure

1. Find the writer(s) in the diff.
2. Ask: on disagreement, which artifact wins?
3. Ask: delete the view — can we regenerate?
4. Cite `sor-vs-derived` and this playbook id.

## Do not

- Stamp a field on a merge result and call it derived.
- Grow STATUS into an SoR of engineering truth (queue + code are SoR; STATUS summarizes).

## Worked example (this repo)

- `certification.json` = derived fold over stage/gate facts.
- `semgrep_rule_fp_baseline.json` = derived measurement over negative fixtures (SoR = fixtures + rules).

## See also

- `replication-lag-and-lww`, `architecture-decision-review`
