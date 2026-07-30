# DDIA north star — design SoR for this product

**Home:** `docs/design/ddia-north-star/` (product design guidance — not under `claude/`).

**Purpose.** Carry-forward, **principal-engineer grade** guidance from *Designing Data-Intensive Applications* (2e, Kleppmann & Riccomini) for **any** work on this project: direction, domain modeling, subdomain boundaries, relationships between artifacts, upstream/downstream contracts, review, refactor, and day-to-day control design. Not a substitute for the book; not a scrape of deepwiki.com (Tier C).

**Copyright.** Paraphrases, structure, fragment ids, and concept maps only. The O'Reilly epub is **not** vendored. Do not paste long verbatim chapter text into this tree.

**Last refined:** 2026-07-30.

## Scope (what “any level” means)

| Level | What you use the catalog for |
|-------|------------------------------|
| **Product / direction** | Which tradeoffs we accept as a doc-engine; what we refuse (band-aids, dual writers, silent LWW). |
| **Domain** | Clusters of related concerns (truth & data-flow, encoding, replication, integrity, maintainability, consistency). |
| **Subdomain** | A single concept page inside a domain (e.g. SoR vs derived inside data-flow). |
| **Relationship** | How two artifacts or concepts interact (SoR feeds view; gate ratchets a baseline). |
| **Control / gate / schema** | Concrete build, CI, and encoding choices — still cite a concept `id`. |
| **Upstream / downstream** | Diagnose whether a local fix papers over a bad upstream design; refuse silent deviation. |

If a decision at *any* of those levels would surprise a principal SE, it must be findable here — or recorded under [deviations/](deviations/) with evidence.

## Deviations are not blind spots

When this repo **does not** follow a DDIA-shaped approach:

1. Open [deviations/README.md](deviations/README.md) and file (or update) a deviation entry.
2. The entry must state **why** the local approach is correct **with evidence**, and must answer: *did we check upstream bad design / dual writers / stale SoR before accepting the deviation?*
3. Band-aid fixes that create later debt are **out of policy** — prefer fixing the SoR or the relationship, not papering the symptom.

Unstated deviation = process failure, same class as undocumented dual writer.

## Information architecture

```
docs/design/ddia-north-star/
  README.md, INDEX.md, COMPLETENESS.md, catalog.json
  meta/           taxonomy, usage levels, enrichment protocol
  domains/        nested by concern — concepts + relationships
  chapters/       deep who/what/when/where/why/how atlases (ch01–ch14)
  playbooks/      decision procedures for recurring work
  deviations/     explicit project ≠ book with evidence
```

- **SoR hierarchy (cite-or-deviate):**
  1. **Pipeline / code behavior** (dispatch graph, gates, writers) — highest for runtime truth.
  2. **North-star markdown + `catalog.json`** — design claim SoR for DDIA-shaped decisions; cite `id` or file a [deviation](deviations/).
  3. **Derived views** — INDEX, COMPLETENESS, STATUS / prompt-10 pointers, `capacity_preflight_report.json` (label metrics honestly: e.g. Stage-4 `upper_bound`).
  4. **Not SoR** — chat transcripts; local epub (Tier A offline); chronological `claude/research/` memos (those *cite* this tree).
- **Prior art:** [meta/prior-art.md](meta/prior-art.md) (Took / Declined / Why).

## When to open

| Activity | Start |
|----------|--------|
| Any design / direction / review question | [INDEX.md](INDEX.md) → one domain or `operational` page |
| “How deep should I go?” | [meta/usage-levels.md](meta/usage-levels.md) |
| Chapter context (5W1H) | [chapters/](chapters/) |
| Project ≠ DDIA | [deviations/](deviations/) |
| Ambiguity / conflicting docs | [playbooks/claims-and-status-drift.md](playbooks/claims-and-status-drift.md) |

Cite catalog **`id`** values in PR bodies, review findings, ADRs, and session-log entries.

## Agent / human load protocol

1. Read this README once per session that needs the lens.
2. Query [INDEX.md](INDEX.md) with the decision or review question (domain-first if unsure).
3. Open **one** page whose `completeness` is `operational` (see [COMPLETENESS.md](COMPLETENESS.md)).
4. If the work **deviates** from a concept’s Core claims, open [deviations/](deviations/) before merging.
5. Open `related` ids only if blocked.
6. If the page is `outline` or `partial`, say so — do not fake Tier A from a stub.
7. Cite the `id` (and deviation id if any) in the finding.

Machine index: [catalog.json](catalog.json) (schema: [catalog.schema.json](catalog.schema.json)).

## Completeness enum

| Value | Meaning |
|-------|---------|
| `outline` | Titles / section map only — **not** decision authority |
| `partial` | Digested claims exist; review checks or 5W1H may still be thin |
| `operational` | Enough to decide / build / review without reopening the epub for that question |

## Enrichment

See [meta/enrichment-protocol.md](meta/enrichment-protocol.md). Prefer deepening an existing `id` over spawning overlapping pages. Keep `catalog.json` 1:1 with page files (`tests/research/test_ddia_north_star_catalog.py`).

## Relationship to review prompts and `claude/`

[`claude/steering-prompts/10-review-persona-and-standards.md`](../../../claude/steering-prompts/10-review-persona-and-standards.md) anchors DDIA for plugin review. This catalog is the **lookupable** claim set. Session memos under `claude/research/` remain chronological notes; they must **cite** north-star ids rather than restate them. The previous location `claude/research/ddia-north-star/` is a **redirect stub only**.
