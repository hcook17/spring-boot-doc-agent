# Completeness matrix

Recomputed by humans when pages change; `catalog.json` is the machine list. Enum: `outline` | `partial` | `operational` (see [README.md](README.md)).

## Policy

- Chapters marked `operational` must have honest **Who / What / When / Where / Why / How** sections — not title-only atlases.
- Domains may be `operational` while some child concepts remain `partial`.
- Deviations should be `operational` when filed (evidence complete) or not filed.
- Prefer deepening over claiming operational for stubs.

## How to read

Open [catalog.json](catalog.json) and filter by `kind` / `completeness`. INDEX links only decision-ready pages for build/review; chapter atlases always disclose their completeness in frontmatter.

## Intentional thin spots (honest)

| Area | Status | Why |
|------|--------|-----|
| Domain 06 consistency | `partial` | Product rarely needs consensus; deepen before relying |
| `transactions-and-integrity-lite` | `partial` | Vocabulary only until a concrete concurrent writer lands |
| `consistency-and-consensus-lite` | `partial` | Same |
| ch02–ch04, ch07–ch10 | `partial` | 5W1H present; deepen section claims when those domains bite |

## Enrichment order (suggested)

1. Any page cited in a PR that is still `partial`
2. Relationships for new artifact edges
3. New deviations in the same change as the divergence
4. Chapter section maps when epub re-read adds claims
