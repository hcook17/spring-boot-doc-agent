# Enrichment protocol

1. Prefer **deepening an existing `id`** over adding overlapping pages.
2. Add a new concept only if no existing “When to open” covers the question.
3. Add a **relationship** page when the hard part is the *edge* between two concepts/artifacts, not either endpoint alone.
4. Always update `completeness` and `last_refined` in frontmatter.
5. If the page is a chapter, keep the required 5W1H H2 sections honest — do not mark `operational` while Why/How are stubs.
6. Project-specific chronology stays in `claude/research/*-memo-*.md` and **cites** north-star ids — this catalog is not a second STATUS.md.
7. Intentional DDIA divergence → [deviations/](../deviations/) entry in the **same change** when practical.
8. Rebuild `catalog.json` via `_build_catalog.py` and keep the sync test green.
9. Domain README must list every concept and relationship under that domain.
