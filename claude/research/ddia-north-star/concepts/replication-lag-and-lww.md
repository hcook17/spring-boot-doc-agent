---
id: replication-lag-and-lww
kind: concept
completeness: operational
tags: [replication, lww, conflict, lag]
epub_anchors:
  - { chapter: 6, title: "Last write wins (discarding concurrent writes)" }
  - { chapter: 6, title: "Problems with Replication Lag" }
related: [sor-vs-derived, consistency-and-consensus-lite, choosing-sor-vs-view]
last_refined: 2026-07-30
---

# Replication lag and last-write-wins

## In one sentence

Async copies introduce lag anomalies; resolving conflicts by “latest timestamp wins” silently discards concurrent writes.

## When to open

- Merge strategies for concurrent updates to the same artifact.
- Whether to LWW-merge certificates/stages vs re-derive.
- Multi-writer docs (STATUS vs queue).

## Core claims

- Lag can break read-your-writes, monotonic reads, and causal prefix reads.
- LWW is lossy conflict resolution — concurrent updates are dropped, not merged.
- Prefer conflict avoidance, explicit merge, or CRDT/OT when correctness matters.
- Derived recompute from a single fact log avoids LWW between writers of the view.

## Tradeoffs

- Sync replication / consensus costs latency and availability.
- LWW is simple and wrong for many integrity domains.
- Manual merge needs operability.

## Repo analogues

- B2.5: certification as derived fold — not LWW merge + stamp (`certification-derived-view-2026-07-30.md`).
- Content-stable claim fingerprints vs ordinal renumber churn.
- Do not let STATUS and adoption-queue “win” by recency; correct the derived view.

## Review checks

1. Are there two writers for one key?
2. If concurrent edits are possible, is the resolve rule stated (and is it LWW)?
3. Would derive-from-facts remove the conflict class?

## Refactor signals

- `dict.update` / merge helpers on cert or manifests without fold rules.
- “Last session’s STATUS paragraph” overriding the queue SoR.

## Anti-patterns seen

- Pre-B2.5 live cert merge stamped `generative_executor: live` without deriving stages.

## See also

- `sor-vs-derived`, `claude/research/certification-derived-view-2026-07-30.md`
