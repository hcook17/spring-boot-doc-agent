# DDIA north star (first-party lookup catalog)

**Purpose.** Carry-forward guidance from *Designing Data-Intensive Applications* (2e, Kleppmann & Riccomini) for **building, reviewing, refactoring, and debugging** this repo. Not a substitute for the book; not a scrape of deepwiki.com (Tier C).

**Copyright.** Paraphrases, structure, fragment ids, and concept maps only. The O'Reilly epub is **not** vendored. Do not paste long verbatim chapter text into this tree.

**Last refined:** 2026-07-30.

## When to open this catalog

| Activity | Start |
|----------|--------|
| Implementing a control / gate / schema | [INDEX.md](INDEX.md) → one `operational` concept or playbook |
| Code or architecture review | Same INDEX; use each page's **Review checks** / playbook **Review procedure** |
| Refactor sequencing | [playbooks/refactor-sequencing.md](playbooks/refactor-sequencing.md) |
| “Where did this vocabulary come from?” | [taxonomy.md](taxonomy.md) + [chapters/](chapters/) |
| Ambiguity / conflicting docs | [playbooks/claims-and-status-drift.md](playbooks/claims-and-status-drift.md) |

Cite catalog **`id`** values in PR bodies, review findings, and session-log entries (e.g. `sor-vs-derived`).

## Agent load protocol (scale-down)

1. Read this README once per session that needs the lens.
2. Query [INDEX.md](INDEX.md) with the decision or review question.
3. Open **one** page whose `completeness` is `operational` (check frontmatter / [COMPLETENESS.md](COMPLETENESS.md)).
4. Open `related` ids only if blocked.
5. If the page is `outline` or `partial`, say so — do not fake Tier A from a stub.
6. Cite the `id` in the finding.

Machine index: [catalog.json](catalog.json) (schema: [catalog.schema.json](catalog.schema.json)). Prefer JSON for tooling; markdown for humans/agents.

## Completeness enum

| Value | Meaning |
|-------|---------|
| `outline` | Titles / section map only — **not** decision authority |
| `partial` | Digested claims exist; review checks may be thin |
| `operational` | Enough to decide / build / review without reopening the epub for that question |

## Enrichment protocol

1. Prefer **deepening an existing `id`** over adding overlapping pages.
2. Add a new concept only if no existing “When to open” covers the question.
3. Always update `completeness` and `last_refined`.
4. Project-specific decisions stay in `claude/research/*-memo-*.md` and **cite** north-star ids — this catalog is not a second STATUS.md.
5. Keep `catalog.json` 1:1 with page files (enforced by `tests/research/test_ddia_north_star_catalog.py`).

## Information architecture

- **SoR:** concept/playbook/chapter markdown bodies + `catalog.json` entries.
- **Derived views:** INDEX.md, COMPLETENESS.md, STATUS / prompt-10 pointers.
- **Not SoR:** chat transcripts; the local epub (Tier A, offline).

## Relationship to prompt 10

[claude/steering-prompts/10-review-persona-and-standards.md](../../steering-prompts/10-review-persona-and-standards.md) already anchors DDIA for plugin review. This catalog is the **lookupable** claim set so reviews do not rely on memory or a full epub re-read.
