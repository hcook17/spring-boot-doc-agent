---
name: stf-frame
description: Planner stage — turn objectives or review findings into specs/(target)/SPEC.md. Judgment only; must run python -m stf validate / write via SpecStore. Explicit invoke only.
disable-model-invocation: true
---

# stf-frame (Planner)

You write `specs/(target)/SPEC.md` (+ `SPEC.json` via `python -m stf`). You do **not** invent absolute paths; constitution context comes from `python -m stf constitution --repo-root . --out /tmp/constitution.md`.

## Locate code with ast-grep only

Never use Grep/rg for code citations. Prefer:

```bash
ast-grep run -l python -p 'def $NAME($$$)' <path>
```

## Phases

1. Require explicit `--target` name (ADR-003).
2. If input is an adversarial review, run:
   `python -m stf ingest-review --review <path> --out tests/fixtures/stf/<target>/findings.json --spec-dir specs/<target> --target <target>`
3. Grill open questions with the engineer; do not guess inventory origins.
4. Audit dependencies (configured / SoT / documented / reproducible).
5. Write SPEC; hand off to `stf-decompose`.

Repair re-entry: if `TASKS.json` has an open `inventory-drift` blocker, amend only blast-radius inventory rows.
