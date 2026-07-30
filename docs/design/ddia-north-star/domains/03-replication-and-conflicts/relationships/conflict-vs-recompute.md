---
id: rel-conflict-vs-recompute
kind: relationship
completeness: operational
tags: [relationship, conflict, lww]
related: [replication-lag-and-lww, sor-vs-derived, rel-sor-feeds-views]
last_refined: 2026-07-30
path: domains/03-replication-and-conflicts/relationships/conflict-vs-recompute.md

---

# Relationship: conflict vs recompute

## In one sentence

When two artifacts disagree, prefer **recompute from SoR** or **single-writer repair** over last-write-wins merge of two truth candidates.

## Who

On-call / reviewer who sees STATUS vs code, certification vs facts, docs vs gate.

## What

Decision edge: `Conflict --resolve_by--> {recompute, fix-SoR, explicit-merge-with-deviation}` — not silent LWW.

## When

Any dual narrative (queue says done, STATUS says next; baseline vs measured; CI comment vs script).

## Where

STATUS, CONSTRAINTS, adoption queue, certification, coverage docs, session-log.

## Why

LWW loses information and teaches the wrong SoR; recompute preserves the definition of derived data.

## How

1. Identify SoR.
2. Delete or regenerate the view.
3. If you truly need multi-writer merge, file a [deviation](../../deviations/) with upstream check — do not ship a silent merge.

## Anti-band-aids

- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

## Repo path witness

- [Repo] `domains/03-replication-and-conflicts/relationships/conflict-vs-recompute.md`

## See also

`replication-lag-and-lww`, `dev-certification-derived-view`
