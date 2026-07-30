# Completeness matrix

Recomputed by humans when pages change; `catalog.json` is the machine list. Enum: `outline` | `partial` | `operational` (see [README.md](README.md)).

## Policy

- Chapters marked `operational` must have honest **Who / What / When / Where / Why / How** sections plus **###** digests for each Section map bullet — not title-only atlases.
- Domains marked `operational` must **own** ≥1 `concepts/*.md` under that domain directory (no hollow pointer-only domains).
- Operational concepts/chapters need ≥1 **page-specific** Fail-if (not only shared boilerplate).
- Deviations should be `operational` when filed (evidence complete) or not filed.
- Prefer deepening over claiming operational for stubs.
- Depth gate: `tests/research/test_ddia_north_star_depth.py` + `operational_count_baseline.json`.

## How to read

Open [catalog.json](catalog.json) and filter by `kind` / `completeness`. INDEX links only decision-ready pages for build/review; chapter atlases always disclose their completeness in frontmatter.

## Intentional thin spots (honest)

| Area | Status | Why |
|------|--------|-----|
| Domain 06 consistency | `partial` | Product rarely needs consensus; deepen before relying |
| Domain 08 transactions | `partial` | Hollow until it owns a local concept (not only a cross-domain pointer) |
| Domain 10 reliability goals | `partial` | Same — goals shell until a local concept lands |
| `ch04`, `ch10` | `partial` | Bridges — open ch05 / ch11 for ADRs |
| `transactions-and-integrity-lite` | `partial` | Vocabulary only until a concrete concurrent writer lands |
| `consistency-and-consensus-lite` | `partial` | Same |

## Enrichment order (suggested)

1. Any page cited in a PR that is still `partial`
2. Own a local concept before promoting domains 08 / 10
3. New deviations in the same change as the divergence
4. Promote domain 06 / lite concepts when concurrent writers or consensus actually bite
