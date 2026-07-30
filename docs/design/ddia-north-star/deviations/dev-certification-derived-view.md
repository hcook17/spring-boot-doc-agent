---
id: dev-certification-derived-view
kind: deviation
completeness: operational
tags: [deviation, certification, derived, lww]
related: [sor-vs-derived, materialized-views-and-caches, replication-lag-and-lww, choosing-sor-vs-view]
last_refined: 2026-07-30
path: deviations/dev-certification-derived-view.md

---

# Deviation: certification.json is derived — never LWW-merged with pipeline facts

## DDIA claim id(s)

- `sor-vs-derived` / `materialized-views-and-caches` — derived views are recomputable; on conflict SoR wins.
- `replication-lag-and-lww` — last-write-wins across two “truth” candidates is lossy and usually wrong.
- Naive product instinct: treat certification blob as a second SoR that can be hand-edited or merged when it disagrees with stage facts.

## Local approach

`certification.json` is a **derived view** over pipeline / gate facts (B2.5 locked). Disagreement is resolved by **recomputing from SoR**, not by merging timestamps or editing the view to “look right.” Do not reopen B2.5 as dual-writer SoR.

## Why correct here

- Locked decision and memo: `claude/research/certification-derived-view-2026-07-30.md` (B2.5).
- Matches DDIA SoR/derived: certification is a serving/audit projection, not a new input channel.
- Adoption queue marks reopening B2/B2.5 out of scope for L1 work — intentional standing constraint.

## Upstream check

- Writers inspected: pipeline facts / gates that feed certification; certification writer path; STATUS/queue language about B2.5.
- SoR = stage/gate facts; derived = certification artifact + any prose summarizing it.
- Dual-writer / LWW ruled out by policy: no hand-merge of certification against facts; fix upstream fact or regenerator.
- Upstream errors that *look like* “certification is wrong” are investigated as **stale derivation or wrong SoR**, not as “edit the JSON.”

## Rejected band-aids

- Hand-edit `certification.json` in a customer out-dir to pass a demo — rejected (teaches view-as-SoR).
- LWW-merge certification fields with STATUS bullets — rejected (`replication-lag-and-lww`).
- Reopen B2.5 to make certification a second writer “for convenience” — rejected (creates permanent dual home).

## Expiry / revisit

`standing` while B2.5 holds. Revisit only with an explicit ADR that names a new SoR and migration — not a silent reopen.

## See also

- `choosing-sor-vs-view`, `materialized-views-and-caches`
- `claude/research/certification-derived-view-2026-07-30.md`
