# Deviations — when this project intentionally ≠ DDIA textbook shape

**Policy.** Unstated deviation from a north-star Core claim is a **blind spot**. Filing a deviation is how we keep principal-grade honesty: we either follow the book-shaped claim, or we prove why not — including that we did **not** miss upstream bad design that made the deviation look necessary.

## When you must file

- A PR or design chooses a path that contradicts a concept’s **Core claims** or a playbook’s **Do not**.
- A control “works around” a dual writer, stale SoR, or docs/code mismatch instead of fixing it.
- You are about to merge a temporary mitigation that could become permanent debt.

## Required evidence (every entry)

Each deviation file must answer:

| Field | Intent |
|-------|--------|
| **DDIA claim id(s)** | Which catalog page(s) we are departing from |
| **Local approach** | What we do instead |
| **Why correct here** | Evidence: code paths, gates, memos, measured behavior |
| **Upstream check** | What writers/SoR/relationships were inspected; why this is not papering over dual writers or bad design |
| **Rejected band-aids** | Alternatives we refused and why |
| **Expiry / revisit** | When to re-open (event or date), or `standing` with owner |
| **See also** | Related ids, memos, PRs |

Use [_TEMPLATE.md](_TEMPLATE.md). Catalog `id` = frontmatter `id` (e.g. `dev-coverage-denominator-codeql`).

## Index of filed deviations

| id | Summary |
|----|---------|
| `dev-coverage-denominator-codeql` | Coverage non-vacuity keys off CodeQL `rule_id`s + `spring_signals`, not ast-grep YAML count / `rule_fixtures` |
| `dev-certification-derived-view` | `certification.json` is a derived view; do not LWW-merge with pipeline facts |
| `dev-fp-ratchet-separate-from-recall` | Semgrep FP ratchet is inverted and separate from recall ratchet; no invented client-named recall baseline |

## Relationship to memos under `claude/research/`

Memos are chronological. Deviations here are **standing design SoR**. A memo may motivate a deviation; the deviation entry is what later sessions must find without reading chat history.
